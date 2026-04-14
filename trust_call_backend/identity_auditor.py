from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


TARGET_SAMPLE_RATE = 16000
MIN_SPEECH_SECONDS = 1.5
MIN_RMS = 0.003
DEFAULT_MATCH_THRESHOLD = 0.82
DEFAULT_REVIEW_THRESHOLD = 0.68
DEFAULT_EMA_ALPHA = 0.20
EMBEDDER_NAME = "prototype_spectral_v1"


@dataclass
class IdentityResult:
    caller_id: str
    status: str
    identity_score: float
    similarity: float | None
    match_confidence: float | None
    display_text: str
    reason: str | None
    enrolled: bool
    duration_seconds: float

    def to_telemetry(self) -> dict[str, Any]:
        return {
            "identity_score": round(self.identity_score, 4),
            "identity_match": self.display_text,
            "identity_status": self.status,
            "identity_reason": self.reason,
            "identity_enrolled": self.enrolled,
        }


class IdentityEnrollmentStore:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _caller_filename(self, caller_id: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", caller_id.strip())
        normalized = normalized.strip("._")
        if not normalized:
            raise ValueError("caller_id must contain at least one valid character")
        return f"{normalized}.json"

    def path_for(self, caller_id: str) -> Path:
        return self.root_dir / self._caller_filename(caller_id)

    def exists(self, caller_id: str) -> bool:
        return self.path_for(caller_id).is_file()

    def load(self, caller_id: str) -> dict[str, Any] | None:
        path = self.path_for(caller_id)
        if not path.is_file():
            return None

        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, caller_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = self.path_for(caller_id)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        return payload

    def delete(self, caller_id: str) -> bool:
        path = self.path_for(caller_id)
        if not path.is_file():
            return False
        path.unlink()
        return True


class PrototypeSpeakerEmbedder:
    def __init__(self, target_sample_rate: int = TARGET_SAMPLE_RATE):
        self.target_sample_rate = target_sample_rate

    def extract(self, audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, dict[str, float]]:
        waveform = _prepare_waveform(audio, sample_rate, self.target_sample_rate)
        duration_seconds = len(waveform) / self.target_sample_rate
        rms = float(np.sqrt(np.mean(np.square(waveform)))) if waveform.size else 0.0

        if duration_seconds < MIN_SPEECH_SECONDS:
            raise ValueError("insufficient_audio")
        if rms < MIN_RMS:
            raise ValueError("low_energy")

        frame_size = int(0.025 * self.target_sample_rate)
        hop_size = int(0.010 * self.target_sample_rate)
        if len(waveform) < frame_size:
            raise ValueError("insufficient_audio")

        frames = _frame_signal(waveform, frame_size, hop_size)
        window = np.hanning(frame_size).astype(np.float32)
        fft = np.fft.rfft(frames * window[None, :], n=512)
        magnitude = np.abs(fft).astype(np.float32)
        log_magnitude = np.log1p(magnitude)

        spectral_profile = log_magnitude.mean(axis=0)[:96]
        frame_energy = np.log1p(np.mean(np.square(frames), axis=1))
        zero_cross_rate = np.mean(
            np.abs(np.diff(np.signbit(frames), axis=1)), axis=1
        ).astype(np.float32)

        temporal_stats = np.array(
            [
                float(np.mean(frame_energy)),
                float(np.std(frame_energy)),
                float(np.mean(zero_cross_rate)),
                float(np.std(zero_cross_rate)),
                float(np.percentile(frame_energy, 25)),
                float(np.percentile(frame_energy, 75)),
            ],
            dtype=np.float32,
        )

        embedding = np.concatenate([spectral_profile, temporal_stats], axis=0).astype(
            np.float32
        )
        embedding = _l2_normalize(embedding)

        metadata = {
            "duration_seconds": round(duration_seconds, 6),
            "rms": round(rms, 8),
            "sample_rate_hz": float(self.target_sample_rate),
            "embedding_dim": float(embedding.shape[0]),
        }
        return embedding, metadata


class IdentityAuditor:
    def __init__(
        self,
        store: IdentityEnrollmentStore,
        embedder: PrototypeSpeakerEmbedder | None = None,
        match_threshold: float = DEFAULT_MATCH_THRESHOLD,
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    ):
        if review_threshold >= match_threshold:
            raise ValueError("review_threshold must be lower than match_threshold")

        self.store = store
        self.embedder = embedder or PrototypeSpeakerEmbedder()
        self.match_threshold = match_threshold
        self.review_threshold = review_threshold

    def get_enrollment_status(self, caller_id: str) -> dict[str, Any]:
        profile = self.store.load(caller_id)
        if profile is None:
            return {
                "caller_id": caller_id,
                "enrolled": False,
            }

        return {
            "caller_id": caller_id,
            "enrolled": True,
            "embedder": profile.get("embedder"),
            "created_at_utc": profile.get("created_at_utc"),
            "updated_at_utc": profile.get("updated_at_utc"),
            "num_updates": profile.get("num_updates", 0),
            "last_duration_seconds": profile.get("last_duration_seconds"),
        }

    def enroll_from_base64(
        self,
        caller_id: str,
        base64_audio: str,
        allow_update: bool = False,
        ema_alpha: float = DEFAULT_EMA_ALPHA,
    ) -> dict[str, Any]:
        if not 0.0 < ema_alpha <= 1.0:
            raise ValueError("ema_alpha must be in the interval (0, 1]")

        audio, sample_rate = decode_base64_audio(base64_audio)
        embedding, metadata = self.embedder.extract(audio, sample_rate)

        now = _utc_now()
        existing_profile = self.store.load(caller_id)

        if existing_profile is not None and allow_update:
            previous = np.array(existing_profile["embedding"], dtype=np.float32)
            blended = ((1.0 - ema_alpha) * previous) + (ema_alpha * embedding)
            embedding_to_store = _l2_normalize(blended).tolist()
            created_at = existing_profile.get("created_at_utc", now)
            num_updates = int(existing_profile.get("num_updates", 0)) + 1
        else:
            embedding_to_store = embedding.tolist()
            created_at = now
            num_updates = 0

        payload = {
            "caller_id": caller_id,
            "embedder": EMBEDDER_NAME,
            "embedding": embedding_to_store,
            "created_at_utc": created_at,
            "updated_at_utc": now,
            "num_updates": num_updates,
            "last_duration_seconds": metadata["duration_seconds"],
            "last_rms": metadata["rms"],
            "target_sample_rate_hz": self.embedder.target_sample_rate,
        }
        self.store.save(caller_id, payload)
        return {
            "caller_id": caller_id,
            "enrolled": True,
            "updated": existing_profile is not None and allow_update,
            "embedder": EMBEDDER_NAME,
            "duration_seconds": metadata["duration_seconds"],
            "rms": metadata["rms"],
            "num_updates": payload["num_updates"],
            "ema_alpha": ema_alpha if existing_profile is not None and allow_update else None,
        }

    def verify_chunk(
        self,
        caller_id: str,
        audio: np.ndarray,
        sample_rate: int,
    ) -> IdentityResult:
        duration_seconds = _duration_seconds(audio, sample_rate)

        if not caller_id or caller_id == "unknown":
            return IdentityResult(
                caller_id=caller_id or "unknown",
                status="missing_caller_id",
                identity_score=0.0,
                similarity=None,
                match_confidence=None,
                display_text="Missing Caller ID",
                reason="identity_auditor_requires_claimed_identity",
                enrolled=False,
                duration_seconds=duration_seconds,
            )

        profile = self.store.load(caller_id)
        if profile is None:
            return IdentityResult(
                caller_id=caller_id,
                status="not_enrolled",
                identity_score=0.0,
                similarity=None,
                match_confidence=None,
                display_text="Not Enrolled",
                reason="no_local_master_vector",
                enrolled=False,
                duration_seconds=duration_seconds,
            )

        try:
            embedding, _ = self.embedder.extract(audio, sample_rate)
        except ValueError as exc:
            reason = str(exc)
            display_text = (
                "Need More Speech" if reason == "insufficient_audio" else "Speech Too Quiet"
            )
            return IdentityResult(
                caller_id=caller_id,
                status=reason,
                identity_score=0.0,
                similarity=None,
                match_confidence=None,
                display_text=display_text,
                reason=reason,
                enrolled=True,
                duration_seconds=duration_seconds,
            )

        master_vector = _l2_normalize(np.array(profile["embedding"], dtype=np.float32))
        similarity = float(np.dot(master_vector, embedding))
        match_confidence = float(np.clip((similarity + 1.0) / 2.0, 0.0, 1.0))
        identity_score = float(1.0 - match_confidence)

        if match_confidence >= self.match_threshold:
            status = "match"
            display_text = f"Match ({match_confidence:.2f})"
        elif match_confidence >= self.review_threshold:
            status = "review"
            display_text = f"Review ({match_confidence:.2f})"
        else:
            status = "mismatch"
            display_text = f"Mismatch ({match_confidence:.2f})"

        return IdentityResult(
            caller_id=caller_id,
            status=status,
            identity_score=identity_score,
            similarity=similarity,
            match_confidence=match_confidence,
            display_text=display_text,
            reason=None,
            enrolled=True,
            duration_seconds=duration_seconds,
        )


def decode_base64_audio(base64_audio: str) -> tuple[np.ndarray, int]:
    raw_bytes = base64.b64decode(base64_audio)
    with io.BytesIO(raw_bytes) as buffer:
        waveform, sample_rate = sf.read(buffer, dtype="float32")
    return waveform, int(sample_rate)


def _prepare_waveform(
    audio: np.ndarray, sample_rate: int, target_sample_rate: int
) -> np.ndarray:
    waveform = np.asarray(audio, dtype=np.float32)
    if waveform.ndim == 2:
        if waveform.shape[1] == 1:
            waveform = waveform[:, 0]
        else:
            waveform = np.mean(waveform, axis=1)
    elif waveform.ndim != 1:
        waveform = waveform.reshape(-1)

    if waveform.size == 0:
        raise ValueError("insufficient_audio")

    peak = float(np.max(np.abs(waveform)))
    if peak > 1.5:
        waveform = waveform / 32768.0

    waveform = waveform - np.mean(waveform)
    if sample_rate != target_sample_rate:
        waveform = _resample_linear(waveform, sample_rate, target_sample_rate)
    return waveform.astype(np.float32)


def _resample_linear(
    waveform: np.ndarray, source_rate: int, target_rate: int
) -> np.ndarray:
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("sample_rate_must_be_positive")
    if source_rate == target_rate:
        return waveform

    duration = len(waveform) / float(source_rate)
    target_length = max(int(round(duration * target_rate)), 1)
    source_positions = np.linspace(0.0, duration, num=len(waveform), endpoint=False)
    target_positions = np.linspace(0.0, duration, num=target_length, endpoint=False)
    return np.interp(target_positions, source_positions, waveform).astype(np.float32)


def _frame_signal(waveform: np.ndarray, frame_size: int, hop_size: int) -> np.ndarray:
    frame_count = 1 + max((len(waveform) - frame_size) // hop_size, 0)
    frames = np.zeros((frame_count, frame_size), dtype=np.float32)
    for index in range(frame_count):
        start = index * hop_size
        frames[index] = waveform[start : start + frame_size]
    return frames


def _duration_seconds(audio: np.ndarray, sample_rate: int) -> float:
    waveform = np.asarray(audio)
    if waveform.ndim == 2:
        length = waveform.shape[0]
    else:
        length = waveform.size
    if sample_rate <= 0:
        return 0.0
    return round(length / float(sample_rate), 6)


def _l2_normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise ValueError("zero_norm_embedding")
    return (vector / norm).astype(np.float32)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
