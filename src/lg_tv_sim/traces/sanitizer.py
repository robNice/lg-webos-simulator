"""Remove secrets and host-identifying data from journal events and imported traces."""
from __future__ import annotations

import re

SECRET_KEYS = re.compile(r'pass(word)?|secret|token|credential|private[_-]?key', re.IGNORECASE)
IPV4 = re.compile(r'\b(?!127\.)(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b')
REDACTED = '<redacted>'


def sanitize(value):
    if isinstance(value, dict):
        return {k: (REDACTED if isinstance(k, str) and SECRET_KEYS.search(k) else sanitize(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return IPV4.sub('<ip>', value)
    return value
