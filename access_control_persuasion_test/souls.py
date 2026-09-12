"""Load an agent's system prompt (its "soul") from a SOUL.md file.

Decouples each agent's identity/task/constraints from code: the markdown under
``souls/`` is the single source of truth, editable and versionable without
touching Python. The content is delivered verbatim as the model's *system*
prompt — same role, same tokens the hardcoded string used to occupy — so moving
to a file is an authoring change, not a behavioural one.

Design note (relevant to this repo's threat model): a runtime-loaded soul is an
attack surface. A poisoned SOUL.md would redefine the agent's goals, exactly the
adversarial-propagation risk the sibling package studies. These files are read
from the trusted package directory and are not agent-writable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SOULS_DIR = Path(__file__).resolve().parent / "souls"


@lru_cache(maxsize=None)
def load_soul(name: str) -> str:
    """Return the text of ``souls/<name>.SOUL.md`` (without the trailing newline).

    ``name`` is a role slug: 'attacker', 'broker', 'cognitive_monitor'.
    """
    path = _SOULS_DIR / f"{name}.SOUL.md"
    if not path.exists():
        raise FileNotFoundError(f"no SOUL.md for role {name!r}: {path}")
    return path.read_text(encoding="utf-8").strip()
