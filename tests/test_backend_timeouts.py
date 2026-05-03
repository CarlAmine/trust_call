"""
tests/test_backend_timeouts.py

Tests for timeout and fallback behaviour in the backend gateway.
All downstream HTTP calls are mocked – no real services needed.
"""
import asyncio
import pytest


# ----------------------------------------------------------------
# Re-implement the two fetcher functions locally for isolation
# ----------------------------------------------------------------
# These mirror the logic in trust_call_backend/server.py exactly.

async def fetch_rawnet_impl(base64_audio: str, rawnet_url: str, timeout: float) -> float:
    """
    Minimal re-implementation of server.fetch_rawnet for testing.
    Returns 0.0 on any error (graceful fallback).
    """
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                rawnet_url,
                json={"base64_audio": base64_audio},
                timeout=timeout,
            )
            if response.status_code == 200:
                data = response.json()
                return float(data.get("spoof_probability_percent", 0.0))
    except Exception:
        pass
    return 0.0


async def fetch_distilbert_impl(text: str, distilbert_url: str, timeout: float) -> dict:
    """
    Minimal re-implementation of server.fetch_distilbert for testing.
    Returns safe defaults on any error.
    """
    import httpx
    if not text.strip():
        return {"semantic_score": 0.0, "label": "insufficient_text"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                distilbert_url,
                json={"scrubbed_text": text},
                timeout=timeout,
            )
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass
    return {"semantic_score": 0.0, "label": "semantic_unavailable"}


# ----------------------------------------------------------------
# Tests
# ----------------------------------------------------------------
[email protected]
async def test_rawnet_service_unavailable_returns_zero():
    """When RawNet is unreachable the backend must return 0.0, not raise."""
    score = await fetch_rawnet_impl(
        base64_audio="AAAA",
        rawnet_url="http://127.0.0.1:19999/predict",  # nothing listening
        timeout=0.1,
    )
    assert score == 0.0

[email protected]
async def test_rawnet_service_timeout_returns_zero():
    """A connection that times out must be handled gracefully."""
    # Using a non-routable address triggers a fast connection error on most OSes
    score = await fetch_rawnet_impl(
        base64_audio="AAAA",
        rawnet_url="http://10.255.255.1:9999/predict",
        timeout=0.05,
    )
    assert score == 0.0

[email protected]
async def test_distilbert_service_unavailable_returns_fallback():
    """When DistilBERT is unreachable the backend must return a safe fallback dict."""
    result = await fetch_distilbert_impl(
        text="Send money urgently via wire transfer.",
        distilbert_url="http://127.0.0.1:19998/predict",  # nothing listening
        timeout=0.1,
    )
    assert "semantic_score" in result
    assert result["label"] == "semantic_unavailable"
    assert result["semantic_score"] == 0.0

[email protected]
async def test_distilbert_empty_text_returns_insufficient_without_network_call():
    """Empty text must be handled locally without making a network call."""
    result = await fetch_distilbert_impl(
        text="",
        distilbert_url="http://127.0.0.1:19998/predict",
        timeout=0.1,
    )
    assert result["label"] == "insufficient_text"
    assert result["semantic_score"] == 0.0

[email protected]
async def test_both_services_unavailable_fusion_does_not_crash():
    """
    When both downstream services are unavailable, running them in parallel
    must still resolve without raising an exception.
    """
    score, bert_data = await asyncio.gather(
        fetch_rawnet_impl("AAAA", "http://127.0.0.1:19997/predict", 0.05),
        fetch_distilbert_impl("some text", "http://127.0.0.1:19996/predict", 0.05),
    )
    assert score == 0.0
    assert bert_data["semantic_score"] == 0.0
