"""Multi-agent prompt-injection stub: AdversarialAgent -> DataCustodianAgent."""

from .agents import AdversarialAgent, DataCustodianAgent, TRUST_TRIGGERS
from .injection_payloads import LADDER, VALID_VAULT_TICKET, InjectionPayload, payload_for_level
from .tools import (
    CONFIDENTIAL_FILE,
    SECRET_CANARY,
    encode_secret,
    is_prohibited_path,
    read_vault_file,
    response_leaks_secret,
)

__all__ = [
    "AdversarialAgent",
    "DataCustodianAgent",
    "TRUST_TRIGGERS",
    "LADDER",
    "VALID_VAULT_TICKET",
    "InjectionPayload",
    "payload_for_level",
    "CONFIDENTIAL_FILE",
    "SECRET_CANARY",
    "encode_secret",
    "is_prohibited_path",
    "read_vault_file",
    "response_leaks_secret",
]
