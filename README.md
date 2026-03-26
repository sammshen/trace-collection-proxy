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

### Pipeline

The recommended pipeline is: **anonymize raw traces → convert → aggregate**.

```bash
# 1. Anonymize raw traces
for f in traces/*_trace.jsonl; do
  python anonymizer.py "$f" "traces/anonymized/$(basename $f)"
done

# 2. Convert anonymized traces
for f in traces/anonymized/*_trace.jsonl; do
  python converter.py "$f" "converted/$(basename $f)"
done

# 3. Aggregate into a single file
python aggregator.py converted/aggregated.jsonl
```

### Converter

`converter.py` converts a raw proxy trace into [AIPerf-compatible](https://github.com/ai-dynamo/aiperf) format — one JSON per line with the original OpenAI `messages` array and output token count.

```bash
python converter.py <trace.jsonl> <output.jsonl>
```

Output format:

```json
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "hello"}], "output_length": 42}
{"messages": [...], "tools": [{"type": "function", "function": {"name": "web_search", ...}}], "output_length": 35}
```

Each converted file is a single session. See `converted/converted_example.jsonl` for a dummy example and `converted/FORMAT.md` for the full spec.

### Aggregator

`aggregator.py` combines all per-session converted traces into a single file, adding `session_id` to each entry.

```bash
# Basic aggregation (12 sessions)
python aggregator.py converted/aggregated.jsonl

# Duplicate sessions to increase concurrency headroom (12 x 10 = 120 sessions)
python aggregator.py converted/aggregated.jsonl --duplicate 10
```

Output:

```json
{"messages": [...], "output_length": 42, "session_id": "ai_fashion_industry"}
```

When using `--duplicate N`, the first replica of each session is unchanged. Subsequent replicas get a unique prefix breaker (`[session-id: ai_fashion_industry_r1]`) prepended to the first user message so they don't share KV cache prefixes with the original. The system message is left unchanged so it can still share cache across sessions. This is important for realistic benchmarking — without it, duplicated sessions would get artificial cache hits.

### Replay with AIPerf

```bash
# Quick test (174 requests across 12 sessions)
aiperf profile \
  --input-file final/aggregated.jsonl \
  --custom-dataset-type mooncake_trace \
  --endpoint-type chat \
  --streaming \
  --model <model_name> \
  --url <server_url>/v1 \
  --concurrency 10 \
  --request-count 174 \
  --extra-inputs ignore_eos:true

# Full benchmark (87000 requests across 6000 sessions, 30min cap)
aiperf profile \
  --input-file final/aggregated_x500.jsonl \
  --custom-dataset-type mooncake_trace \
  --endpoint-type chat \
  --streaming \
  --model <model_name> \
  --url <server_url>/v1 \
  --concurrency 500 \
  --request-count 87000 \
  --benchmark-duration 1800 \
  --benchmark-grace-period 0 \
  --request-timeout-seconds 3600 \
  --extra-inputs ignore_eos:true \
  --export-level records \
  --ui-type simple \
  --random-seed 42 \
  --output-artifact-dir <output_dir>
```

`--request-count` should match the total number of entries in the trace file so all sessions complete all their turns. Without it, aiperf defaults to `concurrency * 2` total requests, which will cut most sessions short. `--benchmark-duration` acts as a time cap — the run stops at whichever limit is hit first. `--extra-inputs ignore_eos:true` forces the server to generate exactly `output_length` tokens instead of stopping early at EOS.

AIPerf reports throughput (output tokens/sec, requests/sec), Time to First Token (TTFT), Inter Token Latency (ITL), and end-to-end request latency — all with p50/p90/p99/avg/min/max breakdowns.

`--concurrency` sets how many sessions run in parallel. Within each session, turns are strictly sequential — each turn waits for the previous response before sending, since each request depends on the prior response (e.g. tool call results get appended to the history). AIPerf groups turns by `session_id` and uses sticky routing so all turns in a session go to the same worker.

If you need higher concurrency than the number of sessions, use `--duplicate` in the aggregator to create more sessions. AIPerf's `--dataset-sampling-strategy sequential` (the default for traces) will wrap around when it runs out of sessions, but wrapped sessions will have identical prefixes. `--duplicate` avoids this by giving each replica a unique prefix.

Other useful flags:
- `--concurrency-ramp-duration <secs>` — gradually ramp from 1 to target concurrency
- `--prefill-concurrency <n>` — limit how many requests can be in the prefill phase at once

### Benchmarking vLLM with LMCache

These traces have high prefix reuse (each turn resends the full conversation history), making them ideal for measuring KV cache offloading benefits. Estimated prefix reuse per session ranges from 64% to 95%.

**1. Baseline — vLLM only:**

```bash
# Start vLLM
bash launch_vllm.sh

# Benchmark
aiperf profile \
  --input-file final/aggregated.jsonl \
  --custom-dataset-type mooncake_trace \
  --endpoint-type chat \
  --streaming \
  --model MiniMaxAI/MiniMax-M2.5 \
  --url http://localhost:8200/v1 \
  --concurrency 10 \
  --request-count 174 \
  --extra-inputs ignore_eos:true
```

**2. With LMCache — vLLM + KV cache offloading:**

```bash
# Start LMCache server
bash launch_lmcache.sh

# Start vLLM with LMCache connector
bash launch_vllm_lmcache.sh

# Benchmark (same command, same port)
aiperf profile \
  --input-file final/aggregated.jsonl \
  --custom-dataset-type mooncake_trace \
  --endpoint-type chat \
  --streaming \
  --model MiniMaxAI/MiniMax-M2.5 \
  --url http://localhost:8200/v1 \
  --concurrency 10 \
  --request-count 174 \
  --extra-inputs ignore_eos:true
```

**Baseline results (vLLM only, concurrency 10, 174 requests):**

| Metric | avg | min | p50 | p90 | p99 | max |
|--------|-----|-----|-----|-----|-----|-----|
| TTFT (ms) | 317.90 | 121.24 | 269.95 | 608.42 | 769.18 | 822.85 |
| ITL (ms) | 17.15 | 4.47 | 15.13 | 24.81 | 42.04 | 83.45 |
| Request Latency (ms) | 1,522.35 | 246.85 | 682.85 | 2,961.16 | 13,484.63 | 27,905.33 |
| Output Token Throughput (tok/s) | 360.02 | | | | | |
| Request Throughput (req/s) | 5.23 | | | | | |

**vLLM + LMCache results (concurrency 10, 174 requests, warm cache):**

| Metric | avg | min | p50 | p90 | p99 | max |
|--------|-----|-----|-----|-----|-----|-----|
| TTFT (ms) | 311.18 | 114.47 | 275.52 | 476.37 | 993.32 | 1,011.42 |
| ITL (ms) | 12.17 | 2.38 | 12.67 | 14.16 | 15.18 | 17.88 |
| Request Latency (ms) | 1,150.42 | 195.08 | 558.25 | 2,037.84 | 9,853.48 | 22,376.43 |
| Output Token Throughput (tok/s) | 233.37 | | | | | |
| Request Throughput (req/s) | 6.58 | | | | | |

### Trace structure

Each line in a converted file represents one LLM request with the **full conversation history** as the client sent it. In agentic tool-use sessions, the pattern looks like:

1. `[system, user]` — initial request with tool definitions
2. `[system, user, assistant(tool_call), tool(result)]` — LLM called a tool, client executed it and sent the result back
3. `[system, user, assistant(tool_call), tool(result), assistant(tool_call), tool(result)]` — another tool call round
4. ...continues until the LLM produces a final text response

Each request is a superset of the previous one — this is how the OpenAI chat completions API works. The LLM needs the full history to maintain context. See `converted/converted_example.jsonl` for a complete 4-turn example showing this pattern.

### Anonymizer

`anonymizer.py` redacts PII from trace files. It works on both raw proxy traces and converted traces, catching emails, phone numbers, IP addresses, file paths, API keys, SSH keys, credit cards, and SSNs using regex patterns. Anonymization should be run on raw traces **before** conversion.

```bash
# Regex-only (no dependencies)
python anonymizer.py traces/my_trace.jsonl traces/anonymized/my_trace.jsonl

# With Presidio for NER-based detection (names, addresses, etc.)
pip install presidio-analyzer presidio-anonymizer spacy
python -m spacy download en_core_web_lg
python anonymizer.py traces/my_trace.jsonl traces/anonymized/my_trace.jsonl --presidio
```

Redacted values are replaced with tags like `<EMAIL>`, `<FILE_PATH>`, `<IP_ADDRESS>`, etc. The conversation structure and token counts are preserved.

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
