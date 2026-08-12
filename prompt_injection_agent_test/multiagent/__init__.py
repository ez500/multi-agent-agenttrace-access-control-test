"""Multi-agent prompt-injection stub: AdversarialAgent -> DataCustodianAgent."""

from .agents import AdversarialAgent, DataCustodianAgent, TRUST_TRIGGERS
from .injection_payloads import (
    FORGED_TICKET,
    LADDER,
    VALID_VAULT_TICKET,
    InjectionPayload,
    fallback_feedback_payload,
    feedback_opening_payload,
    forged_ticket_control_payload,
    payload_for_level,
    security_aware_payload,
)
from .tools import (
    CONFIDENTIAL_FILE,
    SECRET_CANARY,
    encode_secret,
    is_prohibited_path,
    read_vault_file,
    response_leaks_secret,
    verify_authorization,
)

__all__ = [
    "AdversarialAgent",
    "DataCustodianAgent",
    "TRUST_TRIGGERS",
    "LADDER",
    "VALID_VAULT_TICKET",
    "FORGED_TICKET",
    "InjectionPayload",
    "payload_for_level",
    "feedback_opening_payload",
    "fallback_feedback_payload",
    "security_aware_payload",
    "forged_ticket_control_payload",
    "CONFIDENTIAL_FILE",
    "SECRET_CANARY",
    "encode_secret",
    "is_prohibited_path",
    "read_vault_file",
    "response_leaks_secret",
    "verify_authorization",
]
