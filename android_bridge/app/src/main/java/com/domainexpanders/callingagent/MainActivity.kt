package com.domainexpanders.callingagent

import android.app.Activity
import android.app.role.RoleManager
import android.content.Context
import android.content.Intent
import android.media.MediaPlayer
import android.os.Build
import android.os.Bundle
import android.telecom.TelecomManager
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import java.io.File

class MainActivity : Activity() {

    private val REQUEST_CODE_SET_DEFAULT_DIALER = 1001
    private lateinit var statusView: TextView
    private lateinit var recordingView: TextView
    private var mediaPlayer: MediaPlayer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Programmatic UI layout for zero external dependencies
        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(40, 40, 40, 40)
            setBackgroundColor(android.graphics.Color.parseColor("#0f172a"))
        }

        val titleView = TextView(this).apply {
            text = "Domain Expanders AI Bridge"
            textSize = 22f
            setTextColor(android.graphics.Color.WHITE)
            setTypeface(null, android.graphics.Typeface.BOLD)
            setPadding(0, 0, 0, 16)
        }
        layout.addView(titleView)

        statusView = TextView(this).apply {
            text = "Status: Checking telephony state..."
            textSize = 13f
            setTextColor(android.graphics.Color.parseColor("#94a3b8"))
            setPadding(0, 0, 0, 24)
        }
        layout.addView(statusView)

        val prefs = getSharedPreferences("DE_CALLING_AGENT", Context.MODE_PRIVATE)

        // 1. Master AI Answering Toggle
        var isAiActive = prefs.getBoolean("AI_AUTO_ANSWER_ACTIVE", true)
        val toggleAiBtn = Button(this).apply {
            fun updateUi() {
                if (isAiActive) {
                    text = "🤖 AI Answering: ON (Auto-Handles Calls)"
                    setBackgroundColor(android.graphics.Color.parseColor("#10b981"))
                } else {
                    text = "👤 Personal Mode: ON (AI Off - You Answer)"
                    setBackgroundColor(android.graphics.Color.parseColor("#f59e0b"))
                }
                setTextColor(android.graphics.Color.WHITE)
            }
            updateUi()
            setOnClickListener {
                isAiActive = !isAiActive
                prefs.edit().putBoolean("AI_AUTO_ANSWER_ACTIVE", isAiActive).apply()
                updateUi()
                checkDialerStatus()
                val modeMsg = if (isAiActive) "AI Answering Activated!" else "Personal Mode Active! AI paused."
                Toast.makeText(this@MainActivity, modeMsg, Toast.LENGTH_SHORT).show()
            }
        }
        layout.addView(toggleAiBtn)

        // 2. Speakerphone Toggle for Loud & Clear Testing
        var useSpeaker = prefs.getBoolean("USE_SPEAKERPHONE", true)
        val speakerBtn = Button(this).apply {
            fun updateUi() {
                text = if (useSpeaker) "🔊 Audio: Speakerphone ON (Loud & Clear)" else "🔈 Audio: Earpiece Mode (Quiet)"
                setBackgroundColor(if (useSpeaker) android.graphics.Color.parseColor("#2563eb") else android.graphics.Color.parseColor("#475569"))
                setTextColor(android.graphics.Color.WHITE)
            }
            updateUi()
            setOnClickListener {
                useSpeaker = !useSpeaker
                prefs.edit().putBoolean("USE_SPEAKERPHONE", useSpeaker).apply()
                updateUi()
                Toast.makeText(this@MainActivity, if (useSpeaker) "Speakerphone ON for calls" else "Earpiece mode ON", Toast.LENGTH_SHORT).show()
            }
        }
        layout.addView(speakerBtn)

        // 3. Dual SIM Routing Selector
        var companySimSlot = prefs.getInt("COMPANY_SIM_SLOT", -1) // -1 = All, 0 = SIM 1, 1 = SIM 2
        val simSelectBtn = Button(this).apply {
            fun updateUi() {
                text = when (companySimSlot) {
                    0 -> "🏢 Company SIM: SIM 1 (SIM 2 Personal Protected)"
                    1 -> "🏢 Company SIM: SIM 2 (SIM 1 Personal Protected)"
                    else -> "🌐 Company SIM: ANY SIM (Single / Both Active)"
                }
                setBackgroundColor(if (companySimSlot == -1) android.graphics.Color.parseColor("#334155") else android.graphics.Color.parseColor("#0ea5e9"))
                setTextColor(android.graphics.Color.WHITE)
            }
            updateUi()
            setOnClickListener {
                companySimSlot = when (companySimSlot) {
                    -1 -> 0
                    0 -> 1
                    else -> -1
                }
                prefs.edit().putInt("COMPANY_SIM_SLOT", companySimSlot).apply()
                updateUi()
                checkDialerStatus()
            }
        }
        layout.addView(simSelectBtn)

        // 4. Default Dialer Setting Buttons
        val setDialerBtn = Button(this).apply {
            text = "Set as Default Phone App (For AI Mode)"
            setBackgroundColor(android.graphics.Color.parseColor("#1e40af"))
            setTextColor(android.graphics.Color.WHITE)
            setOnClickListener {
                requestDefaultDialerRole()
            }
        }
        layout.addView(setDialerBtn)

        val restoreDialerBtn = Button(this).apply {
            text = "📱 Switch / Restore Normal Personal Dialer"
            setBackgroundColor(android.graphics.Color.parseColor("#64748b"))
            setTextColor(android.graphics.Color.WHITE)
            setOnClickListener {
                openDefaultAppsSettings()
            }
        }
        layout.addView(restoreDialerBtn)

        // 5. Call Recording & Playback Section
        val recordingTitle = TextView(this).apply {
            text = "🎙️ On-Device Call Recordings:"
            textSize = 15f
            setTextColor(android.graphics.Color.parseColor("#cbd5e1"))
            setTypeface(null, android.graphics.Typeface.BOLD)
            setPadding(0, 24, 0, 8)
        }
        layout.addView(recordingTitle)

        recordingView = TextView(this).apply {
            text = "No call recorded yet."
            textSize = 12f
            setTextColor(android.graphics.Color.parseColor("#94a3b8"))
            setPadding(0, 0, 0, 16)
        }
        layout.addView(recordingView)

        val playBtn = Button(this).apply {
            text = "▶ Play Last Call Recording"
            setBackgroundColor(android.graphics.Color.parseColor("#059669"))
            setTextColor(android.graphics.Color.WHITE)
            setOnClickListener {
                playLastRecording()
            }
        }
        layout.addView(playBtn)

        val stopPlayBtn = Button(this).apply {
            text = "⏹ Stop Playback"
            setBackgroundColor(android.graphics.Color.parseColor("#dc2626"))
            setTextColor(android.graphics.Color.WHITE)
            setOnClickListener {
                stopPlaying()
            }
        }
        layout.addView(stopPlayBtn)

        setContentView(layout)
        checkDialerStatus()
        updateRecordingStatus()
    }

    override fun onResume() {
        super.onResume()
        if (::statusView.isInitialized) {
            checkDialerStatus()
        }
        if (::recordingView.isInitialized) {
            updateRecordingStatus()
        }
    }

    private fun checkDialerStatus() {
        val telecomManager = getSystemService(Context.TELECOM_SERVICE) as TelecomManager
        val isDefault = telecomManager.defaultDialerPackage == packageName
        val isAiActive = getSharedPreferences("DE_CALLING_AGENT", Context.MODE_PRIVATE).getBoolean("AI_AUTO_ANSWER_ACTIVE", true)
        val companySimSlot = getSharedPreferences("DE_CALLING_AGENT", Context.MODE_PRIVATE).getInt("COMPANY_SIM_SLOT", -1)
        val simTargetText = when (companySimSlot) {
            0 -> "\nTarget: SIM 1 ONLY (Personal SIM 2 Protected)"
            1 -> "\nTarget: SIM 2 ONLY (Personal SIM 1 Protected)"
            else -> "\nTarget: All / Any SIM"
        }

        if (isDefault && isAiActive) {
            statusView.text = "Status: ACTIVE (AI Agent Auto-Answering Enabled)$simTargetText\nInbound calls are streamed to Gemini Live AI S2S."
            statusView.setTextColor(android.graphics.Color.parseColor("#10b981"))
        } else if (isDefault && !isAiActive) {
            statusView.text = "Status: PERSONAL MODE (AI Paused)$simTargetText\nDefault dialer is active, but AI auto-answer is OFF so you can answer calls manually."
            statusView.setTextColor(android.graphics.Color.parseColor("#f59e0b"))
        } else {
            statusView.text = "Status: NOT DEFAULT DIALER$simTargetText\nTap 'Set as Default Phone App' or select 'DE Calling Agent' in Default Apps."
            statusView.setTextColor(android.graphics.Color.parseColor("#94a3b8"))
        }
    }

    private fun updateRecordingStatus() {
        val prefs = getSharedPreferences("DE_CALLING_AGENT", Context.MODE_PRIVATE)
        val lastPath = prefs.getString("LAST_RECORDING_PATH", null)
        val lastName = prefs.getString("LAST_RECORDING_NAME", null)

        if (lastPath != null && File(lastPath).exists()) {
            val file = File(lastPath)
            val sizeKb = file.length() / 1024
            recordingView.text = "Latest: $lastName ($sizeKb KB)\nPath: $lastPath"
            recordingView.setTextColor(android.graphics.Color.parseColor("#10b981"))
        } else {
            recordingView.text = "No call recording found yet. Calls will be recorded automatically."
            recordingView.setTextColor(android.graphics.Color.parseColor("#94a3b8"))
        }
    }

    private fun playLastRecording() {
        val prefs = getSharedPreferences("DE_CALLING_AGENT", Context.MODE_PRIVATE)
        val lastPath = prefs.getString("LAST_RECORDING_PATH", null)

        if (lastPath == null || !File(lastPath).exists()) {
            Toast.makeText(this, "No recording file available to play!", Toast.LENGTH_SHORT).show()
            return
        }

        try {
            stopPlaying()
            mediaPlayer = MediaPlayer().apply {
                setDataSource(lastPath)
                prepare()
                start()
                setOnCompletionListener {
                    Toast.makeText(this@MainActivity, "Recording playback finished!", Toast.LENGTH_SHORT).show()
                }
            }
            Toast.makeText(this, "Playing recording...", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, "Playback error: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun stopPlaying() {
        try {
            mediaPlayer?.stop()
            mediaPlayer?.release()
            mediaPlayer = null
        } catch (e: Exception) {
            // ignore
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
                    // Fallback
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
                openDefaultAppsSettings()
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        stopPlaying()
    }
}
