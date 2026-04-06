# trust_call
A real-time, multimodal AI defense system against voice fraud and social engineering.



## Engineering Progress: Phase 1 & 2 Complete (DATE: 03/10/2026, AUTHOR: GEORGE HABIB)

**Current Active Branch for AI Models:** `feature/rawnet-init`
**Stable Gateway Code:** `dev`

We have successfully locked in the central API Gateway (EEP) and initialized the workspace for our first AI microservice. 

### 1. The API Gateway (EEP) - Fully Functional
* **Framework:** Built using `FastAPI` and `uvicorn` (ASGI) for asynchronous, non-blocking performance.
* **Input Validation:** Implemented a strict Pydantic `AudioPayload` data class to act as a shield. The EEP will instantly reject malformed payloads before they reach our internal AI models.
* **Parallel Orchestration:** Integrated `httpx.AsyncClient` and `asyncio.gather()` to fire simultaneous, concurrent requests to the Internal Endpoints (IEPs) without freezing the server.
* **Late Fusion Math:** The `/analyze` endpoint successfully calculates the final risk score using our custom Sigmoid formula: `Total_Risk = \sigma(W_1*Signal + W_2*Semantic + W_3*Identity)`. 
* **Intervention Triggers:** Configured to return a `{"threat": "CRITICAL", "action": "DUCK_AUDIO"}` JSON response if the Fusion score exceeds `0.75`, unblocking the React Native team to start testing the UI haptics.

### 2. The Signal Auditor (RawNet2) - Initialized
* **Workspace:** Created an isolated directory (`rawnet-service`) and a dedicated Python virtual environment to prevent dependency conflicts with the Gateway.
* **Dependencies Locked:** Installed `fastapi`, `librosa`, and `soundfile` to handle the heavy audio-to-Mel-Spectrogram conversions. 
* **Next Steps:** Write the Python logic to decode the Base64 audio string and feed the spectrogram matrix into the AI model.


## Engineering Progress: IEP 1 (RawNet2) Preprocessing & Testing Complete (DATE: 03/11/2026, AUTHOR: GEORGE HABIB)

**Current Stable Branch:** `dev`

We have successfully built and verified the audio ingestion pipeline for the Signal Auditor (RawNet2 microservice).

### IEP 1: Signal Auditor - Audio Pipeline
* **Environment Setup:** Configured an isolated virtual environment for `rawnet-service` and locked required dependencies (`fastapi`, `librosa`, `soundfile`, `httpx`) in `requirements.txt` to prevent conflicts with the EEP Gateway.
* [cite_start]**Endpoint Creation:** Built the `/predict` POST endpoint to catch the Base64 audio payloads forwarded by the API Gateway[cite: 123, 125].
* **Privacy-First Decoding (Ephemeral RAM):** Implemented secure in-memory processing using `io.BytesIO`. The incoming Base64 audio string is decoded directly in the server's RAM. No voice data is ever written to the hard drive, maintaining strict privacy compliance.
* [cite_start]**DSP Matrix Generation:** Integrated the `librosa` library to calculate the Mel-Spectrogram visual matrix from the decoded audio[cite: 126]. [cite_start]We successfully validated the matrix shape as `[128, 94]`, which is the exact format required to feed into the warm AI model[cite: 126].
* [cite_start]**Local Integration Testing:** Created a standalone `test_client.py` script to simulate the mobile app's behavior[cite: 122]. The script successfully generated 3 seconds of raw audio [cite: 122], converted it to a Base64 text string[cite: 123], and verified that the microservice endpoint returns a `200 OK` status with the correct matrix dimensions without throwing errors.



## Engineering Progress: IEP 1 (RawNet2) FastAPI Inference Complete (DATE: 19/3/2026, AUTHOR: GEORGE HABIB)

**Current Stable Branch:** `dev`

We have successfully migrated the RawNet2 PyTorch model into the production FastAPI microservice. The Signal Auditor is now fully online and capable of processing Base64 audio streams in real-time.

### IEP 1: Microservice Implementation
* **Memory Management (Warm Start):** Implemented a FastAPI `@asynccontextmanager` lifespan event. The 150MB `pre_trained_DF_model.pth` file is loaded directly into the server's RAM upon startup, guaranteeing sub-500ms latency for all incoming requests.
* **Audio Pipeline Bypass:** Successfully bypassed strict OS-level FFmpeg dependencies by integrating the `soundfile` C-library, ensuring raw bytes are decoded strictly in volatile memory.
* **Dynamic Tensor Padding:** Wrote dynamic truncation and padding logic (`torch.nn.functional.pad`) to format variable-length human speech into the strict `[1, 64000]` 1D tensor required by the RawNet2 SincConv layer.
* **End-to-End Validation:** The `test_client.py` successfully sends local `.wav` files as Base64 JSON payloads to the `/predict` endpoint, which accurately returns logarithmic softmax probabilities converted to readable percentages.

***🚨 CAPSTONE REQUIREMENT FLAG:** The microservice architecture is complete, but the current `pre_trained_DF_model.pth` uses baseline ASVspoof weights. This model MUST be fine-tuned on a custom dataset of telephonically-filtered AI voices before final submission.*

## Engineering Progress: Cross-Microservice Integration Complete (DATE: 20/3/2026, AUTHOR: GEORGE HABIB)

**Current Stable Branch:** `dev`

Successfully established local network communication between the EEP API Gateway and the RawNet2 AI Microservice. The cloud architecture is now fully capable of end-to-end payload routing and centralized decision-making.

### IEP 2: Gateway Routing & Business Logic
* **Asynchronous Networking:** Upgraded the EEP Gateway (`eep-gateway/main.py`) with `httpx.AsyncClient`. It now successfully intercepts Base64 audio payloads from the mobile client and securely forwards them to the isolated AI Microservice (`http://localhost:8000/predict`).
* **Centralized Cloud Logic:** Shifted the core business logic from the mobile client to the cloud. The Gateway evaluates raw AI telemetry to generate an actionable system directive (`BLOCK` or `ALLOW`) based on a >50% spoof probability threshold.
* **Hybrid JSON Responses:** Structured the API to return a dual-payload containing both the strict system directive (for device execution) and the raw AI percentages (for UI rendering).
* **End-to-End Validation:** Verified the complete pipeline using a local Python client. Real audio is correctly processed through the Gateway to the AI brain and back, returning a 99.96% `SAFE` classification.


## 📱 Mobile App Setup (Android) (DATE: 22/3/2026, AUTHOR: GEORGE HABIB)

Welcome to the Trust-Call React Native app! Native Android development on Windows requires strict environment configurations. **Please read this carefully before running the app.**

### ⚠️ Crucial Windows Prerequisites
If you are developing on Windows, you **MUST** do these two things before building, or the C++ compiler will crash:
1. **Move out of OneDrive:** Do not clone this repo into a OneDrive or deeply nested folder. Clone it directly to a root drive (e.g., `C:\trust_call` or `E:\trust_call`).
2. **Enable Windows Long Paths:** The WebRTC and TFLite C++ libraries exceed standard Windows file path limits. Open an Administrator PowerShell and run:
   `New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force`

### 🛠️ Required Android Studio Tools
Open Android Studio -> SDK Manager -> SDK Tools (Check "Show Package Details" at the bottom right) and ensure you have these installed:
* **NDK (Side by side):** Version `27.1.12297006`
* **CMake:** Version `3.22.1`

### 🚀 Running the App
1. Open your Android Virtual Device (AVD) in Android Studio and ensure it is powered on.
2. Install dependencies:
   ```bash
    npm install

3. Start the Metro Bundler (in terminal 1):
    ```Bash
    npm start

4. Build the Android app (in terminal 2):
    ```Bash
    npx react-native run-android



## Engineering Progress:  (DATE: 31/3/2026, AUTHOR: GEORGE HABIB)
📱 React Native Frontend
WebRTC Integration: Successfully implemented react-native-webrtc to handle real-time audio streams.

Native Security: Engineered a robust Android permissions flow to safely request and handle hardware access (Microphone/Camera) without triggering OS-level crashes.

Signaling Pipeline: Built an SDP Offer generation system in CallScreen.tsx that successfully transmits WebRTC handshakes to the local Python server via the Android emulator's network bridge.

UI/UX: Constructed the foundational CallScreen interface to display live AI telemetry metrics and late-fusion decision status.

🧠 Python AI Backend
Environment Setup: Initialized an isolated Python virtual environment utilizing FastAPI and aiortc for real-time media handling.

API Architecture: Created a local server endpoint (/offer) equipped with CORS middleware to catch and negotiate WebRTC handshakes from the mobile app.

Real-Time Audio Buffer Engine: Engineered an asynchronous background worker that successfully consumes live 20ms audio frames, extracts the sample rate, and efficiently batches them into precise 3-second numpy arrays entirely in RAM, preparing them for downstream ML processing (RawNet2/ECAPA).





## Session Log: AI Fine-Tuning & Microservice Bridge (DATE: 1/4/2026, AUTHOR: GEORGE HABIB)

### 🧠 1. RawNet2 Transfer Learning (Domain Adaptation)
* **The Data Strategy:** Bypassed outdated datasets (ASVspoof 2021) to focus on modern TTS engines (ElevenLabs, Hume AI, etc.). Built `download_data.py` to stream the `garystafford/deepfake-audio-detection` dataset directly from Hugging Face.
* **FFmpeg Bypass:** Engineered a solution to bypass Windows FFmpeg C++ dependency crashes by directly casting Hugging Face audio to raw bytes and writing them to disk using standard file I/O.
* **The Training Pipeline:** Wrote `train_transfer.py` to perform transfer learning on our pre-trained RawNet2 weights. 
  * **Frozen Layers:** Sinc_conv filters and Residual Blocks 0-5.
  * **Unfrozen Layers:** GRU and Fully Connected classification layers.
* **Results:** Fine-tuned the model on 1,000 files (500 Real / 500 Fake) for 20 epochs, achieving **96.7% training accuracy**.
* **Zero-Shot Validation:** Successfully tested the new `fine_tuned_DF_model.pth` against a blind ElevenLabs deepfake via the `test_client.py` API, returning a **99.95% Spoof Probability**. 

### 🌉 2. WebRTC to AI Bridge (The Microservice Link)
* Connected the `trust_call_backend` (WebRTC) to the `rawnet-service` (AI FastAPI).
* Upgraded the 3-second buffer engine in `server.py`:
  * Concatenates live 20ms PyAV frames into a single `numpy` array.
  * Fixes sample rate distortion by dynamically catching the native WebRTC mic sample rate (usually 48kHz) and converting it to a WAV file in memory (`io.BytesIO`).
  * Utilizes `asyncio` and `httpx.AsyncClient` to POST the Base64 audio payload to the AI server in the background, ensuring the live phone call never drops packets or blocks the thread.

### 📁 3. Version Control & Hygiene
* Updated `.gitignore` in the AI directory to block massive binary files (`*.pth`), `hf_cache/`, and local `training_data/` from bloating the GitHub repository.
* Safely merged the upgraded `rawnet-service` to the `dev` branch.



# 🚀 Progress Update: Real-Time AI Telemetry Integration (DATE: 3/4/2026, AUTHOR: GEORGE HABIB)

## 1. Real-Time Telemetry Bridge (FastAPI & WebSockets)

Established a parallel WebSocket connection alongside the existing WebRTC audio pipeline to enable bidirectional, real-time communication.

Implemented a `ConnectionManager` in the FastAPI gateway to manage active mobile client sockets and broadcast JSON payloads.

Configured the backend to instantly push `RawNet2` biometric predictions down to the mobile device the moment a 3-second audio chunk is processed, achieving near-zero latency for UI updates.

## 2. Dynamic UI & Threat Visualization (React Native)

Upgraded the `CallScreen` component to actively listen to the WebSocket stream and parse incoming telemetry data.

Mapped the JSON payload to React Native state variables, allowing the "Live AI Telemetry" board to update continuously without refreshing the screen.

Implemented a dynamic threat-formatting engine: the backend now evaluates the spoof probability against a `>50%` threshold and sends an `is_threat` flag. The mobile UI dynamically formats the text ("Human" vs. "AI (Deepfake)") and swaps typography colors (Green for safe, Red for threat) based on this flag.

## 3. Call Lifecycle & State Management

Replaced automatic background audio streaming with an explicit `isCallActive` state machine.

Implemented an "Accept Call" UI flow, ensuring that microphone permissions, WebRTC handshakes, WebSocket connections, and the call duration timer only initialize when the user explicitly interacts with the call prompt.

## 4. Raw Audio Capture Optimization

Configured advanced `mediaDevices.getUserMedia` constraints to intentionally disable Android's native audio preprocessing (Echo Cancellation, Noise Suppression, and Auto Gain Control).

This ensures the `RawNet2` neural network receives pure, uncompressed, and unaltered acoustic data, drastically improving the model's ability to detect synthetic audio signatures and presentation attacks.




# 🛡️ Phase 2: Semantic Intent & Late Fusion Integration (DATE: 6/4/2026, AUTHOR: GEORGE HABIB)

> **Multi-Modal Threat Detection | Parallel Microservices | Context-Aware AI Auditing**

## 📖 Overview
Phase 2 evolves the system from a single-threaded pipeline into a **Parallel Fan-Out Architecture**. The core `server.py` now acts as an intelligent API Gateway ("The Brain"), orchestrating concurrent AI microservices to analyze both the acoustic properties and semantic intent of incoming voice streams in real-time.

## 🏗️ System Architecture

### 🧠 Orchestrated API Gateway
The gateway manages concurrent inference across three specialized microservices:
- **🔊 Acoustic Auditor (`RawNet2`):** Detects synthetic voice artifacts and deepfake signatures by analyzing raw audio waveforms.
- **📝 Semantic Auditor (`DistilBERT`):** Evaluates transcribed text for manipulative language, phishing intent, and social engineering patterns.
- **🎙️ Whisper STT Engine:** Performs low-latency, on-device transcription of the encrypted WebRTC audio stream.

## 🧠 Contextual Memory: The 21-Second Buffer
To eliminate false positives from isolated keywords, the system implements a **Rolling Context Buffer**:
- Audio is processed in `3-second chunks`
- Maintains a sliding window of the `last 7 chunks` (~21 seconds of conversation)
- Enables cross-sentence intent recognition (e.g., linking *"I'm calling from your bank"* at `t=5s` with *"Please verify your OTP"* at `t=18s`)

## ⚖️ Late Fusion Decision Logic
Instead of relying on a single modality, the gateway employs a custom **Late Fusion Layer** that mathematically combines acoustic and semantic confidence scores:

$$ \text{Threat} = (P_{\text{acoustic}} > 0.5) \lor (P_{\text{semantic}} > 0.6) $$

**Why this works:**
- 🛡️ **Acoustic bypass:** If a deepfake is acoustically perfect (`P_acoustic < 0.5`), the semantic model can still trigger an alert.
- 🗣️ **Contextual bypass:** If malicious intent is disguised in natural speech, the acoustic analyzer catches synthetic artifacts.
- ⚡ **Low latency:** Parallel inference + weighted OR logic ensures real-time decisioning without blocking the WebRTC stream.

## 🤖 Neural Semantic Fine-Tuning Pipeline *(In Progress)*
Moving beyond keyword matching, we're fine-tuning `DistilBERT` on a domain-specific dataset:

### 📊 Data Generation & Curation
- **Synthetic Vishing Corpus:** LLM-generated transcripts covering modern attack vectors (crypto scams, AI voice cloning, OTP fraud)
- **Public Dataset Integration:** Merged with UC Irvine SMS Spam Corpus
- **Final Matrix:** ~2,500 balanced samples (`50/50` class distribution)

### 🏷️ Class Distribution
| Class | Label | Description |
|-------|-------|-------------|
| `0` | ✅ Safe | Everyday conversations & benign SMS |
| `1` | ⚠️ Scam | Modern vishing scripts & malicious phishing texts |

## 🚀 Next Steps
- [ ] Complete DistilBERT fine-tuning & validation
- [ ] Optimize chunk overlap & buffer windowing
- [ ] Implement dynamic threshold adjustment based on user feedback
- [ ] Add confidence scoring telemetry to the WebSocket stream

---
*Built for real-time, multi-modal threat detection. Phase 2 transforms reactive filtering into proactive, context-aware AI auditing.*