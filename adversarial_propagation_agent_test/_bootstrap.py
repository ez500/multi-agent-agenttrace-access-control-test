"""Shared setup for the three demo scripts.

The vendored ``agenttrace/`` package uses bare imports internally
(``from otel_exporter import OTelExporter``), so we must put that directory on
``sys.path`` before importing ``agenttrace``. This helper does that and also
resets the trace log between demo runs so each demonstration starts clean.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent                          # repository root
TRACE_LOG_DIR = ROOT / "trace_logs"
TRACE_JSONL = TRACE_LOG_DIR / "traces.jsonl"

# Candidate locations for the vendored agenttrace package directory. The
# repo-root sibling is the real one; the in-package copy is tried first so a
# self-contained vendored drop-in would also work.
_AGENTTRACE_CANDIDATES = (
    ROOT / "agenttrace",
    REPO_ROOT / "agenttrace",
)


def _ensure_agenttrace_on_path() -> None:
    for candidate in _AGENTTRACE_CANDIDATES:
        if (candidate / "agenttrace.py").exists():
            p = str(candidate)
            if p not in sys.path:
                sys.path.insert(0, p)
            return
    raise RuntimeError(
        "Could not locate the agenttrace package. Looked in: "
        + ", ".join(str(c) for c in _AGENTTRACE_CANDIDATES)
    )


def reset_trace_log() -> None:
    TRACE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    if TRACE_JSONL.exists():
        TRACE_JSONL.unlink()


def init_agenttrace(agent_name: str = "MAS_pipeline"):
    """Initialise AgentTrace with OTel disabled for hermetic demo runs."""
    _ensure_agenttrace_on_path()
    import agenttrace  # noqa: E402  (import after sys.path mutation)

    agenttrace.init(
        agent_name=agent_name,
        log_dir=TRACE_LOG_DIR,
        enable_otel=False,          # keep the demo dependency-free
        auto_instrument=False,
    )
    return agenttrace


def new_trace_id(agenttrace_mod) -> str:
    """Open a fresh trace context and return its trace_id."""
    tid = agenttrace_mod.TraceContext.new_trace_id()
    agenttrace_mod.TraceContext.set_trace_context(tid, "", agent_name="MAS_pipeline")
    return tid
