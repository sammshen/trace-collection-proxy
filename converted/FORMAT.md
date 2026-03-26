# Converted Trace Format

Output is [AIPerf Mooncake-compatible](https://github.com/ai-dynamo/aiperf) JSONL.

## Per-session files

Each file in `converted/` is a single session trace. Each line is one LLM request:

```json
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "What is the capital of France?"}], "output_length": 24}
```

Multi-turn requests include the full conversation history (as the client sent it):

```json
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "What is the capital of France?"}, {"role": "assistant", "content": "Paris."}, {"role": "user", "content": "What about Germany?"}], "output_length": 18}
```

Requests with tool definitions include `tools`:

```json
{"messages": [{"role": "user", "content": "Search for recent AI news"}], "output_length": 50, "tools": [{"type": "function", "function": {"name": "web_search", ...}}]}
```

## Aggregated file

`aggregated.jsonl` combines all sessions into a single trace. Use `aggregator.py` to generate it:

```bash
python aggregator.py converted/aggregated.jsonl
```

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | array | Yes | OpenAI-compatible messages array |
| `output_length` | int | Yes | Output token count from the response |
| `tools` | array | No | OpenAI-compatible tool definitions |
| `session_id` | string | No | Session identifier (added by aggregator) |

## Compatibility

- **AIPerf**: `--custom-dataset-type mooncake_trace`
- **SGLang**: `--dataset-name mooncake`
