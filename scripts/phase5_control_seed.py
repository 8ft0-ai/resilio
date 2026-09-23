"""Credential-free Phase 5 delivery-contract seed.

These pure checks do not create a Cloud Build, registry, IAM or Cloud Run client.
Future credential-bearing controls require separate Slice B authority and review.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

CONTROL_PROJECT = "resilio-control-e882d4"
REFERENCE_PROJECT = "resilio-reference-e882d4"
REGION = "us-central1"
IMAGE_REPOSITORY = f"{REGION}-docker.pkg.dev/{CONTROL_PROJECT}/resilio-product/resilio-app"
EVIDENCE_BUCKET = f"gs://{CONTROL_PROJECT}-product-evidence"
SERVICES = {
    "resilio-ingest": ("ingest", f"p5-ingest-runtime@{REFERENCE_PROJECT}.iam.gserviceaccount.com"),
    "resilio-processor": ("processor", f"p5-processor-runtime@{REFERENCE_PROJECT}.iam.gserviceaccount.com"),
    "resilio-api": ("api", f"p5-api-runtime@{REFERENCE_PROJECT}.iam.gserviceaccount.com"),
}
EXACT_RESOURCES = tuple(
    f"projects/{REFERENCE_PROJECT}/locations/{REGION}/services/{name}"
    for name in SERVICES
)
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PRODUCT_IMAGE = re.compile(re.escape(IMAGE_REPOSITORY) + r"@sha256:([0-9a-f]{64})\Z")
FIXED_CONFIG = {"min_instances": 0, "max_instances": 1,
                "timeout_seconds": 10, "concurrency": 10, "public": False}


class ControlError(ValueError):
    pass


def _exact(value: Any, required: set[str]) -> None:
    if type(value) is not dict or set(value) != required:
        raise ControlError("CLOSED_CONTROL_FIELDS_REQUIRED")


def _sha(value: Any, size: int = 64) -> str:
    if type(value) is not str or not (FULL_SHA if size == 40 else HEX64).fullmatch(value):
        raise ControlError("CONTROL_SHA_INVALID")
    return value


def _string(value: Any) -> str:
    if type(value) is not str or not value or len(value) > 1024:
        raise ControlError("CONTROL_STRING_INVALID")
    return value


def validate_release(envelope: Any) -> str:
    """Validate a proposed one-image/three-service envelope as inert data."""
    _exact(envelope, {"contract", "source_sha", "control_sha", "image",
                      "build_id", "evidence", "services"})
    if envelope["contract"] != "resilio-phase5-product-release/v1":
        raise ControlError("RELEASE_CONTRACT_INVALID")
    _sha(envelope["source_sha"], 40)
    _sha(envelope["control_sha"], 40)
    if type(envelope["image"]) is not str or not PRODUCT_IMAGE.fullmatch(envelope["image"]):
        raise ControlError("PRODUCT_IMAGE_MISMATCH")
    _string(envelope["build_id"])
    evidence = envelope["evidence"]
    _exact(evidence, {"tests_sha256", "sbom", "vulnerability", "provenance"})
    _sha(evidence["tests_sha256"])
    for kind in ("sbom", "vulnerability", "provenance"):
        record = evidence[kind]
        _exact(record, {"ref", "sha256"})
        ref = _string(record["ref"])
        if kind == "sbom" and not ref.startswith(EVIDENCE_BUCKET + "/"):
            raise ControlError("EVIDENCE_BUCKET_MISMATCH")
        _sha(record["sha256"])
    services = envelope["services"]
    if type(services) is not dict or set(services) != set(SERVICES):
        raise ControlError("SERVICE_SET_INVALID")
    for name, (component, runtime) in SERVICES.items():
        config = services[name]
        _exact(config, {"resource", "component", "runtime_service_account",
                        "image", "min_instances", "max_instances", "timeout_seconds",
                        "concurrency", "public"})
        if (config["resource"] !=
                f"projects/{REFERENCE_PROJECT}/locations/{REGION}/services/{name}"
                or config["component"] != component
                or config["runtime_service_account"] != runtime
                or config["image"] != envelope["image"]
                or any(type(config[k]) is not type(v) or config[k] != v
                       for k, v in FIXED_CONFIG.items())):
            raise ControlError("SERVICE_CONFIG_MISMATCH")
    return hashlib.sha256(
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                   allow_nan=False).encode("utf-8")
    ).hexdigest()


def require_absence(observation: Any) -> None:
    """Fail closed unless the three exact future service targets are confirmed absent."""
    if type(observation) is not dict or set(observation) != set(EXACT_RESOURCES):
        raise ControlError("DEPLOY_TARGETS_MISMATCH")
    if any(type(observation[k]) is not dict or observation[k] != {"status": "ABSENT"}
           for k in EXACT_RESOURCES):
        raise ControlError("DEPLOY_CREATE_IF_ABSENT_PRECONDITION_FAILED")


def validate_inert_operation(kind: str) -> None:
    if kind not in {"build", "evidence", "deploy", "verify", "acceptance",
                    "terraform-plan", "terraform-apply"}:
        raise ControlError("UNKNOWN_PHASE5_CONTROL")
    # In particular this helper never obtains OIDC tokens or calls providers.
    raise ControlError(f"PHASE5_SLICE_A_INERT:{kind}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("usage: phase5_control_seed.py <control-kind>")
    validate_inert_operation(sys.argv[1])
