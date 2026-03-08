"""Structured per-session LLM trace logging with binary payload capture."""

from __future__ import annotations

import hashlib
import json
import base64
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import GAMES_DIR


_COUNTER_LOCK = threading.Lock()
_SESSION_COUNTERS: dict[str, int] = {}


class LoggedFile:
    """Reference to a file whose bytes should be logged as a raw request blob."""

    def __init__(self, path: str, mime_type: str | None = None):
        self.path = path
        self.mime_type = mime_type


class _BlobStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.counter = 0

    def _next_name(self, mime_type: str | None) -> str:
        self.counter += 1
        ext = _extension_for_mime(mime_type)
        return f"{self.counter:04d}{ext}"

    def write_bytes(self, data: bytes, mime_type: str | None = None) -> dict[str, Any]:
        filename = self._next_name(mime_type)
        output_path = self.directory / filename

        digest = hashlib.sha256()
        digest.update(data)
        output_path.write_bytes(data)

        return {
            "kind": "blob",
            "file": filename,
            "relative_path": str(output_path.relative_to(self.directory.parent)),
            "mime_type": mime_type or "application/octet-stream",
            "byte_length": len(data),
            "sha256": digest.hexdigest(),
        }

    def write_file(self, file_path: str, mime_type: str | None = None) -> dict[str, Any]:
        src = Path(file_path)
        if not src.exists():
            return {
                "kind": "missing_file",
                "path": str(file_path),
            }

        filename = self._next_name(mime_type)
        output_path = self.directory / filename

        digest = hashlib.sha256()
        size = 0
        with src.open("rb") as in_f, output_path.open("wb") as out_f:
            while True:
                chunk = in_f.read(1024 * 1024)
                if not chunk:
                    break
                out_f.write(chunk)
                digest.update(chunk)
                size += len(chunk)

        return {
            "kind": "blob",
            "file": filename,
            "relative_path": str(output_path.relative_to(self.directory.parent)),
            "source_path": str(src),
            "mime_type": mime_type or "application/octet-stream",
            "byte_length": size,
            "sha256": digest.hexdigest(),
        }


def _extension_for_mime(mime_type: str | None) -> str:
    if not mime_type:
        return ".bin"

    mapping = {
        "application/json": ".json",
        "text/plain": ".txt",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
    }
    return mapping.get(mime_type, ".bin")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_") or "unknown"


def _session_log_dir(session_id: str) -> Path:
    base = Path(GAMES_DIR) / session_id / "llm_logs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _initialize_session_counter(session_id: str, session_dir: Path) -> int:
    max_seen = 0
    pattern = re.compile(r"^(\d{4})_")
    for entry in session_dir.iterdir():
        if not entry.is_dir():
            continue
        match = pattern.match(entry.name)
        if match:
            max_seen = max(max_seen, int(match.group(1)))
    _SESSION_COUNTERS[session_id] = max_seen
    return max_seen


def _next_call_dir(session_id: str, agent: str, operation: str) -> tuple[Path, int]:
    session_dir = _session_log_dir(session_id)

    with _COUNTER_LOCK:
        if session_id not in _SESSION_COUNTERS:
            _initialize_session_counter(session_id, session_dir)
        _SESSION_COUNTERS[session_id] += 1
        call_index = _SESSION_COUNTERS[session_id]

    name = f"{call_index:04d}_{_safe_slug(agent)}_{_safe_slug(operation)}"
    call_dir = session_dir / name
    call_dir.mkdir(parents=True, exist_ok=True)
    return call_dir, call_index


def _append_event(session_id: str, event: dict[str, Any]) -> None:
    events_path = _session_log_dir(session_id) / "events.jsonl"
    line = json.dumps(event, ensure_ascii=False)
    with _COUNTER_LOCK:
        with events_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _serialize_payload(
    payload: Any,
    blob_store: _BlobStore,
    seen: set[int] | None = None,
) -> Any:
    if seen is None:
        seen = set()

    if payload is None or isinstance(payload, (bool, int, float, str)):
        return payload

    if isinstance(payload, LoggedFile):
        return blob_store.write_file(payload.path, mime_type=payload.mime_type)

    if isinstance(payload, (bytes, bytearray, memoryview)):
        return blob_store.write_bytes(bytes(payload))

    if isinstance(payload, Path):
        return str(payload)

    if isinstance(payload, dict):
        return {
            str(k): _serialize_payload(v, blob_store, seen)
            for k, v in payload.items()
        }

    if isinstance(payload, (list, tuple, set)):
        return [_serialize_payload(item, blob_store, seen) for item in payload]

    obj_id = id(payload)
    if obj_id in seen:
        return {"kind": "circular_ref", "repr": repr(payload)}
    seen.add(obj_id)

    inline_data = getattr(payload, "inline_data", None)
    if inline_data is not None:
        mime_type = getattr(inline_data, "mime_type", None)
        data = getattr(inline_data, "data", None)
        blob_meta = None

        if isinstance(data, str):
            try:
                decoded = base64.b64decode(data, validate=False)
                blob_meta = blob_store.write_bytes(decoded, mime_type=mime_type)
            except Exception:
                blob_meta = blob_store.write_bytes(data.encode("utf-8"))
        elif isinstance(data, (bytes, bytearray, memoryview)):
            blob_meta = blob_store.write_bytes(bytes(data), mime_type=mime_type)

        return {
            "text": getattr(payload, "text", None),
            "thought": getattr(payload, "thought", None),
            "inline_data": blob_meta,
        }

    parts = getattr(payload, "parts", None)
    if isinstance(parts, (list, tuple)):
        return {
            "text": getattr(payload, "text", None),
            "parts": [_serialize_payload(part, blob_store, seen) for part in parts],
            "repr": repr(payload),
        }

    if hasattr(payload, "__dict__"):
        obj_dict = {}
        for key, value in vars(payload).items():
            if key.startswith("__"):
                continue
            obj_dict[str(key)] = _serialize_payload(value, blob_store, seen)
        if obj_dict:
            return obj_dict

    if hasattr(payload, "model_dump") and callable(payload.model_dump):
        try:
            dumped = payload.model_dump(mode="python")
        except TypeError:
            dumped = payload.model_dump()
        return _serialize_payload(dumped, blob_store, seen)

    if hasattr(payload, "to_dict") and callable(payload.to_dict):
        try:
            return _serialize_payload(payload.to_dict(), blob_store, seen)
        except Exception:
            pass

    return repr(payload)


def start_call(
    session_id: str | None,
    agent: str,
    operation: str,
    request_payload: Any,
) -> dict[str, Any] | None:
    """Create a per-call log folder and write request payload artifacts."""
    if not session_id:
        return None

    call_dir, call_index = _next_call_dir(session_id, agent, operation)
    request_blob_dir = call_dir / "request_blobs"
    request_store = _BlobStore(request_blob_dir)

    request_record = {
        "timestamp_utc": _utc_now_iso(),
        "session_id": session_id,
        "agent": agent,
        "operation": operation,
        "call_index": call_index,
        "request": _serialize_payload(request_payload, request_store),
    }
    with (call_dir / "request.json").open("w", encoding="utf-8") as f:
        json.dump(request_record, f, indent=2, ensure_ascii=False)

    _append_event(
        session_id,
        {
            "timestamp_utc": request_record["timestamp_utc"],
            "event": "call_started",
            "call_id": call_dir.name,
            "call_index": call_index,
            "agent": agent,
            "operation": operation,
        },
    )

    return {
        "session_id": session_id,
        "agent": agent,
        "operation": operation,
        "call_dir": call_dir,
        "call_id": call_dir.name,
        "call_index": call_index,
    }


def finish_call(
    call_ctx: dict[str, Any] | None,
    response_payload: Any = None,
    error: Exception | str | None = None,
) -> None:
    """Write response payload artifacts and close the per-call trace."""
    if not call_ctx:
        return

    response_blob_dir = call_ctx["call_dir"] / "response_blobs"
    response_store = _BlobStore(response_blob_dir)
    status = "error" if error else "ok"

    response_record = {
        "timestamp_utc": _utc_now_iso(),
        "session_id": call_ctx["session_id"],
        "agent": call_ctx["agent"],
        "operation": call_ctx["operation"],
        "call_index": call_ctx["call_index"],
        "status": status,
        "error": str(error) if error else None,
        "response": _serialize_payload(response_payload, response_store),
    }
    with (call_ctx["call_dir"] / "response.json").open("w", encoding="utf-8") as f:
        json.dump(response_record, f, indent=2, ensure_ascii=False)

    _append_event(
        call_ctx["session_id"],
        {
            "timestamp_utc": response_record["timestamp_utc"],
            "event": "call_finished",
            "call_id": call_ctx["call_id"],
            "call_index": call_ctx["call_index"],
            "agent": call_ctx["agent"],
            "operation": call_ctx["operation"],
            "status": status,
            "error": str(error) if error else None,
        },
    )


def log_file_upload(
    session_id: str | None,
    agent: str,
    operation: str,
    file_path: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Initialize upload-call logging and include the full file bytes as a blob."""
    payload = {
        "file_path": file_path,
        "file_payload": LoggedFile(file_path),
        "metadata": metadata or {},
    }
    return start_call(session_id, agent, operation, payload)
