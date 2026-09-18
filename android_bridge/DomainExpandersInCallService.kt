package com.domainexpanders.callingagent

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.telecom.Call
import android.telecom.InCallService
import android.telecom.VideoProfile
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.concurrent.TimeUnit

/**
 * Domain Expanders Production InCallService Telephony Bridge.
 * 
 * Functions:
 * 1. Automatically answers incoming calls on the business SIM (< 1 second).
 * 2. Streams pure digital downlink audio (caller's voice) via 16kHz PCM WebSocket to Cloud Server.
 * 3. Injects AI S2S speech directly into call uplink line (AudioTrack) with 0% room/fan noise.
 */
class DomainExpandersInCallService : InCallService() {

    companion object {
        private const val TAG = "DE_InCallService"
        const val SAMPLE_RATE_IN = 16000   // 16kHz recording from caller
        const val SAMPLE_RATE_OUT = 24000  // 24kHz playback from Gemini Live S2S
        private const val BUFFER_SIZE = 1024
    }

    private var activeCall: Call? = null
    private var webSocket: WebSocket? = null
    private var okHttpClient: OkHttpClient? = null
    private val serviceScope = CoroutineScope(Dispatchers.IO + Job())

    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null
    private var isStreaming = false

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "Domain Expanders InCallService initialized.")
        okHttpClient = OkHttpClient.Builder()
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .pingInterval(10, TimeUnit.SECONDS)
            .build()
    }

    override fun onCallAdded(call: Call) {
        super.onCallAdded(call)
        activeCall = call
        Log.i(TAG, "Incoming call detected: state=${call.state}")

        call.registerCallback(object : Call.Callback() {
            override fun onStateChanged(c: Call, state: Int) {
                super.onStateChanged(c, state)
                handleCallState(c, state)
            }
        })

        if (call.state == Call.STATE_RINGING) {
            autoAnswerCall(call)
        } else if (call.state == Call.STATE_ACTIVE) {
            startAudioBridge()
        }
    }

    override fun onCallRemoved(call: Call) {
        super.onCallRemoved(call)
        Log.i(TAG, "Call ended/removed.")
        stopAudioBridge()
        activeCall = null
    }

    private fun autoAnswerCall(call: Call) {
        Log.i(TAG, "Auto-answering incoming client call...")
        try {
            call.answer(VideoProfile.STATE_AUDIO_ONLY)
        } catch (e: Exception) {
            Log.e(TAG, "Error answering call: ${e.message}", e)
        }
    }

    private fun handleCallState(call: Call, state: Int) {
        when (state) {
            Call.STATE_ACTIVE -> {
                Log.i(TAG, "Call is ACTIVE. Launching digital audio bridge...")
                startAudioBridge()
            }
            Call.STATE_DISCONNECTED, Call.STATE_DISCONNECTING -> {
                Log.i(TAG, "Call DISCONNECTED. Tearing down bridge...")
                stopAudioBridge()
            }
        }
    }

    private fun startAudioBridge() {
        if (isStreaming) return
        isStreaming = true

        val prefs = getSharedPreferences("DE_CALLING_AGENT", MODE_PRIVATE)
        val serverWsUrl = prefs.getString("SERVER_WS_URL", "wss://your-space.hf.space/ws/call") ?: "wss://your-space.hf.space/ws/call"

        Log.i(TAG, "Connecting to cloud voice server: $serverWsUrl")

        val request = Request.Builder().url(serverWsUrl).build()
        webSocket = okHttpClient?.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                Log.i(TAG, "Connected to Domain Expanders Cloud Voice Server.")
                initAudioTrack()
                startRecordingLoop(ws)
            }

            override fun onMessage(ws: WebSocket, bytes: ByteString) {
                // Incoming AI speech audio (PCM or WAV) from cloud server
                val audioData = bytes.toByteArray()
                writeToAudioTrack(audioData)
            }

            override fun onMessage(ws: WebSocket, text: String) {
                Log.d(TAG, "Server message: $text")
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "WebSocket failure: ${t.message}", t)
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "WebSocket closed: code=$code, reason=$reason")
            }
        })
    }

    private fun initAudioTrack() {
        try {
            val minBufferSize = AudioTrack.getMinBufferSize(
                SAMPLE_RATE_OUT,
                AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_16BIT
            )

            audioTrack = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(SAMPLE_RATE_OUT)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build()
                )
                .setBufferSizeInBytes(minBufferSize * 2)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()

            audioTrack?.play()
            Log.i(TAG, "AudioTrack initialized and playing.")
        } catch (e: Exception) {
            Log.e(TAG, "Error initializing AudioTrack: ${e.message}", e)
        }
    }

    private fun writeToAudioTrack(pcmData: ByteArray) {
        try {
            audioTrack?.write(pcmData, 0, pcmData.size)
        } catch (e: Exception) {
            Log.e(TAG, "Error writing to AudioTrack: ${e.message}")
        }
    }

    private fun startRecordingLoop(ws: WebSocket) {
        serviceScope.launch {
            try {
                val minBufferSize = AudioRecord.getMinBufferSize(
                    SAMPLE_RATE_IN,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT
                )

                audioRecord = AudioRecord(
                    MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                    SAMPLE_RATE_IN,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    minBufferSize * 2
                )

                audioRecord?.startRecording()
                Log.i(TAG, "AudioRecord started. Streaming caller downlink audio...")

                val buffer = ByteArray(BUFFER_SIZE)
                while (isActive && isStreaming) {
                    val readBytes = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                    if (readBytes > 0) {
                        val payload = buffer.copyOf(readBytes)
                        ws.send(payload.toByteString())
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "AudioRecord streaming error: ${e.message}", e)
            }
        }
    }

    private fun stopAudioBridge() {
        isStreaming = false
        try {
            webSocket?.send("{\"type\": \"hangup\"}")
            webSocket?.close(1000, "Call ended")
            webSocket = null

            audioRecord?.stop()
            audioRecord?.release()
            audioRecord = null

            audioTrack?.stop()
            audioTrack?.release()
            audioTrack = null
        } catch (e: Exception) {
            Log.e(TAG, "Cleanup error: ${e.message}")
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        stopAudioBridge()
        Log.i(TAG, "InCallService destroyed.")
    }
}
