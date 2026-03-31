import asyncio
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi.middleware.cors import CORSMiddleware

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
            
            # Grab the sample rate from the very first frame (usually 48000Hz)
            if sample_rate == 0:
                sample_rate = frame.sample_rate
                print(f"⚙️ Audio format locked in at: {sample_rate}Hz")

            # 3. Add the tiny frame to our waiting room (buffer)
            audio_buffer.append(audio_array)

            # 4. Check if we have collected 3 seconds of audio yet
            # shape[1] contains the number of audio samples in this specific frame
            total_samples = sum(arr.shape[1] for arr in audio_buffer) 
            current_duration = total_samples / sample_rate

            if current_duration >= TARGET_SECONDS:
                print(f"📦 BOOM! {TARGET_SECONDS} seconds of audio buffered. Ready for ML models!")
                
                # ---> THIS IS WHERE THE MAGIC WILL HAPPEN NEXT TIME <---
                # You will concatenate the buffer into one big array:
                # full_audio_chunk = np.concatenate(audio_buffer, axis=1)
                # pass_to_rawnet2(full_audio_chunk)
                # pass_to_ecapa(full_audio_chunk)
                
                # 5. Clear the buffer to start collecting the next 3 seconds
                audio_buffer = []

        except Exception as e:
            print("🛑 Audio stream ended or disconnected.")
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