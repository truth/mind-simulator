package com.rmtt.controller.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 虚拟摇杆。onMove 回调 (x, y)，范围 -1..1，x 向右为正、y 向下为正；松手自动回中。
 * 每个摇杆独立跟踪自己的手指，两只手可同时操作。
 */
@Composable
fun Joystick(
    modifier: Modifier = Modifier,
    top: String,
    bottom: String,
    left: String,
    right: String,
    onMove: (Float, Float) -> Unit,
) {
    var knob by remember { mutableStateOf(Offset.Zero) }
    val callback by rememberUpdatedState(onMove)

    Box(modifier.aspectRatio(1f), contentAlignment = Alignment.Center) {
        Canvas(
            Modifier
                .fillMaxSize()
                .pointerInput(Unit) {
                    val center = Offset(size.width / 2f, size.height / 2f)
                    val travel = size.width / 2f * 0.72f
                    fun update(p: Offset) {
                        var v = (p - center) / travel
                        val len = v.getDistance()
                        if (len > 1f) v /= len
                        knob = v
                        callback(v.x, v.y)
                    }
                    awaitEachGesture {
                        val down = awaitFirstDown()
                        update(down.position)
                        while (true) {
                            val event = awaitPointerEvent()
                            val ch = event.changes.firstOrNull { it.id == down.id } ?: break
                            if (!ch.pressed) break
                            update(ch.position)
                            ch.consume()
                        }
                        knob = Offset.Zero
                        callback(0f, 0f)
                    }
                }
        ) {
            val r = size.minDimension / 2f
            val c = center
            drawCircle(Color(0xFF1A232D), r * 0.98f, c)
            drawCircle(Border, r * 0.98f, c, style = Stroke(3f))
            drawCircle(Border, r * 0.5f, c, style = Stroke(1.5f))
            drawLine(Border, Offset(c.x - r * 0.9f, c.y), Offset(c.x + r * 0.9f, c.y), 1.5f)
            drawLine(Border, Offset(c.x, c.y - r * 0.9f), Offset(c.x, c.y + r * 0.9f), 1.5f)
            val k = c + knob * (r * 0.72f)
            val active = knob != Offset.Zero
            drawCircle(if (active) Accent.copy(alpha = 0.35f) else Color(0x22FFFFFF), r * 0.34f, k)
            drawCircle(if (active) Accent else Color(0xFF8A96A3), r * 0.26f, k)
        }
        val labelMod = Modifier.padding(6.dp)
        Text(top, labelMod.align(Alignment.TopCenter), color = Muted, fontSize = 11.sp)
        Text(bottom, labelMod.align(Alignment.BottomCenter), color = Muted, fontSize = 11.sp)
        Text(left, labelMod.align(Alignment.CenterStart), color = Muted, fontSize = 11.sp)
        Text(right, labelMod.align(Alignment.CenterEnd), color = Muted, fontSize = 11.sp)
    }
}
