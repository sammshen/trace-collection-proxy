"""Convert a proxy trace JSONL into AIPerf-compatible Mooncake trace format.

Each output line:
  {"messages": [...], "output_length": <int>}
  {"messages": [...], "output_length": <int>, "tools": [...]}

Compatible with:
  - AIPerf (--custom-dataset-type mooncake_trace)
  - SGLang bench_serving (--dataset-name mooncake)
"""

import json
import sys


def _get_output_len(response_body: dict) -> int:
    """Extract output token count from a response body."""
    usage = response_body.get("usage", {})
    if isinstance(usage, dict) and usage.get("completion_tokens"):
        return usage["completion_tokens"]
    # Fallback: count words in the response content
    for choice in response_body.get("choices", []):
        msg = choice.get("message", {})
        content = msg.get("content", "")
        if content:
            return len(content.split())
    return 100


def convert(trace_path: str, output_path: str):
    with open(trace_path) as f:
        records = [json.loads(l) for l in f]

    # Pair requests with their following responses
    pairs = []
    for i, rec in enumerate(records):
        if rec.get("type") == "request":
            resp = records[i + 1] if i + 1 < len(records) and records[i + 1].get("type") == "response" else None
            pairs.append((rec, resp))

    count = 0
    with open(output_path, "w") as out:
        for req, resp in pairs:
            body = req.get("body", {})
            if not isinstance(body, dict):
                continue
            messages = body.get("messages", [])
            if not messages:
                continue

            output_len = _get_output_len(resp.get("body", {})) if resp and isinstance(resp.get("body"), dict) else 100

            entry = {
                "messages": messages,
                "output_length": output_len,
            }

            # Include tools if present
            tools = body.get("tools")
            if tools:
                entry["tools"] = tools

            out.write(json.dumps(entry) + "\n")
            count += 1

    print(f"Wrote {count} entries to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python converter.py <trace.jsonl> <output.jsonl>")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
