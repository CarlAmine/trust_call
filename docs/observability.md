# Observability Guide

This document describes the Prometheus metrics and Grafana dashboards for Trust-Call.

---

## Prometheus Scrape Targets

Configuration: `monitoring/prometheus.yml`

| Job name | Target | Metrics path | What it scrapes |
|---|---|---|---|
| `rawnet_audio_ai` | `rawnet-service:8000` | `/metrics` | RawNet FastAPI HTTP metrics (via `prometheus-fastapi-instrumentator`) |
| `distilbert_semantic_ai` | `distilbert-service:8002` | `/metrics` | DistilBERT FastAPI HTTP metrics |
| `iep3_identity_gateway` | `host.docker.internal:8080` | `/metrics` | Custom backend gateway metrics (see below) |
| `prometheus` | `localhost:9090` | `/metrics` | Prometheus self-scrape |

### How to verify Prometheus is scraping
1. Open `http://localhost:9090/targets`
2. All four targets should show `State: UP`

---

## Grafana Dashboard

### Location
- Provisioning: `monitoring/grafana/provisioning/`
- Dashboard JSON: `monitoring/grafana/dashboards/`
- Dashboard name: `Trust-Call AI Services`

### How to open
1. Start with `docker compose up`
2. Open `http://localhost:3000`
3. Default credentials: `admin` / `admin`
4. Navigate to **Dashboards** → **Trust-Call AI Services**

### Grafana on the cloud VM
- URL: `http://35.189.221.158:3000`

---

## Available Metrics

### RawNet Service (IEP1) – via prometheus-fastapi-instrumentator

| Metric | Type | Description |
|---|---|---|
| `http_requests_total` | Counter | Total HTTP requests by method, path, status |
| `http_request_duration_seconds` | Histogram | Request latency distribution |
| `http_requests_in_progress` | Gauge | In-flight requests |

**Rubric support:** M3 (monitoring), T2 (IEP1 inference observable)

### DistilBERT Service (IEP2) – via prometheus-fastapi-instrumentator

| Metric | Type | Description |
|---|---|---|
| `http_requests_total` | Counter | Total HTTP requests by method, path, status |
| `http_request_duration_seconds` | Histogram | Request latency distribution |
| `http_requests_in_progress` | Gauge | In-flight requests |

**Rubric support:** M3 (monitoring), T3 (IEP2 inference observable)

### EEP / IEP3 Backend Gateway – custom metrics at `/metrics`

| Metric | Type | Labels | Description | Rubric support |
|---|---|---|---|---|
| `trust_call_gateway_sessions_started_total` | Counter | `source` (webrtc / live_validation) | Live call sessions started | M3, T4 |
| `trust_call_gateway_audio_frames_total` | Counter | – | Raw WebRTC audio frames received | M3 |
| `trust_call_gateway_audio_chunks_total` | Counter | – | 3-second audio chunks processed through pipeline | M3, T4 |
| `trust_call_iep3_identity_results_total` | Counter | `status` | IEP3 decisions by outcome (verified, mismatch, not_enrolled, candidate_collecting, …) | M3, T1, T3 |
| `trust_call_iep3_candidate_embeddings_total` | Counter | – | TOFU candidate embeddings collected before user confirmation | M3, T1 |
| `trust_call_iep3_candidate_enrollments_total` | Counter | `status` (enrolled / discarded) | TOFU enrollment outcomes | M3 |
| `trust_call_gateway_fusion_results_total` | Counter | `status` (SAFE / THREAT DETECTED / IDENTITY REVIEW / …) | EEP late fusion outcomes | M3, T4, Q1 |
| `trust_call_gateway_errors_total` | Counter | `source` | Gateway errors by source | M3, S3 |
| `trust_call_gateway_active_sessions` | Gauge | – | Live sessions currently retained in memory | M3 |
| `trust_call_iep3_enrolled_profiles` | Gauge | – | Speaker profiles stored in identity store | M3, T1 |

### Key Queries for Grafana / PromQL

```promql
# EEP fusion rate (all outcomes)
rate(trust_call_gateway_fusion_results_total[1m])

# THREAT DETECTED rate specifically
rate(trust_call_gateway_fusion_results_total{status="THREAT DETECTED"}[1m])

# IEP3 identity decision breakdown
rate(trust_call_iep3_identity_results_total[1m])

# Audio chunk throughput
rate(trust_call_gateway_audio_chunks_total[1m])

# Backend error rate
rate(trust_call_gateway_errors_total[1m])

# RawNet inference latency p95
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job="rawnet_audio_ai"}[5m]))

# DistilBERT inference latency p95
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job="distilbert_semantic_ai"}[5m]))
```

---

## ML-Specific Observability Signals

| Signal | Where it appears | How to observe |
|---|---|---|
| Spoof score distribution | `trust_call_iep3_identity_results_total` + WebSocket telemetry `signal_score` | Grafana panel or WebSocket log |
| Semantic risk score distribution | WebSocket telemetry `semantic_score` field | WebSocket log / Grafana (requires custom metric, see below) |
| Identity verification confidence | `trust_call_iep3_identity_results_total` by status; `identity_score` in WebSocket telemetry | WebSocket telemetry |
| Model / service errors | `trust_call_gateway_errors_total` | Grafana error panel |
| Latency p95 | `http_request_duration_seconds` histograms on IEP1 and IEP2 | Grafana latency panel |
| Fallback rate | `trust_call_gateway_errors_total{source=\"rawnet\"}` vs chunks total | Prometheus query |
| Active sessions | `trust_call_gateway_active_sessions` | Grafana gauge panel |
| Enrolled profiles | `trust_call_iep3_enrolled_profiles` | Grafana gauge panel |

### TODO for full ML signal coverage
To track spoof probability and semantic score as Prometheus histograms (for drift detection), add these custom metrics to `server.py`:
```python
# Example (not yet implemented):
metrics.observe_histogram("trust_call_spoof_score", value=synthetic_score)
metrics.observe_histogram("trust_call_semantic_score", value=semantic_score)
```
This is a P1 item in `docs/production_hardening.md`.

---

## Alert Recommendations

| Alert | Condition | Severity |
|---|---|---|
| Backend service down | `up{job="iep3_identity_gateway"} == 0` | Critical |
| High error rate | `rate(trust_call_gateway_errors_total[5m]) > 0.1` | Warning |
| High threat detection rate | `rate(trust_call_gateway_fusion_results_total{status="THREAT DETECTED"}[5m]) > 1` | Info |
| RawNet latency spike | `histogram_quantile(0.95, ...) > 2.0` | Warning |

Alerts are not yet configured in Grafana. Adding alert rules is a P1 hardening item.
