import asyncio
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


import io
import base64
import httpx
import soundfile as sf

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

async def send_to_rawnet(base64_audio: str):
    """Sends the audio to the RawNet2 microservice in the background."""
    payload = {"base64_audio": base64_audio}
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
                display_text = f"{spoof_float}% AI (Deepfake)" if is_threat else f"{real_float}% Human"
                
                await manager.broadcast({
                    "signal_score": display_text,
                    "is_threat": is_threat, 
                    "semantic_intent": "Low Risk", 
                    "identity_match": "Pending...", 
                    "fusion_status": "ANALYZING"
                })
            else:
                print(f"❌ AI Server Error: {response.text}")
                
    except Exception as e:
        print(f"❌ Failed to reach AI server. Is it running on port 8000? Error: {e}")

# --- THE AUDIO BUFFER ENGINE ---
async def consume_audio_track(track):
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
                
                filename = f"debug_chunk_{chunk_counter}.wav"
                with open(filename, "wb") as f:
                    f.write(wav_bytes)

                base64_audio = base64.b64encode(wav_bytes).decode('utf-8')
                asyncio.create_task(send_to_rawnet(base64_audio))
                
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
        asyncio.ensure_future(consume_audio_track(track))

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    print("📤 Sending WebRTC answer back to mobile app...")
    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


# --- START THE SERVER ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)