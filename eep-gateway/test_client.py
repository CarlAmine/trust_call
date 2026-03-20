import httpx
import base64
import os
import sys
import json

# 1. Point this to the audio file in your eep-gateway folder
test_audio_path = "test_voice.wav"

if not os.path.exists(test_audio_path):
    print(f"❌ Error: '{test_audio_path}' not found. Please copy your test_voice.wav into the eep-gateway folder.")
    sys.exit(1)

print(f"1. Phone: Reading raw audio from {test_audio_path}...")
with open(test_audio_path, "rb") as audio_file:
    raw_audio_bytes = audio_file.read()

print("2. Phone: Converting audio to Base64 payload...")
base64_audio = base64.b64encode(raw_audio_bytes).decode('utf-8')
payload = {"base64_audio": base64_audio}

print("3. Phone: Sending payload to EEP Gateway (http://localhost:8001/analyze)...")
try:
    # Send to the Gateway (Port 8001)
    response = httpx.post("http://localhost:8001/analyze", json=payload, timeout=15.0)
    
    print("\n=== MOBILE APP: RECEIVED RESPONSE FROM CLOUD ===")
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        
        # Display the formatted decision
        print("\n✅ CLOUD DECISION LOGIC:")
        print(f"Action:       {data.get('decision')}")
        print(f"Threat Level: {data.get('threat_level')}")
        
        # Display the raw AI details
        details = data.get('details', {})
        print("\n📊 RAW AI TELEMETRY:")
        print(f"Spoof (AI) Probability:   {details.get('spoof_probability_percent')}%")
        print(f"Real (Human) Probability: {details.get('real_probability_percent')}%")
        
        print("\nFull JSON Payload:")
        print(json.dumps(data, indent=2))
        
    else:
        print(f"❌ Error Details: {response.text}")
        
except httpx.ConnectError:
    print("❌ Connection failed. Make sure your Gateway (Port 8001) is running!")