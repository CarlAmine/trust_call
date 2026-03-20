import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Trust-Call EEP Gateway")

# Define the URL of your local AI Microservice (Container 2)
RAWNET_SERVICE_URL = "http://localhost:8000/predict"

# The payload we expect from the mobile app
class AudioPayload(BaseModel):
    base64_audio: str

@app.post("/analyze")
async def analyze_audio(payload: AudioPayload):
    try:
        # 1. Forward the audio to the AI Brain (RawNet2 Microservice)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                RAWNET_SERVICE_URL,
                json={"base64_audio": payload.base64_audio},
                timeout=10.0 # Don't wait forever, drop the call if it takes too long
            )
            
        # 2. Check if the AI Brain crashed or threw an error
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="AI Inference Service Failed")
            
        # 3. Extract the raw percentages from the AI Brain
        ai_data = response.json()
        spoof_prob = ai_data.get("spoof_probability_percent", 0.0)
        real_prob = ai_data.get("real_probability_percent", 0.0)
        
        # 4. The Cloud Decision Logic (Business Logic)
        # If the AI is more than 50% sure it is a deepfake, block the call.
        if spoof_prob > 50.0:
            decision = "BLOCK"
            threat_level = "CRITICAL"
        else:
            decision = "ALLOW"
            threat_level = "SAFE"
            
        # 5. Return the hybrid payload back to the Mobile App
        return {
            "status": "success",
            "decision": decision,
            "threat_level": threat_level,
            "details": {
                "spoof_probability_percent": spoof_prob,
                "real_probability_percent": real_prob
            }
        }

    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="AI Brain is offline. Please ensure rawnet-service is running.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))