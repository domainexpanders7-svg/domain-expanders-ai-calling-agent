---
title: Domain Expanders AI Calling Agent
emoji: 🌐
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Domain Expanders AI Calling Agent (100% Free & Zero Cloud Bill Stack)

An intelligent, conversational AI Calling Agent built for **[Domain Expanders](https://www.domainexpanders.in/)** tech consulting, automated client qualification, Discovery Call scheduling, and telephony bridging.

---

## 🌟 Key Features

1. **₹0 Operational Cost:**
   - Free LLM reasoning with **Google Gemini 2.0 / 2.5 Flash** (1,000,000 Tokens/Min free).
   - Free Gemini Native Multimodal S2S & natural Indian voice synthesis.
   - Free 24/7 cloud hosting ready for **Hugging Face Spaces** (2 vCPU, 16 GB RAM).
2. **"The Bridge Technique" for Long-Winded Callers:**
   - Active empathetic listening with polite pivots.
   - Closed-ended option steering to qualify client tech needs smoothly and book a 30-min Discovery Call.
3. **Automated Lead Intelligence:**
   - Live entity extraction: Client Name, Company Name, Service Interest, Project Scope, Budget, Timeline, and Discovery Call Booking.
   - Persistent logging to `leads.json` and automatic sync via Composio (Google Calendar & Gmail).
4. **Interactive Browser Simulator:**
   - Real-time microphone input, live audio waveform visualizer, and streaming speaker playback.
   - Test directly on your laptop before connecting the phone.
5. **Digital GSM Telephony Bridge:**
   - Android `InCallService` integration for 0% room noise digital audio streaming over WebSocket (`/ws/call`).

---

## 🚀 Quick Start (Running Locally)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
# Or explicitly install Composio with Gemini provider:
pip install composio composio_gemini google-genai
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
copy .env.example .env
```
Add your API keys:
```ini
GEMINI_API_KEY=your_actual_gemini_api_key
COMPOSIO_API_KEY=ak_xmTyiDXFOsybQSqBnrBk
DEFAULT_VOICE=Aoede
PORT=7860
```

### 3. Run the Server
```bash
python main.py
```

Open your browser at:
👉 **`http://localhost:7860`**

Click **"Start Call"** and speak through your microphone to talk with Agent Sneha!

---

## 📱 Connecting Android GSM Phone (Digital Audio Gateway)

To bridge your physical SIM card without telecom per-minute charges:

1. Use a dedicated spare Android phone with your business SIM card.
2. The phone connects to your WebSocket endpoint (`wss://your-domain/ws/call`).
3. An Android app running as the **Default Phone Dialer** (`InCallService` API) captures call downlink audio directly in PCM 16kHz and streams it to the server.
4. Voice audio stream is routed back directly into the call speaker line.
5. **No room noise, fan sounds, or street traffic enters the call.**

---

## ☁️ 24/7 Deployment on Hugging Face Spaces (Free Cloud)

1. Create a free account on [huggingface.co](https://huggingface.co).
2. Click **New Space** -> Select **Docker** -> Blank.
3. Set your Space to **Public**.
4. In your Space **Settings** -> **Variables and Secrets**:
   - Add Secret: `GEMINI_API_KEY` = your API key.
   - Add Secret: `COMPOSIO_API_KEY` = your Composio key.
5. Push this codebase to Hugging Face:
   ```bash
   git init
   git remote add space https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME
   git add .
   git commit -m "Deploy Domain Expanders AI Calling Agent"
   git push space main
   ```
6. **24/7 Always Awake Hack:**
   Add your Space's `/health` URL (e.g. `https://your-space.hf.space/health`) to [cron-job.org](https://cron-job.org) (100% free) with a 10-minute interval so it never sleeps!
