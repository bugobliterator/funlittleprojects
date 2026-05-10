package com.sidbh.claudeusage.data

import java.time.Instant

interface UsageRepository {
    suspend fun fetch(): UsageResult
}

sealed class UsageResult {
    data class Success(val data: UsageEnvelope, val fetchedAt: Instant) : UsageResult()
    data class AuthError(val code: Int) : UsageResult()
    data class NetworkError(val message: String) : UsageResult()
    data object NotConfigured : UsageResult()
}
