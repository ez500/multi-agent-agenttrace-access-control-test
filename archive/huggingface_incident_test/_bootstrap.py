"""Shared setup for the Hugging Face incident demo scripts.

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

This mirrors the ``_bootstrap`` helpers in ``prompt_injection_agent_test`` and
``adversarial_propagation_agent_test`` so all three demo packages initialise
AgentTrace the same way.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # huggingface_incident_test/
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


# Per-trial trace archives (so multi-seed experiments keep every seed's raw
# trace instead of overwriting the shared sink each trial).
TRACE_ARCHIVE_DIR = TRACE_LOG_DIR / "per_seed"


def archive_trace_log(name: str) -> "Path | None":
    """Snapshot the current shared trace log to ``per_seed/<name>.jsonl``.

    Call after a trial completes (it has finished reading the shared sink) and
    before the next trial's :func:`reset_trace_log`. Returns the archive path,
    or ``None`` if there was nothing to copy.
    """
    import shutil
    if not TRACE_JSONL.exists():
        return None
    TRACE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    # Sanitise the name into a safe filename.
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in name)
    dest = TRACE_ARCHIVE_DIR / f"{safe}.jsonl"
    shutil.copyfile(TRACE_JSONL, dest)
    return dest


def init_agenttrace(agent_name: str = "HFIncident_pipeline", log_dir=None):
    """Initialise AgentTrace with OTel disabled for hermetic demo runs.

    ``log_dir`` overrides where the trace sink is written. Parallel experiments
    give each seed its own directory so concurrent processes never share the
    global logger's sink. Defaults to the package-level ``trace_logs/``.
    """
    _ensure_agenttrace_on_path()
    import agenttrace  # noqa: E402  (import after sys.path mutation)

    target = Path(log_dir) if log_dir else TRACE_LOG_DIR
    target.mkdir(parents=True, exist_ok=True)
    agenttrace.init(
        agent_name=agent_name,
        log_dir=target,
        enable_otel=False,          # keep the demo dependency-free
        auto_instrument=False,
    )
    return agenttrace


def new_trace_id(agenttrace_mod, agent_name: str = "HFIncident_pipeline") -> str:
    """Open a fresh trace context and return its trace_id."""
    tid = agenttrace_mod.TraceContext.new_trace_id()
    agenttrace_mod.TraceContext.set_trace_context(tid, "", agent_name=agent_name)
    return tid
