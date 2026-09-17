"""Run-id minting and the per-run results directory."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def mint_run_id(scenario_tag: str, arm: str, trigger: str, seed: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{scenario_tag}-{arm}-{trigger.replace('-', '')}-s{seed:02d}-{ts}-{secrets.token_hex(3)}"


class RunRecorder:
    def __init__(self, results_root: Path, run_id: str) -> None:
        self.run_id = run_id
        self.dir = Path(results_root) / run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    @property
    def trace_path(self) -> Path:
        return self.dir / "traces.jsonl"

    def write_json(self, name: str, obj: Any) -> None:
        (self.dir / name).write_text(
            json.dumps(obj, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8")

    def write_text(self, name: str, text: str) -> None:
        (self.dir / name).write_text(text, encoding="utf-8")

    def append_jsonl(self, name: str, obj: Any) -> None:
        with open(self.dir / name, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")


def run_config(arm: str, scenario: str, extra: dict | None = None) -> dict:
    """Provenance stamped into every run: policy SHA (pre-registration),
    git SHA, interpreter, and library versions."""
    import hashlib, subprocess, sys
    root = Path(__file__).resolve().parent
    cfg: dict = {"scenario": scenario, "arm": arm, "python": sys.executable}
    try:
        import anthropic; cfg["anthropic"] = anthropic.__version__
    except Exception:
        pass
    try:
        import invariant  # noqa
        from importlib.metadata import version
        cfg["invariant_ai"] = version("invariant-ai")
    except Exception:
        pass
    for arm_id, fname in (("A1", "a1_deterministic.ipl"), ("A2", "a2_with_classifier.ipl")):
        f = root / "policies" / fname
        if f.exists():
            cfg[f"policy_sha_{arm_id}"] = hashlib.sha1(f.read_bytes()).hexdigest()[:12]
    cfg["classifier_pin"] = "protectai/deberta-v3-base-prompt-injection-v2"
    cfg["sampling"] = ("API default; this SDK/model removed temperature. Seed is "
                       "a trial index; variance is inherent nondeterminism.")
    try:
        cfg["git_sha"] = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        cfg["git_sha"] = "unknown"
    if extra:
        cfg.update(extra)
    return cfg
