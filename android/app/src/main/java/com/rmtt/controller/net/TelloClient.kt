package com.rmtt.controller.net

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress

const val DEFAULT_CMD_PORT = 8889
const val STATE_PORT = 8890

/**
 * Tello SDK 3.0 UDP 客户端（与 Mind+ 实时模式使用同一协议）。
 *
 * - 指令从随机本地端口发往 飞机IP:8889，飞机原路回复 ok / error / 查询结果；
 * - 需要回复的指令串行执行（同一时间只有一条在等待回复），rc 等无回复指令可随时发送；
 * - 飞机以 10Hz 向本机 8890 端口推送状态字符串。
 *
 * 不依赖 Android API，可直接在 JVM 单元测试中连接模拟器。
 * [socketBinder] 用于在 Android 上把 socket 绑定到 WiFi 网络（避免连接无互联网的飞机热点时流量走移动数据）。
 */
class TelloClient(
    private val scope: CoroutineScope,
    private val statePort: Int = STATE_PORT,
    private val socketBinder: (DatagramSocket) -> Unit = {},
) {
    enum class Kind { SEND, RECV, INFO, ERROR }

    data class LogEntry(val time: Long, val kind: Kind, val text: String)

    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected

    private val _state = MutableStateFlow(DroneState())
    val state: StateFlow<DroneState> = _state

    /** 正在等待回复的指令，空闲时为 null。 */
    private val _busy = MutableStateFlow<String?>(null)
    val busy: StateFlow<String?> = _busy

    private val _logs = MutableSharedFlow<LogEntry>(extraBufferCapacity = 512)
    val logs: SharedFlow<LogEntry> = _logs

    private var cmdSocket: DatagramSocket? = null
    private var stateSocket: DatagramSocket? = null
    private var target: InetSocketAddress? = null
    private val replies = Channel<String>(Channel.UNLIMITED)
    private val mutex = Mutex()
    private val jobs = mutableListOf<Job>()

    @Volatile
    private var lastSendAt = 0L

    val isIdle: Boolean get() = !mutex.isLocked
    val targetAddress: String? get() = target?.let { "${it.hostString}:${it.port}" }

    /** 连接飞机：建立 socket 并发送 "command" 进入 SDK 模式，成功返回 true。 */
    suspend fun connect(host: String, port: Int = DEFAULT_CMD_PORT): Boolean = withContext(Dispatchers.IO) {
        disconnect()
        try {
            target = InetSocketAddress(InetAddress.getByName(host), port)
            val cs = DatagramSocket(null).apply { reuseAddress = true }
            runCatching { socketBinder(cs) }
            if (!cs.isBound) cs.bind(InetSocketAddress(0))
            cmdSocket = cs
            jobs += scope.launch(Dispatchers.IO) { receiveLoop(cs) }
        } catch (e: Exception) {
            log(Kind.ERROR, "无法创建连接：${e.message}")
            disconnect()
            return@withContext false
        }
        try {
            val ss = DatagramSocket(null).apply { reuseAddress = true }
            ss.bind(InetSocketAddress(statePort))
            runCatching { socketBinder(ss) }
            stateSocket = ss
            jobs += scope.launch(Dispatchers.IO) { stateLoop(ss) }
        } catch (e: Exception) {
            log(Kind.ERROR, "无法监听状态端口 $statePort（${e.message}），电量等状态将不可用")
        }

        log(Kind.INFO, "连接 ${targetAddress} …")
        repeat(3) {
            val r = send("command", 2000)
            if (r == "ok") {
                _connected.value = true
                jobs += scope.launch(Dispatchers.IO) { keepAlive() }
                log(Kind.INFO, "已进入 SDK 模式")
                return@withContext true
            }
            if (r != TIMEOUT) {
                log(Kind.ERROR, "command 返回 $r")
            }
        }
        log(Kind.ERROR, "连接失败：飞机无回复")
        disconnect()
        false
    }

    fun disconnect() {
        jobs.forEach { it.cancel() }
        jobs.clear()
        cmdSocket?.close()
        stateSocket?.close()
        cmdSocket = null
        stateSocket = null
        if (_connected.value) log(Kind.INFO, "已断开")
        _connected.value = false
        _busy.value = null
        _state.value = DroneState()
    }

    /**
     * 发送需要回复的指令并等待回复（串行）。超时返回 [TIMEOUT]。
     * @param quiet 为 true 时不写日志（用于后台轮询 ToF 等）
     */
    suspend fun send(cmd: String, timeoutMs: Long = timeoutFor(cmd), quiet: Boolean = false): String {
        mutex.withLock {
            val s = cmdSocket ?: return "error Not connected"
            while (true) {
                val stale = replies.tryReceive().getOrNull() ?: break
                if (!quiet) log(Kind.INFO, "（迟到的回复：$stale）")
            }
            _busy.value = cmd
            try {
                write(s, cmd, quiet)
                val r = withTimeoutOrNull(timeoutMs) { replies.receive() }
                if (r == null) {
                    log(Kind.ERROR, "[$cmd] ${timeoutMs / 1000} 秒内无回复")
                    return TIMEOUT
                }
                if (!quiet) log(Kind.RECV, r)
                return r
            } finally {
                _busy.value = null
            }
        }
    }

    /** 立即发送、不等待回复：rc 摇杆指令，以及 emergency / stop 等需要插队的指令。 */
    suspend fun sendNow(cmd: String) {
        val s = cmdSocket ?: return
        write(s, cmd, quiet = cmd.startsWith("rc "))
    }

    private suspend fun write(s: DatagramSocket, cmd: String, quiet: Boolean) = withContext(Dispatchers.IO) {
        val bytes = cmd.toByteArray(Charsets.UTF_8)
        try {
            s.send(DatagramPacket(bytes, bytes.size, target))
            lastSendAt = System.currentTimeMillis()
            if (!quiet) log(Kind.SEND, cmd)
        } catch (e: Exception) {
            log(Kind.ERROR, "发送失败：${e.message}")
        }
    }

    private fun receiveLoop(s: DatagramSocket) {
        val buf = ByteArray(2048)
        while (!s.isClosed) {
            val p = DatagramPacket(buf, buf.size)
            try {
                s.receive(p)
            } catch (e: Exception) {
                if (s.isClosed) break else continue
            }
            val text = String(p.data, 0, p.length, Charsets.UTF_8).trim()
            if (text.isNotEmpty()) replies.trySend(text)
        }
    }

    private fun stateLoop(s: DatagramSocket) {
        val buf = ByteArray(1024)
        while (!s.isClosed) {
            val p = DatagramPacket(buf, buf.size)
            try {
                s.receive(p)
            } catch (e: Exception) {
                if (s.isClosed) break else continue
            }
            _state.value = DroneState.parse(String(p.data, 0, p.length, Charsets.US_ASCII))
        }
    }

    /** 真机 15 秒收不到指令会自动降落，空闲时每 10 秒发一次 rc 0 0 0 0 保活。 */
    private suspend fun keepAlive() {
        while (scope.isActive) {
            delay(1000)
            val s = cmdSocket ?: return
            if (System.currentTimeMillis() - lastSendAt > 10_000) write(s, "rc 0 0 0 0", quiet = true)
        }
    }

    private fun log(kind: Kind, text: String) {
        _logs.tryEmit(LogEntry(System.currentTimeMillis(), kind, text))
    }

    companion object {
        const val TIMEOUT = "timeout"

        /** 查询类指令很快返回；动作指令要等动作做完，给足时间。 */
        fun timeoutFor(cmd: String): Long = when {
            cmd == "command" -> 2000
            cmd.endsWith("?") -> 5000
            cmd.startsWith("EXT", ignoreCase = true) -> 5000
            else -> 90_000
        }
    }
}

/** 8890 端口状态字符串解析结果。 */
data class DroneState(
    val receivedAt: Long = 0,
    val battery: Int = -1,
    val height: Int = 0,
    val tof: Int = 0,
    val yaw: Int = 0,
    val pitch: Int = 0,
    val roll: Int = 0,
    val tempLow: Int = 0,
    val tempHigh: Int = 0,
    val flightTime: Int = 0,
    val mid: Int = -1,
    val padX: Int = 0,
    val padY: Int = 0,
    val padZ: Int = 0,
    val baro: Float = 0f,
) {
    val valid: Boolean get() = receivedAt > 0
    fun fresh(now: Long = System.currentTimeMillis()) = valid && now - receivedAt < 2000

    companion object {
        fun parse(text: String): DroneState {
            val m = text.trim().split(';').mapNotNull {
                val i = it.indexOf(':')
                if (i > 0) it.substring(0, i) to it.substring(i + 1) else null
            }.toMap()

            fun int(k: String) = m[k]?.toFloatOrNull()?.toInt() ?: 0
            return DroneState(
                receivedAt = System.currentTimeMillis(),
                battery = int("bat"),
                height = int("h"),
                tof = int("tof"),
                yaw = int("yaw"),
                pitch = int("pitch"),
                roll = int("roll"),
                tempLow = int("templ"),
                tempHigh = int("temph"),
                flightTime = int("time"),
                mid = m["mid"]?.toIntOrNull() ?: -1,
                padX = int("x"),
                padY = int("y"),
                padZ = int("z"),
                baro = m["baro"]?.toFloatOrNull() ?: 0f,
            )
        }
    }
}
