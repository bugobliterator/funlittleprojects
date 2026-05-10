package com.sidbh.claudeusage.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.RemoteViews
import com.sidbh.claudeusage.R
import com.sidbh.claudeusage.auth.CredentialsStore
import com.sidbh.claudeusage.config.ConfigActivity
import com.sidbh.claudeusage.config.LoginActivity

class ClaudeUsageWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        val state = readState(context)
        for (id in appWidgetIds) {
            renderWidget(context, appWidgetManager, id, state)
        }
        WidgetUpdateWorker.ensurePeriodic(context)
        if (state is WidgetState.Loading || state == WidgetState.Unconfigured) {
            // initial fetch on first add
            if (CredentialsStore(context).isConfigured()) {
                WidgetUpdateWorker.runOnce(context)
            }
        }
    }

    override fun onAppWidgetOptionsChanged(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetId: Int,
        newOptions: Bundle?,
    ) {
        super.onAppWidgetOptionsChanged(context, appWidgetManager, appWidgetId, newOptions)
        val state = readState(context)
        renderWidget(context, appWidgetManager, appWidgetId, state)
    }

    override fun onEnabled(context: Context) {
        super.onEnabled(context)
        WidgetUpdateWorker.ensurePeriodic(context)
        if (CredentialsStore(context).isConfigured()) {
            WidgetUpdateWorker.runOnce(context)
        }
    }

    override fun onDisabled(context: Context) {
        super.onDisabled(context)
        WidgetUpdateWorker.cancelAll(context)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        when (intent.action) {
            ACTION_REFRESH -> {
                if (CredentialsStore(context).isConfigured()) {
                    WidgetUpdateWorker.runOnce(context)
                } else {
                    refresh(context)
                }
            }
            Intent.ACTION_USER_PRESENT -> {
                if (CredentialsStore(context).isConfigured()) {
                    WidgetUpdateWorker.runOnce(context)
                }
            }
        }
    }

    companion object {
        const val ACTION_REFRESH = "com.sidbh.claudeusage.ACTION_REFRESH"

        fun refresh(context: Context) {
            val mgr = AppWidgetManager.getInstance(context)
            val ids = mgr.getAppWidgetIds(
                ComponentName(context, ClaudeUsageWidgetProvider::class.java)
            )
            val state = readState(context)
            for (id in ids) renderWidget(context, mgr, id, state)
        }

        private fun readState(context: Context): WidgetState {
            val configured = CredentialsStore(context).isConfigured()
            return WidgetStateStore(context).load(configured)
        }

        private fun renderWidget(
            context: Context,
            manager: AppWidgetManager,
            widgetId: Int,
            state: WidgetState,
        ) {
            val views = RemoteViews(context.packageName, R.layout.widget_claude_usage)

            when (state) {
                WidgetState.Unconfigured -> showText(views, context.getString(R.string.widget_state_unconfigured))
                WidgetState.AuthError -> showText(views, context.getString(R.string.widget_state_error_auth))
                WidgetState.Loading -> showText(views, context.getString(R.string.widget_state_loading))
                is WidgetState.NetworkError -> showText(views, context.getString(R.string.widget_state_error_network))
                is WidgetState.Loaded -> {
                    val opts = manager.getAppWidgetOptions(widgetId)
                    val minW = opts.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH, 0)
                    val minH = opts.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT, 0)
                    val maxW = opts.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_WIDTH, 0)
                    val maxH = opts.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT, 0)
                    Log.d("WIDGET-DBG", "options id=$widgetId minW=$minW minH=$minH maxW=$maxW maxH=$maxH")
                    // Portrait actual ≈ MIN_WIDTH × MAX_HEIGHT; pick the most representative of the visible cell.
                    val widthDp = (if (minW > 0) minW else 250)
                    val heightDp = (if (maxH > 0) maxH else 110)
                    Log.d("WIDGET-DBG", "rendering at ${widthDp}x${heightDp}dp")
                    val bitmap = WidgetRenderer.render(context, widthDp, heightDp, state)
                    views.setImageViewBitmap(R.id.widget_image, bitmap)
                    views.setViewVisibility(R.id.widget_image, View.VISIBLE)
                    views.setViewVisibility(R.id.widget_state_text, View.GONE)
                }
            }

            views.setOnClickPendingIntent(R.id.widget_root, tapPendingIntent(context, widgetId, state))
            manager.updateAppWidget(widgetId, views)
        }

        private fun showText(views: RemoteViews, text: String) {
            views.setViewVisibility(R.id.widget_image, View.GONE)
            views.setViewVisibility(R.id.widget_state_text, View.VISIBLE)
            views.setTextViewText(R.id.widget_state_text, text)
        }

        private fun tapPendingIntent(
            context: Context,
            widgetId: Int,
            state: WidgetState,
        ): PendingIntent {
            return when (state) {
                WidgetState.Unconfigured -> {
                    val intent = Intent(context, ConfigActivity::class.java)
                        .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    PendingIntent.getActivity(
                        context, widgetId, intent,
                        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                    )
                }
                WidgetState.AuthError -> {
                    val intent = Intent(context, LoginActivity::class.java)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    PendingIntent.getActivity(
                        context, widgetId, intent,
                        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                    )
                }
                else -> {
                    val intent = Intent(context, ClaudeUsageWidgetProvider::class.java)
                        .setAction(ACTION_REFRESH)
                    PendingIntent.getBroadcast(
                        context, widgetId, intent,
                        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                    )
                }
            }
        }
    }
}
