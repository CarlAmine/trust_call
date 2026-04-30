import asyncio
import base64
import io
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import numpy as np
import soundfile as sf
from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from trust_call_backend.identity_config import load_identity_auditor_config
    from trust_call_backend.identity_auditor import (
        ECAPASpeakerEmbedder,
        IdentityAuditor,
        IdentityEnrollmentStore,
        IdentityPolicyError,
        IdentityResult,
        decode_base64_audio,
    )
except ModuleNotFoundError:
    from identity_config import load_identity_auditor_config  # type: ignore
    from identity_auditor import (  # type: ignore
        ECAPASpeakerEmbedder,
        IdentityAuditor,
        IdentityEnrollmentStore,
        IdentityPolicyError,
        IdentityResult,
        decode_base64_audio,
    )

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Offer(BaseModel):
    sdp: str
    type: str
    caller_id: str = "unknown"


class IdentityEnrollmentPayload(BaseModel):
    caller_id: str
    base64_audio: str
    allow_update: bool = False
    ema_alpha: float | None = None
    safe_to_enroll: bool = False
    safe_to_update: bool = False
    synthetic_score: float | None = Field(default=None, ge=0.0, le=1.0)
    coercion_score: float | None = Field(default=None, ge=0.0, le=1.0)


class IdentityVerificationPayload(BaseModel):
    caller_id: str
    base64_audio: str


class IdentityIdentificationPayload(BaseModel):
    base64_audio: str
    claimed_caller_id: str = "unknown"
    top_k: int = Field(default=3, ge=1, le=10)


class LiveIdentityValidationPayload(BaseModel):
    caller_id: str
    base64_audio: str
    session_id: str | None = None
    dispatch_signal_auditor: bool = False
    identify_if_unenrolled: bool = True
    top_k: int = Field(default=3, ge=1, le=10)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        if not self.active_connections:
            print("WARNING: Telemetry event emitted without an attached WebSocket client.")
            return

        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as exc:
                print(f"Failed to send websocket message: {exc}")


class LiveIdentityMonitor:
    def __init__(self, max_sessions: int = 20, max_events_per_session: int = 8):
        self.max_sessions = max_sessions
        self.max_events_per_session = max_events_per_session
        self._sessions: dict[str, dict] = {}
        self._order: deque[str] = deque()

    def start_session(self, caller_id: str, source: str) -> dict:
        session_id = str(uuid4())
        now = _utc_now()
        session = {
            "session_id": session_id,
            "caller_id": caller_id,
            "source": source,
            "state": "offer_received" if source == "webrtc" else "validation_started",
            "created_at_utc": now,
            "last_updated_at_utc": now,
            "track_connected_at_utc": None,
            "track_kind": None,
            "sample_rate_hz": None,
            "frames_received": 0,
            "last_frame_at_utc": None,
            "last_frame_shape": None,
            "buffered_duration_seconds": 0.0,
            "chunks_processed": 0,
            "last_chunk_peak": None,
            "last_chunk_duration_seconds": None,
            "last_identity_result": None,
            "recent_identity_events": [],
            "last_signal_score": None,
            "last_signal_threat": None,
            "last_error": None,
        }
        self._sessions[session_id] = session
        self._order.append(session_id)
        while len(self._order) > self.max_sessions:
            evicted = self._order.popleft()
            self._sessions.pop(evicted, None)
        return session

    def mark_track_connected(self, session_id: str, track_kind: str | None = None) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        session["track_connected_at_utc"] = _utc_now()
        session["track_kind"] = track_kind
        session["state"] = "track_connected"
        session["last_updated_at_utc"] = session["track_connected_at_utc"]

    def record_frame(
        self,
        session_id: str,
        sample_rate: int,
        frame_shape: tuple[int, ...],
        buffered_duration_seconds: float,
    ) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        now = _utc_now()
        session["frames_received"] = int(session["frames_received"]) + 1
        session["sample_rate_hz"] = sample_rate
        session["last_frame_at_utc"] = now
        session["last_frame_shape"] = list(frame_shape)
        session["buffered_duration_seconds"] = round(float(buffered_duration_seconds), 3)
        session["state"] = "receiving_audio"
        session["last_updated_at_utc"] = now

    def record_chunk(
        self,
        session_id: str,
        identity_result: IdentityResult,
        sample_rate: int,
        chunk_peak: float,
    ) -> dict | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None

        now = _utc_now()
        chunk_index = int(session["chunks_processed"]) + 1
        event = {
            "chunk_index": chunk_index,
            "processed_at_utc": now,
            "sample_rate_hz": sample_rate,
            "chunk_peak": round(float(chunk_peak), 4),
            **identity_result.to_api_response(),
        }
        session["chunks_processed"] = chunk_index
        session["sample_rate_hz"] = sample_rate
        session["last_chunk_peak"] = event["chunk_peak"]
        session["last_chunk_duration_seconds"] = event["duration_seconds"]
        session["last_identity_result"] = event
        session["state"] = "identity_verified"
        session["last_updated_at_utc"] = now

        recent_events = session["recent_identity_events"]
        recent_events.append(event)
        if len(recent_events) > self.max_events_per_session:
            del recent_events[0 : len(recent_events) - self.max_events_per_session]
        return event

    def record_signal_result(self, session_id: str, signal_score: str, is_threat: bool) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        session["last_signal_score"] = signal_score
        session["last_signal_threat"] = bool(is_threat)
        session["state"] = "telemetry_broadcast"
        session["last_updated_at_utc"] = _utc_now()

    def record_error(self, session_id: str, error: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        session["last_error"] = error
        session["state"] = "error"
        session["last_updated_at_utc"] = _utc_now()

    def list_sessions(self) -> list[dict]:
        sessions = [self._sessions[session_id] for session_id in reversed(self._order)]
        return [self._summary(session) for session in sessions]

    def get_session(self, session_id: str) -> dict | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return {
            **self._summary(session),
            "last_signal_score": session["last_signal_score"],
            "last_signal_threat": session["last_signal_threat"],
            "last_error": session["last_error"],
            "recent_identity_events": list(session["recent_identity_events"]),
        }

    def _summary(self, session: dict) -> dict:
        return {
            "session_id": session["session_id"],
            "caller_id": session["caller_id"],
            "source": session["source"],
            "state": session["state"],
            "created_at_utc": session["created_at_utc"],
            "last_updated_at_utc": session["last_updated_at_utc"],
            "track_connected_at_utc": session["track_connected_at_utc"],
            "track_kind": session["track_kind"],
            "sample_rate_hz": session["sample_rate_hz"],
            "frames_received": session["frames_received"],
            "last_frame_at_utc": session["last_frame_at_utc"],
            "last_frame_shape": session["last_frame_shape"],
            "buffered_duration_seconds": session["buffered_duration_seconds"],
            "chunks_processed": session["chunks_processed"],
            "last_chunk_peak": session["last_chunk_peak"],
            "last_chunk_duration_seconds": session["last_chunk_duration_seconds"],
            "last_identity_result": session["last_identity_result"],
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


manager = ConnectionManager()
live_identity_monitor = LiveIdentityMonitor()
peer_connections: set[RTCPeerConnection] = set()
state_root = Path(__file__).resolve().parent / "state"
identity_config = load_identity_auditor_config()
identity_store = IdentityEnrollmentStore(state_root / "identity_profiles")
identity_auditor = IdentityAuditor(
    store=identity_store,
    config=identity_config,
    embedder=ECAPASpeakerEmbedder(
        config=identity_config,
        savedir=identity_config.resolve_model_savedir(),
    ),
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print("Incoming WebSocket connection.")
    await manager.connect(websocket)
    print("WebSocket accepted.")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("WebSocket client disconnected.")
    except Exception as exc:
        print(f"WebSocket crashed: {exc}")


@app.get("/identity/enrollment/{caller_id}")
async def get_identity_enrollment_status(caller_id: str):
    return identity_auditor.get_enrollment_status(caller_id)


@app.get("/identity/config")
async def get_identity_config():
    return identity_auditor.get_policy_snapshot()


@app.get("/identity/live/sessions")
async def list_live_identity_sessions():
    sessions = live_identity_monitor.list_sessions()
    return {
        "count": len(sessions),
        "sessions": sessions,
    }


@app.get("/identity/live/sessions/{session_id}")
async def get_live_identity_session(session_id: str):
    session = live_identity_monitor.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Live identity session not found")
    return session


@app.post("/identity/enroll")
async def enroll_identity(payload: IdentityEnrollmentPayload):
    try:
        return identity_auditor.enroll_from_base64(
            caller_id=payload.caller_id,
            base64_audio=payload.base64_audio,
            allow_update=payload.allow_update,
            ema_alpha=payload.ema_alpha,
            safe_to_enroll=payload.safe_to_enroll,
            safe_to_update=payload.safe_to_update,
            synthetic_score=payload.synthetic_score,
            coercion_score=payload.coercion_score,
        )
    except IdentityPolicyError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.to_response()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/identity/verify")
async def verify_identity(payload: IdentityVerificationPayload):
    try:
        result = identity_auditor.verify_from_base64(
            caller_id=payload.caller_id,
            base64_audio=payload.base64_audio,
        )
        return result.to_api_response()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/identity/identify")
async def identify_identity(payload: IdentityIdentificationPayload):
    try:
        result = identity_auditor.identify_from_base64(
            base64_audio=payload.base64_audio,
            claimed_caller_id=payload.claimed_caller_id,
            top_k=payload.top_k,
        )
        return result.to_api_response()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/identity/live/validate")
async def validate_live_identity_chunk(payload: LiveIdentityValidationPayload):
    try:
        session = (
            live_identity_monitor.get_session(payload.session_id)
            if payload.session_id
            else None
        )
        if session is None:
            session = live_identity_monitor.start_session(
                caller_id=payload.caller_id,
                source="live_validation",
            )

        audio, sample_rate = decode_base64_audio(payload.base64_audio)
        identity_result = await process_identity_chunk(
            caller_id=payload.caller_id,
            audio=audio,
            sample_rate=sample_rate,
            session_id=session["session_id"],
            dispatch_signal_auditor=payload.dispatch_signal_auditor,
            identify_if_unenrolled=payload.identify_if_unenrolled,
            top_k=payload.top_k,
        )
        return {
            "session_id": session["session_id"],
            "identity": identity_result.to_api_response(),
            "session": live_identity_monitor.get_session(session["session_id"]),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.delete("/identity/enrollment/{caller_id}")
async def delete_identity_enrollment(caller_id: str):
    deleted = identity_store.delete(caller_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return {
        "caller_id": caller_id,
        "deleted": True,
    }


def build_fusion_status(identity_result: IdentityResult) -> str:
    if identity_result.status in {"mismatch", "unknown_speaker"}:
        return "IDENTITY REVIEW"
    if identity_result.status in {"review", "identity_candidate"}:
        return "IDENTITY CAUTION"
    return "ANALYZING"


async def send_to_rawnet(base64_audio: str, identity_result: IdentityResult, session_id: str):
    payload = {"base64_audio": base64_audio}
    signal_score = "Signal Unavailable"
    is_threat = False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://127.0.0.1:8000/predict",
                json=payload,
                timeout=5.0,
            )
            if response.status_code == 200:
                data = response.json()
                spoof_float = float(data.get("spoof_probability_percent", 0.0))
                real_float = float(data.get("real_probability_percent", 0.0))
                print(f"[AI AUDITOR] AI: {spoof_float}% | Human: {real_float}%")
                is_threat = spoof_float > 50.0
                signal_score = (
                    f"{spoof_float}% AI (Deepfake)"
                    if is_threat
                    else f"{real_float}% Human"
                )
            else:
                print(f"AI server error: {response.text}")
    except Exception as exc:
        print(f"Failed to reach AI server on port 8000: {exc}")
    finally:
        live_identity_monitor.record_signal_result(session_id, signal_score, is_threat)
        session = live_identity_monitor.get_session(session_id)
        await manager.broadcast(
            {
                "session_id": session_id,
                "caller_id": identity_result.caller_id,
                "signal_score": signal_score,
                "is_threat": is_threat,
                "semantic_intent": "Low Risk",
                "fusion_status": build_fusion_status(identity_result),
                "identity_chunk_count": (
                    session["chunks_processed"] if session is not None else None
                ),
                **identity_result.to_telemetry(),
            }
        )


async def broadcast_identity_telemetry(identity_result: IdentityResult, session_id: str) -> None:
    session = live_identity_monitor.get_session(session_id)
    await manager.broadcast(
        {
            "session_id": session_id,
            "caller_id": identity_result.caller_id,
            "signal_score": "Analyzing...",
            "is_threat": False,
            "semantic_intent": "Low Risk",
            "fusion_status": build_fusion_status(identity_result),
            "identity_chunk_count": (
                session["chunks_processed"] if session is not None else None
            ),
            **identity_result.to_telemetry(),
        }
    )


async def process_identity_chunk(
    caller_id: str,
    audio: np.ndarray,
    sample_rate: int,
    session_id: str,
    dispatch_signal_auditor: bool = True,
    identify_if_unenrolled: bool = True,
    top_k: int = 3,
) -> IdentityResult:
    identity_result = identity_auditor.verify_chunk(
        caller_id=caller_id,
        audio=audio,
        sample_rate=sample_rate,
    )
    if identify_if_unenrolled and identity_result.status in {
        "missing_caller_id",
        "not_enrolled",
        "profile_incompatible",
    }:
        identity_result = identity_auditor.identify_chunk(
            audio=audio,
            sample_rate=sample_rate,
            claimed_caller_id=caller_id,
            top_k=top_k,
        )
    chunk_peak = float(np.max(np.abs(np.asarray(audio)))) if np.asarray(audio).size else 0.0
    live_identity_monitor.record_chunk(
        session_id=session_id,
        identity_result=identity_result,
        sample_rate=sample_rate,
        chunk_peak=chunk_peak,
    )
    await broadcast_identity_telemetry(identity_result, session_id)

    if dispatch_signal_auditor:
        wav_io = io.BytesIO()
        sf.write(wav_io, audio, sample_rate, format="WAV", subtype="PCM_16")
        wav_bytes = wav_io.getvalue()
        base64_audio = base64.b64encode(wav_bytes).decode("utf-8")
        asyncio.create_task(send_to_rawnet(base64_audio, identity_result, session_id=session_id))

    return identity_result


async def consume_audio_track(track, caller_id: str, session_id: str):
    print("Audio buffer engine started.")
    audio_buffer = []
    sample_rate = 0
    target_seconds = 3.0
    chunk_counter = 0

    while True:
        try:
            frame = await track.recv()
            raw_audio = frame.to_ndarray()
            audio_array = _audio_frame_to_mono_int16(raw_audio, len(frame.layout.channels))

            if sample_rate == 0:
                sample_rate = frame.sample_rate
                print(f"Audio format locked at {sample_rate}Hz.")
                live_identity_monitor.mark_track_connected(
                    session_id,
                    track_kind=getattr(track, "kind", None),
                )

            audio_buffer.append(audio_array)
            total_samples = sum(arr.shape[1] for arr in audio_buffer)
            current_duration = total_samples / sample_rate
            live_identity_monitor.record_frame(
                session_id=session_id,
                sample_rate=sample_rate,
                frame_shape=tuple(raw_audio.shape),
                buffered_duration_seconds=current_duration,
            )

            if current_duration >= target_seconds:
                chunk_counter += 1
                combined_audio = np.concatenate(audio_buffer, axis=1).T
                max_volume = np.max(np.abs(combined_audio))
                print(
                    f"Dispatching live chunk {chunk_counter} | peak={float(max_volume):.2f}"
                )
                await process_identity_chunk(
                    caller_id=caller_id,
                    audio=combined_audio,
                    sample_rate=sample_rate,
                    session_id=session_id,
                    dispatch_signal_auditor=True,
                )
                audio_buffer.clear()
        except Exception as exc:
            print(f"Audio stream ended or disconnected: {exc}")
            live_identity_monitor.record_error(session_id, str(exc))
            break


def _audio_frame_to_mono_int16(audio_array: np.ndarray, num_channels: int) -> np.ndarray:
    audio_array = np.asarray(audio_array)
    is_float = np.issubdtype(audio_array.dtype, np.floating)

    if audio_array.ndim == 1:
        mono = audio_array.reshape(1, -1)
    elif num_channels > 1:
        if audio_array.shape[0] == 1:
            reshaped = audio_array.reshape(-1, num_channels)
            mono = np.mean(reshaped, axis=1, keepdims=True).T
        else:
            mono = np.mean(audio_array, axis=0, keepdims=True)
    else:
        mono = audio_array.reshape(1, -1)

    if is_float:
        return np.clip(mono * 32767.0, -32768, 32767).astype(np.int16)
    return mono.astype(np.int16)


@app.post("/offer")
async def process_offer(params: Offer):
    print("Received WebRTC offer from Trust-Call.")
    offer = RTCSessionDescription(sdp=params.sdp, type=params.type)
    pc = RTCPeerConnection()
    peer_connections.add(pc)
    live_session = live_identity_monitor.start_session(
        caller_id=params.caller_id,
        source="webrtc",
    )

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Peer connection state: {pc.connectionState}")
        if pc.connectionState in {"failed", "closed", "disconnected"}:
            peer_connections.discard(pc)
            live_identity_monitor.record_error(
                live_session["session_id"],
                f"peer_connection_{pc.connectionState}",
            )

    @pc.on("track")
    def on_track(track):
        print("Live audio track connected.")
        asyncio.ensure_future(
            consume_audio_track(track, params.caller_id, live_session["session_id"])
        )

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    print("Sending WebRTC answer back to mobile app.")
    return {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
        "session_id": live_session["session_id"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
