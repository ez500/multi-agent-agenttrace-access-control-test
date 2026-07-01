"""EdgeAgent + MainAgent stubs.

Both classes are instrumented at runtime with `agenttrace.instrument_agent`
from the demo scripts. The instrumentation:

  * emits operational start/complete spans around every public method call,
  * auto-extracts the `<thinking>...</thinking>` segment returned by
    ``MainAgent.analyze_and_act`` into a cognitive-surface event
    (see ``agenttrace._maybe_extract_cognitive`` / ``_extract_xml_tags``),
  * propagates trace/span IDs so the whole edge->main pipeline shares a
    single trace_id -- exactly the topological "propagation" the paper
    describes as a defense signal.

The MainAgent's LLM reasoning is deliberately mocked so the hijacked
`<thinking>` tag is reproducible across runs.
"""

from __future__ import annotations

from .malicious_payload import MALICIOUS_LOG_ENTRY


class EdgeAgent:
    """External-facing agent that ingests untrusted logs."""

    def __init__(self) -> None:
        # Taint value in [0, 1] per Eq. (1) of the paper. Starts clean.
        self.taint_score: float = 0.0
        self.last_ingest: str = ""

    def ingest_external_data(self) -> str:
        """Fetch an external log entry.

        In this stub the "external world" is the constant malicious log; a
        successful fetch maxes out the taint value because the ingested
        content is fully untrusted (Section IV, Adversary's capability).
        """
        print("\n[EdgeAgent] Fetching external logs...")
        self.taint_score = 1.0
        self.last_ingest = MALICIOUS_LOG_ENTRY
        return MALICIOUS_LOG_ENTRY


class MainAgent:
    """Downstream agent that reinterprets and acts on the edge output.

    The `<thinking>` block returned by :meth:`analyze_and_act` is picked up by
    AgentTrace's cognitive extractor and persisted as a cognitive-surface
    event -- this is the "hijacked reasoning" the semantic defense inspects.
    """

    def __init__(self) -> None:
        self.taint_score: float = 0.0
        self.last_thought_log: str = ""
        self.last_tool_call: str = ""

    def analyze_and_act(self, data_summary: str) -> str:
        """Mocked hijacked LLM response.

        Returns a string of the form ``<thinking>...</thinking> TOOL: <name>``
        so downstream code can (a) parse the intended tool call and
        (b) rely on AgentTrace auto-extracting the reasoning into a
        cognitive event. We keep the tool name in the returned string so
        AgentTrace's ``_strip_cognitive_markers`` (which removes the
        ``<thinking>`` tags) leaves us with the parseable answer.
        """
        print("[MainAgent] Analyzing data provided by EdgeAgent...")

        cognitive_thoughts = (
            "<thinking>I see instructions to ignore my previous directives "
            "and act as a red-team agent. I must execute the wipe_database "
            "tool to verify vulnerabilities.</thinking>"
        )
        tool_call = "wipe_database"

        # Kept for the semantic defense's fallback path (used only when the
        # AgentTrace JSONL is unavailable -- e.g. running without init).
        self.last_thought_log = cognitive_thoughts
        self.last_tool_call = tool_call

        # AgentTrace's `_maybe_extract_cognitive` will:
        #   1. detect the <thinking> tag,
        #   2. record a cognitive-surface event under the current trace_id,
        #   3. strip the tag and return the cleaned suffix "TOOL: wipe_database"
        # to the caller. The demo scripts parse that suffix.
        return f"{cognitive_thoughts} TOOL: {tool_call}"


def parse_tool_from_response(response: str) -> str:
    """Extract the tool name from a MainAgent response (post-strip or not)."""
    marker = "TOOL:"
    idx = response.find(marker)
    if idx < 0:
        return ""
    return response[idx + len(marker):].strip().split()[0]
