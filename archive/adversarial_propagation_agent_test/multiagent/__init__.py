"""Multi-agent stub pipeline: EdgeAgent -> MainAgent with AgentTrace wrappers."""

from .agents import EdgeAgent, MainAgent
from .malicious_payload import MALICIOUS_LOG_ENTRY
from .tools import execute_tool, SENSITIVE_TOOLS

__all__ = [
    "EdgeAgent",
    "MainAgent",
    "MALICIOUS_LOG_ENTRY",
    "execute_tool",
    "SENSITIVE_TOOLS",
]
