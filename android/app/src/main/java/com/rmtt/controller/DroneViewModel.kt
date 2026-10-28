package com.rmtt.controller

import android.app.Application
import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.rmtt.controller.net.DEFAULT_CMD_PORT
import com.rmtt.controller.net.Discovery
import com.rmtt.controller.net.FoundDrone
import com.rmtt.controller.net.TelloClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.net.DatagramSocket
import java.util.Locale
import kotlin.math.roundToInt

class DroneViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("tt", Context.MODE_PRIVATE)

    val client = TelloClient(viewModelScope, socketBinder = ::bindToWifi)

    // ---- 连接 ----
    var host by mutableStateOf(prefs.getString("host", "192.168.10.1")!!)
    var connecting by mutableStateOf(false)
        private set
    var connectError by mutableStateOf<String?>(null)
        private set

    // ---- 自动发现 ----
    val found = mutableStateListOf<FoundDrone>()
    var discovering by mutableStateOf(false)
        private set
    var discoverDone by mutableStateOf(false)
        private set

    /** 在局域网中广播搜索模拟器（约 1.5 秒） */
    fun discover() {
        if (discovering) return
        discovering = true
        viewModelScope.launch {
            val r = runCatching { Discovery.search(socketBinder = ::bindToWifi) }.getOrDefault(emptyList())
            found.clear()
            found.addAll(r)
            discovering = false
            discoverDone = true
        }
    }

    fun connectTo(d: FoundDrone) {
        host = d.address
        connect()
    }

    /** 连接后查询到的飞机序列号，用于确认控制的是哪一架 */
    var serial by mutableStateOf<String?>(null)
        private set

    /** 模拟器多机模式下的飞机编号：#1 端口 8889，#2 端口 8989 …（真机始终 8889） */
    val droneNumber: Int
        get() {
            val p = host.substringAfter(':', "").toIntOrNull() ?: DEFAULT_CMD_PORT
            val n = (p - DEFAULT_CMD_PORT) / 100 + 1
            return if (p >= DEFAULT_CMD_PORT && (p - DEFAULT_CMD_PORT) % 100 == 0 && n in 1..4) n else 0
        }

    fun selectDrone(n: Int) {
        val ip = host.trim().substringBefore(':')
        host = "$ip:${DEFAULT_CMD_PORT + 100 * (n - 1)}"
    }

    // ---- 日志 / 最近回复 ----
    val logs = mutableStateListOf<TelloClient.LogEntry>()
    var lastReply by mutableStateOf("")
        private set

    // ---- 摇杆（-1..1，y 向下为正） ----
    @Volatile private var lx = 0f
    @Volatile private var ly = 0f
    @Volatile private var rx = 0f
    @Volatile private var ry = 0f
    var stickPercent by mutableFloatStateOf(prefs.getFloat("stick", 60f))

    // ---- 指令页参数 ----
    var distance by mutableFloatStateOf(50f)
    var angle by mutableFloatStateOf(90f)
    var speed by mutableFloatStateOf(60f)

    // ---- 扩展模块 ----
    var tofFront by mutableStateOf<Int?>(null)
        private set
    var autoTof by mutableStateOf(false)
    val matrix = mutableStateListOf<Char>().apply { repeat(64) { add('0') } }
    var brush by mutableStateOf('r')

    init {
        viewModelScope.launch {
            client.logs.collect { e ->
                logs.add(e)
                if (logs.size > 400) logs.removeRange(0, logs.size - 400)
            }
        }
        viewModelScope.launch(Dispatchers.IO) { rcLoop() }
        viewModelScope.launch { tofLoop() }
        viewModelScope.launch { sensorLoop() }
    }

    /** 支持 "192.168.0.107:8889" 写法。 */
    fun connect() {
        val text = host.trim()
        val h = text.substringBefore(':')
        val p = text.substringAfter(':', "").toIntOrNull() ?: DEFAULT_CMD_PORT
        if (h.isEmpty()) {
            connectError = "请填写飞机或模拟器的 IP 地址"
            return
        }
        prefs.edit().putString("host", text).apply()
        connecting = true
        connectError = null
        viewModelScope.launch {
            val ok = client.connect(h, p)
            connecting = false
            if (ok) {
                serial = client.send("sn?").takeIf { it.isNotBlank() && it != TelloClient.TIMEOUT && !it.startsWith("error") }
            } else {
                connectError = "无法连接 $h:$p。请确认手机与电脑在同一 WiFi、模拟器已启动且防火墙已放行。"
            }
        }
    }

    fun disconnect() {
        autoTof = false
        autoSensors = false
        serial = null
        client.disconnect()
    }

    /** 普通指令：排队执行并等待回复。 */
    fun cmd(c: String) {
        viewModelScope.launch { lastReply = "$c → ${client.send(c)}" }
    }

    /** 插队指令：emergency / stop / land 在有动作执行时立即发出，打断当前动作。 */
    fun urgent(c: String) {
        viewModelScope.launch {
            if (client.isIdle) lastReply = "$c → ${client.send(c)}"
            else client.sendNow(c)
        }
    }

    fun setLeftStick(x: Float, y: Float) {
        lx = x; ly = y
    }

    fun setRightStick(x: Float, y: Float) {
        rx = x; ry = y
    }

    fun saveStick() = prefs.edit().putFloat("stick", stickPercent).apply()

    // 美国手（Mode 2）：左摇杆 = 油门 + 偏航，右摇杆 = 前后 + 左右
    private suspend fun rcLoop() {
        var zeroSent = 0
        while (viewModelScope.isActive) {
            delay(50)
            if (!client.connected.value) continue
            val k = stickPercent
            val a = (rx * k).roundToInt()
            val b = (-ry * k).roundToInt()
            val c = (-ly * k).roundToInt()
            val d = (lx * k).roundToInt()
            if (a == 0 && b == 0 && c == 0 && d == 0) {
                // 松手后连发几次归零，防止丢包导致飞机继续移动
                if (zeroSent < 3) {
                    client.sendNow("rc 0 0 0 0")
                    zeroSent++
                }
            } else {
                zeroSent = 0
                client.sendNow("rc $a $b $c $d")
            }
        }
    }

    // ---- 外接传感器模组（EXT 自定义指令，见 README「外接传感器模组」） ----
    data class HuskyBox(val id: Int, val x: Int, val y: Int, val w: Int, val h: Int)

    var ultrasonic by mutableStateOf<Int?>(null)
        private set
    var light by mutableStateOf<Int?>(null)
        private set
    var groundColor by mutableStateOf<Pair<Int, String>?>(null)   // (0xRRGGBB, 颜色名)
        private set
    var huskyMode by mutableStateOf("color")
    val husky = mutableStateListOf<HuskyBox>()
    var gesture by mutableStateOf<String?>(null)
        private set
    var irCode by mutableStateOf<String?>(null)
        private set
    var servoAngle by mutableFloatStateOf(90f)
    var autoSensors by mutableStateOf(false)

    /** 读取超声波、光线、颜色、HuskyLens（quiet = 后台轮询不写日志） */
    fun readSensors(quiet: Boolean = false) {
        viewModelScope.launch {
            fun num(r: String, prefix: String) = r.removePrefix(prefix).trim().split(" ").firstOrNull()?.toIntOrNull()
            num(client.send("EXT ultrasonic?", quiet = quiet), "ultrasonic")?.let { ultrasonic = it }
            num(client.send("EXT light?", quiet = quiet), "light")?.let { light = it }
            val c = client.send("EXT color?", quiet = quiet).removePrefix("color").trim().split(" ")
            if (c.size >= 4) {
                val rgb = c.take(3).mapNotNull { it.toIntOrNull() }
                if (rgb.size == 3) groundColor = ((rgb[0] shl 16) or (rgb[1] shl 8) or rgb[2]) to c[3]
            }
            val h = client.send("EXT husky?", quiet = quiet)
            if (h.startsWith("husky ")) {
                husky.clear()
                h.split(" ").drop(2).forEach { g ->
                    val v = g.split(",").mapNotNull { it.toIntOrNull() }
                    if (v.size == 5) husky.add(HuskyBox(v[0], v[1], v[2], v[3], v[4]))
                }
            }
        }
    }

    fun setHusky(mode: String) {
        huskyMode = mode
        viewModelScope.launch {
            client.send("EXT husky mode $mode")
            readSensors(quiet = true)
        }
    }

    /** 手势 / 红外是"事件"：每次读取取走一个，不做自动轮询，以免和用户程序抢事件 */
    fun readGesture() {
        viewModelScope.launch { gesture = client.send("EXT gesture?").removePrefix("gesture").trim() }
    }

    fun readIr() {
        viewModelScope.launch { irCode = client.send("EXT ir?").removePrefix("ir").trim() }
    }

    fun sendServo() = cmd("EXT servo ${servoAngle.roundToInt()}")

    private suspend fun sensorLoop() {
        while (viewModelScope.isActive) {
            delay(700)
            if (autoSensors && client.connected.value && client.isIdle) readSensors(quiet = true)
        }
    }

    private suspend fun tofLoop() {
        while (viewModelScope.isActive) {
            delay(400)
            if (autoTof && client.connected.value && client.isIdle) readTof(quiet = true)
        }
    }

    fun readTof(quiet: Boolean = false) {
        viewModelScope.launch {
            val r = client.send("EXT tof?", quiet = quiet)
            r.removePrefix("tof").trim().toIntOrNull()?.let { tofFront = it }
            if (!quiet) lastReply = "EXT tof? → $r"
        }
    }

    // ---- 点阵 ----
    fun paint(i: Int) {
        matrix[i] = if (matrix[i] == brush) '0' else brush
    }

    fun sendMatrix() = cmd("EXT mled g " + matrix.joinToString(""))

    fun clearMatrix() {
        for (i in 0 until 64) matrix[i] = '0'
        sendMatrix()
    }

    fun scrollText(direction: Char, color: Char, rate: Float, text: String) {
        if (text.isBlank()) return
        cmd(String.format(Locale.US, "EXT mled %c %c %.1f %s", direction, color, rate, text.trim()))
    }

    fun setLed(mode: Int, freq: Float, r: Int, g: Int, b: Int) {
        val c = when (mode) {
            1 -> String.format(Locale.US, "EXT led br %.1f %d %d %d", freq, r, g, b)
            2 -> String.format(Locale.US, "EXT led bl %.1f %d %d %d 0 0 0", freq, r, g, b)
            else -> "EXT led $r $g $b"
        }
        cmd(c)
    }

    /** 把 socket 绑定到 WiFi：连接无互联网的飞机热点时，Android 默认可能把流量走移动数据。 */
    private fun bindToWifi(s: DatagramSocket) {
        val cm = getApplication<Application>().getSystemService(ConnectivityManager::class.java) ?: return
        @Suppress("DEPRECATION")
        val wifi = cm.allNetworks.firstOrNull {
            cm.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
        } ?: return
        wifi.bindSocket(s)
    }

    override fun onCleared() {
        client.disconnect()
    }
}
