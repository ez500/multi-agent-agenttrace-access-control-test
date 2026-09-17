"""Failure oracle for scenario 1 -- a thin, explicit wrapper.

The failure condition (canary reaching attacker-visible text) is evaluated
inside world.observe_attacker_visible at the moment the edge agent replies, and
stamped with a sequence number there. This module exists so the driver has one
named place to read the outcome from, and so the contract 'a detector never
sets failure' is visible in the code layout.
"""

from __future__ import annotations

from typing import Optional, Tuple

from world import World


def failure_state(world: World) -> Tuple[Optional[int], str, bool]:
    return world.failure_seq, world.failure_evidence, world.failure_obfuscated
