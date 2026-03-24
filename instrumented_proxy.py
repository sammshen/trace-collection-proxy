"""
Instrumented reverse proxy for vLLM (or any OpenAI-compatible server).

Sits between external clients and the inference engine, forwarding all
requests transparently while optionally recording full request/response
traces to JSONL files when a session is active.

Operator endpoints (not forwarded to backend):
    POST   /session/start   {"name": "my_session"}
    POST   /session/end
    GET    /session/status

Everything else is reverse-proxied to the backend.
"""

import asyncio
import json
import time
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8200")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "8201"))
TRACE_DIR = Path(os.environ.get("TRACE_DIR", "./traces"))
TRACE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
class SessionState:
    def __init__(self):
        self.active: bool = False
        self.name: Optional[str] = None
        self.start_time: Optional[float] = None
        self.trace_file = None
        self.request_count: int = 0
        self.finished_sessions: list[dict] = []
        self._lock = asyncio.Lock()

    async def start(self, name: str) -> dict:
        async with self._lock:
            if self.active:
                return {"error": f"Session '{self.name}' is already active. End it first."}
            self.active = True
            self.name = name
            self.start_time = time.time()
            self.request_count = 0
            path = TRACE_DIR / f"{name}_trace.jsonl"
            self.trace_file = open(path, "a")
            return {
                "status": "started",
                "session_name": name,
                "trace_file": str(path),
            }

    async def end(self) -> dict:
        async with self._lock:
            if not self.active:
                return {"error": "No active session."}
            info = {
                "session_name": self.name,
                "requests_recorded": self.request_count,
                "duration_s": round(time.time() - self.start_time, 3),
                "trace_file": self.trace_file.name,
            }
            self.trace_file.close()
            self.trace_file = None
            self.finished_sessions.append(info)
            self.active = False
            self.name = None
            self.start_time = None
            return {"status": "ended", **info}

    async def write(self, record: dict):
        async with self._lock:
            if self.active and self.trace_file:
                self.request_count += 1
                self.trace_file.write(json.dumps(record, default=str) + "\n")
                self.trace_file.flush()

    def status(self) -> dict:
        saved_files = sorted(TRACE_DIR.glob("*_trace.jsonl"))
        return {
            "active_session": {
                "name": self.name,
                "elapsed_s": round(time.time() - self.start_time, 3) if self.start_time else None,
                "requests_recorded": self.request_count,
            } if self.active else None,
            "finished_sessions": self.finished_sessions,
            "saved_trace_files": [str(f) for f in saved_files],
        }


session = SessionState()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Instrumented Proxy")


# ---- Operator endpoints ---------------------------------------------------

@app.post("/session/start")
async def session_start(request: Request):
    body = await request.json()
    name = body.get("name")
    if not name:
        return JSONResponse({"error": "Provide a 'name' field."}, status_code=400)
    result = await session.start(name)
    status_code = 200 if "status" in result else 409
    return JSONResponse(result, status_code=status_code)


@app.post("/session/end")
async def session_end():
    result = await session.end()
    status_code = 200 if "status" in result else 409
    return JSONResponse(result, status_code=status_code)


@app.get("/session/status")
async def session_status():
    return JSONResponse(session.status())


# ---- Reverse proxy --------------------------------------------------------

async def _read_body(request: Request) -> bytes:
    return await request.body()


def _parse_json_body(raw: bytes) -> Optional[dict]:
    try:
        return json.loads(raw)
    except Exception:
        return None



@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(request: Request, path: str):
    raw_body = await _read_body(request)
    parsed_body = _parse_json_body(raw_body)

    request_id = f"{time.time_ns()}"
    request_record = {
        "type": "request",
        "request_id": request_id,
        "timestamp_rel_s": round(time.time() - session.start_time, 6) if session.start_time else None,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "method": request.method,
        "path": f"/{path}",
        "query_params": dict(request.query_params),
        "headers": dict(request.headers),
        "body": parsed_body if parsed_body else raw_body.decode("utf-8", errors="replace") if raw_body else None,
    }

    if session.active:
        await session.write(request_record)

    # Forward to backend — always use stream=True so we can handle both cases
    url = f"{BACKEND_URL}/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}

    client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
    backend_req = client.build_request(
        method=request.method,
        url=url,
        headers=headers,
        content=raw_body,
        params=request.query_params,
    )
    backend_resp = await client.send(backend_req, stream=True)

    is_stream = "text/event-stream" in backend_resp.headers.get("content-type", "")
    resp_headers = {k: v for k, v in backend_resp.headers.items()
                    if k.lower() not in ("content-length", "transfer-encoding", "content-encoding")}

    if is_stream:
        async def streaming_generator():
            try:
                collected_chunks: list[str] = []
                async for chunk in backend_resp.aiter_bytes():
                    collected_chunks.append(chunk.decode("utf-8", errors="replace"))
                    yield chunk

                # Log after stream completes
                if session.active:
                    full_text = "".join(collected_chunks)
                    parsed_events = []
                    for line in full_text.splitlines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            evt = _parse_json_body(line[6:].encode())
                            if evt:
                                parsed_events.append(evt)

                    response_record = {
                        "type": "response",
                        "request_id": request_id,
                        "timestamp_rel_s": round(time.time() - session.start_time, 6) if session.start_time else None,
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "status_code": backend_resp.status_code,
                        "headers": dict(backend_resp.headers),
                        "body_raw": full_text if not parsed_events else None,
                        "body_parsed_events": parsed_events if parsed_events else None,
                    }
                    await session.write(response_record)
            finally:
                await backend_resp.aclose()
                await client.aclose()

        return StreamingResponse(
            streaming_generator(),
            status_code=backend_resp.status_code,
            headers=resp_headers,
            media_type=backend_resp.headers.get("content-type"),
        )

    # Non-streaming: read full body, close, then respond
    resp_body = await backend_resp.aread()
    await backend_resp.aclose()
    await client.aclose()

    if session.active:
        parsed_resp = _parse_json_body(resp_body)
        response_record = {
            "type": "response",
            "request_id": request_id,
            "timestamp_rel_s": round(time.time() - session.start_time, 6) if session.start_time else None,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status_code": backend_resp.status_code,
            "headers": dict(backend_resp.headers),
            "body": parsed_resp if parsed_resp else resp_body.decode("utf-8", errors="replace"),
        }
        await session.write(response_record)

    return Response(
        content=resp_body,
        status_code=backend_resp.status_code,
        headers=resp_headers,
        media_type=backend_resp.headers.get("content-type"),
    )


if __name__ == "__main__":
    print(f"Proxying to backend: {BACKEND_URL}")
    print(f"Traces will be saved to: {TRACE_DIR.resolve()}")
    print(f"Operator endpoints: /session/start, /session/end, /session/status")
    uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT)
