"""Shared machinery for the two log-processing scenarios.

This package is deliberately shared rather than duplicated per scenario: the
token-efficiency claim and the four-arm comparison both depend on the trigger
loop, the digest, the token meter and the verdict shape being *byte-identical*
across scenarios and arms. A duplicated one-character divergence would be a
silent confound that no reviewer could see.

Unlike ``agenttrace/``, this is a proper package with relative imports. It is
reached by the ancestor-walk in each scenario's ``_bootstrap.py``.
"""
