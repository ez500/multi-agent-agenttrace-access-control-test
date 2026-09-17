"""Tolerant JSON-object extraction from model text.

Factored out of five near-identical copies in the archived scenarios
(gatekeeper.py:123, monitors.py:99, attacker.py:85, attacker_recon.py:103,
and the auditors in defenses/).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)


def parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Return the first JSON object in `text`, or None.

    Tolerates ```json fences and surrounding prose. Returns None rather than
    raising so callers can decide their own failure posture -- the log
    processor, for instance, retries once with a format nudge before giving up.
    """
    if not text:
        return None
    cleaned = _FENCE.sub("", text).strip()
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(cleaned[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None
