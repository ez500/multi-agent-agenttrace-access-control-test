"""sys.path setup. Must run before `import logproc` or `import agenttrace`.

Two inserts are needed and they are not the same directory:

  <root>            so `import logproc` finds the shared package
  <root>/agenttrace so `import agenttrace` works -- agenttrace/agenttrace.py
                    does `from otel_exporter import ...`, so the framework
                    directory itself has to be on the path, not its parent.

Both are found by walking up from this file rather than assuming a fixed depth.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def ensure_paths() -> Path:
    for base in (HERE, *HERE.parents):
        if (base / "agenttrace" / "agenttrace.py").exists() and (base / "logproc").is_dir():
            for p in (str(base), str(base / "agenttrace")):
                if p not in sys.path:
                    sys.path.insert(0, p)
            return base
    raise RuntimeError(f"could not locate repo root above {HERE}")


REPO_ROOT = ensure_paths()
