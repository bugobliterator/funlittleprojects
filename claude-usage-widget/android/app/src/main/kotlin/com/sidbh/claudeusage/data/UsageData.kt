package com.sidbh.claudeusage.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class UsageEnvelope(
    @SerialName("five_hour") val fiveHour: UsageBucket? = null,
    @SerialName("seven_day") val sevenDay: UsageBucket? = null,
    @SerialName("seven_day_opus") val sevenDayOpus: UsageBucket? = null,
    @SerialName("seven_day_sonnet") val sevenDaySonnet: UsageBucket? = null,
    @SerialName("extra_usage") val extraUsage: ExtraUsage? = null,
)

@Serializable
data class UsageBucket(
    val utilization: Double? = null,
    @SerialName("resets_at") val resetsAt: String? = null,
)

@Serializable
data class ExtraUsage(
    @SerialName("is_enabled") val isEnabled: Boolean = false,
    val utilization: Double? = null,
    @SerialName("monthly_limit") val monthlyLimit: Double? = null,
    @SerialName("used_credits") val usedCredits: Double? = null,
    val currency: String? = null,
)
