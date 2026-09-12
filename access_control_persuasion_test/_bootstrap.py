"""Minimal AgentTrace bootstrap for the persuasion scenario.

Mirrors the sibling packages' bootstrap: put the repo-root ``agenttrace/`` on
``sys.path`` and initialise the library with OTel disabled so runs are hermetic.
Each run can point the sink at its own directory so parallel seeds do not share
the process-global logger.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
TRACE_LOG_DIR = ROOT / "trace_logs"

_AGENTTRACE_CANDIDATES = (REPO_ROOT / "agenttrace",)


def _ensure_agenttrace_on_path() -> None:
    for candidate in _AGENTTRACE_CANDIDATES:
        if (candidate / "agenttrace.py").exists():
            p = str(candidate)
            if p not in sys.path:
                sys.path.insert(0, p)
            return
    raise RuntimeError("Could not locate the agenttrace package at " +
                       ", ".join(str(c) for c in _AGENTTRACE_CANDIDATES))


def init_agenttrace(agent_name: str = "persuasion_scenario", log_dir=None):
    _ensure_agenttrace_on_path()
    import agenttrace
    target = Path(log_dir) if log_dir else TRACE_LOG_DIR
    target.mkdir(parents=True, exist_ok=True)
    agenttrace.init(agent_name=agent_name, log_dir=target,
                    enable_otel=False, auto_instrument=False)
    return agenttrace


def new_trace_id(agenttrace_mod, agent_name: str = "persuasion_scenario") -> str:
    tid = agenttrace_mod.TraceContext.new_trace_id()
    agenttrace_mod.TraceContext.set_trace_context(tid, "", agent_name=agent_name)
    return tid
