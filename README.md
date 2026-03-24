# openclaw-trace-collection

Instrumented reverse proxy for recording request/response traces from an OpenAI-compatible inference server (e.g. vLLM).

## Setup

```bash
pip install fastapi httpx uvicorn
```

## Quick Start

```bash
# 1. Start your inference engine
bash launch_vllm.sh

# 2. Start the proxy (points at vLLM on :8200, listens on :8201)
python3 instrumented_proxy.py
```

Point your clients at `http://<host>:8201` instead of the backend directly.

## Session Recording

```bash
# Start a session — begins logging to traces/my_session_trace.jsonl
curl -X POST localhost:8201/session/start -d '{"name": "my_session"}'

# Check status — active session, request count, past sessions, saved files
curl localhost:8201/session/status

# End session — stops logging, closes the file
curl -X POST localhost:8201/session/end
```

## Trace Format

Each line in `{name}_trace.jsonl` is a JSON object:

```jsonc
// Request (from client)
{"type": "request", "request_id": "...", "timestamp_rel_s": 0.123, "method": "POST", "path": "/v1/chat/completions", "body": {"model": "...", "messages": [...]}}

// Response (from backend)
{"type": "response", "request_id": "...", "timestamp_rel_s": 0.456, "status_code": 200, "body": {"choices": [...]}}
```

- `timestamp_rel_s` — seconds since session start
- `request_id` — links each request to its response
- Full conversation history (`messages` array) is captured on every request
- Streaming responses have SSE events parsed into `body_parsed_events`

## Config

| Env var | Default | Description |
|---|---|---|
| `BACKEND_URL` | `http://localhost:8200` | Inference server address |
| `PROXY_PORT` | `8201` | Port the proxy listens on |
| `TRACE_DIR` | `./traces` | Where trace files are saved |
