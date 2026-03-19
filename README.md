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



## Engineering Progress: IEP 1 (RawNet2) FastAPI Inference Complete (George Habib, 20/3/2026)

**Current Stable Branch:** `dev`

We have successfully migrated the RawNet2 PyTorch model into the production FastAPI microservice. The Signal Auditor is now fully online and capable of processing Base64 audio streams in real-time.

### IEP 1: Microservice Implementation
* **Memory Management (Warm Start):** Implemented a FastAPI `@asynccontextmanager` lifespan event. The 150MB `pre_trained_DF_model.pth` file is loaded directly into the server's RAM upon startup, guaranteeing sub-500ms latency for all incoming requests.
* **Audio Pipeline Bypass:** Successfully bypassed strict OS-level FFmpeg dependencies by integrating the `soundfile` C-library, ensuring raw bytes are decoded strictly in volatile memory.
* **Dynamic Tensor Padding:** Wrote dynamic truncation and padding logic (`torch.nn.functional.pad`) to format variable-length human speech into the strict `[1, 64000]` 1D tensor required by the RawNet2 SincConv layer.
* **End-to-End Validation:** The `test_client.py` successfully sends local `.wav` files as Base64 JSON payloads to the `/predict` endpoint, which accurately returns logarithmic softmax probabilities converted to readable percentages.

***🚨 CAPSTONE REQUIREMENT FLAG:** The microservice architecture is complete, but the current `pre_trained_DF_model.pth` uses baseline ASVspoof weights. This model MUST be fine-tuned on a custom dataset of telephonically-filtered AI voices before final submission.*


