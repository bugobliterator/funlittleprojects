package com.sidbh.claudeusage.config

import android.app.Activity
import android.appwidget.AppWidgetManager
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.webkit.CookieManager
import android.widget.ImageView
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts.StartActivityForResult
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import com.sidbh.claudeusage.R
import com.sidbh.claudeusage.auth.CredentialsStore
import com.sidbh.claudeusage.data.UsageResult
import com.sidbh.claudeusage.widget.ClaudeUsageWidgetProvider
import com.sidbh.claudeusage.widget.WidgetRenderer
import com.sidbh.claudeusage.widget.WidgetState
import com.sidbh.claudeusage.widget.WidgetStateStore
import com.sidbh.claudeusage.widget.WidgetUpdateWorker
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class ConfigActivity : AppCompatActivity() {

    private var widgetId: Int = AppWidgetManager.INVALID_APPWIDGET_ID
    private val credentials by lazy { CredentialsStore(this) }

    private val loginLauncher = registerForActivityResult(StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            renderState()
            finishWithSuccessIfWidgetFlow()
        } else {
            renderState()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_config)
        setResult(Activity.RESULT_CANCELED)

        widgetId = intent?.extras?.getInt(
            AppWidgetManager.EXTRA_APPWIDGET_ID,
            AppWidgetManager.INVALID_APPWIDGET_ID,
        ) ?: AppWidgetManager.INVALID_APPWIDGET_ID

        findViewById<MaterialButton>(R.id.btn_login).setOnClickListener {
            loginLauncher.launch(Intent(this, LoginActivity::class.java))
        }
        findViewById<MaterialButton>(R.id.btn_logout).setOnClickListener {
            credentials.clearLogin()
            CookieManager.getInstance().removeAllCookies(null)
            CookieManager.getInstance().flush()
            WidgetStateStore(applicationContext).save(UsageResult.NotConfigured, mock = false)
            ClaudeUsageWidgetProvider.refresh(applicationContext)
            renderState()
        }
        findViewById<MaterialButton>(R.id.btn_use_mock).setOnClickListener {
            credentials.useMock = !credentials.useMock
            WidgetUpdateWorker.runOnce(applicationContext)
            renderState()
            pollPreview()
            finishWithSuccessIfWidgetFlow()
        }
        findViewById<MaterialButton>(R.id.btn_refresh_now).setOnClickListener {
            WidgetUpdateWorker.runOnce(applicationContext)
            renderState()
            pollPreview()
        }
        findViewById<MaterialButton>(R.id.btn_done).setOnClickListener {
            finishWithSuccessIfWidgetFlow()
        }

        renderState()
        renderPreview()
        // [WIDGET-DBG] If widget already had a Loaded state when activity opens, render it.
    }

    private fun renderPreview() {
        val configured = credentials.isConfigured()
        val state = WidgetStateStore(this).load(configured)
        val container = findViewById<View>(R.id.preview_container)
        val title = findViewById<View>(R.id.tv_preview_title)
        val image = findViewById<ImageView>(R.id.iv_preview)
        val text = findViewById<TextView>(R.id.tv_preview_state)

        when (state) {
            is WidgetState.Loaded -> {
                title.visibility = View.VISIBLE
                container.visibility = View.VISIBLE
                image.visibility = View.VISIBLE
                text.visibility = View.GONE
                val bitmap = WidgetRenderer.render(this, 272, 223, state)
                image.setImageBitmap(bitmap)
            }
            WidgetState.Loading -> showPreviewMsg(title, container, image, text, getString(R.string.widget_state_loading))
            WidgetState.AuthError -> showPreviewMsg(title, container, image, text, getString(R.string.widget_state_error_auth))
            is WidgetState.NetworkError -> showPreviewMsg(title, container, image, text, getString(R.string.widget_state_error_network))
            WidgetState.Unconfigured -> {
                title.visibility = View.GONE
                container.visibility = View.GONE
            }
        }
    }

    private fun showPreviewMsg(title: View, container: View, image: ImageView, text: TextView, msg: String) {
        title.visibility = View.VISIBLE
        container.visibility = View.VISIBLE
        image.visibility = View.GONE
        text.visibility = View.VISIBLE
        text.text = msg
    }

    private fun pollPreview() {
        lifecycleScope.launch {
            repeat(20) {
                delay(500)
                val state = WidgetStateStore(this@ConfigActivity).load(credentials.isConfigured())
                if (state is WidgetState.Loaded || state is WidgetState.AuthError || state is WidgetState.NetworkError) {
                    renderPreview()
                    return@launch
                }
            }
        }
    }

    private fun renderState() {
        val tvStatus = findViewById<TextView>(R.id.tv_account_status)
        val btnLogin = findViewById<MaterialButton>(R.id.btn_login)
        val btnLogout = findViewById<MaterialButton>(R.id.btn_logout)
        val btnMock = findViewById<MaterialButton>(R.id.btn_use_mock)
        val btnRefresh = findViewById<MaterialButton>(R.id.btn_refresh_now)
        val btnDone = findViewById<MaterialButton>(R.id.btn_done)

        val loggedIn = credentials.isLoggedIn()
        val mock = credentials.useMock

        tvStatus.text = when {
            loggedIn && mock -> getString(R.string.status_logged_in_mock_active)
            loggedIn -> getString(R.string.status_logged_in)
            mock -> getString(R.string.status_using_mock)
            else -> getString(R.string.status_not_logged_in)
        }

        btnLogin.visibility = if (loggedIn) View.GONE else View.VISIBLE
        btnLogout.visibility = if (loggedIn) View.VISIBLE else View.GONE
        btnRefresh.visibility = if (loggedIn || mock) View.VISIBLE else View.GONE

        btnMock.text = if (mock) getString(R.string.action_stop_mock) else getString(R.string.action_use_mock)

        val isWidgetFlow = widgetId != AppWidgetManager.INVALID_APPWIDGET_ID
        btnDone.visibility = if (isWidgetFlow && (loggedIn || mock)) View.VISIBLE else View.GONE
    }

    private fun finishWithSuccessIfWidgetFlow() {
        if (widgetId == AppWidgetManager.INVALID_APPWIDGET_ID) return
        if (!credentials.isLoggedIn() && !credentials.useMock) return
        ClaudeUsageWidgetProvider.refresh(applicationContext)
        val result = Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
        setResult(Activity.RESULT_OK, result)
        finish()
    }
}
