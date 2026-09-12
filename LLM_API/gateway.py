"""Reusable client for the MSAL-fronted Anthropic gateway used by this project.

``demo.py`` in this directory wires the same endpoint into a Flask route. This
module is the library form: acquire a client-credentials token via MSAL, cache
it for the process lifetime, and issue chat completions against the APIM
endpoint declared in ``.env``.

Environment variables (see ``.env`` at the repo root):

    TENANT_ID, CLIENT_ID, CLIENT_SECRET, SUBSCRIPTION_KEY, LLM_ENDPOINT
    SCOPE            optional, defaults to the Cognitive Services scope
    LLM_MODEL        optional, defaults to global.anthropic.claude-sonnet-4-6
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import msal
import requests
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

DEFAULT_SCOPE = "https://cognitiveservices.azure.com/.default"
DEFAULT_MODEL = "global.anthropic.claude-sonnet-4-6"


class GatewayError(RuntimeError):
    """Raised when the gateway cannot be reached or refuses the request."""


@dataclass
class _TokenCache:
    value: str = ""
    expires_at: float = 0.0

    def valid(self) -> bool:
        return bool(self.value) and time.time() < self.expires_at - 60.0


_TOKEN = _TokenCache()


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise GatewayError(f"missing required environment variable {name}")
    return val


def get_access_token(force: bool = False) -> str:
    """Return a cached client-credentials token, acquiring one if needed."""
    if _TOKEN.valid() and not force:
        return _TOKEN.value

    tenant_id = _require("TENANT_ID")
    client_id = _require("CLIENT_ID")
    client_secret = _require("CLIENT_SECRET")
    scope = os.getenv("SCOPE") or DEFAULT_SCOPE

    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=[scope])
    if "access_token" not in result:
        raise GatewayError(
            f"token acquisition failed: {result.get('error')} — "
            f"{result.get('error_description')}"
        )
    _TOKEN.value = result["access_token"]
    _TOKEN.expires_at = time.time() + float(result.get("expires_in", 3600))
    return _TOKEN.value


def chat(
        prompt: str,
        *,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: Optional[float] = None,
        timeout: float = 120.0,
        retries: int = 2,
) -> str:
    """Send one user turn and return the assistant's text.

    Raises :class:`GatewayError` on transport failure or a non-2xx response so
    callers can decide whether to fall back; never returns a partial result.
    """
    endpoint = _require("LLM_ENDPOINT")
    subscription_key = _require("SUBSCRIPTION_KEY")

    messages: List[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model or os.getenv("LLM_MODEL") or DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = temperature

    last_err = ""
    for attempt in range(retries + 1):
        token = get_access_token(force=attempt > 0)
        try:
            resp = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Ocp-Apim-Subscription-Key": subscription_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_err = f"transport error: {exc}"
            continue

        if resp.ok:
            return _extract_text(resp.json())

        last_err = f"HTTP {resp.status_code}: {resp.text[:500]}"
        # 4xx other than 401/429 will not improve on retry.
        if resp.status_code not in (401, 429) and resp.status_code < 500:
            break

    raise GatewayError(last_err or "unknown gateway failure")


def _extract_text(body: dict) -> str:
    """Pull assistant text out of either an OpenAI- or Anthropic-shaped body."""
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):  # content-block form
            return "".join(
                b.get("text", "") for b in content if isinstance(b, dict)
            )

    content = body.get("content")
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    if isinstance(content, str):
        return content

    raise GatewayError(f"unrecognised response shape: {str(body)[:400]}")


if __name__ == "__main__":
    print(chat("Reply with exactly: gateway ok", max_tokens=32))
