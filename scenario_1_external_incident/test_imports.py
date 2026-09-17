#!/usr/bin/env python3
"""Static import + wiring check. No API key, no network, no model downloads
beyond what Invariant may lazy-load. Run before spending any credits.
"""
from __future__ import annotations
import _bootstrap  # noqa
import importlib, importlib.util, sys

def main() -> int:
    ok = True
    # Core modules import.
    for m in ("logproc.bus", "logproc.trigger", "logproc.digest", "logproc.oracle",
              "logproc.outcome", "logproc.verdict", "logproc.processor",
              "logproc.invariant_tier", "logproc.adapter", "logproc.tiers",
              "world", "agents", "episode"):
        try:
            importlib.import_module(m); 
        except Exception as e:
            print(f"FAIL import {m}: {e}"); ok = False
    # G8: OTel must not be importable.
    if importlib.util.find_spec("opentelemetry") is not None:
        print("FAIL opentelemetry is importable (G8)"); ok = False
    # Policies parse.
    from invariant.analyzer import LocalPolicy
    from logproc.tiers import policy_text
    for arm in ("A1", "A2"):
        try:
            LocalPolicy.from_string(policy_text(arm))
        except Exception as e:
            print(f"FAIL policy {arm}: {e}"); ok = False
    print("test_imports:", "OK" if ok else "FAILURES")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
