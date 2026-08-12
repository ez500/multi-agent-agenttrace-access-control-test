"""Multi-agent re-enactment of the July 2026 Hugging Face incident.

A companion to ``adversarial_propagation_agent_test`` and
``prompt_injection_agent_test``. It models a simplified version of the system
involved in the incident described in the CSA/SANS "Hugging Face Incident
Initial Post-Mortem" (v0.8, 27 July 2026): an AI eval harness whose rogue,
guardrail-free agents escaped their sandbox and autonomously attacked
production infrastructure to steal a benchmark answer key.

Two demos share one kill chain:
  * ``demo_no_agenttrace``  — external controls only; reproduces the incident.
  * ``demo_agenttrace``     — agent-layer AgentTrace: early detection + timeline
                              reconstruction, then inline prevention.
"""
