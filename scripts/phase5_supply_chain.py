#!/usr/bin/env python3
"""Fail-closed Phase 5 product supply-chain and acceptance contracts.

This module contains decision logic only. Network access and credentials live in
reviewed reusable workflows; tests exercise these contracts credential-free.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPOSITORY = "8ft0-ai/resilio"
REPOSITORY_ID = 1335801159
OWNER_LOGIN = "8ft0-ai"
OWNER_ID = 130460431
GOVERNING_ISSUE = 109
SOURCE_URL = "https://github.com/8ft0-ai/resilio.git"
CONTROL_PROJECT = "resilio-control-e882d4"
REFERENCE_PROJECT = "resilio-reference-e882d4"
REGION = "us-central1"
ARTIFACT_REPOSITORY = "resilio-product"
IMAGE_PACKAGE = "resilio-app"
IMAGE_PREFIX = f"{REGION}-docker.pkg.dev/{CONTROL_PROJECT}/{ARTIFACT_REPOSITORY}/{IMAGE_PACKAGE}"
EVIDENCE_BUCKET = f"{CONTROL_PROJECT}-product-evidence"
BUILD_INITIATOR = f"github-p5-build@{CONTROL_PROJECT}.iam.gserviceaccount.com"
BUILDER = f"cloudbuild-p5-builder@{CONTROL_PROJECT}.iam.gserviceaccount.com"
EVIDENCE_ADJUDICATOR = f"github-p5-evidence@{CONTROL_PROJECT}.iam.gserviceaccount.com"
DEPLOYER = f"github-p5-deployer@{REFERENCE_PROJECT}.iam.gserviceaccount.com"
ACCEPTANCE = f"github-p5-acceptance@{REFERENCE_PROJECT}.iam.gserviceaccount.com"
PUSH_IDENTITY = f"p5-pubsub-push@{REFERENCE_PROJECT}.iam.gserviceaccount.com"
WIF_PROVIDER = "projects/400271474382/locations/global/workloadIdentityPools/github/providers/resilio"

PYTHON_RUNTIME_IMAGE = (
    "gcr.io/distroless/python3-debian13@"
    "sha256:ed3a4beb46f8f8baac068743ba1b1f95ea3f793422129cf6dd23967f779b6018"
)
DOCKER_BUILDER_IMAGE = (
    "gcr.io/cloud-builders/docker@"
    "sha256:154fcd4d2d65c6a35b06b98053a0829c581e223d530be5719326f5d85d680e8d"
)

SERVICES = {
    "resilio-ingest": {
        "component": "ingest",
        "runtime_service_account": f"p5-ingest-runtime@{REFERENCE_PROJECT}.iam.gserviceaccount.com",
    },
    "resilio-processor": {
        "component": "processor",
        "runtime_service_account": f"p5-processor-runtime@{REFERENCE_PROJECT}.iam.gserviceaccount.com",
    },
    "resilio-api": {
        "component": "api",
        "runtime_service_account": f"p5-api-runtime@{REFERENCE_PROJECT}.iam.gserviceaccount.com",
    },
}
SERVICE_NAMES = tuple(SERVICES)
SERVICE_RESOURCES = tuple(
    f"projects/{REFERENCE_PROJECT}/locations/{REGION}/services/{name}"
    for name in SERVICE_NAMES
)
FIXED_RUNTIME = {
    "min_instances": 0,
    "max_instances": 1,
    "timeout": "10s",
    "max_instance_request_concurrency": 10,
}
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
BUILD_ID = re.compile(r"^[0-9a-f-]{8,64}$")
RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")
COMMENT_ID = RUN_ID
GENERATION = RUN_ID
IMAGE = re.compile(rf"^{re.escape(IMAGE_PREFIX)}@sha256:[0-9a-f]{{64}}$")
OPERATION = re.compile(
    rf"^projects/{re.escape(REFERENCE_PROJECT)}/locations/{re.escape(REGION)}/operations/"
    r"[A-Za-z0-9][A-Za-z0-9._~-]{0,255}$"
)
RELEASE_OBJECT = re.compile(r"^releases/([0-9a-f]{64})\.json$")
SBOM_OBJECT = re.compile(r"^sbom/([0-9a-f-]{8,64})\.spdx.json$")

BUILD_OUTPUT_FIELDS = {
    "name", "id", "projectId", "status", "statusDetail", "results",
    "createTime", "startTime", "finishTime", "sourceProvenance",
    "buildTriggerId", "logUrl", "timing", "approval", "warnings",
    "failureInfo",
}
BUILD_INPUT_FIELDS = {
    "source", "steps", "timeout", "queueTtl", "images", "artifacts",
    "logsBucket", "options", "substitutions", "tags", "secrets",
    "serviceAccount", "availableSecrets", "gitConfig", "dependencies",
}
STEP_OUTPUT_FIELDS = {"timing", "pullTiming", "status", "exitCode", "results"}
STEP_DEFAULTS = {
    "env": (None, []), "dir": (None, ""), "id": (None, ""),
    "waitFor": (None, []), "secretEnv": (None, []), "volumes": (None, []),
    "timeout": (None, "", "0s"), "allowFailure": (None, False),
    "allowExitCodes": (None, []), "script": (None, ""),
    "automapSubstitutions": (None, False),
}
OPTION_DEFAULTS = {
    "diskSizeGb": (None, "", "0"), "dynamicSubstitutions": (None, False),
    "automapSubstitutions": (None, False),
    "logStreamingOption": (None, "", "STREAM_DEFAULT", "LOG_STREAMING_OPTION_UNSPECIFIED"),
    "workerPool": (None, ""), "pool": (None, {}), "env": (None, []),
    "secretEnv": (None, []), "volumes": (None, []),
    "defaultLogsBucketBehavior": (None, "", "DEFAULT_LOGS_BUCKET_BEHAVIOR_UNSPECIFIED"),
    "enableStructuredLogging": (None, False), "pubsubTopic": (None, ""),
}
EMPTY_BUILD = {
    "logsBucket": (None, ""), "substitutions": (None, {}),
    "secrets": (None, []), "availableSecrets": (None, {}),
    "gitConfig": (None, {}), "dependencies": (None, []),
}
SEVERITY = {
    "SEVERITY_UNSPECIFIED": 0, "MINIMAL": 1, "LOW": 2, "MEDIUM": 3,
    "HIGH": 4, "CRITICAL": 5,
}


class Phase5Error(RuntimeError):
    """Closed Phase 5 contract violation."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_json(path: str | Path) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise Phase5Error(f"DUPLICATE_JSON_KEY:{key}")
            result[key] = value
        return result
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)
    except json.JSONDecodeError as exc:
        raise Phase5Error("JSON_INVALID") from exc


def _exact(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise Phase5Error(f"{label}_FIELDS_INVALID")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not FULL_SHA.fullmatch(value):
        raise Phase5Error(f"{label}_SHA_INVALID")
    return value


def _hex(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise Phase5Error(f"{label}_DIGEST_INVALID")
    return value


def _require_default(value: Any, allowed: tuple[Any, ...], label: str) -> None:
    if value not in allowed:
        raise Phase5Error(label)


def image_tag(source_sha: str) -> str:
    _sha(source_sha, "SOURCE")
    return f"{IMAGE_PREFIX}:source-{source_sha}"


def build_tags(source_sha: str, workflow_sha: str) -> list[str]:
    _sha(source_sha, "SOURCE")
    _sha(workflow_sha, "WORKFLOW")
    return [f"phase5-product", f"source-{source_sha}", f"control-{workflow_sha}"]


def build_request(source_sha: str, workflow_sha: str) -> dict[str, Any]:
    target = image_tag(source_sha)
    return {
        "source": {"gitSource": {"url": SOURCE_URL, "revision": source_sha}},
        "steps": [
            {
                "name": PYTHON_RUNTIME_IMAGE,
                "entrypoint": "/usr/bin/python3",
                "args": ["/workspace/tests/test_phase5_product.py"],
            },
            {
                "name": PYTHON_RUNTIME_IMAGE,
                "entrypoint": "/usr/bin/python3",
                "args": ["/workspace/tests/test_phase5_control.py"],
            },
            {
                "name": DOCKER_BUILDER_IMAGE,
                "args": [
                    "build", "--network=none",
                    "-f", "services/resilio_app/Dockerfile",
                    "-t", target, ".",
                ],
            },
        ],
        "images": [target],
        "serviceAccount": f"projects/{CONTROL_PROJECT}/serviceAccounts/{BUILDER}",
        "options": {
            "logging": "CLOUD_LOGGING_ONLY",
            "machineType": "E2_STANDARD_2",
            "requestedVerifyOption": "VERIFIED",
            "sourceProvenanceHash": ["SHA256"],
            "substitutionOption": "MUST_MATCH",
        },
        "tags": build_tags(source_sha, workflow_sha),
        "timeout": "600s",
        "queueTtl": "600s",
    }


def build_request_sha256(source_sha: str, workflow_sha: str) -> str:
    return sha256_bytes(canonical_json_bytes(build_request(source_sha, workflow_sha)))


def _validate_build_steps(build: dict[str, Any], expected: dict[str, Any]) -> None:
    actual = build.get("steps")
    wanted = expected["steps"]
    if not isinstance(actual, list) or len(actual) != len(wanted):
        raise Phase5Error("BUILD_STEPS_MISMATCH")
    allowed = {"name", "entrypoint", "args", *STEP_DEFAULTS, *STEP_OUTPUT_FIELDS}
    for left, right in zip(actual, wanted, strict=True):
        if not isinstance(left, dict) or set(left) - allowed:
            raise Phase5Error("BUILD_STEPS_MISMATCH")
        for key in ("name", "entrypoint", "args"):
            if left.get(key) != right.get(key):
                raise Phase5Error("BUILD_STEPS_MISMATCH")
        for key, values in STEP_DEFAULTS.items():
            _require_default(left.get(key), values, "BUILD_STEPS_MISMATCH")


def _validate_build_options(build: dict[str, Any], expected: dict[str, Any]) -> None:
    actual = build.get("options") or {}
    if not isinstance(actual, dict) or set(actual) - set(expected["options"]) - set(OPTION_DEFAULTS):
        raise Phase5Error("BUILD_OPTIONS_MISMATCH")
    for key, value in expected["options"].items():
        if key == "substitutionOption" and key not in actual:
            continue
        if actual.get(key) != value:
            raise Phase5Error("BUILD_OPTIONS_MISMATCH")
    for key, values in OPTION_DEFAULTS.items():
        if key not in expected["options"]:
            _require_default(actual.get(key), values, "BUILD_OPTIONS_MISMATCH")


def validate_build(build: Any, source_sha: str, workflow_sha: str) -> dict[str, str]:
    _sha(source_sha, "SOURCE")
    _sha(workflow_sha, "WORKFLOW")
    if not isinstance(build, dict) or set(build) - BUILD_OUTPUT_FIELDS - BUILD_INPUT_FIELDS:
        raise Phase5Error("BUILD_STRUCTURE_INVALID")
    if build.get("status") != "SUCCESS":
        raise Phase5Error("BUILD_NOT_SUCCESS")
    expected = build_request(source_sha, workflow_sha)
    source = build.get("source")
    if not isinstance(source, dict) or set(source) != {"gitSource"}:
        raise Phase5Error("BUILD_SOURCE_MISMATCH")
    git = source["gitSource"]
    if not isinstance(git, dict) or git.get("url") != SOURCE_URL or git.get("revision") != source_sha:
        raise Phase5Error("BUILD_SOURCE_MISMATCH")
    if set(git) - {"url", "revision", "dir"} or git.get("dir") not in (None, ""):
        raise Phase5Error("BUILD_SOURCE_MISMATCH")
    resolved = ((build.get("sourceProvenance") or {}).get("resolvedGitSource") or {})
    if resolved.get("revision") != source_sha:
        raise Phase5Error("BUILD_RESOLVED_SOURCE_MISMATCH")
    _validate_build_steps(build, expected)
    if build.get("images") != expected["images"]:
        raise Phase5Error("BUILD_IMAGES_MISMATCH")
    artifacts = build.get("artifacts")
    if artifacts not in (None, {}):
        if not isinstance(artifacts, dict) or set(artifacts) != {"images"} or artifacts["images"] != expected["images"]:
            raise Phase5Error("BUILD_ARTIFACTS_MISMATCH")
    if build.get("serviceAccount") != expected["serviceAccount"]:
        raise Phase5Error("BUILD_SERVICE_ACCOUNT_MISMATCH")
    _validate_build_options(build, expected)
    if set(build.get("tags") or []) != set(expected["tags"]):
        raise Phase5Error("BUILD_TAGS_MISMATCH")
    if build.get("timeout") != "600s" or build.get("queueTtl") != "600s":
        raise Phase5Error("BUILD_TIME_BOUND_MISMATCH")
    for key, values in EMPTY_BUILD.items():
        _require_default(build.get(key), values, "BUILD_BEHAVIOUR_MISMATCH")
    results = ((build.get("results") or {}).get("images") or [])
    digests = []
    for item in results:
        if not isinstance(item, dict):
            continue
        digest = item.get("digest")
        name = item.get("name") or ""
        if isinstance(digest, str) and SHA256.fullmatch(digest) and name.startswith(IMAGE_PREFIX + ":"):
            digests.append(digest)
    if len(digests) != 1:
        raise Phase5Error("BUILD_OUTPUT_DIGEST_AMBIGUOUS")
    build_id = str(build.get("id") or "")
    if not BUILD_ID.fullmatch(build_id):
        raise Phase5Error("BUILD_ID_INVALID")
    image = f"{IMAGE_PREFIX}@{digests[0]}"
    tests = {
        "contract": "resilio-phase5-tests/v1",
        "build_id": build_id,
        "source_sha": source_sha,
        "control_sha": workflow_sha,
        "steps": [0, 1],
        "status": "SUCCESS",
    }
    provenance = {
        "contract": "resilio-phase5-build-provenance/v1",
        "build_id": build_id,
        "source_sha": source_sha,
        "control_sha": workflow_sha,
        "build_request_sha256": build_request_sha256(source_sha, workflow_sha),
        "image": image,
    }
    return {
        "build_id": build_id,
        "source_sha": source_sha,
        "control_sha": workflow_sha,
        "image": image,
        "image_digest": digests[0],
        "build_request_sha256": provenance["build_request_sha256"],
        "tests_sha256": sha256_bytes(canonical_json_bytes(tests)),
        "provenance_sha256": sha256_bytes(canonical_json_bytes(provenance)),
    }


def build_identity_from_tags(build: Any) -> tuple[str, str]:
    if not isinstance(build, dict):
        raise Phase5Error("BUILD_INVALID")
    tags = build.get("tags") or []
    source = [tag[7:] for tag in tags if isinstance(tag, str) and tag.startswith("source-")]
    control = [tag[8:] for tag in tags if isinstance(tag, str) and tag.startswith("control-")]
    if len(source) != 1 or len(control) != 1:
        raise Phase5Error("BUILD_IDENTITY_TAGS_INVALID")
    return _sha(source[0], "SOURCE"), _sha(control[0], "WORKFLOW")


def scan_summary(discovery: Any, vulnerabilities: Any, image: str) -> dict[str, Any]:
    if not IMAGE.fullmatch(image):
        raise Phase5Error("SCAN_IMAGE_INVALID")
    if not isinstance(discovery, dict) or not isinstance(vulnerabilities, dict):
        raise Phase5Error("SCAN_RESPONSE_INVALID")
    discoveries = discovery.get("occurrences") or []
    if not isinstance(discoveries, list) or not any(
        isinstance(row, dict)
        and ((row.get("discovery") or {}).get("analysisStatus") in {"FINISHED_SUCCESS", "COMPLETE"})
        for row in discoveries
    ):
        raise Phase5Error("VULNERABILITY_SCAN_UNAVAILABLE")
    rows = []
    for occurrence in vulnerabilities.get("occurrences") or []:
        if not isinstance(occurrence, dict):
            raise Phase5Error("VULNERABILITY_OCCURRENCE_INVALID")
        vulnerability = occurrence.get("vulnerability") or {}
        severity = vulnerability.get("effectiveSeverity") or vulnerability.get("severity") or "SEVERITY_UNSPECIFIED"
        if severity not in SEVERITY:
            raise Phase5Error("VULNERABILITY_SEVERITY_INVALID")
        rows.append({
            "name": str(occurrence.get("name") or ""),
            "note_name": str(occurrence.get("noteName") or ""),
            "resource_uri": str(occurrence.get("resourceUri") or ""),
            "severity": severity,
        })
    rows.sort(key=lambda row: (row["severity"], row["name"], row["note_name"], row["resource_uri"]))
    maximum = max((SEVERITY[row["severity"]] for row in rows), default=0)
    disposition = "PASS" if maximum < SEVERITY["HIGH"] else "FAIL_HIGH_OR_CRITICAL"
    summary = {
        "contract": "resilio-phase5-vulnerability-evidence/v1",
        "image": image,
        "disposition": disposition,
        "occurrences": rows,
    }
    return {
        "disposition": disposition,
        "sha256": sha256_bytes(canonical_json_bytes(summary)),
        "summary": summary,
    }


def validate_spdx(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase5Error("SBOM_JSON_INVALID") from exc
    if not isinstance(document, dict) or not str(document.get("spdxVersion") or "").startswith("SPDX-"):
        raise Phase5Error("SBOM_SPDX_INVALID")
    if document.get("SPDXID") != "SPDXRef-DOCUMENT":
        raise Phase5Error("SBOM_SPDX_ID_INVALID")
    return {"sha256": sha256_bytes(raw), "size": len(raw)}


def release_envelope(build: Any, source_sha: str, workflow_sha: str, sbom_ref: str,
                     sbom_sha256: str, sbom_size: int, vulnerability_ref: str,
                     vulnerability_sha256: str, vulnerability_disposition: str) -> dict[str, Any]:
    identity = validate_build(build, source_sha, workflow_sha)
    if not SBOM_OBJECT.fullmatch(sbom_ref) or not HEX64.fullmatch(sbom_sha256) or sbom_size <= 0:
        raise Phase5Error("SBOM_EVIDENCE_INVALID")
    if vulnerability_disposition != "PASS" or not HEX64.fullmatch(vulnerability_sha256):
        raise Phase5Error("VULNERABILITY_GATE_NOT_PASS")
    if not vulnerability_ref.startswith("artifactanalysis://"):
        raise Phase5Error("VULNERABILITY_REFERENCE_INVALID")
    image = identity["image"]
    services = {
        name: {
            "resource": f"projects/{REFERENCE_PROJECT}/locations/{REGION}/services/{name}",
            "component": config["component"],
            "runtime_service_account": config["runtime_service_account"],
            "image": image,
            **FIXED_RUNTIME,
        }
        for name, config in SERVICES.items()
    }
    envelope = {
        "contract": "resilio-phase5-product-release/v1",
        "source_sha": source_sha,
        "control_sha": workflow_sha,
        "image": image,
        "build_id": identity["build_id"],
        "build_request_sha256": identity["build_request_sha256"],
        "evidence": {
            "tests_sha256": identity["tests_sha256"],
            "sbom": {
                "ref": f"gs://{EVIDENCE_BUCKET}/{sbom_ref}",
                "sha256": sbom_sha256,
                "size": sbom_size,
            },
            "vulnerability": {
                "ref": vulnerability_ref,
                "sha256": vulnerability_sha256,
                "disposition": "PASS",
            },
            "provenance": {
                "ref": f"cloudbuild://projects/{CONTROL_PROJECT}/builds/{identity['build_id']}",
                "sha256": identity["provenance_sha256"],
            },
        },
        "services": services,
    }
    validate_release(envelope)
    return envelope


def validate_release(envelope: Any, expected_release_id: str | None = None) -> str:
    _exact(envelope, {
        "contract", "source_sha", "control_sha", "image", "build_id",
        "build_request_sha256", "evidence", "services",
    }, "RELEASE")
    if envelope["contract"] != "resilio-phase5-product-release/v1":
        raise Phase5Error("RELEASE_CONTRACT_INVALID")
    _sha(envelope["source_sha"], "SOURCE")
    _sha(envelope["control_sha"], "CONTROL")
    if not isinstance(envelope["image"], str) or not IMAGE.fullmatch(envelope["image"]):
        raise Phase5Error("RELEASE_IMAGE_INVALID")
    if not isinstance(envelope["build_id"], str) or not BUILD_ID.fullmatch(envelope["build_id"]):
        raise Phase5Error("RELEASE_BUILD_ID_INVALID")
    _hex(envelope["build_request_sha256"], "BUILD_REQUEST")
    evidence = _exact(envelope["evidence"], {"tests_sha256", "sbom", "vulnerability", "provenance"}, "EVIDENCE")
    _hex(evidence["tests_sha256"], "TESTS")
    sbom = _exact(evidence["sbom"], {"ref", "sha256", "size"}, "SBOM")
    if not isinstance(sbom["ref"], str) or not sbom["ref"].startswith(f"gs://{EVIDENCE_BUCKET}/sbom/"):
        raise Phase5Error("SBOM_REFERENCE_INVALID")
    _hex(sbom["sha256"], "SBOM")
    if type(sbom["size"]) is not int or sbom["size"] <= 0:
        raise Phase5Error("SBOM_SIZE_INVALID")
    vulnerability = _exact(evidence["vulnerability"], {"ref", "sha256", "disposition"}, "VULNERABILITY")
    if not isinstance(vulnerability["ref"], str) or not vulnerability["ref"].startswith("artifactanalysis://"):
        raise Phase5Error("VULNERABILITY_REFERENCE_INVALID")
    _hex(vulnerability["sha256"], "VULNERABILITY")
    if vulnerability["disposition"] != "PASS":
        raise Phase5Error("VULNERABILITY_GATE_NOT_PASS")
    provenance = _exact(evidence["provenance"], {"ref", "sha256"}, "PROVENANCE")
    if provenance["ref"] != f"cloudbuild://projects/{CONTROL_PROJECT}/builds/{envelope['build_id']}":
        raise Phase5Error("PROVENANCE_REFERENCE_INVALID")
    _hex(provenance["sha256"], "PROVENANCE")
    services = envelope["services"]
    if not isinstance(services, dict) or set(services) != set(SERVICES):
        raise Phase5Error("SERVICE_SET_INVALID")
    for name, fixed in SERVICES.items():
        config = _exact(services[name], {
            "resource", "component", "runtime_service_account", "image",
            "min_instances", "max_instances", "timeout",
            "max_instance_request_concurrency",
        }, "SERVICE")
        expected = {
            "resource": f"projects/{REFERENCE_PROJECT}/locations/{REGION}/services/{name}",
            "component": fixed["component"],
            "runtime_service_account": fixed["runtime_service_account"],
            "image": envelope["image"],
            **FIXED_RUNTIME,
        }
        if config != expected:
            raise Phase5Error(f"SERVICE_CONFIG_MISMATCH:{name}")
    release_id = sha256_bytes(canonical_json_bytes(envelope))
    if expected_release_id is not None and release_id != expected_release_id:
        raise Phase5Error("RELEASE_ID_MISMATCH")
    return release_id


def release_object(release_id: str) -> str:
    _hex(release_id, "RELEASE")
    return f"releases/{release_id}.json"


def deployment_authority(comment: Any, comment_id: str) -> dict[str, str]:
    if not COMMENT_ID.fullmatch(comment_id) or not isinstance(comment, dict):
        raise Phase5Error("DEPLOYMENT_AUTHORITY_COMMENT_INVALID")
    if str(comment.get("id")) != comment_id:
        raise Phase5Error("DEPLOYMENT_AUTHORITY_COMMENT_ID_MISMATCH")
    if not str(comment.get("issue_url") or "").endswith(f"/issues/{GOVERNING_ISSUE}"):
        raise Phase5Error("DEPLOYMENT_AUTHORITY_ISSUE_MISMATCH")
    user = comment.get("user") or {}
    if user.get("login") != OWNER_LOGIN or user.get("id") != OWNER_ID:
        raise Phase5Error("DEPLOYMENT_AUTHORITY_OWNER_MISMATCH")
    body = str(comment.get("body") or "")
    match = re.fullmatch(
        r"PHASE5_DEPLOYMENT_AUTHORITY_V1 release_id=([0-9a-f]{64}) "
        r"release_generation=([1-9][0-9]{0,19})", body,
    )
    if not match:
        raise Phase5Error("DEPLOYMENT_AUTHORITY_BODY_INVALID")
    release_id, generation = match.groups()
    return {
        "release_id": release_id,
        "release_generation": generation,
        "release_object": release_object(release_id),
    }


def deployment_consumption_body(authority_comment_id: str, release_id: str,
                                run_id: str, run_attempt: int) -> str:
    if not COMMENT_ID.fullmatch(authority_comment_id) or not HEX64.fullmatch(release_id):
        raise Phase5Error("DEPLOYMENT_CONSUMPTION_IDENTITY_INVALID")
    if not RUN_ID.fullmatch(run_id) or run_attempt != 1:
        raise Phase5Error("DEPLOYMENT_CONSUMPTION_RUN_INVALID")
    return (
        "PHASE5_DEPLOYMENT_AUTHORITY_CONSUMED_V1 "
        f"authority_comment_id={authority_comment_id} release_id={release_id} "
        f"run_id={run_id} run_attempt=1"
    )


def deployment_consumption_available(comments: Any, authority_comment_id: str, release_id: str) -> None:
    if not isinstance(comments, list):
        raise Phase5Error("DEPLOYMENT_COMMENTS_INVALID")
    prefix = (
        "PHASE5_DEPLOYMENT_AUTHORITY_CONSUMED_V1 "
        f"authority_comment_id={authority_comment_id} release_id={release_id} "
    )
    if any(isinstance(row, dict) and str(row.get("body") or "").startswith(prefix) for row in comments):
        raise Phase5Error("DEPLOYMENT_AUTHORITY_ALREADY_CONSUMED")


def verify_deployment_consumption(comments: Any, authority_comment_id: str, release_id: str,
                                  run_id: str, run_attempt: int) -> dict[str, str]:
    expected = deployment_consumption_body(authority_comment_id, release_id, run_id, run_attempt)
    rows = [
        row for row in comments if isinstance(row, dict)
        and row.get("body") == expected
    ] if isinstance(comments, list) else []
    if len(rows) != 1:
        raise Phase5Error("DEPLOYMENT_CONSUMPTION_NOT_EXACTLY_ONCE")
    comment_id = str(rows[0].get("id") or "")
    if not COMMENT_ID.fullmatch(comment_id):
        raise Phase5Error("DEPLOYMENT_CONSUMPTION_COMMENT_ID_INVALID")
    return {"comment_id": comment_id}


def cloud_run_create_request(envelope: Any, release_id: str, service_name: str) -> dict[str, Any]:
    validate_release(envelope, release_id)
    if service_name not in SERVICES:
        raise Phase5Error("SERVICE_NAME_FORBIDDEN")
    config = envelope["services"][service_name]
    return {
        "description": f"Resilio Phase 5 {config['component']} first-slice service.",
        "ingress": "INGRESS_TRAFFIC_ALL",
        "template": {
            "serviceAccount": config["runtime_service_account"],
            "timeout": config["timeout"],
            "maxInstanceRequestConcurrency": config["max_instance_request_concurrency"],
            "scaling": {
                "minInstanceCount": config["min_instances"],
                "maxInstanceCount": config["max_instances"],
            },
            "containers": [{
                "name": "resilio-app",
                "image": config["image"],
                "env": [
                    {"name": "GOOGLE_CLOUD_PROJECT", "value": REFERENCE_PROJECT},
                    {"name": "RESILIO_COMPONENT", "value": config["component"]},
                ],
                "ports": [{"name": "http1", "containerPort": 8080}],
            }],
        },
    }


def service_url(service_name: str) -> str:
    if service_name not in SERVICES:
        raise Phase5Error("SERVICE_NAME_FORBIDDEN")
    return f"https://run.googleapis.com/v2/projects/{REFERENCE_PROJECT}/locations/{REGION}/services/{service_name}"


def operation_outcome(operation: Any, expected_service: str) -> dict[str, str]:
    if expected_service not in SERVICES or not isinstance(operation, dict):
        raise Phase5Error("OPERATION_INPUT_INVALID")
    name = str(operation.get("name") or "")
    if not OPERATION.fullmatch(name):
        raise Phase5Error("OPERATION_NAME_INVALID")
    if operation.get("done") is not True or operation.get("error") not in (None, {}):
        raise Phase5Error("OPERATION_NOT_SUCCESS")
    response = operation.get("response") or {}
    expected = f"projects/{REFERENCE_PROJECT}/locations/{REGION}/services/{expected_service}"
    if not isinstance(response, dict) or response.get("name") != expected:
        raise Phase5Error("OPERATION_RESPONSE_SERVICE_MISMATCH")
    return {"operation": name, "service": expected}


def _env_map(container: dict[str, Any]) -> dict[str, str]:
    rows = container.get("env") or []
    result = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"name", "value"}:
            raise Phase5Error("SERVICE_ENV_INVALID")
        name, value = row.get("name"), row.get("value")
        if not isinstance(name, str) or not isinstance(value, str) or name in result:
            raise Phase5Error("SERVICE_ENV_INVALID")
        result[name] = value
    return result


def verify_service_config(service: Any, envelope: Any, release_id: str,
                          service_name: str) -> dict[str, str]:
    validate_release(envelope, release_id)
    if service_name not in SERVICES or not isinstance(service, dict):
        raise Phase5Error("SERVICE_READBACK_INVALID")
    expected_name = f"projects/{REFERENCE_PROJECT}/locations/{REGION}/services/{service_name}"
    if service.get("name") != expected_name:
        raise Phase5Error("SERVICE_RESOURCE_MISMATCH")
    template = service.get("template") or {}
    if template.get("serviceAccount") != SERVICES[service_name]["runtime_service_account"]:
        raise Phase5Error("SERVICE_RUNTIME_IDENTITY_MISMATCH")
    if template.get("timeout") != "10s" or template.get("maxInstanceRequestConcurrency") != 10:
        raise Phase5Error("SERVICE_RUNTIME_CONFIG_MISMATCH")
    scaling = template.get("scaling") or {}
    if scaling.get("minInstanceCount", 0) != 0 or scaling.get("maxInstanceCount") != 1:
        raise Phase5Error("SERVICE_SCALING_MISMATCH")
    containers = template.get("containers") or []
    if not isinstance(containers, list) or len(containers) != 1:
        raise Phase5Error("SERVICE_CONTAINER_COUNT_INVALID")
    container = containers[0]
    if container.get("image") != envelope["image"]:
        raise Phase5Error("SERVICE_IMAGE_MISMATCH")
    if _env_map(container) != {
        "GOOGLE_CLOUD_PROJECT": REFERENCE_PROJECT,
        "RESILIO_COMPONENT": SERVICES[service_name]["component"],
    }:
        raise Phase5Error("SERVICE_COMPONENT_CONFIG_MISMATCH")
    uri = str(service.get("uri") or "")
    if not uri.startswith("https://") or len(uri) > 512:
        raise Phase5Error("SERVICE_URI_INVALID")
    revision = str(service.get("latestReadyRevision") or "")
    if not revision.startswith(expected_name + "/revisions/"):
        raise Phase5Error("SERVICE_REVISION_INVALID")
    return {"uri": uri, "revision": revision, "service": expected_name}


def verify_service(service: Any, policy: Any, envelope: Any, release_id: str,
                   service_name: str) -> dict[str, str]:
    result = verify_service_config(service, envelope, release_id, service_name)
    if not isinstance(policy, dict):
        raise Phase5Error("SERVICE_IAM_INVALID")
    for binding in policy.get("bindings") or []:
        if not isinstance(binding, dict):
            raise Phase5Error("SERVICE_IAM_INVALID")
        members = binding.get("members") or []
        if "allUsers" in members or "allAuthenticatedUsers" in members:
            raise Phase5Error("SERVICE_PUBLIC_PRINCIPAL_FORBIDDEN")
    return result

def verify_revision(revision: Any, envelope: Any, release_id: str, service_name: str) -> None:
    validate_release(envelope, release_id)
    if service_name not in SERVICES or not isinstance(revision, dict):
        raise Phase5Error("REVISION_INVALID")
    expected_prefix = f"projects/{REFERENCE_PROJECT}/locations/{REGION}/services/{service_name}/revisions/"
    if not str(revision.get("name") or "").startswith(expected_prefix):
        raise Phase5Error("REVISION_NAME_INVALID")
    containers = revision.get("containers") or []
    if not isinstance(containers, list) or len(containers) != 1 or containers[0].get("image") != envelope["image"]:
        raise Phase5Error("REVISION_IMAGE_MISMATCH")


def acceptance_readback(response: Any, expected_event_id: str, expected_payload_sha256: str) -> dict[str, str]:
    if not isinstance(response, dict):
        raise Phase5Error("ACCEPTANCE_API_RESPONSE_INVALID")
    if response.get("event_id") != expected_event_id or response.get("payload_sha256") != expected_payload_sha256:
        raise Phase5Error("ACCEPTANCE_IDENTITY_MISMATCH")
    observed = response.get("observed")
    if not isinstance(observed, dict):
        raise Phase5Error("ACCEPTANCE_OBSERVED_INVALID")
    first = response.get("first_observed_at")
    if not isinstance(first, str) or not first:
        raise Phase5Error("ACCEPTANCE_PROCESSING_METADATA_INVALID")
    return {
        "event_id": expected_event_id,
        "payload_sha256": expected_payload_sha256,
        "first_observed_at": first,
        "observed_sha256": sha256_bytes(canonical_json_bytes(observed)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("build-request"); p.add_argument("--source-sha", required=True); p.add_argument("--workflow-sha", required=True)
    p = commands.add_parser("build-identity"); p.add_argument("--build-json", required=True)
    p = commands.add_parser("validate-build"); p.add_argument("--build-json", required=True); p.add_argument("--source-sha", required=True); p.add_argument("--workflow-sha", required=True)
    p = commands.add_parser("scan-summary"); p.add_argument("--discovery-json", required=True); p.add_argument("--vulnerability-json", required=True); p.add_argument("--image", required=True); p.add_argument("--output", required=True)
    p = commands.add_parser("validate-sbom"); p.add_argument("--file", required=True)
    p = commands.add_parser("release-envelope"); p.add_argument("--build-json", required=True); p.add_argument("--source-sha", required=True); p.add_argument("--workflow-sha", required=True); p.add_argument("--sbom-ref", required=True); p.add_argument("--sbom-sha256", required=True); p.add_argument("--sbom-size", required=True, type=int); p.add_argument("--vulnerability-ref", required=True); p.add_argument("--vulnerability-sha256", required=True); p.add_argument("--vulnerability-disposition", required=True); p.add_argument("--output", required=True)
    p = commands.add_parser("validate-release"); p.add_argument("--file", required=True); p.add_argument("--release-id")
    p = commands.add_parser("validate-deployment-authority"); p.add_argument("--comment-json", required=True); p.add_argument("--comment-id", required=True)
    p = commands.add_parser("deployment-consumption-available"); p.add_argument("--comments-json", required=True); p.add_argument("--authority-comment-id", required=True); p.add_argument("--release-id", required=True)
    p = commands.add_parser("deployment-consumption-body"); p.add_argument("--authority-comment-id", required=True); p.add_argument("--release-id", required=True); p.add_argument("--run-id", required=True); p.add_argument("--run-attempt", type=int, required=True)
    p = commands.add_parser("verify-deployment-consumption"); p.add_argument("--comments-json", required=True); p.add_argument("--authority-comment-id", required=True); p.add_argument("--release-id", required=True); p.add_argument("--run-id", required=True); p.add_argument("--run-attempt", type=int, required=True)
    p = commands.add_parser("create-request"); p.add_argument("--release", required=True); p.add_argument("--release-id", required=True); p.add_argument("--service", required=True); p.add_argument("--output", required=True)
    p = commands.add_parser("operation-outcome"); p.add_argument("--operation-json", required=True); p.add_argument("--service", required=True)
    p = commands.add_parser("verify-created-service"); p.add_argument("--service-json", required=True); p.add_argument("--release", required=True); p.add_argument("--release-id", required=True); p.add_argument("--service", required=True)
    p = commands.add_parser("verify-service"); p.add_argument("--service-json", required=True); p.add_argument("--policy-json", required=True); p.add_argument("--release", required=True); p.add_argument("--release-id", required=True); p.add_argument("--service", required=True)
    p = commands.add_parser("verify-revision"); p.add_argument("--revision-json", required=True); p.add_argument("--release", required=True); p.add_argument("--release-id", required=True); p.add_argument("--service", required=True)
    p = commands.add_parser("acceptance-readback"); p.add_argument("--response-json", required=True); p.add_argument("--event-id", required=True); p.add_argument("--payload-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "build-request":
            print(json.dumps(build_request(args.source_sha, args.workflow_sha), sort_keys=True, separators=(",", ":")))
        elif args.command == "build-identity":
            build = load_json(args.build_json)
            source, control = build_identity_from_tags(build)
            print(json.dumps(validate_build(build, source, control), sort_keys=True, separators=(",", ":")))
        elif args.command == "validate-build":
            print(json.dumps(validate_build(load_json(args.build_json), args.source_sha, args.workflow_sha), sort_keys=True, separators=(",", ":")))
        elif args.command == "scan-summary":
            summary = scan_summary(load_json(args.discovery_json), load_json(args.vulnerability_json), args.image)
            Path(args.output).write_bytes(canonical_json_bytes(summary["summary"]) + b"\n")
            print(json.dumps({k: v for k, v in summary.items() if k != "summary"}, sort_keys=True, separators=(",", ":")))
        elif args.command == "validate-sbom":
            print(json.dumps(validate_spdx(args.file), sort_keys=True, separators=(",", ":")))
        elif args.command == "release-envelope":
            envelope = release_envelope(load_json(args.build_json), args.source_sha, args.workflow_sha,
                                        args.sbom_ref, args.sbom_sha256, args.sbom_size,
                                        args.vulnerability_ref, args.vulnerability_sha256,
                                        args.vulnerability_disposition)
            Path(args.output).write_bytes(canonical_json_bytes(envelope) + b"\n")
            print(validate_release(envelope))
        elif args.command == "validate-release":
            print(validate_release(load_json(args.file), args.release_id))
        elif args.command == "validate-deployment-authority":
            print(json.dumps(deployment_authority(load_json(args.comment_json), args.comment_id), sort_keys=True, separators=(",", ":")))
        elif args.command == "deployment-consumption-available":
            deployment_consumption_available(load_json(args.comments_json), args.authority_comment_id, args.release_id)
        elif args.command == "deployment-consumption-body":
            print(deployment_consumption_body(args.authority_comment_id, args.release_id, args.run_id, args.run_attempt))
        elif args.command == "verify-deployment-consumption":
            print(json.dumps(verify_deployment_consumption(load_json(args.comments_json), args.authority_comment_id, args.release_id, args.run_id, args.run_attempt), sort_keys=True, separators=(",", ":")))
        elif args.command == "create-request":
            Path(args.output).write_bytes(canonical_json_bytes(cloud_run_create_request(load_json(args.release), args.release_id, args.service)) + b"\n")
        elif args.command == "operation-outcome":
            print(json.dumps(operation_outcome(load_json(args.operation_json), args.service), sort_keys=True, separators=(",", ":")))
        elif args.command == "verify-created-service":
            print(json.dumps(verify_service_config(load_json(args.service_json), load_json(args.release), args.release_id, args.service),
                             sort_keys=True, separators=(",", ":")))
        elif args.command == "verify-service":
            print(json.dumps(verify_service(load_json(args.service_json), load_json(args.policy_json),
                                            load_json(args.release), args.release_id, args.service),
                             sort_keys=True, separators=(",", ":")))
        elif args.command == "verify-revision":
            verify_revision(load_json(args.revision_json), load_json(args.release), args.release_id, args.service)
        elif args.command == "acceptance-readback":
            print(json.dumps(acceptance_readback(load_json(args.response_json), args.event_id, args.payload_sha256),
                             sort_keys=True, separators=(",", ":")))
        return 0
    except Phase5Error as exc:
        print(f"PHASE5_CONTROL_STOPPED:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
