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
    private lateinit var statusView: TextView

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

        statusView = TextView(this).apply {
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
        val defaultUrl = prefs.getString("SERVER_WS_URL", "wss://call.domainexpanders.in/ws/call") ?: "wss://call.domainexpanders.in/ws/call"

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

        // 1. AI Master On/Off Toggle (Personal Mobile Protection)
        var isAiActive = prefs.getBoolean("AI_AUTO_ANSWER_ACTIVE", true)
        val toggleAiBtn = Button(this).apply {
            fun updateUi() {
                if (isAiActive) {
                    text = "🤖 AI Answering: ON (Auto-Handles Client Calls)"
                    setBackgroundColor(android.graphics.Color.parseColor("#10b981"))
                } else {
                    text = "👤 Personal Mode: ON (AI Won't Touch Calls - You Answer)"
                    setBackgroundColor(android.graphics.Color.parseColor("#f59e0b"))
                }
                setTextColor(android.graphics.Color.WHITE)
            }
            updateUi()
            setOnClickListener {
                isAiActive = !isAiActive
                prefs.edit().putBoolean("AI_AUTO_ANSWER_ACTIVE", isAiActive).apply()
                updateUi()
                val modeMsg = if (isAiActive) "AI Answering Activated!" else "Personal Mode Active! AI will not answer incoming calls."
                Toast.makeText(this@MainActivity, modeMsg, Toast.LENGTH_SHORT).show()
            }
        }
        layout.addView(toggleAiBtn)

        // 2. Set as Default Dialer Button
        val setDialerBtn = Button(this).apply {
            text = "Set as Default Phone App (For AI Mode)"
            setBackgroundColor(android.graphics.Color.parseColor("#3b82f6"))
            setTextColor(android.graphics.Color.WHITE)
            setOnClickListener {
                requestDefaultDialerRole()
            }
        }
        layout.addView(setDialerBtn)

        // 3. Switch Back to Normal Personal Dialer Button
        val restoreDialerBtn = Button(this).apply {
            text = "📱 Switch / Restore Normal Personal Dialer"
            setBackgroundColor(android.graphics.Color.parseColor("#64748b"))
            setTextColor(android.graphics.Color.WHITE)
            setOnClickListener {
                try {
                    val intent = Intent(android.provider.Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS)
                    startActivity(intent)
                } catch (e: Exception) {
                    val intent = Intent(android.provider.Settings.ACTION_SETTINGS)
                    startActivity(intent)
                }
            }
        }
        layout.addView(restoreDialerBtn)

        setContentView(layout)
        checkDialerStatus()
    }

    override fun onResume() {
        super.onResume()
        if (::statusView.isInitialized) {
            checkDialerStatus()
        }
    }

    private fun checkDialerStatus() {
        val telecomManager = getSystemService(Context.TELECOM_SERVICE) as TelecomManager
        val isDefault = telecomManager.defaultDialerPackage == packageName
        val isAiActive = getSharedPreferences("DE_CALLING_AGENT", Context.MODE_PRIVATE).getBoolean("AI_AUTO_ANSWER_ACTIVE", true)

        if (isDefault && isAiActive) {
            statusView.text = "Status: ACTIVE (AI Agent Auto-Answering Enabled)\nInbound calls are streamed to Gemini Live AI S2S."
            statusView.setTextColor(android.graphics.Color.parseColor("#10b981"))
        } else if (isDefault && !isAiActive) {
            statusView.text = "Status: PERSONAL MODE (AI Paused)\nDefault dialer is active, but AI auto-answer is OFF so you can answer calls manually."
            statusView.setTextColor(android.graphics.Color.parseColor("#f59e0b"))
        } else {
            statusView.text = "Status: NOT DEFAULT DIALER\nTap 'Set as Default Phone App' or select 'DE Calling Agent' in Default Apps."
            statusView.setTextColor(android.graphics.Color.parseColor("#94a3b8"))
        }
    }

    private fun requestDefaultDialerRole() {
        val telecomManager = getSystemService(Context.TELECOM_SERVICE) as TelecomManager
        if (telecomManager.defaultDialerPackage == packageName) {
            Toast.makeText(this, "Already set as Default Phone App!", Toast.LENGTH_SHORT).show()
            return
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roleManager = getSystemService(RoleManager::class.java)
            if (roleManager.isRoleAvailable(RoleManager.ROLE_DIALER)) {
                try {
                    val intent = roleManager.createRequestRoleIntent(RoleManager.ROLE_DIALER)
                    startActivityForResult(intent, REQUEST_CODE_SET_DEFAULT_DIALER)
                    return
                } catch (e: Exception) {
                    // Fallback to default apps settings
                }
            }
        }

        openDefaultAppsSettings()
    }

    private fun openDefaultAppsSettings() {
        try {
            val intent = Intent(android.provider.Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS)
            startActivity(intent)
            Toast.makeText(this, "Select 'Phone app' -> 'DE Calling Agent Bridge'", Toast.LENGTH_LONG).show()
        } catch (e: Exception) {
            try {
                val intent = Intent(TelecomManager.ACTION_CHANGE_DEFAULT_DIALER).apply {
                    putExtra(TelecomManager.EXTRA_CHANGE_DEFAULT_DIALER_PACKAGE_NAME, packageName)
                }
                startActivityForResult(intent, REQUEST_CODE_SET_DEFAULT_DIALER)
            } catch (ex: Exception) {
                val intent = Intent(android.provider.Settings.ACTION_SETTINGS)
                startActivity(intent)
            }
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_CODE_SET_DEFAULT_DIALER) {
            val isSuccess = resultCode == Activity.RESULT_OK
            if (isSuccess) {
                Toast.makeText(this, "Default Dialer Enabled!", Toast.LENGTH_SHORT).show()
                checkDialerStatus()
            } else {
                // If system dialog was cancelled, guide user to system Default Apps page directly
                openDefaultAppsSettings()
            }
        }
    }
}
