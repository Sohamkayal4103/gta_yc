import json

from backend.utils import llm_logging


def test_llm_logging_writes_request_response_and_events(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_logging, "GAMES_DIR", str(tmp_path))

    source_file = tmp_path / "room.mp4"
    source_file.write_bytes(b"fake video bytes")

    call_ctx = llm_logging.start_call(
        "session_a",
        "agent_x",
        "operation_y",
        {
            "text": "hello",
            "raw_bytes": b"\x01\x02",
            "upload": llm_logging.LoggedFile(str(source_file), mime_type="video/mp4"),
        },
    )
    llm_logging.finish_call(
        call_ctx,
        response_payload={"result": "ok", "audio": b"\x03\x04"},
    )

    session_log_dir = tmp_path / "session_a" / "llm_logs"
    call_dir = session_log_dir / call_ctx["call_id"]

    request_json = json.loads((call_dir / "request.json").read_text())
    response_json = json.loads((call_dir / "response.json").read_text())

    assert request_json["session_id"] == "session_a"
    assert response_json["status"] == "ok"
    assert request_json["request"]["upload"]["mime_type"] == "video/mp4"

    request_blobs = list((call_dir / "request_blobs").iterdir())
    response_blobs = list((call_dir / "response_blobs").iterdir())
    assert request_blobs
    assert response_blobs

    events = (session_log_dir / "events.jsonl").read_text().strip().splitlines()
    assert len(events) == 2
