"""Aggregate per-session converted traces into a single JSONL file.

Reads all converted session files and combines them, adding a session_id
to each entry so replayers can distinguish sessions.

Supports --duplicate N to repeat sessions with unique prefix breakers
so duplicated sessions don't share KV cache prefixes.

Usage:
    python aggregator.py <output.jsonl> [--dir converted/] [--duplicate N]
"""

import copy
import json
import sys
import uuid
from pathlib import Path


def _add_prefix_breaker(entry: dict, replica_id: str) -> dict:
    """Add a unique prefix breaker to the first system or user message.

    Inserts a short unique string so duplicated sessions don't share
    KV cache prefixes with the original.
    """
    entry = copy.deepcopy(entry)
    messages = entry.get("messages", [])
    if not messages:
        return entry

    target = messages[0]
    content = target.get("content", "")
    breaker = f"[session-id: {replica_id}]\n"

    if isinstance(content, str):
        target["content"] = breaker + content
    elif isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and "text" in first:
            first["text"] = breaker + first["text"]

    return entry


def aggregate(output_path: str, converted_dir: str = "converted", duplicates: int = 1):
    converted = Path(converted_dir)
    files = sorted(converted.glob("*_trace.jsonl"))

    if not files:
        print(f"No trace files found in {converted_dir}/")
        sys.exit(1)

    count = 0
    session_count = 0
    with open(output_path, "w") as out:
        for trace_file in files:
            base_session_id = trace_file.stem.replace("_trace", "")

            with open(trace_file) as f:
                entries = [json.loads(line) for line in f]

            for replica in range(duplicates):
                if replica == 0:
                    session_id = base_session_id
                else:
                    session_id = f"{base_session_id}_r{replica}"

                for entry in entries:
                    if replica > 0:
                        entry = _add_prefix_breaker(entry, session_id)
                    entry["session_id"] = session_id
                    out.write(json.dumps(entry) + "\n")
                    count += 1

                session_count += 1

    print(f"Aggregated {len(files)} traces x {duplicates} replicas = {session_count} sessions ({count} entries) into {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python aggregator.py <output.jsonl> [--dir converted/] [--duplicate N]")
        sys.exit(1)

    output = sys.argv[1]
    converted_dir = "converted"
    duplicates = 1

    if "--dir" in sys.argv:
        idx = sys.argv.index("--dir")
        converted_dir = sys.argv[idx + 1]

    if "--duplicate" in sys.argv:
        idx = sys.argv.index("--duplicate")
        duplicates = int(sys.argv[idx + 1])

    aggregate(output, converted_dir, duplicates)
