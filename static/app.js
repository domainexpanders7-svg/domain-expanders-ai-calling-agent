// Domain Expanders Ultra-Low Latency Audio I/O & Conversation Pipeline Client
let ws = null;
let isCallActive = false;
let isAgentSpeaking = false;
let callTimerInterval = null;
let callSeconds = 0;

// Audio Queue & Playback Management
let audioQueue = [];
let currentAudioElement = null;

// Speech Recognition & Fallback MediaRecorder
let recognition = null;
let mediaRecorder = null;
let recordedAudioChunks = [];
let audioContext = null;
let analyser = null;
let microphoneStream = null;
let animationFrameId = null;
let currentSpeechLang = 'hi-IN';
let speechSilenceTimer = null;

// DOM Elements
const startCallBtn = document.getElementById('startCallBtn');
const endCallBtn = document.getElementById('endCallBtn');
const interruptBtn = document.getElementById('interruptBtn');
const textInput = document.getElementById('textInput');
const sendTextBtn = document.getElementById('sendTextBtn');
const connectionDot = document.getElementById('connectionDot');
const connectionStatus = document.getElementById('connectionStatus');
const pulseRing = document.getElementById('pulseRing');
const callTimer = document.getElementById('callTimer');
const audioStateText = document.getElementById('audioStateText');
const transcriptBox = document.getElementById('transcriptBox');
const emptyTranscript = document.getElementById('emptyTranscript');
const visualizerCanvas = document.getElementById('audioVisualizer');
const canvasCtx = visualizerCanvas.getContext('2d');
const micBadge = document.getElementById('micBadge');
const langSelect = document.getElementById('langSelect');
const liveHearingChip = document.getElementById('liveHearingChip');
const liveHearingText = document.getElementById('liveHearingText');
const voiceSelect = document.getElementById('voiceSelect');
const agentNameDisplay = document.getElementById('agentNameDisplay');

// Lead Card Elements
const valName = document.getElementById('valName');
const valCompany = document.getElementById('valCompany');
const valService = document.getElementById('valService');
const valBudget = document.getElementById('valBudget');
const valTimeline = document.getElementById('valTimeline');
const valDiscoveryCall = document.getElementById('valDiscoveryCall');
const valMeetingTime = document.getElementById('valMeetingTime');
const valSummary = document.getElementById('valSummary');
const leadStageBadge = document.getElementById('leadStageBadge');
const savedLeadsList = document.getElementById('savedLeadsList');

// -------------------------------------------------------------
// Acoustic Echo Shield (Prevents Self-Interruption on Speakers)
// -------------------------------------------------------------
let recentAgentWords = new Set();
let lastAgentSpeechEndTime = 0;

function recordAgentUtterance(text) {
  if (!text) return;
  const words = text.toLowerCase().replace(/[^\w\s\u0900-\u097F]/g, ' ').split(/\s+/);
  words.forEach(w => {
    if (w.length > 2) recentAgentWords.add(w);
  });
  if (recentAgentWords.size > 250) {
    recentAgentWords.clear();
  }
}

function isAgentEcho(spokenText) {
  if (!spokenText) return false;
  const words = spokenText.toLowerCase().replace(/[^\w\s\u0900-\u097F]/g, ' ').split(/\s+/).filter(w => w.length > 2);
  if (words.length === 0) return false;
  let matchCount = 0;
  for (const w of words) {
    if (recentAgentWords.has(w)) matchCount++;
  }
  // If 35% or more of words were recently spoken by Sneha, it's an echo from the speakers
  return (matchCount / words.length) >= 0.35;
}

// -------------------------------------------------------------
// WebSocket Connection
// -------------------------------------------------------------
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/browser`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    connectionDot.className = 'status-dot connected';
    connectionStatus.textContent = 'Server Connected';
  };

  ws.onclose = () => {
    connectionDot.className = 'status-dot disconnected';
    connectionStatus.textContent = 'Disconnected (Reconnecting...)';
    if (isCallActive) endCall();
    setTimeout(initWebSocket, 3000);
  };

  ws.onerror = (err) => {
    console.error('WebSocket error:', err);
  };

  ws.onmessage = async (event) => {
    try {
      const data = JSON.parse(event.data);
      handleServerMessage(data);
    } catch (e) {
      console.error('Failed to parse WS message:', e);
    }
  };
}

// Web Audio API Real-time S2S Streaming Player
let liveAudioCtx = null;
let liveNextPlayTime = 0;
let liveActiveSources = [];
let hasPcmPlayedInTurn = false;
let currentStreamingParagraph = null;
let greetingDismissed = false;
let currentTurnId = 0;

function initLiveAudio() {
  if (!liveAudioCtx) {
    liveAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
  }
  if (liveAudioCtx.state === 'suspended') {
    liveAudioCtx.resume();
  }
}

// Master Audio Killer: Guarantees NO dual audio plays concurrently
function stopAllAudio() {
  stopLiveStreamingAudio();

  if (currentAudioElement) {
    try {
      currentAudioElement.pause();
      currentAudioElement.currentTime = 0;
      currentAudioElement.src = '';
      currentAudioElement.onended = null;
      currentAudioElement.onerror = null;
    } catch (e) {}
    currentAudioElement = null;
  }

  audioQueue = [];
  isAgentSpeaking = false;
  hasPcmPlayedInTurn = false;
  pulseRing.classList.remove('active');
  if (interruptBtn) interruptBtn.disabled = true;
}

function playStreamingPcmChunk(base64Pcm) {
  // CRITICAL: Immediately kill any HTML5 audio (like default greeting or fallback TTS)
  // so dual audio CANNOT play at the same time!
  if (currentAudioElement || audioQueue.length > 0) {
    if (currentAudioElement) {
      try {
        currentAudioElement.pause();
        currentAudioElement.currentTime = 0;
        currentAudioElement.src = '';
        currentAudioElement.onended = null;
      } catch (e) {}
      currentAudioElement = null;
    }
    audioQueue = [];
  }
  greetingDismissed = true;

  initLiveAudio();
  hasPcmPlayedInTurn = true;

  if (!isAgentSpeaking) {
    isAgentSpeaking = true;
    pulseRing.classList.add('active');
    if (interruptBtn) interruptBtn.disabled = false;
    audioStateText.textContent = `${agentNameDisplay ? agentNameDisplay.textContent : 'Sneha'} is speaking...`;
    if (recognition) {
      try { recognition.abort(); } catch (e) {}
    }
  }

  const binary = atob(base64Pcm);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
  const int16 = new Int16Array(bytes.buffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768.0;
  }

  const audioBuffer = liveAudioCtx.createBuffer(1, float32.length, 24000);
  audioBuffer.getChannelData(0).set(float32);

  const source = liveAudioCtx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(liveAudioCtx.destination);

  const currentTime = liveAudioCtx.currentTime;
  const startTime = Math.max(currentTime, liveNextPlayTime);
  source.start(startTime);
  liveNextPlayTime = startTime + audioBuffer.duration;
  liveActiveSources.push(source);

  source.onended = () => {
    const idx = liveActiveSources.indexOf(source);
    if (idx !== -1) liveActiveSources.splice(idx, 1);
    if (liveActiveSources.length === 0 && liveNextPlayTime <= liveAudioCtx.currentTime + 0.1) {
      isAgentSpeaking = false;
      lastAgentSpeechEndTime = Date.now();
      pulseRing.classList.remove('active');
      if (interruptBtn) interruptBtn.disabled = true;
      if (isCallActive) {
        audioStateText.textContent = 'Listening to you... (Speak now)';
        setTimeout(() => {
          if (isCallActive && !isAgentSpeaking) restartSpeechCapture();
        }, 350);
      }
    }
  };
}

function stopLiveStreamingAudio() {
  if (liveActiveSources.length > 0) {
    for (const src of liveActiveSources) {
      try { src.stop(); } catch (e) {}
    }
    liveActiveSources = [];
  }
  if (liveAudioCtx) {
    liveNextPlayTime = liveAudioCtx.currentTime;
  }
}

function updateStreamingMessage(role, textChunk) {
  emptyTranscript.style.display = 'none';
  if (!currentStreamingParagraph) {
    currentStreamingParagraph = appendMessage(role, textChunk);
  } else {
    currentStreamingParagraph.textContent += textChunk;
    transcriptBox.scrollTop = transcriptBox.scrollHeight;
  }
}

function finalizeStreamingMessage(role, fullText) {
  if (currentStreamingParagraph) {
    currentStreamingParagraph.textContent = fullText;
    currentStreamingParagraph = null;
  } else {
    appendMessage(role, fullText);
  }
}

function handleServerMessage(data) {
  if (data.type === 'transcript') {
    appendMessage(data.role, data.text);
  } else if (data.type === 'transcript_stream') {
    // Real-time live transcript words from Gemini
    updateStreamingMessage(data.role, data.text);
  } else if (data.type === 's2s_pcm_chunk') {
    // Zero-latency real-time PCM audio streaming
    playStreamingPcmChunk(data.audio_pcm_b64);
  } else if (data.type === 'audio_chunk') {
    // If greeting was cancelled or user already spoke, discard greeting chunk immediately!
    if (data.is_greeting && greetingDismissed) {
      console.log('Discarded late greeting audio chunk because user already interrupted.');
      return;
    }
    // Fallback or initial greeting WAV playback (only if streaming PCM didn't already handle it)
    if (!hasPcmPlayedInTurn) {
      queueSentenceAudio(data.audio_base64, data.text, data.mime_type || 'audio/wav', !!data.is_greeting);
    }
  } else if (data.type === 'turn_complete') {
    if (data.text) {
      finalizeStreamingMessage(data.role, data.text);
      recordAgentUtterance(data.text);
    }
    hasPcmPlayedInTurn = false;
  } else if (data.lead_update) {
    updateLeadCard(data.lead);
  } else if (data.type === 'lead_update') {
    updateLeadCard(data.lead);
  } else if (data.type === 'saved_leads') {
    renderSavedLeads(data.leads);
  }
}

// -------------------------------------------------------------
// Audio Queue & Zero-Gap Sentence Playback
// -------------------------------------------------------------
function queueSentenceAudio(base64Audio, sentenceText, mimeType = 'audio/wav', isGreeting = false) {
  if (isGreeting && greetingDismissed) {
    return;
  }
  if (hasPcmPlayedInTurn) {
    return;
  }
  if (sentenceText) {
    recordAgentUtterance(sentenceText);
  }
  audioQueue.push({ base64: base64Audio, text: sentenceText, mime: mimeType, isGreeting: isGreeting });
  if (!isAgentSpeaking) {
    playNextAudioChunk();
  }
}

function playNextAudioChunk() {
  // Purge any dismissed greeting from queue
  while (audioQueue.length > 0 && audioQueue[0].isGreeting && greetingDismissed) {
    audioQueue.shift();
  }

  if (audioQueue.length === 0) {
    isAgentSpeaking = false;
    lastAgentSpeechEndTime = Date.now();
    pulseRing.classList.remove('active');
    if (interruptBtn) interruptBtn.disabled = true;
    if (isCallActive) {
      audioStateText.textContent = 'Listening to you... (Speak now)';
      setTimeout(() => {
        if (isCallActive && !isAgentSpeaking) {
          restartSpeechCapture();
        }
      }, 350);
    }
    return;
  }

  // If live PCM started playing, wipe queue and do not play HTML5 audio
  if (hasPcmPlayedInTurn) {
    audioQueue = [];
    return;
  }

  const nextItem = audioQueue.shift();
  if (nextItem.isGreeting && greetingDismissed) {
    playNextAudioChunk();
    return;
  }

  isAgentSpeaking = true;
  pulseRing.classList.add('active');
  if (interruptBtn) interruptBtn.disabled = false;
  audioStateText.textContent = `${agentNameDisplay ? agentNameDisplay.textContent : 'Sneha'} is speaking...`;

  if (recognition) {
    try { recognition.abort(); } catch (e) {}
  }

  if (nextItem && nextItem.text) {
    recordAgentUtterance(nextItem.text);
  }
  const mime = nextItem.mime || 'audio/wav';
  currentAudioElement = new Audio(`data:${mime};base64,${nextItem.base64}`);

  currentAudioElement.play().catch(err => {
    console.warn('Audio playback error:', err);
    if (!greetingDismissed) playNextAudioChunk();
  });

  currentAudioElement.onended = () => {
    currentAudioElement = null;
    playNextAudioChunk();
  };
}

// -------------------------------------------------------------
// Barge-in (Interruption Handler)
// -------------------------------------------------------------
function triggerBargeIn() {
  console.log('Barge-in triggered: stopping all agent audio immediately.');
  greetingDismissed = true;
  currentTurnId++;

  stopAllAudio();

  // Notify server to cancel ongoing generation & greeting
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'interrupt', turn_id: currentTurnId }));
  }

  if (isCallActive) {
    audioStateText.textContent = 'Listening to you... (Speak now)';
    restartSpeechCapture();
  }
}

// -------------------------------------------------------------
// Call Lifecycle (Start / End)
// -------------------------------------------------------------
async function startCall() {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    alert('Waiting for server connection...');
    return;
  }

  try {
    microphoneStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 16000
      }
    });

    micBadge.className = 'mic-badge active';
    micBadge.textContent = '🎙️ Mic Active';

    await setupVisualizer(microphoneStream);
    setupMediaRecorderFallback(microphoneStream);
  } catch (err) {
    console.error('Microphone access denied:', err);
    micBadge.className = 'mic-badge error';
    micBadge.textContent = '❌ Mic Blocked';
    alert('Microphone access was denied or not found!\nPlease allow microphone access in your browser address bar.');
  }

  isCallActive = true;
  startCallBtn.disabled = true;
  endCallBtn.disabled = false;
  textInput.disabled = false;
  sendTextBtn.disabled = false;
  emptyTranscript.style.display = 'none';

  // Call duration counter
  callSeconds = 0;
  callTimerInterval = setInterval(() => {
    callSeconds++;
    const m = String(Math.floor(callSeconds / 60)).padStart(2, '0');
    const s = String(callSeconds % 60).padStart(2, '0');
    callTimer.textContent = `${m}:${s}`;
  }, 1000);

  // Reset turn & greeting states
  greetingDismissed = false;
  hasPcmPlayedInTurn = false;
  currentTurnId = 1;
  stopAllAudio();

  // Trigger call on server with chosen voice
  const chosenVoice = voiceSelect ? voiceSelect.value : 'Aoede';
  const isMale = ['Puck', 'Fenrir', 'Charon'].includes(chosenVoice);
  const advisorName = isMale ? 'Rahul' : 'Sneha';
  if (agentNameDisplay) agentNameDisplay.textContent = advisorName;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'set_voice', voice: chosenVoice }));
    ws.send(JSON.stringify({ type: 'start_call', voice: chosenVoice }));
  }
  audioStateText.textContent = `Connecting call with ${advisorName}...`;

  // Start Speech Recognition
  startSpeechCapture();
}

function endCall() {
  isCallActive = false;
  isAgentSpeaking = false;
  greetingDismissed = true;
  startCallBtn.disabled = false;
  endCallBtn.disabled = true;
  if (interruptBtn) interruptBtn.disabled = true;
  textInput.disabled = true;
  sendTextBtn.disabled = true;
  pulseRing.classList.remove('active');
  liveHearingChip.style.display = 'none';

  clearInterval(callTimerInterval);
  audioStateText.textContent = 'Call ended. Lead saved.';
  micBadge.className = 'mic-badge';
  micBadge.textContent = '🎙️ Mic: Standby';

  // Stop all audio playback channels
  stopAllAudio();

  // Stop recognition & recording
  stopSpeechCapture();

  if (microphoneStream) {
    microphoneStream.getTracks().forEach(track => track.stop());
  }
  if (animationFrameId) cancelAnimationFrame(animationFrameId);

  // Clear visualizer
  canvasCtx.clearRect(0, 0, visualizerCanvas.width, visualizerCanvas.height);

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'end_call' }));
  }
}

// -------------------------------------------------------------
// Speech Recognition & Server-Side Fallback Recorder
// -------------------------------------------------------------
function startSpeechCapture() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  
  if (SpeechRecognition) {
    try {
      if (!recognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;
        recognition.lang = currentSpeechLang;

        recognition.onresult = handleSpeechResult;
        recognition.onerror = handleSpeechError;
        recognition.onend = () => {
          if (isCallActive && !isAgentSpeaking) {
            try { recognition.start(); } catch (e) {}
          }
        };
      }
      recognition.lang = currentSpeechLang;
      try {
        recognition.start();
      } catch (err) {
        // Recognition already active
      }
      return;
    } catch (e) {
      console.warn('SpeechRecognition failed to start, using Server-Side audio fallback:', e);
    }
  }

  // Fallback: Start MediaRecorder
  startMediaRecording();
}

function stopSpeechCapture() {
  if (recognition) {
    try { recognition.stop(); } catch (e) {}
  }
  stopMediaRecording();
}

function restartSpeechCapture() {
  if (!isCallActive || isAgentSpeaking) return;
  startSpeechCapture();
}

// SpeechRecognition Result Handler with Silence Turn Detection
let pendingTurnText = '';

function handleSpeechResult(event) {
  let interim = '';
  let final = '';

  for (let i = event.resultIndex; i < event.results.length; ++i) {
    const transcriptPiece = event.results[i][0].transcript;
    if (event.results[i].isFinal) {
      final += transcriptPiece;
    } else {
      interim += transcriptPiece;
    }
  }

  const currentSpoken = (final || interim).trim();
  if (!currentSpoken) return;

  // Echo Shield: If recognized text is from Sneha's own speech, ignore completely!
  if (isAgentEcho(currentSpoken)) {
    console.log('Echo Shield: Ignored agent self-voice from speakers:', currentSpoken);
    return;
  }

  // Unconditionally silence any greeting or agent speech the moment the caller speaks
  greetingDismissed = true;
  triggerBargeIn();

  pendingTurnText = currentSpoken;
  liveHearingChip.style.display = 'flex';
  liveHearingText.textContent = `Hearing: "${currentSpoken}"`;

  // Reset silence timer (450ms of silence after speaking means user finished sentence)
  clearTimeout(speechSilenceTimer);
  speechSilenceTimer = setTimeout(() => {
    commitUserSpeechTurn();
  }, 450);

  // If browser explicitly marked it final, commit ultra-fast (200ms)
  if (final.trim() && isCallActive) {
    clearTimeout(speechSilenceTimer);
    speechSilenceTimer = setTimeout(() => {
      commitUserSpeechTurn();
    }, 200);
  }
}

function commitUserSpeechTurn() {
  const textToSend = pendingTurnText.trim();
  if (!textToSend || !isCallActive) return;

  // Make sure all previous speech or greeting is 100% stopped
  stopAllAudio();
  greetingDismissed = true;

  // Final Echo Shield check: never send agent's own echoed words to the server
  if (isAgentEcho(textToSend)) {
    console.log('Echo Shield: Discarded self-echo commit:', textToSend);
    pendingTurnText = '';
    liveHearingChip.style.display = 'none';
    return;
  }

  pendingTurnText = '';
  clearTimeout(speechSilenceTimer);
  liveHearingChip.style.display = 'none';

  // Temporarily pause recognition while agent generates and speaks
  if (recognition) {
    try { recognition.abort(); } catch (e) {}
  }

  currentTurnId++;
  appendMessage('user', textToSend);
  audioStateText.textContent = `${agentNameDisplay ? agentNameDisplay.textContent : 'Sneha'} is thinking...`;
  console.log('Dispatching user speech to server:', textToSend);
  ws.send(JSON.stringify({ type: 'user_speech', text: textToSend, turn_id: currentTurnId }));
}

function handleSpeechError(e) {
  console.warn('Speech recognition status:', e.error);
  if (e.error === 'not-allowed') {
    micBadge.className = 'mic-badge error';
    micBadge.textContent = '❌ Mic Blocked (Allow in Address Bar)';
  } else if (e.error === 'network' || e.error === 'service-not-allowed') {
    micBadge.textContent = '🎙️ Audio Fallback Active';
    startMediaRecording();
  }
}

// -------------------------------------------------------------
// MediaRecorder Audio Streaming Fallback (Server STT)
// -------------------------------------------------------------
function setupMediaRecorderFallback(stream) {
  try {
    const options = MediaRecorder.isTypeSupported('audio/webm') ? { mimeType: 'audio/webm' } : {};
    mediaRecorder = new MediaRecorder(stream, options);

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        recordedAudioChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      if (recordedAudioChunks.length > 0 && isCallActive && !isAgentSpeaking) {
        const audioBlob = new Blob(recordedAudioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
        recordedAudioChunks = [];

        // Convert blob to base64
        const reader = new FileReader();
        reader.onloadend = () => {
          const base64Data = reader.result.split(',')[1];
          if (base64Data && ws && ws.readyState === WebSocket.OPEN) {
            audioStateText.textContent = 'Transcribing voice on server...';
            ws.send(JSON.stringify({
              type: 'user_audio',
              audio_base64: base64Data,
              mime_type: audioBlob.type
            }));
          }
        };
        reader.readAsDataURL(audioBlob);
      }
    };
  } catch (err) {
    console.warn('MediaRecorder setup issue:', err);
  }
}

function startMediaRecording() {
  if (mediaRecorder && mediaRecorder.state === 'inactive') {
    recordedAudioChunks = [];
    try { mediaRecorder.start(1000); } catch (e) {}
  }
}

function stopMediaRecording() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    try { mediaRecorder.stop(); } catch (e) {}
  }
}

// -------------------------------------------------------------
// Text Input Fallback
// -------------------------------------------------------------
function sendTextMessage() {
  const text = textInput.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

  triggerBargeIn();
  liveHearingChip.style.display = 'none';
  appendMessage('user', text);
  textInput.value = '';
  audioStateText.textContent = 'Sneha is thinking...';
  ws.send(JSON.stringify({ type: 'user_speech', text: text }));
}

// -------------------------------------------------------------
// UI Message & Lead Card Updates
// -------------------------------------------------------------
function appendMessage(role, text) {
  emptyTranscript.style.display = 'none';

  const bubble = document.createElement('div');
  bubble.className = `message-bubble ${role === 'user' ? 'user' : 'agent'}`;

  const sender = document.createElement('span');
  sender.className = 'sender-tag';
  sender.textContent = role === 'user' ? 'You (Client)' : 'Sneha (Domain Expanders)';

  const content = document.createElement('p');
  content.textContent = text;

  bubble.appendChild(sender);
  bubble.appendChild(content);
  transcriptBox.appendChild(bubble);

  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}

function updateLeadCard(lead) {
  if (!lead) return;

  if (lead.customer_name) valName.textContent = lead.customer_name;
  if (lead.company_name) valCompany.textContent = lead.company_name;
  if (lead.service_interest) valService.textContent = lead.service_interest;
  if (lead.budget) valBudget.textContent = lead.budget;
  if (lead.timeline) valTimeline.textContent = lead.timeline;

  if (lead.discovery_call_scheduled || lead.site_visit_scheduled) {
    valDiscoveryCall.textContent = 'Confirmed ✓';
    valDiscoveryCall.className = 'field-value status-tag confirmed';
  }
  if (lead.visit_date_time) valMeetingTime.textContent = lead.visit_date_time;
  if (lead.call_summary) valSummary.textContent = lead.call_summary;
  if (lead.lead_stage) leadStageBadge.textContent = lead.lead_stage;
}

function renderSavedLeads(leads) {
  if (!leads || leads.length === 0) {
    savedLeadsList.innerHTML = '<div class="empty-mini">No saved prospects yet. Complete a call to log data.</div>';
    return;
  }

  savedLeadsList.innerHTML = '';
  leads.slice(-5).reverse().forEach(lead => {
    const item = document.createElement('div');
    item.className = 'saved-lead-card';
    item.innerHTML = `
      <div>
        <strong>${lead.customer_name || 'Client Lead'}</strong> (${lead.company_name || lead.service_interest || 'Tech Inquiry'})
        <div style="font-size: 11px; color: #94a3b8;">${lead.service_interest || 'Custom AI/Software'} • ${lead.budget || 'Budget TBD'}</div>
      </div>
      <span style="color: #10b981; font-weight: 600;">${lead.lead_stage || 'Saved'}</span>
    `;
    savedLeadsList.appendChild(item);
  });
}

// -------------------------------------------------------------
// Waveform Visualizer & VAD Meter
// -------------------------------------------------------------
async function setupVisualizer(stream) {
  audioContext = new (window.AudioContext || window.webkitAudioContext)();
  if (audioContext.state === 'suspended') {
    await audioContext.resume();
  }

  const source = audioContext.createMediaStreamSource(stream);
  analyser = audioContext.createAnalyser();
  analyser.fftSize = 64;
  source.connect(analyser);

  const bufferLength = analyser.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLength);

  function draw() {
    animationFrameId = requestAnimationFrame(draw);
    analyser.getByteFrequencyData(dataArray);

    canvasCtx.clearRect(0, 0, visualizerCanvas.width, visualizerCanvas.height);

    const barWidth = (visualizerCanvas.width / bufferLength) * 2;
    let x = 0;
    let sum = 0;

    for (let i = 0; i < bufferLength; i++) {
      const val = dataArray[i];
      sum += val;
      const barHeight = (val / 255) * visualizerCanvas.height;
      const gradient = canvasCtx.createLinearGradient(0, visualizerCanvas.height, 0, 0);
      gradient.addColorStop(0, '#06b6d4');
      gradient.addColorStop(1, '#3b82f6');

      canvasCtx.fillStyle = gradient;
      canvasCtx.fillRect(x, visualizerCanvas.height - barHeight, barWidth - 2, barHeight);
      x += barWidth;
    }

    // Voice Activity Meter
    if (isCallActive && !isAgentSpeaking) {
      const avg = Math.round(sum / bufferLength);
      if (avg > 18) {
        micBadge.textContent = `🎙️ Hearing Voice (${avg}%)`;
        micBadge.className = 'mic-badge active';
      } else {
        micBadge.textContent = `🎙️ Mic Ready (${currentSpeechLang})`;
      }
    }
  }

  draw();
}

// -------------------------------------------------------------
// Event Listeners
// -------------------------------------------------------------
startCallBtn.addEventListener('click', startCall);
endCallBtn.addEventListener('click', endCall);
sendTextBtn.addEventListener('click', sendTextMessage);
textInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') sendTextMessage();
});

if (langSelect) {
  langSelect.addEventListener('change', (e) => {
    currentSpeechLang = e.target.value;
    if (recognition) {
      recognition.lang = currentSpeechLang;
    }
  });
}

if (voiceSelect) {
  voiceSelect.addEventListener('change', (e) => {
    const selectedVoice = e.target.value;
    const isMale = ['Puck', 'Fenrir', 'Charon'].includes(selectedVoice);
    const advisorName = isMale ? 'Rahul' : 'Sneha';
    if (agentNameDisplay) {
      agentNameDisplay.textContent = advisorName;
    }
    const avatarCircle = document.querySelector('.avatar-circle .avatar-initials');
    if (avatarCircle) {
      avatarCircle.textContent = isMale ? 'RH' : 'SN';
    }
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'set_voice', voice: selectedVoice }));
      console.log('Switched AI Voice persona to Gemini S2S:', selectedVoice, `(${advisorName})`);
    }
  });
}

// Manual Interrupt Button & Spacebar Keydown Handler
if (interruptBtn) {
  interruptBtn.onclick = () => {
    if (isAgentSpeaking) {
      triggerBargeIn();
    }
  };
}

window.addEventListener('keydown', (e) => {
  if (e.code === 'Space' && isCallActive && isAgentSpeaking && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
    e.preventDefault();
    triggerBargeIn();
  }
});

window.addEventListener('load', () => {
  visualizerCanvas.width = visualizerCanvas.offsetWidth;
  visualizerCanvas.height = visualizerCanvas.offsetHeight;
  initWebSocket();
});
