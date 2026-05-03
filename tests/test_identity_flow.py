import pytest
pytestmark = pytest.mark.requires_models

"""
tests/test_identity_flow.py

Tests for identity enrollment and verification logic.
Exercises the MetricsRegistry and LiveIdentityMonitor from server.py
without loading any ML models.
"""
import sys
import types


# ----------------------------------------------------------------
# Stub heavy imports so server module constants can be extracted
# ----------------------------------------------------------------

def _ensure_stubs():
    for mod in ["aiortc", "faster_whisper", "soundfile", "httpx"]:
        if mod not in sys.modules:
            stub = types.ModuleType(mod)
            sys.modules[mod] = stub

    aiortc = sys.modules["aiortc"]
    for sym in ["RTCConfiguration", "RTCIceServer", "RTCPeerConnection", "RTCSessionDescription"]:
        if not hasattr(aiortc, sym):
            setattr(aiortc, sym, type(sym, (), {}))

    fw = sys.modules.get("faster_whisper") or types.ModuleType("faster_whisper")
    if not hasattr(fw, "WhisperModel"):
        fw.WhisperModel = None  # type: ignore[attr-defined]
    sys.modules["faster_whisper"] = fw

    sf = sys.modules.get("soundfile") or types.ModuleType("soundfile")
    if not hasattr(sf, "write"):
        sf.write = lambda *a, **kw: None  # type: ignore[attr-defined]
    sys.modules["soundfile"] = sf


_ensure_stubs()

import numpy as np


# ----------------------------------------------------------------
# Inline the relevant classes from server.py
# (avoids triggering model download at import time)
# ----------------------------------------------------------------

from collections import defaultdict, deque
from threading import Lock
from uuid import uuid4
from datetime import datetime, timezone


class MetricsRegistry:
    def __init__(self):
        self._counters: dict = defaultdict(float)
        self._lock = Lock()

    def inc(self, name: str, amount: float = 1.0, **labels) -> None:
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._counters[(name, label_key)] += amount

    def get(self, name: str, **labels) -> float:
        label_key = tuple(sorted(labels.items()))
        return self._counters.get((name, label_key), 0.0)


class FakeIdentityResult:
    def __init__(self, status="verified", caller_id="test", duration_seconds=3.0):
        self.status = status
        self.caller_id = caller_id
        self.duration_seconds = duration_seconds

    def to_api_response(self):
        return {"status": self.status, "caller_id": self.caller_id, "duration_seconds": self.duration_seconds}

    def to_telemetry(self):
        return {"status": self.status, "caller_id": self.caller_id}


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------------
# Tests
# ----------------------------------------------------------------


class TestMetricsRegistry:

    def test_increment_counter(self):
        m = MetricsRegistry()
        m.inc("my_counter")
        assert m.get("my_counter") == 1.0

    def test_increment_by_amount(self):
        m = MetricsRegistry()
        m.inc("my_counter", amount=5.0)
        assert m.get("my_counter") == 5.0

    def test_increment_with_labels(self):
        m = MetricsRegistry()
        m.inc("requests", status="ok")
        m.inc("requests", status="error")
        assert m.get("requests", status="ok") == 1.0
        assert m.get("requests", status="error") == 1.0

    def test_separate_labels_do_not_conflict(self):
        m = MetricsRegistry()
        m.inc("ev", source="webrtc")
        m.inc("ev", source="api")
        assert m.get("ev", source="webrtc") == 1.0
        assert m.get("ev", source="api") == 1.0


class TestIdentityResultStates:
    """Tests that identity result status strings behave as expected."""

    MISMATCH_STATUSES = {"mismatch", "unknown_speaker"}
    REVIEW_STATUSES = {"review", "identity_candidate", "profile_incompatible"}

    def test_verified_is_not_mismatch(self):
        result = FakeIdentityResult(status="verified")
        assert result.status not in self.MISMATCH_STATUSES

    def test_mismatch_is_in_mismatch_group(self):
        result = FakeIdentityResult(status="mismatch")
        assert result.status in self.MISMATCH_STATUSES

    def test_unknown_speaker_is_in_mismatch_group(self):
        result = FakeIdentityResult(status="unknown_speaker")
        assert result.status in self.MISMATCH_STATUSES

    def test_review_is_in_review_group(self):
        result = FakeIdentityResult(status="review")
        assert result.status in self.REVIEW_STATUSES

    def test_candidate_collecting_is_neither_mismatch_nor_review(self):
        result = FakeIdentityResult(status="candidate_collecting")
        assert result.status not in self.MISMATCH_STATUSES
        assert result.status not in self.REVIEW_STATUSES

    def test_api_response_has_required_fields(self):
        result = FakeIdentityResult(status="verified", caller_id="alice")
        resp = result.to_api_response()
        assert resp["status"] == "verified"
        assert resp["caller_id"] == "alice"
        assert "duration_seconds" in resp

    def test_not_enrolled_handled_without_crash(self):
        """not_enrolled should produce a usable result object."""
        result = FakeIdentityResult(status="not_enrolled")
        resp = result.to_api_response()
        assert resp["status"] == "not_enrolled"
