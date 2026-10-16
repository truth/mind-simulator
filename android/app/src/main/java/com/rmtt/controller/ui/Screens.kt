@file:OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)

package com.rmtt.controller.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.rmtt.controller.DroneViewModel
import com.rmtt.controller.net.TelloClient
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

@Composable
fun App(vm: DroneViewModel) {
    val connected by vm.client.connected.collectAsState()
    Surface(Modifier.fillMaxSize(), color = Bg) {
        if (connected) MainScreen(vm) else ConnectScreen(vm)
    }
}

// ============================================================ 连接页

@Composable
fun ConnectScreen(vm: DroneViewModel) {
    Box(Modifier.fillMaxSize().padding(16.dp), contentAlignment = Alignment.Center) {
        Column(
            Modifier
                .widthIn(max = 560.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(Panel)
                .border(1.dp, Border, RoundedCornerShape(12.dp))
                .padding(20.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.clip(RoundedCornerShape(4.dp)).background(Orange).padding(horizontal = 6.dp, vertical = 1.dp)
                ) { Text("TT", color = Color.White, fontWeight = FontWeight.Bold) }
                Spacer(Modifier.width(8.dp))
                Text("RoboMaster TT 遥控器", fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
            }
            Text(
                "使用 Tello SDK 3.0 协议，可连接电脑上的 TT 模拟器，也可连接真实的 RoboMaster TT / Tello EDU。",
                color = Muted, fontSize = 13.sp,
            )
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    value = vm.host,
                    onValueChange = { vm.host = it },
                    label = { Text("飞机地址（IP 或 IP:端口）") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Go),
                    keyboardActions = KeyboardActions(onGo = { vm.connect() }),
                )
                Button(
                    onClick = { vm.connect() },
                    enabled = !vm.connecting,
                    modifier = Modifier.padding(top = 8.dp).height(56.dp).width(120.dp),
                ) {
                    if (vm.connecting) {
                        CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = Color.White)
                    } else {
                        Text("连接", fontSize = 16.sp)
                    }
                }
            }
            vm.connectError?.let { Text(it, color = Danger, fontSize = 13.sp) }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("模拟器飞机", fontSize = 13.sp, color = Muted)
                Segmented(listOf("#1", "#2", "#3", "#4"), vm.droneNumber - 1) { vm.selectDrone(it + 1) }
                Text("双机模式：两部手机各选一个编号", fontSize = 12.sp, color = Muted)
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { vm.host = "192.168.10.1" }) { Text("真机 192.168.10.1") }
                OutlinedButton(onClick = { vm.host = "10.0.2.2:8889" }) { Text("Android 模拟器 10.0.2.2") }
            }
            Text(
                "连接电脑上的模拟器：手机和电脑连同一个 WiFi，填写模拟器网页「连接 → 手机 App」一栏显示的地址，例如 192.168.0.107:8889。\n" +
                    "连接真机：手机连接 RMTT-xxxxxx 热点，扩展模块开关拨到 AP 档，地址填 192.168.10.1。",
                color = Muted, fontSize = 12.sp, lineHeight = 18.sp,
            )
        }
    }
}

// ============================================================ 主界面

@Composable
fun MainScreen(vm: DroneViewModel) {
    var tab by rememberSaveable { mutableIntStateOf(0) }
    Row(Modifier.fillMaxSize()) {
        NavigationRail(containerColor = Panel, modifier = Modifier.fillMaxHeight()) {
            val items = listOf(
                "飞行" to Icons.Filled.PlayArrow,
                "指令" to Icons.Filled.Build,
                "扩展模块" to Icons.Filled.Star,
                "日志" to Icons.Filled.Info,
            )
            items.forEachIndexed { i, (label, icon) ->
                NavigationRailItem(
                    selected = tab == i,
                    onClick = { tab = i },
                    icon = { Icon(icon, label) },
                    label = { Text(label, fontSize = 11.sp) },
                )
            }
            Spacer(Modifier.weight(1f))
            NavigationRailItem(
                selected = false,
                onClick = { vm.disconnect() },
                icon = { Icon(Icons.Filled.Close, "断开") },
                label = { Text("断开", fontSize = 11.sp) },
            )
        }
        Column(Modifier.weight(1f).fillMaxHeight()) {
            StatusBar(vm)
            Box(Modifier.weight(1f).fillMaxWidth().padding(8.dp)) {
                when (tab) {
                    0 -> FlightTab(vm)
                    1 -> CommandTab(vm)
                    2 -> ExtTab(vm)
                    else -> LogTab(vm)
                }
            }
        }
    }
}

@Composable
private fun StatusBar(vm: DroneViewModel) {
    val s by vm.client.state.collectAsState()
    val busy by vm.client.busy.collectAsState()
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(500); now = System.currentTimeMillis()
        }
    }
    val fresh = s.fresh(now)
    Row(
        Modifier.fillMaxWidth().background(Panel).padding(horizontal = 12.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(Modifier.size(9.dp).clip(CircleShape).background(if (fresh) Ok else Color(0xFFF3A712)))
        if (vm.droneNumber > 0 && vm.host.contains(':')) {
            Box(Modifier.clip(RoundedCornerShape(4.dp)).background(Orange).padding(horizontal = 6.dp)) {
                Text("#${vm.droneNumber}", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold, maxLines = 1)
            }
        }
        // 第一行地址；第二行显示正在执行的指令（优先）或 SN
        Column(Modifier.widthIn(max = 170.dp)) {
            Text(vm.client.targetAddress ?: "", fontSize = 12.sp, color = Muted, maxLines = 1, softWrap = false)
            Text(
                busy?.let { "▶ $it" } ?: vm.serial?.let { "SN $it" } ?: "",
                fontSize = 10.sp, color = if (busy != null) Accent else Muted, maxLines = 1,
                overflow = TextOverflow.Ellipsis, fontFamily = FontFamily.Monospace,
            )
        }
        Row(
            Modifier.weight(1f),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (s.valid) {
                Stat("电量", "${s.battery}%", if (s.battery < 20) Danger else if (s.battery < 50) Color(0xFFF3C969) else null)
                Stat("高度", "${s.height}cm")
                Stat("ToF↓", "${s.tof}cm")
                Stat("航向", "${s.yaw}°")
                Stat("温度", "${s.tempHigh}℃")
                Stat("卡", if (s.mid > 0) "m${s.mid}" else "-")
            } else {
                Text("未收到 8890 状态推送", fontSize = 12.sp, color = Color(0xFFF3A712), maxLines = 1)
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: String, color: Color? = null) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(label, fontSize = 11.sp, color = Muted, maxLines = 1, softWrap = false)
        Spacer(Modifier.width(3.dp))
        Text(
            value, fontSize = 13.sp, fontFamily = FontFamily.Monospace, maxLines = 1, softWrap = false,
            color = color ?: MaterialTheme.colorScheme.onSurface,
        )
    }
}

// ============================================================ 飞行页：双摇杆

@Composable
private fun FlightTab(vm: DroneViewModel) {
    Row(Modifier.fillMaxSize(), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.weight(1f).fillMaxHeight(), contentAlignment = Alignment.Center) {
            Joystick(Modifier.fillMaxHeight(0.96f), "上升", "下降", "左转", "右转", vm::setLeftStick)
        }
        Column(
            Modifier.width(230.dp).fillMaxHeight().verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterVertically),
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Button(onClick = { vm.cmd("takeoff") }, Modifier.weight(1f)) { Text("起飞") }
                Button(onClick = { vm.urgent("land") }, Modifier.weight(1f)) { Text("降落") }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                FilledTonalButton(onClick = { vm.urgent("stop") }, Modifier.weight(1f)) { Text("悬停") }
                Button(
                    onClick = { vm.urgent("emergency") }, Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = Danger),
                ) { Text("急停") }
            }
            Text("翻滚", fontSize = 12.sp, color = Muted)
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                listOf("前" to "f", "后" to "b", "左" to "l", "右" to "r").forEach { (t, d) ->
                    OutlinedButton(
                        onClick = { vm.cmd("flip $d") }, Modifier.weight(1f).height(36.dp),
                        contentPadding = PaddingValues(0.dp),
                    ) { Text(t) }
                }
            }
            // 灵敏度标签与滑条同一行，节省竖向空间（横屏手机高度有限）
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("灵敏度 ${vm.stickPercent.roundToInt()}%", fontSize = 12.sp, color = Muted, maxLines = 1)
                Slider(
                    value = vm.stickPercent,
                    onValueChange = { vm.stickPercent = it },
                    onValueChangeFinished = { vm.saveStick() },
                    valueRange = 10f..100f,
                    modifier = Modifier.weight(1f).height(32.dp).padding(start = 6.dp),
                )
            }
            if (vm.lastReply.isNotEmpty()) {
                Text(
                    vm.lastReply, fontSize = 11.sp, fontFamily = FontFamily.Monospace, maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    color = if (vm.lastReply.contains("error")) Danger else Ok,
                )
            }
        }
        Box(Modifier.weight(1f).fillMaxHeight(), contentAlignment = Alignment.Center) {
            Joystick(Modifier.fillMaxHeight(0.96f), "前进", "后退", "左移", "右移", vm::setRightStick)
        }
    }
}

// ============================================================ 指令页：与 Mind+ 积木对应的动作指令

@Composable
private fun CommandTab(vm: DroneViewModel) {
    val d = vm.distance.roundToInt()
    val a = vm.angle.roundToInt()
    Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("移动距离 $d cm", color = Muted, fontSize = 12.sp)
            Slider(vm.distance, { vm.distance = (it / 10).roundToInt() * 10f }, valueRange = 20f..500f)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                CmdButton("上升", Modifier.weight(1f)) { vm.cmd("up $d") }
                CmdButton("前进", Modifier.weight(1f)) { vm.cmd("forward $d") }
                CmdButton("下降", Modifier.weight(1f)) { vm.cmd("down $d") }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                CmdButton("左移", Modifier.weight(1f)) { vm.cmd("left $d") }
                CmdButton("后退", Modifier.weight(1f)) { vm.cmd("back $d") }
                CmdButton("右移", Modifier.weight(1f)) { vm.cmd("right $d") }
            }
            Spacer(Modifier.height(4.dp))
            Text("旋转角度 $a°", color = Muted, fontSize = 12.sp)
            Slider(vm.angle, { vm.angle = it }, valueRange = 1f..360f)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                CmdButton("↺ 逆时针", Modifier.weight(1f)) { vm.cmd("ccw $a") }
                CmdButton("↻ 顺时针", Modifier.weight(1f)) { vm.cmd("cw $a") }
            }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("飞行速度 ${vm.speed.roundToInt()} cm/s", color = Muted, fontSize = 12.sp)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Slider(vm.speed, { vm.speed = it }, Modifier.weight(1f), valueRange = 10f..100f)
                Spacer(Modifier.width(8.dp))
                OutlinedButton(onClick = { vm.cmd("speed ${vm.speed.roundToInt()}") }) { Text("设置") }
            }
            Text("挑战卡 / 视频", color = Muted, fontSize = 12.sp)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                CmdButton("开启挑战卡") { vm.cmd("mon") }
                CmdButton("关闭挑战卡") { vm.cmd("moff") }
                CmdButton("飞到挑战卡正上方") { vm.cmd("go 0 0 100 50 m-1") }
                CmdButton("开视频流") { vm.cmd("streamon") }
            }
            Text("查询", color = Muted, fontSize = 12.sp)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("battery?", "speed?", "time?", "sn?", "sdk?", "hardware?", "wifi?").forEach { q ->
                    CmdButton(q) { vm.cmd(q) }
                }
            }
            Text("最近回复：${vm.lastReply}", fontSize = 12.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

@Composable
private fun CmdButton(text: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    FilledTonalButton(onClick = onClick, modifier = modifier, contentPadding = PaddingValues(horizontal = 10.dp)) {
        Text(text, maxLines = 1)
    }
}

// ============================================================ 扩展模块页：点阵 / RGB 灯 / ToF

@Composable
private fun ExtTab(vm: DroneViewModel) {
    Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        // 点阵编辑器
        Column(Modifier.fillMaxHeight().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("8×8 点阵（点击绘制）", color = Muted, fontSize = 12.sp)
            Column(
                Modifier.clip(RoundedCornerShape(8.dp)).background(Color(0xFF0A0D10)).padding(6.dp),
                verticalArrangement = Arrangement.spacedBy(3.dp),
            ) {
                for (r in 0 until 8) {
                    Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        for (c in 0 until 8) {
                            val i = r * 8 + c
                            Box(
                                Modifier.size(22.dp).clip(CircleShape).background(matrixColor(vm.matrix[i]))
                                    .clickable { vm.paint(i) }
                            )
                        }
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                listOf('r' to "红", 'b' to "蓝", 'p' to "紫").forEach { (ch, name) ->
                    FilterChip(
                        selected = vm.brush == ch, onClick = { vm.brush = ch },
                        label = { Text(name) },
                        leadingIcon = { Box(Modifier.size(10.dp).clip(CircleShape).background(matrixColor(ch))) },
                    )
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Button(onClick = { vm.sendMatrix() }) { Text("显示图案") }
                OutlinedButton(onClick = { vm.clearMatrix() }) { Text("清屏") }
            }
        }

        Column(Modifier.weight(1f).fillMaxHeight().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            ScrollTextCard(vm)
            LedCard(vm)
            TofCard(vm)
        }
    }
}

@Composable
private fun Card(title: String, content: @Composable () -> Unit) {
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(Panel)
            .border(1.dp, Border, RoundedCornerShape(8.dp)).padding(10.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(title, color = Color(0xFF9FC3FF), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        content()
    }
}

@Composable
private fun ScrollTextCard(vm: DroneViewModel) {
    var text by rememberSaveable { mutableStateOf("Hello TT") }
    var dir by rememberSaveable { mutableIntStateOf(0) }
    var color by rememberSaveable { mutableIntStateOf(0) }
    var rate by rememberSaveable { mutableFloatStateOf(1.0f) }
    val dirs = listOf('l' to "←", 'r' to "→", 'u' to "↑", 'd' to "↓")
    val colors = listOf('r' to "红", 'b' to "蓝", 'p' to "紫")
    Card("点阵文字") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            OutlinedTextField(
                text, { if (it.length < 70) text = it }, Modifier.weight(1f),
                singleLine = true, label = { Text("文字（英文 / 数字）") },
            )
            Button(onClick = { vm.scrollText(dirs[dir].first, colors[color].first, rate, text) }) { Text("滚动") }
            OutlinedButton(onClick = { vm.cmd("EXT mled s ${colors[color].first} ${text.firstOrNull() ?: ' '}") }) { Text("静态") }
            OutlinedButton(onClick = { vm.cmd("EXT mled s ${colors[color].first} heart") }) { Text("♥") }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Segmented(dirs.map { it.second }, dir) { dir = it }
            Segmented(colors.map { it.second }, color) { color = it }
            Text(String.format(Locale.US, "%.1fHz", rate), fontSize = 12.sp, color = Muted)
            Slider(rate, { rate = (it * 10).roundToInt() / 10f }, Modifier.weight(1f), valueRange = 0.1f..2.5f)
        }
    }
}

@Composable
private fun LedCard(vm: DroneViewModel) {
    var r by rememberSaveable { mutableFloatStateOf(0f) }
    var g by rememberSaveable { mutableFloatStateOf(160f) }
    var b by rememberSaveable { mutableFloatStateOf(255f) }
    var mode by rememberSaveable { mutableIntStateOf(0) }
    var freq by rememberSaveable { mutableFloatStateOf(1f) }
    var brightness by rememberSaveable { mutableFloatStateOf(255f) }
    val presets = listOf(
        Triple(255, 0, 0), Triple(0, 255, 0), Triple(0, 0, 255), Triple(255, 200, 0),
        Triple(0, 255, 255), Triple(180, 0, 255), Triple(255, 255, 255), Triple(0, 0, 0),
    )
    fun send() = vm.setLed(mode, freq, r.roundToInt(), g.roundToInt(), b.roundToInt())
    Card("顶部 RGB 灯") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(
                Modifier.size(34.dp).clip(CircleShape)
                    .background(Color(r.roundToInt(), g.roundToInt(), b.roundToInt()))
                    .border(2.dp, Border, CircleShape)
            )
            presets.forEach { (pr, pg, pb) ->
                Box(
                    Modifier.size(26.dp).clip(CircleShape).background(Color(pr, pg, pb))
                        .border(1.dp, Border, CircleShape)
                        .clickable { r = pr.toFloat(); g = pg.toFloat(); b = pb.toFloat(); send() }
                )
            }
        }
        ColorSlider("R", r, Color(0xFFFF5A5A)) { r = it }
        ColorSlider("G", g, Color(0xFF4CC38A)) { g = it }
        ColorSlider("B", b, Color(0xFF5A8CFF)) { b = it }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Segmented(listOf("常亮", "呼吸", "闪烁"), mode) { mode = it }
            if (mode != 0) {
                Text(String.format(Locale.US, "%.1fHz", freq), fontSize = 12.sp, color = Muted)
                Slider(freq, { freq = (it * 10).roundToInt() / 10f }, Modifier.weight(1f), valueRange = 0.1f..2.5f)
            } else {
                Spacer(Modifier.weight(1f))
            }
            Button(onClick = { send() }) { Text("设置灯光") }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("点阵亮度 ${brightness.roundToInt()}", fontSize = 12.sp, color = Muted)
            Slider(
                brightness, { brightness = it }, Modifier.weight(1f).padding(horizontal = 8.dp),
                valueRange = 0f..255f,
                onValueChangeFinished = { vm.cmd("EXT mled sl ${brightness.roundToInt()}") },
            )
        }
    }
}

@Composable
private fun ColorSlider(label: String, value: Float, color: Color, onChange: (Float) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.height(28.dp)) {
        Text(label, Modifier.width(16.dp), color = color, fontWeight = FontWeight.Bold)
        Slider(value, onChange, Modifier.weight(1f), valueRange = 0f..255f)
        Text("${value.roundToInt()}", Modifier.width(34.dp), fontSize = 12.sp, fontFamily = FontFamily.Monospace)
    }
}

@Composable
private fun TofCard(vm: DroneViewModel) {
    Card("前向 ToF 测距") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            val t = vm.tofFront
            Text(
                when {
                    t == null -> "--"
                    t >= 8192 -> "超出量程"
                    else -> "$t mm"
                },
                fontSize = 22.sp, fontFamily = FontFamily.Monospace,
                color = if (t != null && t < 500) Orange else MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.weight(1f))
            Text("自动刷新", fontSize = 12.sp, color = Muted)
            Switch(vm.autoTof, { vm.autoTof = it })
            OutlinedButton(onClick = { vm.readTof() }) { Text("读取") }
        }
        val frac = vm.tofFront?.let { if (it >= 8192) 1f else (it / 1200f).coerceIn(0f, 1f) } ?: 0f
        Box(Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)).background(Color(0xFF0A0D10))) {
            Box(Modifier.fillMaxWidth(frac).fillMaxHeight().background(if (frac < 0.4f) Orange else Ok))
        }
    }
}

@Composable
private fun Segmented(options: List<String>, selected: Int, onSelect: (Int) -> Unit) {
    SingleChoiceSegmentedButtonRow {
        options.forEachIndexed { i, label ->
            SegmentedButton(
                selected = selected == i,
                onClick = { onSelect(i) },
                shape = SegmentedButtonDefaults.itemShape(i, options.size),
                icon = {},
            ) { Text(label, fontSize = 12.sp) }
        }
    }
}

// ============================================================ 日志页：SDK 控制台

@Composable
private fun LogTab(vm: DroneViewModel) {
    var input by rememberSaveable { mutableStateOf("") }
    val listState = rememberLazyListState()
    LaunchedEffect(vm.logs.size) {
        if (vm.logs.isNotEmpty()) listState.animateScrollToItem(vm.logs.size - 1)
    }
    val fmt = remember { SimpleDateFormat("HH:mm:ss", Locale.getDefault()) }
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            OutlinedTextField(
                input, { input = it }, Modifier.weight(1f),
                singleLine = true,
                placeholder = { Text("输入任意 SDK 指令，如 go 100 0 50 60 / curve 50 50 0 0 100 0 30") },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = {
                    if (input.isNotBlank()) vm.cmd(input.trim()); input = ""
                }),
            )
            Button(onClick = { if (input.isNotBlank()) vm.cmd(input.trim()); input = "" }) { Text("发送") }
            TextButton(onClick = { vm.logs.clear() }) { Text("清空") }
        }
        LazyColumn(
            Modifier.fillMaxSize().clip(RoundedCornerShape(6.dp)).background(Color(0xFF0D1217)).padding(6.dp),
            state = listState,
        ) {
            items(vm.logs) { e ->
                val (tag, color) = when (e.kind) {
                    TelloClient.Kind.SEND -> "→" to Color(0xFF8FD3FF)
                    TelloClient.Kind.RECV ->
                        "←" to if (e.text.startsWith("error") || e.text.startsWith("unknown")) Color(0xFFFF8A8A) else Color(0xFF9BE7B0)
                    TelloClient.Kind.ERROR -> "⚠" to Color(0xFFF3C969)
                    TelloClient.Kind.INFO -> "·" to Muted
                }
                Row {
                    Text(fmt.format(Date(e.time)), fontSize = 12.sp, color = Color(0xFF56616D), fontFamily = FontFamily.Monospace)
                    Spacer(Modifier.width(6.dp))
                    Text("$tag ${e.text}", fontSize = 12.sp, color = color, fontFamily = FontFamily.Monospace)
                }
            }
        }
    }
}
