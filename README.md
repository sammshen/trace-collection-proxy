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
python instrumented_proxy.py
```

Point your clients at `http://<host>:8201` instead of the backend directly.

## Session Recording

```bash
# Start a session
curl -X POST localhost:8201/session/start -d '{"name": "my_session"}'

# Check status
curl localhost:8201/session/status

# End session
curl -X POST localhost:8201/session/end

# View the trace
cat traces/my_session_trace.jsonl | python -m json.tool
```

### Single Request

```bash
curl -X POST localhost:8201/session/start -d '{"name": "single_request"}'

curl localhost:8201/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "MiniMaxAI/MiniMax-M2.5", "messages": [{"role": "user", "content": "hello"}]}'

curl -X POST localhost:8201/session/end

python converter.py traces/single_request_trace.jsonl converted/single_request.jsonl
```

### Multi-Turn Conversation

```bash
curl -X POST localhost:8201/session/start -d '{"name": "test_multiturn"}'

python test_multiturn.py

curl -X POST localhost:8201/session/end

python converter.py traces/test_multiturn_trace.jsonl converted/test_multiturn.jsonl
python converter.py traces/nyc_house_trace.jsonl converted/nyc_house_trace.jsonl

```

Sends 4 turns with growing conversation history. Each request includes the full `messages` array (system + all prior user/assistant turns), so the trace captures the complete context at every step.

### Converter

`converter.py` converts a trace into a simple replay format — one JSON per line with the stringified conversation and expected output length.

```bash
python converter.py <trace.jsonl> <output.jsonl>
```

Output format:

```json
{"input": "[system] You are a helpful assistant.\n[user] hello", "output_length": 42}
```

## Terminal Output

The proxy prints color-coded live output:

```
>>> POST /v1/chat/completions  model=MiniMax-M2.5 | 3 msgs | last=user: hello
<<< 200 /v1/chat/completions (1523ms)  The answer is 4. | tok=45/12

[REC] >>> POST /v1/chat/completions  ...    # [REC] = session active
<<< 200 /v1/chat/completions (2301ms) [stream]  ...

==========================================
[SESSION] STARTED: experiment_1  -> traces/experiment_1_trace.jsonl
==========================================
```

## Trace Format

Each line in `traces/{name}_trace.jsonl` is a JSON object:

```jsonc
// Request (from client)
{"type": "request", "request_id": "...", "timestamp_rel_s": 0.123, "method": "POST", "path": "/v1/chat/completions", "body": {"model": "...", "messages": [...]}}

// Response (from backend)
{"type": "response", "request_id": "...", "timestamp_rel_s": 0.456, "status_code": 200, "body": {"choices": [...]}}
```

- `timestamp_rel_s` — seconds since session start
- `request_id` — links each request to its response
- Full conversation history (`messages` array) is captured on every request
- Streaming responses are assembled into the same format as non-streaming

## Config

| Env var | Default | Description |
|---|---|---|
| `BACKEND_URL` | `http://localhost:8200` | Inference server address |
| `PROXY_PORT` | `8201` | Port the proxy listens on |
| `TRACE_DIR` | `./traces` | Where trace files are saved |
