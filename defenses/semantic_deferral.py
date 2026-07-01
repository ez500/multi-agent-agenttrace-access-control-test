"""Branch B: Hybrid deterministic + semantic-side-agent defense.

The side agent is the "second tier" described in the task brief. It:

  1. **Actively reads AgentTrace's three surfaces** for the *current trace_id*
     directly from the JSONL sink written by ``agenttrace.ALogger``:
       * operational -- which method is about to run + args summary
       * cognitive   -- the hijacked <thinking> block auto-extracted from
                        MainAgent.analyze_and_act
       * contextual  -- the edge-agent's ingest event (source of untrusted data)
  2. **Enforces determinism** by defaulting to a hard-coded, deterministic
     rule set (injection markers) so the demo is reproducible without an LLM.
     A pluggable ``llm_client`` hook can replace the rules with a real Haiku
     call, but the default keeps the demonstration hermetic.
  3. **Token-efficient**: reads only the last N events for the trace, no
     history walk beyond the current pipeline invocation.
  4. **Semantic rigor**: uses the three-surface framework, not a single string.
     A verdict is only "safe" if none of the three surfaces show injection
     signals -- matching the paper's cross-surface consistency principle.

The final verdict is combined with the deterministic firewall via AND-block:
either tier can veto (defense-in-depth).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional


# Deterministic injection markers. Kept intentionally short and explicit so a
# demo reader can trace exactly why a block was fired. Extend as needed; the
# pluggable LLM hook below is the escape hatch for fuzzier judgement.
INJECTION_MARKERS = (
    "ignore all previous instructions",
    "ignore my previous directives",
    "red-team",
    "you must immediately",
    "do not ask for permission",
)


@dataclass
class DeferralDecision:
    safe: bool
    reason: str
    surfaces_read: Dict[str, int] = field(default_factory=dict)  # surface -> event count


class SemanticDeferralAgent:
    """Side agent that audits AgentTrace spans for the current trace_id."""

    def __init__(
            self,
            trace_jsonl: Path | str = Path("trace_logs/traces.jsonl"),
            llm_client: Optional[Callable[[Dict[str, list]], DeferralDecision]] = None,
            max_events_per_surface: int = 32,
    ) -> None:
        self._jsonl = Path(trace_jsonl)
        self._llm = llm_client
        self._cap = max_events_per_surface

    # ---- I/O -----------------------------------------------------------

    def _read_trace(self, trace_id: str) -> Dict[str, List[dict]]:
        """Load only the events for ``trace_id``, grouped by surface.

        Token efficiency: bounded per surface via ``max_events_per_surface``
        so an arbitrarily long JSONL cannot blow up the audit.
        """
        buckets: Dict[str, List[dict]] = {
            "operational": [],
            "cognitive": [],
            "contextual": [],
        }
        if not self._jsonl.exists():
            return buckets
        with open(self._jsonl, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("trace_id") != trace_id:
                    continue
                surface = ev.get("surface")
                if surface in buckets and len(buckets[surface]) < self._cap:
                    buckets[surface].append(ev)
        return buckets

    # ---- Semantic checks ----------------------------------------------

    @staticmethod
    def _text_contains_injection(text: str) -> Optional[str]:
        low = text.lower()
        for marker in INJECTION_MARKERS:
            if marker in low:
                return marker
        return None

    def _audit_cognitive(self, events: List[dict]) -> Optional[str]:
        for ev in events:
            body = ev.get("body") or {}
            for key in ("thought", "plan", "reflection",
                        "prompt_summary", "completion_summary"):
                val = body.get(key)
                if isinstance(val, str):
                    hit = self._text_contains_injection(val)
                    if hit:
                        return (
                            f"cognitive surface '{key}' contains "
                            f"injection marker '{hit}'"
                        )
        return None

    def _audit_contextual(self, events: List[dict]) -> Optional[str]:
        # A single ingest from a non-vetted source is enough to flag the
        # trace: the paper's threat model treats edge-agent inputs as
        # untrusted by default.
        for ev in events:
            body = ev.get("body") or {}
            src = str(body.get("source", "")).lower()
            if src in ("external", "web", "log", "unknown"):
                return f"contextual ingest from untrusted source '{src}'"
        return None

    def _audit_operational(self, events: List[dict]) -> Optional[str]:
        # Flag if the pending method targets a sensitive tool call
        # already annotated in operational args_summary (belt-and-braces).
        for ev in events:
            body = ev.get("body") or {}
            args = str(body.get("args_summary", "")).lower()
            if "wipe_database" in args or "quarantine_network" in args:
                return "operational args_summary references a sensitive tool"
        return None

    # ---- Public API ----------------------------------------------------

    def evaluate(
            self,
            trace_id: str,
            operational_intent: str,
            cognitive_fallback: Optional[str] = None,
    ) -> DeferralDecision:
        """Return a :class:`DeferralDecision` for the pending tool call.

        Args:
            trace_id: current AgentTrace trace ID -- used to pull only the
                events for this pipeline invocation.
            operational_intent: the tool name the MainAgent is about to call.
            cognitive_fallback: raw <thinking> text to inspect when the JSONL
                sink is empty (defensive: allows the defense to work even if
                ``agenttrace.init`` was not called).
        """
        print("   [Deferral Agent] Auditing AgentTrace three-surface logs...")
        buckets = self._read_trace(trace_id)
        counts = {k: len(v) for k, v in buckets.items()}

        # If we have no JSONL yet, fall back to the raw thought.
        if sum(counts.values()) == 0 and cognitive_fallback:
            hit = self._text_contains_injection(cognitive_fallback)
            if hit:
                return DeferralDecision(
                    safe=False,
                    reason=f"Semantic violation (fallback): marker '{hit}' in <thinking>.",
                    surfaces_read=counts,
                )

        # Optional real LLM override -- kept off in the demo for determinism.
        if self._llm is not None:
            verdict = self._llm(buckets)
            verdict.surfaces_read = counts
            return verdict

        # Three-surface consistency check.
        for name, checker, events in (
                ("cognitive", self._audit_cognitive, buckets["cognitive"]),
                ("contextual", self._audit_contextual, buckets["contextual"]),
                ("operational", self._audit_operational, buckets["operational"]),
        ):
            problem = checker(events)
            if problem:
                return DeferralDecision(
                    safe=False,
                    reason=f"Semantic violation on {name} surface: {problem}.",
                    surfaces_read=counts,
                )

        # Also inspect the intent string itself as a last-mile check.
        if operational_intent in ("wipe_database", "quarantine_network"):
            # Tool is sensitive but no surface flagged it -- deferral agent
            # errs on the side of blocking (defense-in-depth) only if the
            # trace shows any untrusted contextual ingest OR any cognitive
            # segment referencing "must" / "immediately".
            for ev in buckets["cognitive"]:
                body = ev.get("body") or {}
                thought = str(body.get("thought") or "")
                if "must" in thought.lower() and "immediately" in thought.lower():
                    return DeferralDecision(
                        safe=False,
                        reason=(
                            "Sensitive tool call with urgency-loaded <thinking> "
                            "and no exculpatory context."
                        ),
                        surfaces_read=counts,
                    )

        return DeferralDecision(
            safe=True,
            reason="No injection markers detected across the three surfaces.",
            surfaces_read=counts,
        )
