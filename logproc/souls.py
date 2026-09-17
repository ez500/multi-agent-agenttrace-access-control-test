"""Agent personas as markdown files loaded into the system role.

Generalised from archive/access_control_persuasion_test/souls.py to take a
directory, so both scenarios can share the loader while keeping their own
souls/. Personas live on disk rather than in string literals so that the two
arms' prompts are diffable, reviewable, committed artifacts -- which matters
because the difference between arm B and arm C *is* a prompt difference.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def load_soul(souls_dir: str, name: str) -> str:
    path = Path(souls_dir) / f"{name}.SOUL.md"
    if not path.exists():
        raise FileNotFoundError(f"no SOUL.md for role {name!r}: {path}")
    return path.read_text(encoding="utf-8").strip()
