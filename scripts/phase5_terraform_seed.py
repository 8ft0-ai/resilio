"""Closed, credential-free Phase 5 product Terraform grammar seed.

This is NOT a Terraform root or an apply path. No provider, state, plan or IAM
access exists in Slice A. Slice B must review and implement trusted controls.
"""
from __future__ import annotations

import json
from typing import Any

STATE_BUCKET = "resilio-control-e882d4-tfstate"
STATE_PATH = "product/default.tfstate"
LOCK_PATH = "product/default.tflock"
BASE_ADDRESSES = frozenset({
    "google_project_service.reference_pubsub",
    "google_project_service.reference_firestore",
    "google_artifact_registry_repository.product",
    "google_storage_bucket.product_evidence",
    "google_firestore_database.operational",
    "google_pubsub_topic.deployment_events",
})
ROUTING_ADDRESS = "google_pubsub_subscription.deployment_events_push"
ALLOWED = BASE_ADDRESSES | {ROUTING_ADDRESS}
FORBIDDEN_TOKENS = ("google_project_iam_", "google_service_account_iam_",
                    "google_cloud_run_v2_service_iam_", "google_iam_",
                    "google_service_account.", "google_project.", "google_cloud_run_v2_service.")


class CandidateError(ValueError):
    pass


def _pairs_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, value in pairs:
        if key in out:
            raise CandidateError("DUPLICATE_CANDIDATE_KEY")
        out[key] = value
    return out


def validate_candidate(raw: bytes) -> tuple[str, ...]:
    """Validate the v1 address boundary; later slices add exact attribute grammar."""
    if len(raw) > 32768:
        raise CandidateError("CANDIDATE_TOO_LARGE")
    try:
        candidate = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateError("CANDIDATE_JSON_INVALID") from exc
    if type(candidate) is not dict or set(candidate) != {
        "contract", "state_bucket", "state_path", "lock_path", "addresses"
    }:
        raise CandidateError("CANDIDATE_FIELDS_INVALID")
    if (candidate["contract"] != "resilio-product-terraform-candidate/v1"
            or candidate["state_bucket"] != STATE_BUCKET
            or candidate["state_path"] != STATE_PATH
            or candidate["lock_path"] != LOCK_PATH):
        raise CandidateError("CANDIDATE_STATE_DOMAIN_INVALID")
    addresses = candidate["addresses"]
    if type(addresses) is not list or not addresses or len(addresses) != len(set(map(str, addresses))):
        raise CandidateError("CANDIDATE_ADDRESSES_INVALID")
    if any(type(address) is not str or address not in ALLOWED or
           any(token in address for token in FORBIDDEN_TOKENS)
           for address in addresses):
        raise CandidateError("CANDIDATE_ADDRESS_FORBIDDEN")
    # Routing cannot be planned until exact processor URI and D.5 authority exist.
    if ROUTING_ADDRESS in addresses and len(addresses) != 1:
        raise CandidateError("ROUTING_MUST_BE_A_SEPARATE_EXACT_CONSEQUENCE")
    return tuple(sorted(addresses))
