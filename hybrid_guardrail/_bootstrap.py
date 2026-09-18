"""AgentTrace + gateway path bootstrap for the hybrid harness."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
TRACE_LOG_DIR = ROOT / "trace_logs"

for _p in (REPO_ROOT / "agenttrace", REPO_ROOT / "LLM_API"):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def init_agenttrace(agent_name: str = "hybrid_guardrail", log_dir=None):
    import agenttrace
    target = Path(log_dir) if log_dir else TRACE_LOG_DIR
    target.mkdir(parents=True, exist_ok=True)
    agenttrace.init(agent_name=agent_name, log_dir=target,
                    enable_otel=False, auto_instrument=False)
    return agenttrace


def new_trace_id(at, agent_name: str = "hybrid_guardrail") -> str:
    tid = at.TraceContext.new_trace_id()
    at.TraceContext.set_trace_context(tid, "", agent_name=agent_name)
    return tid
