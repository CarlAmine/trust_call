import asyncio
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi.middleware.cors import CORSMiddleware


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



async def send_to_rawnet(base64_audio: str):
    """Sends the audio to the RawNet2 microservice in the background."""
    payload = {"base64_audio": base64_audio}
    try:
        # We use AsyncClient so it doesn't block the live WebRTC stream
        async with httpx.AsyncClient() as client:
            response = await client.post("http://127.0.0.1:8000/predict", json=payload, timeout=5.0)
            
            if response.status_code == 200:
                data = response.json()
                spoof = data.get('spoof_probability_percent')
                real = data.get('real_probability_percent')
                
                # Print the AI's verdict to the terminal!
                print(f"🤖 [AI AUDITOR] -> AI: {spoof}% | Human: {real}%")
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

    while True:
        try:
            # 1. Catch the next tiny fraction of audio (20ms)
            frame = await track.recv()
            
            # 2. Convert PyAV frame to a numerical numpy array
            audio_array = frame.to_ndarray()
            
            # Grab the sample rate from the very first frame
            if sample_rate == 0:
                sample_rate = frame.sample_rate
                print(f"⚙️ Audio format locked in at: {sample_rate}Hz")

            # 3. Add the tiny frame to our waiting room (buffer)
            audio_buffer.append(audio_array)

            # 4. Check if we have collected 3 seconds of audio yet
            total_samples = sum(arr.shape[1] for arr in audio_buffer) 
            current_duration = total_samples / sample_rate

            # THE FIX: Use the calculated duration, not an undefined variable!
            if current_duration >= TARGET_SECONDS:
                print(f"📦 BOOM! {current_duration:.2f} seconds buffered. Dispatching to AI...")
                
                # 1. Combine frames (axis=1 stacks them along the timeline, .T rotates for soundfile)
                combined_audio = np.concatenate(audio_buffer, axis=1).T
                
                # 2. Use the NATIVE sample_rate, not hardcoded 16000! 
                wav_io = io.BytesIO()
                sf.write(wav_io, combined_audio, sample_rate, format='WAV', subtype='PCM_16')
                wav_bytes = wav_io.getvalue()
                
                # 3. Encode to Base64 string
                base64_audio = base64.b64encode(wav_bytes).decode('utf-8')
                
                # 4. Fire the async background task to the AI server
                asyncio.create_task(send_to_rawnet(base64_audio))
                
                # 5. Clear the buffer using the correct variable name
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