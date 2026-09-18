package com.domainexpanders.callingagent

import android.app.Activity
import android.app.role.RoleManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.telecom.TelecomManager
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {

    private val REQUEST_CODE_SET_DEFAULT_DIALER = 1001

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Programmatic UI layout for zero external dependencies
        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(48, 48, 48, 48)
            setBackgroundColor(android.graphics.Color.parseColor("#0f172a"))
        }

        val titleView = TextView(this).apply {
            text = "Domain Expanders AI Bridge"
            textSize = 22f
            setTextColor(android.graphics.Color.WHITE)
            setTypeface(null, android.graphics.Typeface.BOLD)
            setPadding(0, 0, 0, 32)
        }
        layout.addView(titleView)

        val statusView = TextView(this).apply {
            text = "Status: Checking default dialer permissions..."
            textSize = 14f
            setTextColor(android.graphics.Color.parseColor("#94a3b8"))
            setPadding(0, 0, 0, 48)
        }
        layout.addView(statusView)

        val urlLabel = TextView(this).apply {
            text = "Cloud WebSocket Endpoint (wss://.../ws/call):"
            textSize = 14f
            setTextColor(android.graphics.Color.parseColor("#cbd5e1"))
            setPadding(0, 0, 0, 16)
        }
        layout.addView(urlLabel)

        val prefs = getSharedPreferences("DE_CALLING_AGENT", Context.MODE_PRIVATE)
        val defaultUrl = prefs.getString("SERVER_WS_URL", "wss://your-space.hf.space/ws/call")

        val urlInput = EditText(this).apply {
            setText(defaultUrl)
            setTextColor(android.graphics.Color.WHITE)
            setBackgroundColor(android.graphics.Color.parseColor("#1e293b"))
            setPadding(24, 24, 24, 24)
        }
        layout.addView(urlInput)

        val saveBtn = Button(this).apply {
            text = "Save Endpoint URL"
            setBackgroundColor(android.graphics.Color.parseColor("#2563eb"))
            setTextColor(android.graphics.Color.WHITE)
            setOnClickListener {
                val url = urlInput.text.toString().trim()
                prefs.edit().putString("SERVER_WS_URL", url).apply()
                Toast.makeText(this@MainActivity, "Server URL Saved!", Toast.LENGTH_SHORT).show()
            }
        }
        layout.addView(saveBtn)

        val setDialerBtn = Button(this).apply {
            text = "Set as Default Phone App (Required)"
            setBackgroundColor(android.graphics.Color.parseColor("#10b981"))
            setTextColor(android.graphics.Color.WHITE)
            setOnClickListener {
                requestDefaultDialerRole()
            }
        }
        layout.addView(setDialerBtn)

        setContentView(layout)
        checkDialerStatus(statusView)
    }

    private fun checkDialerStatus(statusView: TextView) {
        val telecomManager = getSystemService(Context.TELECOM_SERVICE) as TelecomManager
        val isDefault = telecomManager.defaultDialerPackage == packageName
        if (isDefault) {
            statusView.text = "Status: ACTIVE (Default Phone Dialer)\nReady to auto-bridge SIM calls to AI S2S"
            statusView.setTextColor(android.graphics.Color.parseColor("#10b981"))
        } else {
            statusView.text = "Status: NOT DEFAULT DIALER\nClick the button below to enable call interception."
            statusView.setTextColor(android.graphics.Color.parseColor("#f59e0b"))
        }
    }

    private fun requestDefaultDialerRole() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roleManager = getSystemService(RoleManager::class.java)
            if (roleManager.isRoleAvailable(RoleManager.ROLE_DIALER)) {
                val intent = roleManager.createRequestRoleIntent(RoleManager.ROLE_DIALER)
                startActivityForResult(intent, REQUEST_CODE_SET_DEFAULT_DIALER)
            }
        } else {
            val intent = Intent(TelecomManager.ACTION_CHANGE_DEFAULT_DIALER).apply {
                putExtra(TelecomManager.EXTRA_CHANGE_DEFAULT_DIALER_PACKAGE_NAME, packageName)
            }
            startActivityForResult(intent, REQUEST_CODE_SET_DEFAULT_DIALER)
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_CODE_SET_DEFAULT_DIALER) {
            val isSuccess = resultCode == Activity.RESULT_OK
            Toast.makeText(this, if (isSuccess) "Default Dialer Enabled!" else "Permission Denied", Toast.LENGTH_SHORT).show()
            recreate()
        }
    }
}
