package com.rmtt.controller.net

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.Inet4Address
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.SocketTimeoutException

const val DISCOVERY_PORT = 8899

/** 局域网中找到的一架模拟飞机。 */
data class FoundDrone(
    val computer: String,   // 模拟器所在电脑名
    val host: String,       // 连接地址（电脑的局域网 IP）
    val number: Int,        // 飞机编号 #1 ~ #4
    val port: Int,
    val sn: String,
    val flying: Boolean,
    val client: String?,    // 正在控制它的客户端 IP，"pc" 表示电脑本机（Mind+），null 表示空闲
) {
    val address: String get() = "$host:$port"
}

/**
 * 自动发现：向局域网广播 "RMTT-DISCOVER 1"，收集各台电脑上模拟器的回复（协议见 rmtt_sim/discovery.py）。
 * 不依赖 Android API，可在 JVM 单元测试中直接使用。
 */
object Discovery {
    suspend fun search(
        timeoutMs: Int = 1500,
        port: Int = DISCOVERY_PORT,
        extraTargets: List<InetAddress> = emptyList(),
        socketBinder: (DatagramSocket) -> Unit = {},
    ): List<FoundDrone> = withContext(Dispatchers.IO) {
        // 同一台电脑可能从多块网卡回复（WLAN / 虚拟网卡），按"电脑名 + SN"去重，优先保留直接可达的地址
        val found = linkedMapOf<String, Pair<FoundDrone, Boolean>>()
        DatagramSocket(null).use { s ->
            s.reuseAddress = true
            runCatching { socketBinder(s) }
            if (!s.isBound) s.bind(InetSocketAddress(0))
            s.broadcast = true
            val request = "RMTT-DISCOVER 1".toByteArray()
            val targets = (broadcastAddresses() + extraTargets).distinct()
            // 发两轮，降低 WiFi 丢包的影响
            repeat(2) {
                for (t in targets) runCatching { s.send(DatagramPacket(request, request.size, t, port)) }
            }
            val deadline = System.currentTimeMillis() + timeoutMs
            val buf = ByteArray(4096)
            while (true) {
                val left = deadline - System.currentTimeMillis()
                if (left <= 0) break
                s.soTimeout = left.toInt()
                val p = DatagramPacket(buf, buf.size)
                try {
                    s.receive(p)
                } catch (e: SocketTimeoutException) {
                    break
                }
                val text = String(p.data, 0, p.length, Charsets.UTF_8)
                val source = p.address.hostAddress ?: continue
                for (d in parse(text, source)) {
                    val key = "${d.computer}|${d.sn}"
                    val direct = d.host == source
                    val old = found[key]
                    if (old == null || (direct && !old.second)) found[key] = d to direct
                }
            }
        }
        found.values.map { it.first }.sortedWith(compareBy({ it.computer }, { it.number }))
    }

    /** 解析模拟器回复；sourceIp 为回复包的来源地址。 */
    fun parse(text: String, sourceIp: String): List<FoundDrone> {
        val lines = text.lines().map { it.trim() }.filter { it.isNotEmpty() }
        if (lines.firstOrNull()?.startsWith("RMTT-SIM") != true) return emptyList()
        val fields = lines.drop(1).filter { !it.startsWith("drone=") }
            .associate { it.substringBefore('=') to it.substringAfter('=', "") }
        val name = fields["name"].orEmpty().ifEmpty { sourceIp }
        val ips = fields["ips"].orEmpty().split(',').map { it.trim() }.filter { it.isNotEmpty() }
        // 优先用回复包的来源地址（一定可达）；若不在模拟器监听的地址里，则退回列表第一个
        val host = if (ips.isEmpty() || sourceIp in ips) sourceIp else ips.first()
        return lines.filter { it.startsWith("drone=") }.mapNotNull { line ->
            val kv = line.split(';').associate { it.substringBefore('=') to it.substringAfter('=', "") }
            val n = kv["drone"]?.toIntOrNull() ?: return@mapNotNull null
            val port = kv["port"]?.toIntOrNull() ?: return@mapNotNull null
            FoundDrone(
                computer = name, host = host, number = n, port = port,
                sn = kv["sn"].orEmpty(), flying = kv["flying"] == "1",
                client = kv["client"]?.takeIf { it.isNotEmpty() && it != "-" },
            )
        }
    }

    /** 所有 IPv4 网卡的子网广播地址，再加上 255.255.255.255。 */
    private fun broadcastAddresses(): List<InetAddress> {
        val out = mutableListOf<InetAddress>(InetAddress.getByName("255.255.255.255"))
        runCatching {
            for (nif in NetworkInterface.getNetworkInterfaces()) {
                if (!nif.isUp || nif.isLoopback) continue
                for (ia in nif.interfaceAddresses) {
                    if (ia.address is Inet4Address) ia.broadcast?.let { out += it }
                }
            }
        }
        return out
    }
}
