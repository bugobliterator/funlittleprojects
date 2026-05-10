package com.sidbh.claudeusage.data

import kotlinx.coroutines.delay
import java.time.Instant
import java.time.temporal.ChronoUnit

class MockUsageRepository : UsageRepository {
    override suspend fun fetch(): UsageResult {
        delay(120)
        val now = Instant.now()
        return UsageResult.Success(
            data = UsageEnvelope(
                fiveHour = UsageBucket(
                    utilization = 24.0,
                    resetsAt = now.plus(3, ChronoUnit.HOURS).plus(38, ChronoUnit.MINUTES).toString(),
                ),
                sevenDay = UsageBucket(
                    utilization = 45.0,
                    resetsAt = now.plus(2, ChronoUnit.DAYS).toString(),
                ),
                sevenDayOpus = UsageBucket(
                    utilization = 38.0,
                    resetsAt = now.plus(2, ChronoUnit.DAYS).toString(),
                ),
            ),
            fetchedAt = now,
        )
    }
}
