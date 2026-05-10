package com.sidbh.claudeusage.widget

import android.content.Context
import com.sidbh.claudeusage.R
import com.sidbh.claudeusage.data.UsageResult
import java.time.Instant

class WidgetStateStore(private val context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences("claude_usage_state", Context.MODE_PRIVATE)

    fun save(result: UsageResult, mock: Boolean) {
        val ed = prefs.edit()
        when (result) {
            is UsageResult.Success -> {
                val pct5 = result.data.fiveHour?.utilization?.toFloat() ?: -1f
                val resets5 = result.data.fiveHour?.resetsAt

                // Prefer Opus-specific 7-day if tracked; else fall back to overall 7-day.
                val opus = result.data.sevenDayOpus
                val overall = result.data.sevenDay
                val showOverall = opus == null && overall != null
                val bucket = opus ?: overall
                val pct7 = bucket?.utilization?.toFloat() ?: -1f
                val resets7 = bucket?.resetsAt

                ed.putString("last_status", STATUS_OK)
                    .putFloat("five_hour_pct", pct5)
                    .putString("five_hour_resets", resets5)
                    .putFloat("seven_day_pct", pct7)
                    .putString("seven_day_resets", resets7)
                    .putBoolean("seven_day_show_overall", showOverall)
                    .putLong("fetched_at", result.fetchedAt.toEpochMilli())
                    .putBoolean("mock", mock)
            }
            is UsageResult.AuthError -> ed.putString("last_status", STATUS_AUTH)
            is UsageResult.NetworkError -> ed
                .putString("last_status", STATUS_NETWORK)
                .putString("last_error", result.message)
            UsageResult.NotConfigured -> ed.putString("last_status", STATUS_UNCONFIGURED)
        }
        ed.apply()
    }

    fun load(credentialsConfigured: Boolean): WidgetState {
        if (!credentialsConfigured) return WidgetState.Unconfigured
        return when (prefs.getString("last_status", null)) {
            STATUS_AUTH -> WidgetState.AuthError
            STATUS_NETWORK -> {
                val msg = prefs.getString("last_error", "network").orEmpty()
                if (hasCachedSuccess()) loadCached() else WidgetState.NetworkError(msg)
            }
            STATUS_OK -> loadCached()
            else -> WidgetState.Loading
        }
    }

    private fun hasCachedSuccess(): Boolean =
        prefs.getLong("fetched_at", 0L) > 0L

    private fun loadCached(): WidgetState.Loaded {
        val pct5 = prefs.getFloat("five_hour_pct", 0f).toDouble()
        val resets5 = prefs.getString("five_hour_resets", null)?.let { runCatching { Instant.parse(it) }.getOrNull() }
        val pct7Raw = prefs.getFloat("seven_day_pct", -1f).toDouble()
        val pct7 = if (pct7Raw < 0) null else pct7Raw
        val resets7 = prefs.getString("seven_day_resets", null)?.let { runCatching { Instant.parse(it) }.getOrNull() }
        val showOverall = prefs.getBoolean("seven_day_show_overall", false)
        val labelRes = if (showOverall) R.string.ring_label_7d else R.string.ring_label_7d_opus
        val fetched = Instant.ofEpochMilli(prefs.getLong("fetched_at", 0L))
        val mock = prefs.getBoolean("mock", false)
        return WidgetState.Loaded(
            fiveHourPct = pct5,
            fiveHourResetsAt = resets5,
            sevenDayPct = pct7,
            sevenDayResetsAt = resets7,
            sevenDayLabel = context.getString(labelRes),
            fetchedAt = fetched,
            mock = mock,
        )
    }

    companion object {
        private const val STATUS_OK = "ok"
        private const val STATUS_AUTH = "auth"
        private const val STATUS_NETWORK = "network"
        private const val STATUS_UNCONFIGURED = "unconfigured"
    }
}
