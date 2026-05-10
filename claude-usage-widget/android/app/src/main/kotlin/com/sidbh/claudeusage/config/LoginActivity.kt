package com.sidbh.claudeusage.config

import android.annotation.SuppressLint
import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.util.Log
import android.view.View
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.appbar.MaterialToolbar
import com.sidbh.claudeusage.R
import com.sidbh.claudeusage.auth.CredentialsStore
import com.sidbh.claudeusage.widget.WidgetUpdateWorker
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class LoginActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var progress: View
    private val credentials by lazy { CredentialsStore(this) }
    private var captured = false
    private var pollJob: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)
        setResult(RESULT_CANCELED)

        findViewById<MaterialToolbar>(R.id.toolbar).apply {
            setNavigationOnClickListener {
                setResult(RESULT_CANCELED)
                finish()
            }
            inflateMenu(R.menu.login_menu)
            setOnMenuItemClickListener { item ->
                when (item.itemId) {
                    R.id.action_done -> {
                        if (!tryCaptureNow()) {
                            Toast.makeText(this@LoginActivity, R.string.login_not_ready, Toast.LENGTH_SHORT).show()
                        }
                        true
                    }
                    R.id.action_paste_url -> {
                        loadUrlFromClipboard()
                        true
                    }
                    else -> false
                }
            }
        }

        progress = findViewById(R.id.progress)
        webView = findViewById(R.id.webview)
        configureWebView()
        webView.loadUrl(LOGIN_URL)

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else finish()
            }
        })

        startCookiePolling()
    }

    private fun startCookiePolling() {
        pollJob?.cancel()
        pollJob = lifecycleScope.launch {
            while (isActive && !captured) {
                delay(2000)
                tryCaptureNow()
            }
        }
    }

    override fun onDestroy() {
        pollJob?.cancel()
        super.onDestroy()
    }

    private fun loadUrlFromClipboard() {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val raw = cm.primaryClip?.getItemAt(0)?.text?.toString()?.trim()
        if (raw.isNullOrBlank() || !raw.startsWith("http")) {
            Toast.makeText(this, R.string.login_no_clipboard_url, Toast.LENGTH_SHORT).show()
            return
        }
        Log.d("WIDGET-DBG", "loading clipboard url=$raw")
        webView.loadUrl(raw)
    }

    private fun tryCaptureNow(): Boolean {
        if (captured) return true
        val url = webView.url
        val cookieJar = CookieManager.getInstance().getCookie("https://claude.ai")
        val cookieJarRoot = CookieManager.getInstance().getCookie("https://www.claude.ai")
        val anthropicJar = CookieManager.getInstance().getCookie("https://anthropic.com")
        Log.d("WIDGET-DBG", "tryCaptureNow url=$url")
        Log.d("WIDGET-DBG", "claude.ai cookies=${cookieJar?.take(400)}")
        Log.d("WIDGET-DBG", "www.claude.ai cookies=${cookieJarRoot?.take(400)}")
        Log.d("WIDGET-DBG", "anthropic.com cookies=${anthropicJar?.take(400)}")

        if (cookieJar.isNullOrBlank()) return false
        val sessionKey = parseCookie(cookieJar, "sessionKey")
        val orgId = parseCookie(cookieJar, "lastActiveOrg")
        Log.d("WIDGET-DBG", "sessionKey present=${!sessionKey.isNullOrBlank()} orgId present=${!orgId.isNullOrBlank()}")
        if (sessionKey.isNullOrBlank() || orgId.isNullOrBlank()) return false

        captured = true
        credentials.sessionKey = sessionKey
        credentials.orgId = orgId
        credentials.userAgent = webView.settings.userAgentString
        credentials.useMock = false

        WidgetUpdateWorker.runOnce(applicationContext)
        setResult(RESULT_OK)
        finish()
        return true
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            userAgentString = MOBILE_UA
            mediaPlaybackRequiresUserGesture = false
        }
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }
        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                super.onPageStarted(view, url, favicon)
                progress.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                progress.visibility = View.GONE
                tryCapture(url)
            }

            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val url = request?.url?.toString() ?: return false
                return url.startsWith("intent://") || url.startsWith("mailto:")
            }
        }
    }

    override fun onStop() {
        super.onStop()
        tryCapture(webView.url)
    }

    private fun tryCapture(url: String?) {
        if (captured) return
        if (url == null || !url.startsWith("https://claude.ai")) return
        if (url.contains("/login")) return
        tryCaptureNow()
    }

    private fun parseCookie(cookies: String, name: String): String? =
        cookies.split(";")
            .map { it.trim() }
            .firstOrNull { it.startsWith("$name=") }
            ?.substringAfter("=")

    companion object {
        private const val LOGIN_URL = "https://claude.ai/login"
        // Matches a current Chrome on Android UA so claude.ai serves the mobile web app.
        private const val MOBILE_UA =
            "Mozilla/5.0 (Linux; Android 14; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    }
}
