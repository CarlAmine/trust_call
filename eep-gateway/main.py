import asyncio
import httpx
import math
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Trust-Call API Gateway", version="1.0")

class AudioPayload(BaseModel):
    caller_id: str          
    identity_score: float   
    scrubbed_text: str      
    audio_base64: str       

# ---------------------------------------------------------
# MOCK IEP ENDPOINTS (Simulating Container 2 and Container 3)
# ---------------------------------------------------------
@app.post("/mock_rawnet")
async def mock_rawnet():
    await asyncio.sleep(0.1) # Simulates PyTorch/GPU processing time
    return {"signal_score": 0.85}

@app.post("/mock_distilbert")
async def mock_distilbert():
    await asyncio.sleep(0.15) # Simulates DistilBERT processing time
    return {"semantic_score": 0.92}

# ---------------------------------------------------------
# LATE FUSION MATH
# ---------------------------------------------------------
def calculate_late_fusion(signal: float, semantic: float, identity: float) -> float:
    """
    Executes the Late Fusion formula to combine the scores from 
    the Signal, Semantic, and Identity auditors.
    """
    # Weights for the formula (these can be tuned later based on testing)
    w1, w2, w3 = 0.4, 0.4, 0.2 
    
    raw_score = (w1 * signal) + (w2 * semantic) + (w3 * identity)
    
    # Sigmoid function normalizing the final threat score between 0 and 1
    return 1 / (1 + math.exp(-raw_score))

# ---------------------------------------------------------
# THE GATEWAY ORCHESTRATOR
# ---------------------------------------------------------
@app.post("/analyze")
async def analyze_audio(payload: AudioPayload):
    """
    Receives payload, fires parallel requests to IEPs, and calculates risk.
    """
    # In production, these URLs will be http://rawnet-container:8000/predict 
    # and http://distilbert-container:8000/predict
    url_rawnet = "http://127.0.0.1:8000/mock_rawnet"
    url_distilbert = "http://127.0.0.1:8000/mock_distilbert"
    
    
    async with httpx.AsyncClient() as client:
        # Fire both HTTP requests simultaneously
        task_1 = client.post(url_rawnet)
        task_2 = client.post(url_distilbert)
        
        # Wait for both AI models to return their scores
        results = await asyncio.gather(task_1, task_2)
        
        rawnet_data = results[0].json()
        distilbert_data = results[1].json()

    signal_score = rawnet_data.get("signal_score", 0.0)
    semantic_score = distilbert_data.get("semantic_score", 0.0)
    
    # Apply the mathematical formula
    final_risk = calculate_late_fusion(signal_score, semantic_score, payload.identity_score)
    
    # Define intervention threshold
    threat_level = "CRITICAL" if final_risk > 0.75 else "SAFE"
    action = "DUCK_AUDIO" if threat_level == "CRITICAL" else "NONE"
    
    return {
        "status": "success",
        "threat": threat_level,
        "action": action,
        "late_fusion_score": round(final_risk, 3),
        "breakdown": {
            "signal": signal_score,
            "semantic": semantic_score,
            "identity": payload.identity_score
        }
    }