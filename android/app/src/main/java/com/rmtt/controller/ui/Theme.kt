package com.rmtt.controller.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Bg = Color(0xFF0F1419)
val Panel = Color(0xFF18212B)
val Border = Color(0xFF2A3644)
val Accent = Color(0xFF2F6FDE)
val Orange = Color(0xFFE4572E)
val Danger = Color(0xFFD64545)
val Ok = Color(0xFF4CC38A)
val Muted = Color(0xFF7D8B9C)
val MatrixRed = Color(0xFFFF2A2A)
val MatrixBlue = Color(0xFF2A6BFF)
val MatrixPurple = Color(0xFFC040FF)
val MatrixOff = Color(0xFF232A33)

private val scheme = darkColorScheme(
    primary = Accent,
    onPrimary = Color.White,
    secondary = Orange,
    background = Bg,
    surface = Panel,
    surfaceVariant = Color(0xFF1F2832),
    surfaceContainer = Panel,
    surfaceContainerHigh = Color(0xFF1F2832),
    outline = Border,
    error = Danger,
)

@Composable
fun TTTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = scheme, content = content)
}

fun matrixColor(c: Char): Color = when (c) {
    'r' -> MatrixRed
    'b' -> MatrixBlue
    'p' -> MatrixPurple
    else -> MatrixOff
}
