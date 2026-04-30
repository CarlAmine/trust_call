import asyncio
import base64
import io
from pathlib import Path

import httpx
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import io
import base64
import httpx
import soundfile as sf

# --- NEW IMPORTS ---
from faster_whisper import WhisperModel
# -------------------

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

# --- WARM START: LOAD WHISPER ---
print("⏳ Loading Whisper STT Model (Warm Start)...")
# Using 'tiny.en' for blazing fast English transcription to stay under 500ms
whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
print("✅ Whisper Loaded!")
# --------------------------------

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
        if len(self.active_connections) == 0:
            print("⚠️ WARNING: AI graded the audio, but no phone is connected to the WebSocket!")
            return
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
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("🛑 WebSocket Client Disconnected")
    except Exception as e:
        print(f"⚠️ WebSocket Crash: {e}")


# --- THE PARALLEL FAN-OUT ARCHITECTURE ---

async def fetch_rawnet(base64_audio: str):
    """IEP 1: Acoustic Deepfake Detection"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("http://127.0.0.1:8000/predict", json={"base64_audio": base64_audio}, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                spoof_raw = data.get('spoof_probability_percent', 0)
                return float(spoof_raw)
    except Exception as e:
        print(f"❌ RawNet Error: {e}")
    return 0.0 

async def fetch_distilbert(text: str):
    """IEP 2b: Semantic Intent Detection"""
    if not text.strip():
        return {"semantic_score": 0.0, "label": "benign"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("http://127.0.0.1:8002/predict", json={"scrubbed_text": text}, timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        print(f"❌ DistilBERT Error: {e}")
    return {"semantic_score": 0.0, "label": "benign"} 

async def orchestrate_late_fusion(base64_audio: str, text_context: str):
    """Executes the parallel fan-out and Late Fusion math."""
    print(f"\n🚀 Firing Parallel Requests -> Text Context: '{text_context}'")
    
    # 1. Fire both requests simultaneously!
    rawnet_task = fetch_rawnet(base64_audio)
    distilbert_task = fetch_distilbert(text_context)
    
    # Wait for both AI models to finish
    spoof_float, distilbert_data = await asyncio.gather(rawnet_task, distilbert_task)
    
    # 2. Extract Semantic Scores
    semantic_score = distilbert_data.get("semantic_score", 0.0)
    semantic_label = distilbert_data.get("label", "benign")
    
    # 3. Print verification to the terminal
    real_float = 100.0 - spoof_float
    print(f"🤖 [AI AUDITOR] -> AI: {spoof_float}% | Human: {real_float}%")
    print(f"🧠 [SEMANTIC AUDITOR] -> Score: {semantic_score} | Label: {semantic_label}")
    
    # 4. Late Fusion Logic 
    is_threat = (spoof_float > 50.0) or (semantic_score >= 0.6)
    display_text = f"{spoof_float}% AI (Deepfake)" if spoof_float > 50.0 else f"{real_float}% Human"
    semantic_display = f"{semantic_label.upper()} ({semantic_score:.2f})"
    
    # 5. Push to Phone
    print(f"📊 FUSION RESULT: Threat={'YES' if is_threat else 'NO'}\n")
    await manager.broadcast({
        "signal_score": display_text,
        "is_threat": is_threat,
        "semantic_intent": semantic_display,
        "identity_match": "Pending...", 
        "fusion_status": "THREAT DETECTED" if is_threat else "SAFE"
    })

# --- END PARALLEL ARCHITECTURE ---


def sync_transcribe(filename: str) -> str:
    """Runs the heavy Whisper math synchronously"""
    segments, _ = whisper_model.transcribe(filename, beam_size=1)
    return " ".join([segment.text for segment in segments]).strip()

async def consume_audio_track(track):
    print("🎙️ Audio buffer engine started! Waiting for frames...")
    audio_buffer = []
    context_memory = [] # THE 30-SECOND ROLLING TEXT BUFFER
    sample_rate = 0
    TARGET_SECONDS = 3.0 

    chunk_counter = 0
    while True:
        try:
            frame = await track.recv()
            audio_array = frame.to_ndarray()
            
            is_float = np.issubdtype(audio_array.dtype, np.floating)
            num_channels = len(frame.layout.channels)
            
            if num_channels > 1:
                if audio_array.shape[0] == 1:
                    audio_array = audio_array.reshape(-1, num_channels)
                    audio_array = np.mean(audio_array, axis=1).reshape(1, -1)
                else:
                    audio_array = np.mean(audio_array, axis=0, keepdims=True)

            if is_float:
                audio_array = (audio_array * 32767.0).astype(np.int16)
            else:
                audio_array = audio_array.astype(np.int16)

            if sample_rate == 0:
                sample_rate = frame.sample_rate
                print(f"⚙️ Audio format locked in at: {sample_rate}Hz (Float: {is_float})")

            audio_buffer.append(audio_array)

            total_samples = sum(arr.shape[1] for arr in audio_buffer) 
            current_duration = total_samples / sample_rate

            if current_duration >= TARGET_SECONDS:
                chunk_counter += 1
                combined_audio = np.concatenate(audio_buffer, axis=1).T
                
                max_volume = np.max(np.abs(combined_audio))
                print(f"📦 BOOM! Chunk {chunk_counter} | Max Volume: {max_volume} | Dispatching...")
                
                # 1. Save File (Whisper needs a file to read)
                filename = f"debug_chunk_{chunk_counter}.wav"
                wav_io = io.BytesIO()
                sf.write(wav_io, combined_audio, sample_rate, format='WAV', subtype='PCM_16')
                wav_bytes = wav_io.getvalue()
                with open(filename, "wb") as f:
                    f.write(wav_bytes)

                # 2. Base64 for RawNet
                base64_audio = base64.b64encode(wav_bytes).decode('utf-8')
                
                # 3. Transcribe via Whisper (Non-blocking)
                transcription = await asyncio.to_thread(sync_transcribe, filename)
                
                # 4. Update Rolling Text Buffer
                if transcription:
                    context_memory.append(transcription)
                if len(context_memory) > 10: # Keep up to 30 seconds (10 chunks of 3s)
                    context_memory.pop(0)
                    
                # 5. Grab the last 9 seconds of context (last 3 chunks)
                recent_context = " ".join(context_memory[-7:])
                
                # 6. Dispatch Parallel Fan-Out
                asyncio.create_task(orchestrate_late_fusion(base64_audio, recent_context))
                
                audio_buffer.clear()

        except Exception as e:
            print(f"🛑 Audio stream ended or disconnected. Reason: {e}")
            break

@app.post("/offer")
async def process_offer(params: Offer):
    print("📡 Received WebRTC offer from Trust-Call Shield...")
    
    offer = RTCSessionDescription(sdp=params.sdp, type=params.type)
    pc = RTCPeerConnection()

    @pc.on("track")
    def on_track(track):
        print("🟢 Live Audio track connected!")
        asyncio.ensure_future(consume_audio_track(track))

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    print("📤 Sending WebRTC answer back to mobile app...")
    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
