package com.sidbh.claudeusage.data

import com.sidbh.claudeusage.auth.CredentialsStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import java.time.Instant
import java.util.concurrent.TimeUnit

class ClaudeAiUsageRepository(
    private val credentials: CredentialsStore,
    private val client: OkHttpClient = defaultClient,
    private val json: Json = defaultJson,
) : UsageRepository {

    override suspend fun fetch(): UsageResult = withContext(Dispatchers.IO) {
        val sessionKey = credentials.sessionKey
        val orgId = credentials.orgId
        if (sessionKey.isNullOrBlank() || orgId.isNullOrBlank()) {
            return@withContext UsageResult.NotConfigured
        }
        val ua = credentials.userAgent ?: FALLBACK_UA

        val req = Request.Builder()
            .url("https://claude.ai/api/organizations/$orgId/usage")
            .header("Cookie", "sessionKey=$sessionKey")
            .header("User-Agent", ua)
            .header("Accept", "*/*")
            .header("Accept-Language", "en-US,en;q=0.9")
            .header("anthropic-client-platform", "web_claude_ai")
            .header("anthropic-client-version", "1.0.0")
            .header("Referer", "https://claude.ai/settings/usage")
            .get()
            .build()

        try {
            client.newCall(req).execute().use { resp ->
                when {
                    resp.code == 401 || resp.code == 403 -> UsageResult.AuthError(resp.code)
                    !resp.isSuccessful -> UsageResult.NetworkError("HTTP ${resp.code}")
                    else -> {
                        val body = resp.body?.string()
                        if (body.isNullOrBlank()) {
                            UsageResult.NetworkError("empty body")
                        } else {
                            val envelope = json.decodeFromString<UsageEnvelope>(body)
                            UsageResult.Success(envelope, Instant.now())
                        }
                    }
                }
            }
        } catch (e: IOException) {
            UsageResult.NetworkError(e.message ?: "io error")
        } catch (e: SerializationException) {
            UsageResult.NetworkError("parse error: ${e.message}")
        }
    }

    companion object {
        private const val FALLBACK_UA =
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"

        val defaultJson: Json = Json {
            ignoreUnknownKeys = true
            isLenient = true
            explicitNulls = false
        }

        val defaultClient: OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .callTimeout(20, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }
}
