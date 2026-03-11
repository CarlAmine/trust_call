from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import base64
import io
import librosa
import numpy as np
import soundfile as sf

# Initialize the IEP 1: Signal Auditor
app = FastAPI(title="RawNet2 Audio Microservice", version="1.0")

# ---------------------------------------------------------
# INCOMING PAYLOAD CONTRACT
# ---------------------------------------------------------
class AudioInput(BaseModel):
    audio_base64: str

# ---------------------------------------------------------
# EPHEMERAL PROCESSING & SPECTROGRAM GENERATION
# ---------------------------------------------------------
def generate_mel_spectrogram(base64_string: str) -> np.ndarray:
    """
    Decodes the Base64 string in RAM and converts it to a Mel-Spectrogram.
    The audio is never saved to disk, preserving 100% privacy.
    """
    try:
        # 1. Decode Base64 back into raw binary bytes
        audio_bytes = base64.b64decode(base64_string)
        
        # 2. Load the bytes into an ephemeral RAM buffer
        audio_buffer = io.BytesIO(audio_bytes)
        
        # 3. Read the audio data using soundfile
        audio_data, sample_rate = sf.read(audio_buffer)
        
        # Ensure audio is mono (1 channel) for RawNet2
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)

        
        
        # 4. Generate the Mel-Spectrogram matrix using librosa
        mel_spectrogram = librosa.feature.melspectrogram(
            y=audio_data, 
            sr=sample_rate, 
            n_mels=128, 
            fmax=8000
        )
        
        # Convert to decibel scale (standard for AI audio models)
        mel_spectrogram_db = librosa.power_to_db(mel_spectrogram, ref=np.max)
        
        return mel_spectrogram_db

    except Exception as e:
        raise ValueError(f"Failed to process audio: {str(e)}")

# ---------------------------------------------------------
# THE MICROSERVICE ENDPOINT
# ---------------------------------------------------------
@app.post("/predict")
async def predict_deepfake(payload: AudioInput):
    """
    Receives base64 audio from the Gateway, generates the spectrogram, 
    and (eventually) feeds it to the RawNet2 AI model.
    """
    try:
        # Generate the matrix in RAM
        spectrogram_matrix = generate_mel_spectrogram(payload.audio_base64)
        
        # TODO: Feed 'spectrogram_matrix' into the warm PyTorch/ONNX model
        # For now, we simulate the AI output to unblock testing
        
        matrix_shape = spectrogram_matrix.shape
        print(f"Success! Generated Spectrogram Matrix of shape: {matrix_shape}")
        
        return {
            "status": "success",
            "signal_score": 0.12, # Dummy safe score for testing
            "debug_matrix_shape": list(matrix_shape)
        }
        
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error during audio processing")