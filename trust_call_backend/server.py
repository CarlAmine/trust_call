import asyncio
import base64
import io
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf
from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from trust_call_backend.identity_auditor import (
        ECAPASpeakerEmbedder,
        DEFAULT_EMA_ALPHA,
        IdentityAuditor,
        IdentityEnrollmentStore,
        IdentityResult,
    )
except ModuleNotFoundError:
    from identity_auditor import (  # type: ignore
        ECAPASpeakerEmbedder,
        DEFAULT_EMA_ALPHA,
        IdentityAuditor,
        IdentityEnrollmentStore,
        IdentityResult,
    )

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Offer(BaseModel):
    sdp: str
    type: str
    caller_id: str = "unknown"


class IdentityEnrollmentPayload(BaseModel):
    caller_id: str
    base64_audio: str
    allow_update: bool = False
    ema_alpha: float = DEFAULT_EMA_ALPHA


class IdentityVerificationPayload(BaseModel):
    caller_id: str
    base64_audio: str


# --- WEBSOCKET CONNECTION MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # --- THE FIX: Warn us if the array is empty! ---
        if len(self.active_connections) == 0:
            print("⚠️ WARNING: AI graded the audio, but no phone is connected to the WebSocket!")
            return
        # -----------------------------------------------
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Failed to send websocket message: {e}")

manager = ConnectionManager()
state_root = Path(__file__).resolve().parent / "state"
identity_store = IdentityEnrollmentStore(
    state_root / "identity_profiles"
)
identity_auditor = IdentityAuditor(
    store=identity_store,
    embedder=ECAPASpeakerEmbedder(savedir=state_root / "models" / "ecapa_voxceleb"),
)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print("\n👀 INCOMING WEBSOCKET CONNECTION...")
    await manager.connect(websocket)
    print("✅ WEBSOCKET ACCEPTED AND LOCKED IN!\n")
    try:
        while True:
            # Keep the connection open waiting for the client
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("🛑 WebSocket Client Disconnected")
    except Exception as e:
        print(f"⚠️ WebSocket Crash: {e}")

@app.get("/identity/enrollment/{caller_id}")
async def get_identity_enrollment_status(caller_id: str):
    return identity_auditor.get_enrollment_status(caller_id)


@app.post("/identity/enroll")
async def enroll_identity(payload: IdentityEnrollmentPayload):
    try:
        return identity_auditor.enroll_from_base64(
            caller_id=payload.caller_id,
            base64_audio=payload.base64_audio,
            allow_update=payload.allow_update,
            ema_alpha=payload.ema_alpha,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/identity/verify")
async def verify_identity(payload: IdentityVerificationPayload):
    try:
        result = identity_auditor.verify_from_base64(
            caller_id=payload.caller_id,
            base64_audio=payload.base64_audio,
        )
        return result.to_api_response()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.delete("/identity/enrollment/{caller_id}")
async def delete_identity_enrollment(caller_id: str):
    deleted = identity_store.delete(caller_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return {
        "caller_id": caller_id,
        "deleted": True,
    }


def build_fusion_status(identity_result: IdentityResult) -> str:
    if identity_result.status == "mismatch":
        return "IDENTITY REVIEW"
    if identity_result.status == "review":
        return "IDENTITY CAUTION"
    return "ANALYZING"


async def send_to_rawnet(base64_audio: str, identity_result: IdentityResult):
    """Sends the audio to the RawNet2 microservice in the background."""
    payload = {"base64_audio": base64_audio}
    signal_score = "Signal Unavailable"
    is_threat = False
    try:
        # We use AsyncClient so it doesn't block the live WebRTC stream
        async with httpx.AsyncClient() as client:
            response = await client.post("http://127.0.0.1:8000/predict", json=payload, timeout=5.0)
            
            if response.status_code == 200:
                data = response.json()
                spoof_raw = data.get('spoof_probability_percent')
                real_raw = data.get('real_probability_percent')
                
                # 2. FORCE them to be floats so Python doesn't crash during math!
                spoof_float = float(spoof_raw)
                real_float = float(real_raw)
                
                print(f"🤖 [AI AUDITOR] -> AI: {spoof_float}% | Human: {real_float}%")
                
                # 3. Calculate the threat using the safe float numbers
                is_threat = spoof_float > 50.0 
                signal_score = (
                    f"{spoof_float}% AI (Deepfake)" if is_threat else f"{real_float}% Human"
                )
            else:
                print(f"❌ AI Server Error: {response.text}")
                
    except Exception as e:
        print(f"❌ Failed to reach AI server. Is it running on port 8000? Error: {e}")
    finally:
        await manager.broadcast({
            "signal_score": signal_score,
            "is_threat": is_threat,
            "semantic_intent": "Low Risk",
            "fusion_status": build_fusion_status(identity_result),
            **identity_result.to_telemetry(),
        })

# --- THE AUDIO BUFFER ENGINE ---
async def consume_audio_track(track, caller_id: str):
    print("🎙️ Audio buffer engine started! Waiting for frames...")
    audio_buffer = []
    sample_rate = 0
    TARGET_SECONDS = 3.0 

    chunk_counter = 0
    while True:
        try:
            frame = await track.recv()
            audio_array = frame.to_ndarray()
            
            # --- SAFEGUARD: Prevent float-to-int silence bugs ---
            is_float = np.issubdtype(audio_array.dtype, np.floating)

            num_channels = len(frame.layout.channels)
            if num_channels > 1:
                if audio_array.shape[0] == 1:
                    audio_array = audio_array.reshape(-1, num_channels)
                    audio_array = np.mean(audio_array, axis=1).reshape(1, -1)
                else:
                    audio_array = np.mean(audio_array, axis=0, keepdims=True)

            # If the audio came in as a tiny decimal (-1.0 to 1.0), we MUST multiply it 
            # by 32767 before turning it into a 16-bit integer, or it becomes zero!
            if is_float:
                audio_array = (audio_array * 32767.0).astype(np.int16)
            else:
                audio_array = audio_array.astype(np.int16)
            # --------------------------------------------------------

            if sample_rate == 0:
                sample_rate = frame.sample_rate
                print(f"⚙️ Audio format locked in at: {sample_rate}Hz (Float: {is_float})")

            audio_buffer.append(audio_array)

            total_samples = sum(arr.shape[1] for arr in audio_buffer) 
            current_duration = total_samples / sample_rate

            if current_duration >= TARGET_SECONDS:
                chunk_counter += 1
                combined_audio = np.concatenate(audio_buffer, axis=1).T
                
                # --- THE X-RAY: Check the absolute loudest sound in the chunk ---
                max_volume = np.max(np.abs(combined_audio))
                print(f"📦 BOOM! Chunk {chunk_counter} | Max Volume: {max_volume} | Dispatching...")
                # ----------------------------------------------------------------

                wav_io = io.BytesIO()
                sf.write(wav_io, combined_audio, sample_rate, format='WAV', subtype='PCM_16')
                wav_bytes = wav_io.getvalue()

                identity_result = identity_auditor.verify_chunk(
                    caller_id=caller_id,
                    audio=combined_audio,
                    sample_rate=sample_rate,
                )

                filename = f"debug_chunk_{chunk_counter}.wav"
                with open(filename, "wb") as f:
                    f.write(wav_bytes)

                base64_audio = base64.b64encode(wav_bytes).decode('utf-8')
                asyncio.create_task(send_to_rawnet(base64_audio, identity_result))
                
                audio_buffer.clear()

        except Exception as e:
            print(f"🛑 Audio stream ended or disconnected. Reason: {e}")
            break
# -------------------------------

@app.post("/offer")
async def process_offer(params: Offer):
    print("📡 Received WebRTC offer from Trust-Call Shield...")
    
    offer = RTCSessionDescription(sdp=params.sdp, type=params.type)
    pc = RTCPeerConnection()

    @pc.on("track")
    def on_track(track):
        print("🟢 Live Audio track connected!")
        # Spin up our buffer engine in the background the moment the track connects
        asyncio.ensure_future(consume_audio_track(track, params.caller_id))

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    print("📤 Sending WebRTC answer back to mobile app...")
    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


# --- START THE SERVER ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
