# start_services.ps1
# Helper script to launch the local cloud backend for development and testing

Write-Host "🚀 Starting Trust-Call Microservices Architecture..." -ForegroundColor Cyan
Write-Host "This will spawn 3 separate background windows. Keep them open while testing!" -ForegroundColor Yellow

# 1. Start RawNet Service (Port 8000)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { cd rawnet-service; if (Test-Path .venv\Scripts\Activate.ps1) { .\.venv\Scripts\Activate.ps1 }; Write-Host '--- RAWNET SERVICE ---' -ForegroundColor Magenta; uvicorn main:app --port 8000 }"

# 2. Start DistilBERT Service (Port 8002)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { cd distilbert-service; if (Test-Path .venv\Scripts\Activate.ps1) { .\.venv\Scripts\Activate.ps1 }; Write-Host '--- DISTILBERT SERVICE ---' -ForegroundColor Magenta; uvicorn main:app --port 8002 }"

# 3. Start EEP Gateway (Port 8001)
# We start this last so the internal models have a second to boot their lifespan events
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { cd eep-gateway; if (Test-Path .venv\Scripts\Activate.ps1) { .\.venv\Scripts\Activate.ps1 }; Write-Host '--- EEP GATEWAY ---' -ForegroundColor Green; uvicorn main:app --port 8001 }"

Write-Host ""
Write-Host "✅ All services launched!" -ForegroundColor Green
Write-Host "Rawnet (IEP1):       http://localhost:8000"
Write-Host "DistilBERT (IEP2b):  http://localhost:8002"
Write-Host "EEP Gateway:         http://localhost:8001"
Write-Host ""
Write-Host "👉 The mobile app should point to http://[YOUR-IP]:8001/analyze" -ForegroundColor Cyan
