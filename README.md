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