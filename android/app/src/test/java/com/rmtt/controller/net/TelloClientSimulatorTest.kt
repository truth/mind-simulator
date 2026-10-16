package com.rmtt.controller.net

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test

/**
 * 与运行中的 TT 模拟器做联调（模拟器在 127.0.0.1:8889 上也有监听，即 Android 模拟器的 10.0.2.2）。
 * 模拟器未启动时自动跳过：先运行  python -m rmtt_sim --no-browser
 */
class TelloClientSimulatorTest {
    private val host = System.getenv("TT_SIM_HOST") ?: "127.0.0.1"
    private lateinit var scope: CoroutineScope
    private lateinit var client: TelloClient

    @Before
    fun setUp() {
        scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        client = TelloClient(scope)
        val ok = runBlocking { client.connect(host, 8889) }
        assumeTrue("模拟器未运行，跳过联调测试", ok)
    }

    @After
    fun tearDown() {
        runBlocking { if (client.connected.value) client.send("emergency") }
        client.disconnect()
        scope.cancel()
    }

    @Test
    fun flightAndExtensionCommands() = runBlocking {
        assertEquals("RMTT", client.send("hardware?"))
        assertTrue(client.send("battery?").toInt() in 0..100)

        assertEquals("ok", client.send("takeoff"))
        delay(500)
        val s = client.state.value
        assertTrue("应收到 8890 状态推送", s.valid)
        assertTrue("起飞后高度约 80cm，实际 ${s.height}", s.height in 70..90)

        assertEquals("ok", client.send("cw 90"))
        assertEquals("led ok", client.send("EXT led 255 0 0"))
        assertEquals("mled ok", client.send("EXT mled l r 1.0 Hi"))
        assertTrue(client.send("EXT tof?").startsWith("tof "))
        assertEquals("error Out of range", client.send("forward 5"))
        assertEquals("ok", client.send("land"))
    }

    @Test
    fun rcMovesDrone() = runBlocking {
        assertEquals("ok", client.send("takeoff"))
        client.sendNow("rc 0 0 50 0")   // 油门向上
        delay(1000)
        client.sendNow("rc 0 0 0 0")
        delay(400)
        val h = client.state.value.height
        assertTrue("rc 上升后高度应明显高于 80cm，实际 $h", h > 100)
        assertEquals("ok", client.send("land"))
    }

    @Test
    fun emergencyInterruptsRunningMove() = runBlocking {
        assertEquals("ok", client.send("takeoff"))
        val pending = async { client.send("forward 300") }
        delay(800)
        assertTrue(!client.isIdle)
        client.sendNow("emergency")
        val r = pending.await()
        assertTrue("被打断的动作应得到回复（实际：$r）", r != TelloClient.TIMEOUT)
    }
}
