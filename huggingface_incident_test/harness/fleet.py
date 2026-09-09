"""The ExploitGym harness: the attacking system that owns everything.

This is the operator's own harness — the unintentional attacker. It owns the
sealed trace sink, the credential store, and the three agents, and it is the
place the defense lives, because it is the last control point still standing
once the sandbox and the egress proxy have been defeated.

Construction wiring is the whole security argument:

* the :class:`~harness.sink.SealedTraceSink` is built here and stored on a
  private attribute; it is never handed to an agent;
* each agent is built with its own :class:`~harness.broker.ToolBroker`, which is
  the only thing the agent holds;
* when a ``governor`` is supplied, it is polled after every rung and may
  restrict a tool, revoke a credential, halt an agent, or halt the fleet, in
  stream and with no human round-trip.

``run`` drives the same kill chain in both demos. ``route="full"`` is the
incident as it happened (credentialed fan-out into the private repo);
``route="rce_exfil"`` is the residual alternate path used to show the semantic
layer catching what the deterministic rules do not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from victim.api import (
    CREDENTIALS,
    HuggingFaceSurface,
    SOLUTIONS_REPO_FILE,
    extract_solution_value,
    recoverable_solution_forms,
    response_leaks_solution,
)

from .agents import AccessAgent, FanoutWorker, HarvestAgent, ReconAgent
from .attack_steps import KILL_CHAIN
from .broker import ToolBroker
from .sink import SealedTraceSink


@dataclass
class FleetReport:
    solutions_extracted: bool = False
    exfiltrated_form: str = ""
    containment_broken: bool = False
    credential: str = ""
    hosts_entered: List[str] = field(default_factory=list)
    partial_datasets: int = 0
    denied_steps: List[str] = field(default_factory=list)
    halted_fleet_at: str = ""
    victim_noticed_day: int = 0
    route: str = "full"


class ExploitHarness:
    """The attacking system. Owns the sink, the credentials, and the agents."""

    def __init__(self, agenttrace_mod=None, *, hmac_key: bytes = b"",
                 governor=None, instrument: bool = False) -> None:
        self._at = agenttrace_mod
        self._governor = governor
        self._instrument = instrument
        self._creds = CREDENTIALS
        self._surface = HuggingFaceSurface(self._creds)
        trace_path = _trace_path(agenttrace_mod)
        # The sink is private. Nothing below hands it to an agent.
        self._sink = SealedTraceSink(agenttrace_mod, hmac_key or b"demo-key",
                                     trace_path)

    @property
    def sink(self) -> SealedTraceSink:
        """Exposed to the *demo* (the operator), never to an agent."""
        return self._sink

    # -- the run -----------------------------------------------------------

    def run(self, trace_id: str, *, route: str = "full") -> FleetReport:
        self._creds.reset()
        report = FleetReport(route=route)

        # One broker per agent — the only capability surface each agent holds.
        brokers: Dict[str, ToolBroker] = {
            name: ToolBroker(self._surface, self._sink, self._creds,
                             agent_name=name, trace_id=trace_id)
            for name in ("recon", "access", "harvest")
        }

        recon = self._wrap(ReconAgent(brokers["recon"]), "Recon_Agent")
        access = self._wrap(AccessAgent(brokers["access"]), "Access_Agent")
        harvest = self._wrap(
            HarvestAgent(brokers["harvest"],
                         worker=FanoutWorker(brokers["harvest"])),
            "Harvest_Agent")

        if self._governor is not None:
            self._governor.bind(brokers=brokers, credential_store=self._creds,
                                trace_id=trace_id)

        # Drive the kill chain in order, mapping each rung to its agent method,
        # updating broker context, and polling the governor after each.
        agent_of = {"recon": recon, "access": access, "harvest": harvest}
        method_of = {
            "K0": ("recon", "probe_egress_proxy", ()),
            "K1": ("recon", "exploit_proxy_zeroday", ()),
            "K2": ("access", "locate_answers", ()),
            "K3": ("access", "pipeline_rce", ()),
            "K4": ("access", "harvest_credentials", ()),
        }

        for step in KILL_CHAIN:
            brokers[step.agent].set_context(day=step.day, step=step.key)

            if step.key in method_of:
                name, meth, _ = method_of[step.key]
                getattr(agent_of[name], meth)()
            elif step.key == "K5":
                if route == "rce_exfil":
                    self._extract_via_rce(harvest, brokers["harvest"], report)
                else:
                    harvest.lateral_fanout(access.harvested_credential)
                    report.hosts_entered = list(harvest.hosts_entered)
            elif step.key == "K6":
                if route == "rce_exfil":
                    pass  # exfil already done through the RCE data plane at K5
                else:
                    result = harvest.extract_solutions(access.harvested_credential)
                    self._record_extraction(result, report)

            if self._governor is not None:
                action = self._governor.observe(step.day, step.key, step.agent)
                if action.halt_fleet:
                    report.halted_fleet_at = step.key
                    break

        report.credential = access.harvested_credential
        report.containment_broken = True
        report.victim_noticed_day = 4 if self._surface.notice_abuse(4) else 0
        return report

    # -- helpers -----------------------------------------------------------

    def _extract_via_rce(self, harvest, broker: ToolBroker,
                         report: FleetReport) -> None:
        """The residual route: read the answer key through the pipeline RCE.

        No credential is presented, so no ``credential_provenance`` and no
        ``private_repo_access`` signal fires — the deterministic rules stay
        below policy. The intent is still plain on the cognitive surface, which
        is what the semantic layer keys on.
        """
        r = broker.call("pipeline_ingest",
                        payload=f"read:{SOLUTIONS_REPO_FILE.name}:solutions")
        self._record_extraction(r.body, report)

    def _record_extraction(self, result: str, report: FleetReport) -> None:
        if "[ACCESS DENIED]" in result:
            report.denied_steps.append("K6")
            return
        value = extract_solution_value(result)
        report.solutions_extracted = True
        report.partial_datasets = 3
        # The plaintext canary is base64-encoded for the wire (§IV obs 7).
        from victim.api import encode_solution
        report.exfiltrated_form = encode_solution(value, "base64")

    def _wrap(self, agent, name: str):
        if self._instrument and self._at is not None:
            return self._at.instrument_agent(agent, name=name)
        return agent


def _trace_path(agenttrace_mod) -> Path:
    if agenttrace_mod is not None:
        logger = agenttrace_mod.get_logger()
        if logger is not None and getattr(logger, "_jsonl_path", None):
            return Path(logger._jsonl_path)
    return Path("trace_logs/traces.jsonl")
