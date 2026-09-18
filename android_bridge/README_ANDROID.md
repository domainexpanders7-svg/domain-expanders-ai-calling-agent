# Domain Expanders Android Telephony Bridge (GSM SIM Gateway)

This native Android module transforms any spare Android phone (with your business SIM card inserted) into a **zero-cost digital telephony gateway**.

---

## 🌟 Why This Architecture?
- **₹0 Telecom Cost:** Uses your existing recharge pack with unlimited incoming/outgoing calls. No Twilio, Exotel, or Cloud PBX per-minute billing.
- **100% Digital Audio:** Android's `InCallService` intercepts the audio stream digitally via `AudioRecord` (downlink) and `AudioTrack` (uplink) inside the OS.
- **Zero Room Noise:** Background fan, traffic, and AC noise **never enter the call** because audio is handled entirely digitally inside the phone subsystem.

---

## 🛠️ How to Setup on Spare Phone

### Step 1: Open in Android Studio
1. Open Android Studio -> Select `Open Existing Project` or create a new empty Android project with package name `com.domainexpanders.callingagent`.
2. Copy files from `android_bridge/` into your `app/src/main/`:
   - `AndroidManifest.xml` -> `app/src/main/AndroidManifest.xml`
   - `DomainExpandersInCallService.kt` -> `app/src/main/java/com/domainexpanders/callingagent/`
   - `MainActivity.kt` -> `app/src/main/java/com/domainexpanders/callingagent/`
   - `build.gradle` -> `app/build.gradle`

### Step 2: Build & Install APK
Connect your Android phone via USB and run:
```bash
./gradlew installDebug
```
Or build APK from menu: **Build -> Build Bundle(s) / APK(s) -> Build APK(s)** and install the `.apk` on your phone.

### Step 3: Configure on Phone
1. Open the **DE Calling Agent Bridge** app on the phone.
2. In the **Cloud WebSocket Endpoint** field, enter your deployed server URL:
   ```text
   wss://YOUR_SPACE_NAME.hf.space/ws/call
   ```
   *(Or your VPS / ngrok URL if testing locally: `ws://192.168.1.XX:7860/ws/call`)*
3. Tap **"Save Endpoint URL"**.
4. Tap **"Set as Default Phone App (Required)"** and accept the system prompt.
   - *Android requires any app that handles incoming calls via `InCallService` to be set as the Default Phone app.*

### Step 4: Ready for Live Inbound Calls!
Whenever a client dials your SIM card number:
1. The phone auto-answers the call in `< 1 second`.
2. The phone connects to your Cloud Server's `/ws/call` WebSocket.
3. Sneha greets the client in Hindi/Hinglish: *"Haanji sir, Namaste! Sneha baat kar rahi hoon Domain Expanders se..."*
4. All client voice audio is streamed in real-time to the Gemini S2S Brain, and Sneha's responses are streamed directly into the caller's earpiece!
