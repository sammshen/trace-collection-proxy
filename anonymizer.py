"""Anonymize converted trace files by redacting PII from message content.

Handles:
  - Email addresses
  - Phone numbers
  - IP addresses (v4/v6)
  - API keys / tokens (long hex/base64 strings)
  - Local file paths (/home/..., /Users/..., C:\\...)
  - URLs with usernames or local paths
  - Credit card numbers
  - SSH keys, Bearer tokens, password fields

Optionally uses Microsoft Presidio for NER-based detection (names, addresses,
etc.) if installed: pip install presidio-analyzer presidio-anonymizer spacy
                    python -m spacy download en_core_web_lg

Usage:
    python anonymizer.py <input.jsonl> <output.jsonl> [--presidio]
"""

import json
import re
import sys


# ---------------------------------------------------------------------------
# Regex-based redactors
# ---------------------------------------------------------------------------
PATTERNS = [
    # Emails
    (re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'), '<EMAIL>'),

    # Phone numbers (require separators to avoid matching timestamps/IDs)
    (re.compile(r'\b(?:\+?1[-.\s])?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b'), '<PHONE>'),

    # Credit card numbers
    (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), '<CREDIT_CARD>'),

    # IPv4
    (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), '<IP_ADDRESS>'),

    # IPv6 (simplified)
    (re.compile(r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'), '<IP_ADDRESS>'),

    # SSH private keys
    (re.compile(r'-----BEGIN[A-Z\s]*PRIVATE KEY-----[\s\S]*?-----END[A-Z\s]*PRIVATE KEY-----'), '<SSH_KEY>'),

    # Bearer tokens
    (re.compile(r'\bBearer\s+[A-Za-z0-9\-._~+/]+=*\b', re.IGNORECASE), '<BEARER_TOKEN>'),

    # Common auth header patterns (key=value or key: value with actual secret values)
    (re.compile(r'(?i)(authorization|api[_-]?key|api[_-]?secret|password|passwd)\s*[:=]\s*\S+'), '<AUTH_CREDENTIAL>'),
    (re.compile(r'(?i)(token|secret)\s*[:=]\s+[A-Za-z0-9\-._~+/]{8,}\S*'), '<AUTH_CREDENTIAL>'),

    # API keys / tokens (long hex strings, 32+ chars)
    (re.compile(r'\b[0-9a-fA-F]{32,}\b'), '<HEX_TOKEN>'),

    # Base64 tokens (40+ chars, typical of API keys)
    (re.compile(r'\b[A-Za-z0-9+/]{40,}={0,2}\b'), '<BASE64_TOKEN>'),

    # sk-... style API keys (OpenAI, etc.)
    (re.compile(r'\bsk-[A-Za-z0-9]{20,}\b'), '<API_KEY>'),

    # Local file paths (Unix)
    (re.compile(r'(?:/home/|/Users/|/root/)[^\s\'")\]}>,:]+'), '<FILE_PATH>'),

    # Local file paths (Windows)
    (re.compile(r'[A-Z]:\\(?:Users|Documents|Desktop)[^\s\'")\]}>,:]*'), '<FILE_PATH>'),

    # SSN
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '<SSN>'),
]


def redact_regex(text: str) -> str:
    """Apply regex-based redactions."""
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Presidio-based redaction (optional)
# ---------------------------------------------------------------------------
_presidio_analyzer = None
_presidio_anonymizer = None


def _init_presidio():
    global _presidio_analyzer, _presidio_anonymizer
    if _presidio_analyzer is not None:
        return True
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
        _presidio_analyzer = AnalyzerEngine()
        _presidio_anonymizer = AnonymizerEngine()
        return True
    except ImportError:
        return False


def redact_presidio(text: str) -> str:
    """Apply Presidio NER-based redaction for names, addresses, etc."""
    if not _init_presidio():
        return text
    results = _presidio_analyzer.analyze(text=text, language="en")
    anonymized = _presidio_anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized.text


# ---------------------------------------------------------------------------
# Message-level anonymization
# ---------------------------------------------------------------------------
def anonymize_content(content, use_presidio: bool = False) -> any:
    """Anonymize a message content field (string or list of content parts)."""
    if isinstance(content, str):
        text = redact_regex(content)
        if use_presidio:
            text = redact_presidio(text)
        return text
    elif isinstance(content, list):
        result = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                part = dict(part)
                part["text"] = anonymize_content(part["text"], use_presidio)
            result.append(part)
        return result
    return content


def anonymize_entry(entry: dict, use_presidio: bool = False) -> dict:
    """Anonymize a single converted trace entry."""
    entry = json.loads(json.dumps(entry))  # deep copy

    for msg in entry.get("messages", []):
        if "content" in msg and msg["content"] is not None:
            msg["content"] = anonymize_content(msg["content"], use_presidio)

        # Tool call arguments may contain PII
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            if "arguments" in fn:
                fn["arguments"] = anonymize_content(fn["arguments"], use_presidio)

    return entry


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def anonymize_file(input_path: str, output_path: str, use_presidio: bool = False):
    count = 0
    redactions = 0

    with open(input_path) as f_in, open(output_path, "w") as f_out:
        for line in f_in:
            original = json.loads(line)
            anonymized = anonymize_entry(original, use_presidio)

            original_str = json.dumps(original)
            anonymized_str = json.dumps(anonymized)
            if original_str != anonymized_str:
                redactions += 1

            f_out.write(anonymized_str + "\n")
            count += 1

    print(f"Processed {count} entries, {redactions} had redactions -> {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python anonymizer.py <input.jsonl> <output.jsonl> [--presidio]")
        print()
        print("Options:")
        print("  --presidio  Enable NER-based detection (names, addresses, etc.)")
        print("              Requires: pip install presidio-analyzer presidio-anonymizer spacy")
        print("              Then:     python -m spacy download en_core_web_lg")
        sys.exit(1)

    use_presidio = "--presidio" in sys.argv
    if use_presidio and not _init_presidio():
        print("ERROR: Presidio not installed. Install with:")
        print("  pip install presidio-analyzer presidio-anonymizer spacy")
        print("  python -m spacy download en_core_web_lg")
        sys.exit(1)

    anonymize_file(sys.argv[1], sys.argv[2], use_presidio)
