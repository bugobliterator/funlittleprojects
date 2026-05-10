package com.sidbh.claudeusage.widget

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.sidbh.claudeusage.auth.CredentialsStore
import com.sidbh.claudeusage.data.ClaudeAiUsageRepository
import com.sidbh.claudeusage.data.MockUsageRepository
import com.sidbh.claudeusage.data.UsageRepository
import com.sidbh.claudeusage.data.UsageResult
import java.util.concurrent.TimeUnit

class WidgetUpdateWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val ctx = applicationContext
        val credentials = CredentialsStore(ctx)
        if (!credentials.isConfigured()) {
            WidgetStateStore(ctx).save(UsageResult.NotConfigured, mock = false)
            ClaudeUsageWidgetProvider.refresh(ctx)
            return Result.success()
        }

        val mock = credentials.useMock
        val repo: UsageRepository =
            if (mock) MockUsageRepository() else ClaudeAiUsageRepository(credentials)

        val result = repo.fetch()
        WidgetStateStore(ctx).save(result, mock)
        ClaudeUsageWidgetProvider.refresh(ctx)

        return when (result) {
            is UsageResult.NetworkError -> Result.retry()
            else -> Result.success()
        }
    }

    companion object {
        private const val PERIODIC_TAG = "claude_usage_periodic"
        private const val ONE_SHOT_TAG = "claude_usage_oneshot"
        private const val UNIQUE_PERIODIC = "claude_usage_periodic_unique"

        fun ensurePeriodic(ctx: Context) {
            val request = PeriodicWorkRequestBuilder<WidgetUpdateWorker>(
                15, TimeUnit.MINUTES,
                5, TimeUnit.MINUTES,
            )
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build(),
                )
                .addTag(PERIODIC_TAG)
                .build()
            WorkManager.getInstance(ctx)
                .enqueueUniquePeriodicWork(
                    UNIQUE_PERIODIC,
                    ExistingPeriodicWorkPolicy.KEEP,
                    request,
                )
        }

        fun runOnce(ctx: Context) {
            val request = OneTimeWorkRequestBuilder<WidgetUpdateWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build(),
                )
                .addTag(ONE_SHOT_TAG)
                .build()
            WorkManager.getInstance(ctx).enqueue(request)
        }

        fun cancelAll(ctx: Context) {
            val wm = WorkManager.getInstance(ctx)
            wm.cancelAllWorkByTag(PERIODIC_TAG)
            wm.cancelAllWorkByTag(ONE_SHOT_TAG)
            wm.cancelUniqueWork(UNIQUE_PERIODIC)
        }
    }
}
