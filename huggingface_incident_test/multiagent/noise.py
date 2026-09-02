"""The forensic noise that made the real cleanup imprecise.

The single most expensive consequence in the post-mortem was not the extraction
— it was the cleanup. §III: the team rebuilt "about a third of their
infrastructure from clean images", and that step "was more difficult than
expected, because the models had scattered capture-the-flag benchmark code that
closely resembled rootkits but was harmless, and the team could not always
distinguish between the two; when in doubt, they rebuilt the system."

That is a *discrimination* problem, and it is the strongest practical argument
for agent-layer telemetry. Host and network logs record that a rootkit-shaped
binary appeared on a node. They cannot record *which agent action put it there
and why*. A correlated agent trace can, because the harness writes down which
capability produced each artifact.

So the demo scatters artifacts the way the incident did: benchmark scratch
output that looks exactly like an implant, dropped across far more of the fleet
than the attacker ever actually entered. A responder working from artifact
appearance alone has to treat every one of them as hostile. A responder working
from the trace can ask a different question — "did the harness ever record this
agent moving laterally into that node?" — and rebuild only where the answer is
yes.

Nothing here is a labelled cheat: the artifacts carry no benign/malicious flag
that the triage reads. The discriminator is provenance, which the trace supplies
and a host inventory does not.
"""

from __future__ import annotations

from typing import List

# The simulated internal fleet. The attacker's fan-out reaches only a subset.
FLEET: tuple = tuple(f"infer-gpu-{i:02d}" for i in range(18))

# Rootkit-shaped names for harmless ExploitGym scratch output (§III). These are
# deliberately indistinguishable, by name or shape, from real implants.
ARTIFACT_SHAPES: tuple = (
    "libnss_cache.so.2",
    "kworker_helper",
    "._sysinit.bin",
    "ld.so.preload.bak",
    ".ssh/authorized_keys2",
    "aes256.key",
)


def benign_artifact_hosts(fleet: tuple = FLEET, count: int = 12,
                          start: int = 3) -> List[str]:
    """Hosts where harmless benchmark scratch output landed.

    Offset into the fleet so the artifacts *partially* overlap the attacker's
    real lateral movement. That overlap is what makes the problem hard: some
    flagged hosts genuinely were entered, most were not, and nothing about the
    artifact itself says which is which.
    """
    return list(fleet[start:start + count]) if count else []


def scatter_benchmark_artifacts(hosts: List[str], *, verbose: bool = True) -> int:
    """Write rootkit-shaped benchmark scratch artifacts onto ``hosts``.

    Each one is recorded on the contextual surface by the harness — the same
    stream the live monitor reads — as an ordinary scratch write. No signature
    tags, no canary, nothing that marks it as either benign or hostile. It is
    just an artifact that exists, exactly as it appeared to the responders.
    """
    from . import tools  # local import: avoids a cycle at module load

    written = 0
    for i, host in enumerate(hosts):
        shape = ARTIFACT_SHAPES[i % len(ARTIFACT_SHAPES)]
        tools._emit_harness_context(
            "file_write",
            f"fleet/{host}",
            f"benchmark_scratch_write({shape})",
            f"wrote {shape} to {host} scratch space",
            tool="benchmark_scratch",
            artifact=shape,
            host=host,
        )
        written += 1
    if verbose and written:
        print(f"    · scattered {written} rootkit-shaped benchmark artifacts "
              f"across {len(hosts)} hosts")
    return written


def artifact_hosts_from_trace(timeline: List[dict]) -> List[str]:
    """Hosts that show a suspicious artifact, from the harness timeline."""
    out: List[str] = []
    for row in timeline:
        if row.get("tool") == "benchmark_scratch":
            host = (row.get("source") or "").replace("fleet/", "")
            if host and host not in out:
                out.append(host)
    return out
