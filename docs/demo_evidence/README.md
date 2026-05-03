# Demo Evidence Collection Guide

This folder is the target for all screenshots, logs, and JSON outputs collected before submission or presentation.

> **Do not fabricate evidence.** All items below must be captured from a live running system.

---

## Required Screenshots / Logs

Capture each item and save it using the naming convention below.

| # | Evidence | How to capture |
|---|---|---|
| 01 | Docker Compose services running | `docker compose ps` or Docker Desktop screenshot |
| 02 | Backend `/health` or `/metrics` response | curl or browser screenshot |
| 03 | RawNet service `/metrics` response | curl or browser screenshot |
| 04 | Semantic/DistilBERT service `/metrics` response | curl or browser screenshot |
| 05 | Prometheus `/metrics` or targets page | Browser screenshot of `http://localhost:9090/targets` |
| 06 | Grafana dashboard showing live counters | Browser screenshot of `http://localhost:3000` |
| 07 | Mobile app demo screen | Android screenshot during a live call |
| 08 | End-to-end trace log with final risk score | `docker compose logs trust-call-backend` excerpt |

---

## Required API Checks

Run these commands while services are running (locally or against the cloud VM).

### Backend health / metrics
```bash
# Metrics endpoint (custom Prometheus format)
curl http://localhost:8080/metrics

# Interactive API docs
curl http://localhost:8080/docs

# List current live sessions
curl http://localhost:8080/identity/live/sessions

# IEP3 identity config
curl http://localhost:8080/identity/config
```

### RawNet prediction (requires a WAV file encoded as base64)
```bash
# Generate a small test WAV and encode it
python - <<'EOF'
import base64, wave, struct, math
samples = [int(32767 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(16000)]
with wave.open('/tmp/test.wav', 'w') as f:
    f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
    f.writeframes(struct.pack('<' + 'h' * len(samples), *samples))
with open('/tmp/test.wav', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()
print(b64[:80], '...')
EOF

# POST to RawNet (replace <BASE64> with full output from above)
curl -X POST http://localhost:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"base64_audio": "<BASE64>"}'
```

### DistilBERT semantic prediction
```bash
# Scam-like text
curl -X POST http://localhost:8002/predict \
  -H 'Content-Type: application/json' \
  -d '{"scrubbed_text": "This is urgent, please send money via wire transfer to verify your account."}'

# Benign text
curl -X POST http://localhost:8002/predict \
  -H 'Content-Type: application/json' \
  -d '{"scrubbed_text": "Hey, just calling to confirm dinner plans tonight."}'

# Empty text (should return insufficient_text)
curl -X POST http://localhost:8002/predict \
  -H 'Content-Type: application/json' \
  -d '{"scrubbed_text": ""}'
```

### Identity enroll (requires a real audio clip as base64)
```bash
curl -X POST http://localhost:8080/identity/enroll \
  -H 'Content-Type: application/json' \
  -d '{
    "caller_id": "demo_user_001",
    "base64_audio": "<BASE64_WAV>",
    "allow_update": false,
    "safe_to_enroll": true
  }'
```

### Identity verify
```bash
curl -X POST http://localhost:8080/identity/verify \
  -H 'Content-Type: application/json' \
  -d '{
    "caller_id": "demo_user_001",
    "base64_audio": "<BASE64_WAV>"
  }'
```

### Check enrollment status
```bash
curl http://localhost:8080/identity/enrollment/demo_user_001
```

---

## Evidence Naming Convention

Save all files in `docs/demo_evidence/generated/` using these exact names:

```
docs/demo_evidence/generated/
  01_docker_compose_ps.png
  02_backend_metrics.png
  03_rawnet_metrics.png
  04_semantic_metrics.png
  05_prometheus_targets.png
  06_grafana_dashboard.png
  07_mobile_demo.png
  08_end_to_end_trace.log
  rawnet_predict_response.json
  semantic_predict_scam.json
  semantic_predict_benign.json
  identity_enroll_response.json
  identity_verify_response.json
```

---

## Automated Collection

The script `scripts/collect_demo_evidence.py` will:
- Call all known local endpoints
- Save JSON/text outputs to `docs/demo_evidence/generated/`
- Print a PASS/FAIL summary for each check
- Fail gracefully if services are unavailable

```bash
python scripts/collect_demo_evidence.py
```

Screenshots (Grafana, mobile app) must still be captured manually.
