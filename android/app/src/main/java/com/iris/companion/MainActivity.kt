package com.iris.companion

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.webkit.CookieManager
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private val prefs by lazy { getSharedPreferences("iris", Context.MODE_PRIVATE) }

    private val scanLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            val pairUrl = result.data?.getStringExtra("pair_url") ?: return@registerForActivityResult
            val baseUrl = result.data?.getStringExtra("base_url") ?: return@registerForActivityResult
            prefs.edit().putString("server_url", baseUrl).apply()
            webView.loadUrl(pairUrl)
        } else {
            if (prefs.getString("server_url", null) == null) finish()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        window.statusBarColor = Color.parseColor("#48B2E9")

        webView = findViewById(R.id.webView)
        setupWebView()

        val serverUrl = prefs.getString("server_url", null)
        if (serverUrl == null) {
            autoDiscoverOrScan()
        } else {
            webView.loadUrl(serverUrl)
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) {
            hideSystemUI()
        }
    }

    private fun hideSystemUI() {
        window.statusBarColor = Color.parseColor("#48B2E9")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(false)
            window.insetsController?.let { controller ->
                controller.show(WindowInsets.Type.statusBars())
                controller.hide(WindowInsets.Type.navigationBars())
                controller.systemBarsBehavior =
                    WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = (
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            )
        }
    }

    private fun setupWebView() {
        webView.setBackgroundColor(Color.parseColor("#0C0D0F"))

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        }

        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }

        webView.webViewClient = object : WebViewClient() {
            override fun onReceivedHttpError(
                view: WebView,
                request: WebResourceRequest,
                errorResponse: WebResourceResponse
            ) {
                if (request.isForMainFrame && errorResponse.statusCode == 401) {
                    prefs.edit().remove("server_url").apply()
                    CookieManager.getInstance().removeAllCookies(null)
                    Toast.makeText(
                        this@MainActivity,
                        "Session expired — please scan QR code",
                        Toast.LENGTH_SHORT
                    ).show()
                    launchScanner()
                }
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError
            ) {
                if (request.isForMainFrame) {
                    autoDiscoverOrScan()
                }
            }
        }
    }

    private fun autoDiscoverOrScan() {
        Thread {
            val discoveredUrl = DiscoveryManager.discoverServer(this, timeoutMs = 2000)
            runOnUiThread {
                if (discoveredUrl != null) {
                    val currentSaved = prefs.getString("server_url", null)
                    prefs.edit().putString("server_url", discoveredUrl).apply()
                    if (currentSaved == null) {
                        webView.loadUrl("$discoveredUrl/index.html")
                    } else {
                        webView.loadUrl(discoveredUrl)
                    }
                } else {
                    launchScanner()
                }
            }
        }.start()
    }

    private fun launchScanner() {
        scanLauncher.launch(Intent(this, ScanActivity::class.java))
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(Menu.NONE, MENU_RESCAN, Menu.NONE, "Re-scan QR")
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == MENU_RESCAN) {
            prefs.edit().remove("server_url").apply()
            CookieManager.getInstance().removeAllCookies(null)
            launchScanner()
            return true
        }
        return super.onOptionsItemSelected(item)
    }

    @Suppress("OVERRIDE_DEPRECATION")
    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack()
        else super.onBackPressed()
    }

    companion object {
        private const val MENU_RESCAN = 1
    }
}
