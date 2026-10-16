package com.rmtt.controller.net

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.net.InetAddress

class DiscoveryTest {
    private val reply = """
        RMTT-SIM 1
        name=DESKTOP-075FDC7
        ips=192.168.0.107,172.17.64.1
        drone=1;port=8889;sn=0TQZK7SIM00001;flying=0;client=-
        drone=2;port=8989;sn=0TQZK7SIM00002;flying=1;client=192.168.0.106
    """.trimIndent()

    @Test
    fun parseUsesSourceIpAndReadsDrones() {
        val list = Discovery.parse(reply, "192.168.0.107")
        assertEquals(2, list.size)
        assertEquals("192.168.0.107:8889", list[0].address)
        assertEquals("DESKTOP-075FDC7", list[0].computer)
        assertNull(list[0].client)
        assertEquals(2, list[1].number)
        assertTrue(list[1].flying)
        assertEquals("192.168.0.106", list[1].client)
    }

    @Test
    fun parseFallsBackToListedIpWhenSourceUnknown() {
        // 回复从虚拟网卡发出时，来源地址不在模拟器监听列表中
        val list = Discovery.parse(reply, "198.18.0.1")
        assertEquals("192.168.0.107:8889", list[0].address)
    }

    @Test
    fun parseIgnoresGarbage() {
        assertTrue(Discovery.parse("hello", "1.2.3.4").isEmpty())
        assertTrue(Discovery.parse("RMTT-SIM 1\ndrone=x;port=1", "1.2.3.4").isEmpty())
    }

    /** 与正在运行的模拟器联调：广播搜索应能找到它（模拟器未运行时跳过）。 */
    @Test
    fun searchFindsRunningSimulator() = runBlocking {
        val found = Discovery.search(extraTargets = listOf(InetAddress.getByName("127.0.0.1")))
        assumeTrue("局域网中没有运行模拟器，跳过", found.isNotEmpty())
        assertTrue(found.all { it.sn.startsWith("0TQZK7SIM") && it.port in 8889..9189 })
        assertEquals(1, found.count { it.number == 1 })
    }
}
