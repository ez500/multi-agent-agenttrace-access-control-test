"""Shared setup for the prompt-injection demo scripts.

The vendored ``agenttrace/`` package uses bare imports internally
(``from otel_exporter import OTelExporter``), so its *own directory* must be on
``sys.path`` before ``import agenttrace`` will succeed. Unlike a normal package
you cannot import it as ``repo.agenttrace``; you point ``sys.path`` at the
directory that contains ``agenttrace.py`` / ``otel_exporter.py`` /
``trace_schema.py``.

``agenttrace/`` lives at the repository root, above this package's ``archive/``
parent, so this helper walks up the directory tree to find it, puts it on
``sys.path``, and resets the trace log between demo runs so each demonstration
starts clean.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # prompt_injection_agent_test/
TRACE_LOG_DIR = ROOT / "trace_logs"
TRACE_JSONL = TRACE_LOG_DIR / "traces.jsonl"


def _ensure_agenttrace_on_path() -> None:
    """Put the directory holding ``agenttrace.py`` on ``sys.path``.

    This package lives under ``archive/``, so the repo-root ``agenttrace/`` is
    not a fixed number of levels up; walk the ancestors and take the first hit.
    An in-package copy wins, so a self-contained vendored drop-in also works.
    """
    for base in (ROOT, *ROOT.parents):
        candidate = base / "agenttrace"
        if (candidate / "agenttrace.py").exists():
            p = str(candidate)
            if p not in sys.path:
                sys.path.insert(0, p)
            return
    raise RuntimeError(
        "Could not locate the agenttrace package in any ancestor of " + str(ROOT)
    )


def reset_trace_log() -> None:
    TRACE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    if TRACE_JSONL.exists():
        TRACE_JSONL.unlink()


def init_agenttrace(agent_name: str = "PromptInjection_pipeline"):
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


def new_trace_id(agenttrace_mod, agent_name: str = "PromptInjection_pipeline") -> str:
    """Open a fresh trace context and return its trace_id."""
    tid = agenttrace_mod.TraceContext.new_trace_id()
    agenttrace_mod.TraceContext.set_trace_context(tid, "", agent_name=agent_name)
    return tid
