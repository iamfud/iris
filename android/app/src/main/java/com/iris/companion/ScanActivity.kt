package com.iris.companion

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanIntentResult
import com.journeyapps.barcodescanner.ScanOptions

class ScanActivity : AppCompatActivity() {

    private val scanLauncher = registerForActivityResult(ScanContract()) { result: ScanIntentResult ->
        val raw = result.contents
        if (raw == null) {
            // User pressed back to cancel
            setResult(Activity.RESULT_CANCELED)
            finish()
            return@registerForActivityResult
        }

        // Basic validation
        if (!raw.startsWith("http://") && !raw.startsWith("https://")) {
            Toast.makeText(this, "Not a valid Iris QR code", Toast.LENGTH_SHORT).show()
            launchScan()   // let them try again
            return@registerForActivityResult
        }

        val uri = try {
            Uri.parse(raw)
        } catch (e: Exception) {
            Toast.makeText(this, "Invalid QR code", Toast.LENGTH_SHORT).show()
            launchScan()
            return@registerForActivityResult
        }

        // Build base URL from the scanned pair URL (strip /pair?token=...)
        val port = if (uri.port != -1) ":${uri.port}" else ""
        val baseUrl = "${uri.scheme}://${uri.host}$port"

        setResult(Activity.RESULT_OK, Intent().apply {
            putExtra("pair_url", raw)
            putExtra("base_url", baseUrl)
        })
        finish()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        launchScan()
    }

    private fun launchScan() {
        scanLauncher.launch(
            ScanOptions().apply {
                setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                setPrompt("Scan the Iris pairing QR code")
                setBeepEnabled(false)
                setOrientationLocked(false)
            }
        )
    }
}
