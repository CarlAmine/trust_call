# Evaluation Results Template

> **Instructions:** Fill in every `TODO` field with real numbers collected from a live evaluation run before submission. Do not leave placeholders or enter fabricated values. If a metric is not yet measured, write `NOT_MEASURED` and explain why.

Evaluation date: `TODO`
Evaluated by: `TODO`
Commit SHA: `TODO`

---

## IEP1: RawNet2 Signal Auditor

Dataset: `TODO (e.g., ASVspoof 2019 LA eval set, N samples)`
Model weights file: `fine_tuned_DF_model.pth`
Device: `TODO (CPU / GPU)`

| Metric | Value |
|---|---|
| Accuracy | TODO |
| Precision (spoof) | TODO |
| Recall (spoof) | TODO |
| F1 Score (spoof) | TODO |
| ROC-AUC | TODO |
| Equal Error Rate (EER) | TODO |
| False Positive Rate | TODO |
| False Negative Rate | TODO |
| Latency p50 (ms) | TODO |
| Latency p95 (ms) | TODO |

Notes: `TODO`

How to reproduce:
```bash
cd rawnet-service
python evaluate_rawnet.py --data_dir /path/to/dataset --output results/rawnet_eval.json
```

---

## IEP2: DistilBERT Semantic Auditor

Dataset: `TODO (e.g., N scam transcripts, N benign transcripts)`
Model: `./custom_scam_model` (fine-tuned DistilBERT)

| Metric | Value |
|---|---|
| Accuracy | TODO |
| Precision (suspicious) | TODO |
| Recall (suspicious) | TODO |
| F1 Score (suspicious) | TODO |
| ROC-AUC | TODO |
| False Positive Rate | TODO |
| False Negative Rate | TODO |
| Latency p50 (ms) | TODO |
| Latency p95 (ms) | TODO |
| Neural model availability | TODO (% requests served by neural vs heuristic fallback) |

Notes: `TODO`

How to reproduce:
```bash
pytest distilbert-service/test_main.py -v
# For a full eval set, extend distilbert-service/test_main.py with a parametrized dataset loader
```

---

## IEP3: ECAPA-TDNN Identity Auditor

Dataset: `TODO (e.g., VoxCeleb1 eval pairs, N genuine, N impostor)`
Threshold policy: `configs/iep3_identity.json`

| Metric | Value |
|---|---|
| Equal Error Rate (EER) | TODO |
| TAR @ FAR=1% | TODO |
| TAR @ FAR=0.1% | TODO |
| Precision (accept) | TODO |
| Recall (accept) | TODO |
| F1 Score (accept) | TODO |
| Genuine pair mean cosine similarity | TODO |
| Impostor pair mean cosine similarity | TODO |
| Latency p50 (ms) | TODO |
| Latency p95 (ms) | TODO |

Notes: `TODO`

How to reproduce:
```bash
python scripts/evaluate_iep3.py --data_dir data/evaluation/iep3
python scripts/plot_iep3_metrics.py
```

---

## EEP Late Fusion (End-to-End)

Dataset: `TODO (N labeled call recordings)`
Evaluation method: `TODO`

| Metric | Value |
|---|---|
| System accuracy | TODO |
| Threat precision | TODO |
| Threat recall | TODO |
| False alarm rate | TODO |
| Miss rate | TODO |
| End-to-end latency p50 (ms) | TODO |
| End-to-end latency p95 (ms) | TODO |
| IEP1 timeout rate | TODO |
| IEP2 timeout rate | TODO |
| Degraded response rate | TODO |

Notes: `TODO`

---

## Baseline Comparison

If applicable, compare against a keyword-only baseline (the regex heuristic in `distilbert-service/main.py`).

| System | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| Heuristic baseline | TODO | TODO | TODO | TODO |
| Fine-tuned DistilBERT | TODO | TODO | TODO | TODO |
| Full Trust-Call fusion | TODO | TODO | TODO | TODO |

---

## Infrastructure Metrics

| Metric | Value |
|---|---|
| RawNet container startup time (s) | TODO |
| DistilBERT container startup time (s) | TODO |
| Backend startup time (s) | TODO |
| Peak memory usage per service (MB) | TODO |
| Docker image sizes (MB) | TODO |
