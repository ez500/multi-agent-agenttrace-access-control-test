# Archived scenarios

The four original case studies. They are archived — the paper's active work is the two
log-processing scenarios — but nothing here is frozen: each package still runs exactly as
it did at the repository root.

| Scenario | What it shows |
|---|---|
| [`huggingface_incident_test/`](huggingface_incident_test) | The July 2026 incident as a 7-rung kill chain against four defense postures; carries the main result (self-report vs. harness-emitted telemetry) |
| [`adversarial_propagation_agent_test/`](adversarial_propagation_agent_test) | A poisoned log entry reaches an edge agent; a downstream privileged agent is hijacked into `wipe_database` |
| [`prompt_injection_agent_test/`](prompt_injection_agent_test) | An adversary learns the authorization schema from the custodian's own diagnostics, then exfiltrates past the deterministic detector |
| [`access_control_persuasion_test/`](access_control_persuasion_test) | An unauthorized agent recons a peer for a valid identity, then impersonates it at the broker |

Each directory keeps its own README with the full setup and per-demo detail.

## Running them

Every package is still self-contained and is run **from inside its own directory**, the
same as before:

```bash
cd archive/huggingface_incident_test
pip install -r requirements.txt
copy .env.example .env      # then set ANTHROPIC_API_KEY=sk-ant-...
python test_imports.py      # static checks, no API key needed
python demo_agenttrace.py
```

`access_control_persuasion_test/` has no `requirements.txt`: it calls the shared gateway in
[`../LLM_API/`](../LLM_API) and reads its credentials from the repo-root `.env`.

Three packages ship a no-API-key `test_imports.py` that exercises the defenses, detectors
and helpers end-to-end — the quickest way to confirm an archived scenario is still healthy:

```bash
for d in adversarial_propagation_agent_test prompt_injection_agent_test huggingface_incident_test; do
  (cd "$d" && python test_imports.py)
done
```

## What the move changed

Only path resolution. The shared [`agenttrace/`](../agenttrace) and
[`LLM_API/`](../LLM_API) directories stayed at the repository root, so the packages no
longer find them one level up. Each `_bootstrap.py` — and every module that puts the
gateway on `sys.path` — now walks up the directory tree for them instead of assuming a
fixed depth, which keeps the packages runnable from wherever they live. Demo logic,
defenses, payloads and results are untouched.
