import base64
import io
import httpx
import asyncio
import numpy as np
import soundfile as sf

async def simulate_mobile_app():
    print("1. Simulating React Native microphone recording (3 seconds)...")
    sample_rate = 16000
    # Generate 3 seconds of a 440Hz sine wave (a standard audio "beep")
    t = np.linspace(0, 3, 3 * sample_rate)
    dummy_audio = np.sin(2 * np.pi * 440 * t)
    
    # Save the audio into a temporary RAM buffer as a standard .wav file
    wav_buffer = io.BytesIO()
    sf.write(wav_buffer, dummy_audio, sample_rate, format='WAV')
    wav_bytes = wav_buffer.getvalue()
    
    print("2. Converting raw audio to Base64 string...")
    b64_string = base64.b64encode(wav_bytes).decode('utf-8')
    
    print("3. Sending JSON payload to RawNet2 Microservice...")
    url = "http://127.0.0.1:8001/predict"
    payload = {"audio_base64": b64_string}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=5.0)
            print("\n=== SERVER RESPONSE ===")
            print(f"Status Code: {response.status_code}")
            print(f"Data: {response.json()}")
        except Exception as e:
            print(f"Connection failed: {e}. Is the server running on port 8001?")

if __name__ == "__main__":
    asyncio.run(simulate_mobile_app())