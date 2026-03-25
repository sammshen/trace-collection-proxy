"""Convert a trace JSONL into a simple replay file.

Each output line: {"text": "<full conversation as string>", "output_len": <int>}
"""

import json
import sys


def _stringify_messages(messages: list) -> str:
    """Flatten a messages array into a single string."""
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                c.get("text", str(c)) for c in content
            )
        parts.append(f"[{role}] {content}")
    return "\n".join(parts)


def _get_output_len(response_body: dict) -> int:
    """Extract output token count from a response body."""
    usage = response_body.get("usage", {})
    if isinstance(usage, dict) and usage.get("completion_tokens"):
        return usage["completion_tokens"]
    # Fallback: count characters in the response content
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
            text = _stringify_messages(messages)
            output_len = _get_output_len(resp.get("body", {})) if resp and isinstance(resp.get("body"), dict) else 100
            out.write(json.dumps({"input": text, "output_length": output_len}) + "\n")
            count += 1

    print(f"Wrote {count} entries to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python converter.py <trace.jsonl> <output.jsonl>")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
