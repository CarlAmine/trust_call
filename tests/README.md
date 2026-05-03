# Trust-Call Test Suite

This directory contains pytest tests for Trust-Call's backend and AI services.

## Test files

| File | What it tests |
|---|---|
| `test_backend_fusion.py` | EEP fusion / risk scoring logic |
| `test_backend_validation.py` | Request validation (semantic service, bad payloads) |
| `test_backend_timeouts.py` | Timeout and fallback behavior (mocked httpx) |
| `test_identity_flow.py` | IdentityEnrollmentStore (no model weights) |
| `test_rawnet_service.py` | RawNet health, audio, invalid input (mocked model) |
| `test_semantic_service.py` | DistilBERT heuristic mode, no model download |

## Running all tests

```bash
pip install pytest pytest-asyncio httpx fastapi pydantic
pytest tests/ -v
```

## Notes

- Tests here do **not** require large model weight files.
- Tests needing torch/transformers are in `distilbert-service/test_main.py`.
- Add `@pytest.mark.requires_models` to any test needing real weights so CI can skip it.
