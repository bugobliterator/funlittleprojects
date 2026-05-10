package com.sidbh.claudeusage.widget

import java.time.Instant

sealed class WidgetState {
    data object Unconfigured : WidgetState()
    data object Loading : WidgetState()
    data object AuthError : WidgetState()
    data class NetworkError(val message: String) : WidgetState()
    data class Loaded(
        val fiveHourPct: Double,
        val fiveHourResetsAt: Instant?,
        val sevenDayPct: Double?, // null = no 7-day data at all
        val sevenDayResetsAt: Instant?,
        val sevenDayLabel: String, // "7-day Opus" when opus is tracked, else "7-day"
        val fetchedAt: Instant,
        val mock: Boolean,
    ) : WidgetState()
}
