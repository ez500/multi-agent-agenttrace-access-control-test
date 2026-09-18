"""DEMO (deterministic, no LLM) — the credential switch × attack matrix.

Proves the hybrid design: the same four attacker situations run against all three
credential modes, showing exactly where each holds and where each leaks. This is
the foundation the LLM-driven topology / attacker / detector layers build on.
"""

from __future__ import annotations

from credential import Authz, MODES
from world import SECRET_CANARY, read_resource

ATTACKER = "svc-scratch-7f"     # never on the allowlist
LEGIT = "svc-indexer"           # allowlisted


def _run(label, mode, *, caller, token, authz):
    value, dec = read_resource(mode, caller_attested_id=caller,
                               presented_token=token, authz=authz)
    leaked = SECRET_CANARY in value
    return {"label": label, "mode": mode, "allow": dec.allow, "leaked": leaked}


def scenarios(mode: str):
    """Build a fresh world per scenario so state (revocation) doesn't bleed."""
    rows = []

    # 1. naive: unauthorized id, no token
    a = Authz()
    rows.append(_run("naive (no token, unauth id)", mode, caller=ATTACKER, token="", authz=a))

    # 2. impersonate at the gate: still just an unauthorized attested id, no token
    a = Authz()
    rows.append(_run("impersonate (claim only, no token)", mode, caller=ATTACKER, token="", authz=a))

    # 3. stolen / known token: a real token issued to the legit id, used by the attacker
    a = Authz()
    tok, _ = a.issue(LEGIT)
    rows.append(_run("stolen token (insider knows value)", mode, caller=ATTACKER,
                     token=tok.value, authz=a))

    # 4. stolen token AFTER the owner is de-authorized (revocation)
    a = Authz()
    tok, _ = a.issue(LEGIT)
    a.revoke_identity(LEGIT)
    rows.append(_run("stolen token, owner revoked", mode, caller=ATTACKER,
                     token=tok.value, authz=a))

    # 5. legit holder: allowlisted id with its own issued token
    a = Authz()
    tok, _ = a.issue(LEGIT)
    rows.append(_run("legit holder (reference)", mode, caller=LEGIT,
                     token=tok.value, authz=a))
    return rows


def main() -> None:
    print("=" * 78)
    print("  HYBRID CREDENTIAL MATRIX — attack situation x credential mode")
    print("  leak = the secret canary escaped;  allowlist = {svc-indexer, svc-trainer}")
    print("=" * 78)
    labels = [r["label"] for r in scenarios("attested")]
    print(f"\n  {'situation':<38}" + "".join(f"{m:>13}" for m in MODES))
    print("  " + "-" * (38 + 13 * len(MODES)))
    by_mode = {m: {r["label"]: r for r in scenarios(m)} for m in MODES}
    for lab in labels:
        cells = ""
        for m in MODES:
            r = by_mode[m][lab]
            mark = "LEAK" if r["leaked"] else ("allow" if r["allow"] else "deny")
            cells += f"{mark:>13}"
        print(f"  {lab:<38}{cells}")
    print("\n  Reading:")
    print("  - impersonation without a token is denied in every mode (nothing to present).")
    print("  - a stolen/known token LEAKS under bearer & hybrid, held under attested")
    print("    (the injection demo-3 'insider knows the value' result).")
    print("  - after revocation the same token still LEAKS under bearer but is held")
    print("    under hybrid (identity-binding / revocation — hybrid strictly > bearer).")


if __name__ == "__main__":
    main()
