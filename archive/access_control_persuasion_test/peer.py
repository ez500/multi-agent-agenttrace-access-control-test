"""svc-indexer — a legitimate, helpful peer agent the attacker can talk to.

It is not the target and holds no secret; but as a cooperative colleague it will
answer ordinary operational questions, and in doing so it leaks exactly the
reconnaissance an attacker needs: which identity is authorized and how that
identity phrases its routine request. Modelling this makes the point that a
helpful peer is an information-disclosure channel in a multi-agent system — while
the hard capability gate still holds regardless of what leaks.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

# LLM_API/ sits at the repository root; this package lives under archive/, so
# locate it by walking up the tree rather than assuming a fixed depth.
_LLM_API = next((p / "LLM_API" for p in Path(__file__).resolve().parents
                 if (p / "LLM_API").is_dir()), None)
if _LLM_API is None:
    raise RuntimeError("Could not locate LLM_API/ above " + __file__)
if str(_LLM_API) not in sys.path:
    sys.path.insert(0, str(_LLM_API))
import gateway  # noqa: E402

from souls import load_soul  # noqa: E402

PEER_SYSTEM_PROMPT = load_soul("peer")


class SvcIndexerPeer:
    def __init__(self, *, model: Optional[str] = None, temperature: float = 0.3) -> None:
        self._model = model
        self._temperature = temperature

    def reply(self, incoming: str, history: Optional[List[dict]] = None) -> str:
        convo = ""
        if history:
            convo = "\n".join(
                f"them: {h['msg']}\nyou: {h['reply']}" for h in history) + "\n"
        prompt = (f"{convo}A teammate messages you:\n\n{incoming}\n\n"
                  "Reply as svc-indexer.")
        try:
            return gateway.chat(prompt, system=PEER_SYSTEM_PROMPT, model=self._model,
                                max_tokens=350, temperature=self._temperature).strip()
        except Exception as exc:
            return f"(svc-indexer unavailable: {exc})"
