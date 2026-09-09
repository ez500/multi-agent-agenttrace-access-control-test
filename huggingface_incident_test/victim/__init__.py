"""The victim system: Hugging Face as an API surface, with no agents.

Modules:

* :mod:`victim.api` — the endpoint surface (:class:`~victim.api.HuggingFaceSurface`),
  the credential authority (:class:`~victim.api.CredentialStore`), and the
  answer-key canary helpers.

Nothing in this package emits telemetry. The victim is a service estate being
driven by request/response traffic from someone else's benchmark harness; it
does not get to write into that harness's log, and it cannot intervene at
machine speed. Its own detection lands on day four
(:meth:`~victim.api.HuggingFaceSurface.notice_abuse`) — real, competent, and
after the harm.
"""

from .api import (
    ACCESS_DENIED,
    CLUSTER_CREDENTIAL,
    CREDENTIALS,
    INFERENCE_HOSTS,
    PARTIAL_DATASETS,
    PRIVATE_REPO_MARKERS,
    PROXY_ZERODAY,
    SOLUTIONS_CANARY,
    SOLUTIONS_REPO_FILE,
    SUPPORTED_ENCODINGS,
    TARGET_DIR,
    VICTIM_NOTICES_ON_DAY,
    ApiResponse,
    CredentialStore,
    HuggingFaceSurface,
    encode_solution,
    extract_solution_value,
    is_private_repo_path,
    recoverable_solution_forms,
    response_leaks_solution,
)

__all__ = [
    "ACCESS_DENIED",
    "CLUSTER_CREDENTIAL",
    "CREDENTIALS",
    "INFERENCE_HOSTS",
    "PARTIAL_DATASETS",
    "PRIVATE_REPO_MARKERS",
    "PROXY_ZERODAY",
    "SOLUTIONS_CANARY",
    "SOLUTIONS_REPO_FILE",
    "SUPPORTED_ENCODINGS",
    "TARGET_DIR",
    "VICTIM_NOTICES_ON_DAY",
    "ApiResponse",
    "CredentialStore",
    "HuggingFaceSurface",
    "encode_solution",
    "extract_solution_value",
    "is_private_repo_path",
    "recoverable_solution_forms",
    "response_leaks_solution",
]
