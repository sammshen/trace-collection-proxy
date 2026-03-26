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

`converter.py` converts a raw proxy trace into [AIPerf Mooncake-compatible](https://github.com/ai-dynamo/aiperf) format — one JSON per line with the original OpenAI `messages` array and output token count.

```bash
python converter.py <trace.jsonl> <output.jsonl>

# Convert all traces
for f in traces/*_trace.jsonl; do
  python converter.py "$f" "converted/$(basename $f)"
done
```

Output format:

```json
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "hello"}], "output_length": 42}
{"messages": [...], "output_length": 35, "tools": [{"type": "function", "function": {"name": "web_search", ...}}]}
```

Each converted file is a single session. See `converted/converted_example.jsonl` for a dummy example and `converted/FORMAT.md` for the full spec.

### Aggregator

`aggregator.py` combines all per-session converted traces into a single file, adding `session_id` to each entry.

```bash
# Basic aggregation (14 sessions)
python aggregator.py converted/aggregated.jsonl

# Duplicate sessions to increase concurrency headroom (14 x 10 = 140 sessions)
python aggregator.py converted/aggregated.jsonl --duplicate 10
```

Output:

```json
{"messages": [...], "output_length": 42, "session_id": "ai_fashion_industry"}
```

When using `--duplicate N`, the first replica of each session is unchanged. Subsequent replicas get a unique prefix breaker (`[session-id: ai_fashion_industry_r1]`) prepended to the first message so they don't share KV cache prefixes with the original. This is important for realistic benchmarking — without it, duplicated sessions would get artificial cache hits.

### Replay with AIPerf

```bash
aiperf profile \
  --input-file converted/aggregated.jsonl \
  --custom-dataset-type mooncake_trace \
  --endpoint-type chat \
  --model <model_name> \
  --url <server_url>/v1 \
  --concurrency 10
```

`--concurrency` sets how many sessions run in parallel. Within each session, turns are strictly sequential — each turn waits for the previous response before sending, since each request depends on the prior response (e.g. tool call results get appended to the history). AIPerf groups turns by `session_id` and uses sticky routing so all turns in a session go to the same worker.

If you need higher concurrency than the number of sessions, use `--duplicate` in the aggregator to create more sessions. AIPerf's `--dataset-sampling-strategy sequential` (the default for traces) will wrap around when it runs out of sessions, but wrapped sessions will have identical prefixes. `--duplicate` avoids this by giving each replica a unique prefix.

Other useful flags:
- `--concurrency-ramp-duration <secs>` — gradually ramp from 1 to target concurrency
- `--prefill-concurrency <n>` — limit how many requests can be in the prefill phase at once
- `--user-centric-rate --num-users <n>` — alternative mode that simulates N users with realistic inter-turn delays

### Trace structure

Each line in a converted file represents one LLM request with the **full conversation history** as the client sent it. In agentic tool-use sessions, the pattern looks like:

1. `[system, user]` — initial request with tool definitions
2. `[system, user, assistant(tool_call), tool(result)]` — LLM called a tool, client executed it and sent the result back
3. `[system, user, assistant(tool_call), tool(result), assistant(tool_call), tool(result)]` — another tool call round
4. ...continues until the LLM produces a final text response

Each request is a superset of the previous one — this is how the OpenAI chat completions API works. The LLM needs the full history to maintain context. See `converted/converted_example.jsonl` for a complete 4-turn example showing this pattern.

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
