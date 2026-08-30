#!/usr/bin/env python3
"""Pure fail-closed helpers for the Resilio Phase 4 trusted supply-chain seed."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPOSITORY = "8ft0-ai/resilio"
REPOSITORY_ID = 1335801159
OWNER_LOGIN = "8ft0-ai"
OWNER_ID = 130460431
SOURCE_URL = "https://github.com/8ft0-ai/resilio.git"
CONTROL_PROJECT = "resilio-control-e882d4"
REFERENCE_PROJECT = "resilio-reference-e882d4"
REGION = "us-central1"
ARTIFACT_REPOSITORY = "resilio-phase4"
IMAGE_PACKAGE = "phase4-proof"
IMAGE_PREFIX = f"{REGION}-docker.pkg.dev/{CONTROL_PROJECT}/{ARTIFACT_REPOSITORY}/{IMAGE_PACKAGE}"
EVIDENCE_BUCKET = "resilio-control-e882d4-phase4-evidence"
CLOUD_RUN_SERVICE = "phase4-proof"
BUILD_INITIATOR = f"github-p4-build@{CONTROL_PROJECT}.iam.gserviceaccount.com"
BUILDER = f"cloudbuild-p4-builder@{CONTROL_PROJECT}.iam.gserviceaccount.com"
EVIDENCE_ADJUDICATOR = f"github-p4-evidence@{CONTROL_PROJECT}.iam.gserviceaccount.com"
DEPLOYER = f"github-p4-deployer@{REFERENCE_PROJECT}.iam.gserviceaccount.com"
RUNTIME = f"p4-proof-runtime@{REFERENCE_PROJECT}.iam.gserviceaccount.com"
VERIFIER = f"github-p4-verifier@{REFERENCE_PROJECT}.iam.gserviceaccount.com"

# Resolved from current evidence before Slice A. These references are immutable.
PYTHON_RUNTIME_IMAGE = (
    "gcr.io/distroless/python3-debian13@"
    "sha256:ed3a4beb46f8f8baac068743ba1b1f95ea3f793422129cf6dd23967f779b6018"
)
DOCKER_BUILDER_IMAGE = (
    "gcr.io/cloud-builders/docker@"
    "sha256:154fcd4d2d65c6a35b06b98053a0829c581e223d530be5719326f5d85d680e8d"
)

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
BUILD_ID = re.compile(r"^[0-9a-f-]{8,64}$")
WORKFLOW_RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")
GOOGLE_ERROR_STATUS = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
GOOGLE_ERROR_REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
GOOGLE_ERROR_DOMAIN = re.compile(r"^(?:[a-z][a-z0-9-]*\.)*googleapis\.com$")
GOOGLE_METADATA_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
GOOGLE_PERMISSION_VALUE = re.compile(r"^containeranalysis\.[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$")
IMAGE_DIGEST_REF = re.compile(
    rf"^{re.escape(IMAGE_PREFIX)}@sha256:[0-9a-f]{{64}}$"
)
TRANSITION_OBJECT = re.compile(r"^transitions/[0-9a-f-]{8,64}\.json$")
ALLOWED_BUILD_STATUSES = {"SUCCESS"}
SEVERITY_RANK = {
    "SEVERITY_UNSPECIFIED": 0,
    "MINIMAL": 1,
    "LOW": 2,
    "MEDIUM": 3,
    "HIGH": 4,
    "CRITICAL": 5,
}

GOOGLE_API_RESPONSE_MAX_BYTES = 65_536
GOOGLE_API_REQUEST_CATEGORIES = {
    "DISCOVERY", "VULNERABILITY", "PROVENANCE", "EXPORT_SBOM", "SBOM_REFERENCE",
}
GOOGLE_ERROR_ROOT_FIELDS = {"error"}
GOOGLE_ERROR_FIELDS = {"code", "message", "status", "details"}
GOOGLE_ERROR_INFO_FIELDS = {"@type", "reason", "domain", "metadata"}
GOOGLE_ERROR_INFO_TYPE = "type.googleapis.com/google.rpc.ErrorInfo"
GOOGLE_SAFE_SERVICE_VALUES = {"containeranalysis.googleapis.com"}
GOOGLE_MESSAGE_CATEGORIES = {
    "UNAUTHENTICATED": "UNAUTHENTICATED",
    "PERMISSION_DENIED": "PERMISSION_DENIED",
    "RESOURCE_EXHAUSTED": "QUOTA_OR_RATE_LIMIT",
    "INVALID_ARGUMENT": "INVALID_REQUEST",
    "FAILED_PRECONDITION": "FAILED_PRECONDITION",
    "NOT_FOUND": "NOT_FOUND",
    "ABORTED": "ABORTED",
    "DEADLINE_EXCEEDED": "SERVICE_UNAVAILABLE",
    "INTERNAL": "SERVICE_UNAVAILABLE",
    "UNAVAILABLE": "SERVICE_UNAVAILABLE",
}

BUILD_OUTPUT_ONLY_FIELDS = {
    "name", "id", "projectId", "status", "statusDetail", "results",
    "createTime", "startTime", "finishTime", "sourceProvenance",
    "buildTriggerId", "logUrl", "timing", "approval", "warnings",
    "failureInfo",
}
BUILD_BEHAVIOUR_FIELDS = {
    "source", "steps", "timeout", "queueTtl", "images", "artifacts",
    "logsBucket", "options", "substitutions", "tags", "secrets",
    "serviceAccount", "availableSecrets", "gitConfig", "dependencies",
}
EMPTY_BUILD_BEHAVIOUR = {
    "artifacts": (None, {}),
    "logsBucket": (None, ""),
    "substitutions": (None, {}),
    "secrets": (None, []),
    "availableSecrets": (None, {}),
    "gitConfig": (None, {}),
    "dependencies": (None, []),
}
STEP_OUTPUT_ONLY_FIELDS = {"timing", "pullTiming", "status", "exitCode", "results"}
STEP_DEFAULTS = {
    "env": (None, []),
    "dir": (None, ""),
    "id": (None, ""),
    "waitFor": (None, []),
    "secretEnv": (None, []),
    "volumes": (None, []),
    "timeout": (None, "", "0s"),
    "allowFailure": (None, False),
    "allowExitCodes": (None, []),
    "script": (None, ""),
    "automapSubstitutions": (None, False),
}
OPTION_DEFAULTS = {
    "diskSizeGb": (None, "", "0"),
    "dynamicSubstitutions": (None, False),
    "automapSubstitutions": (None, False),
    "logStreamingOption": (None, "", "STREAM_DEFAULT", "LOG_STREAMING_OPTION_UNSPECIFIED"),
    "workerPool": (None, ""),
    "pool": (None, {}),
    "env": (None, []),
    "secretEnv": (None, []),
    "volumes": (None, []),
    "defaultLogsBucketBehavior": (None, "", "DEFAULT_LOGS_BUCKET_BEHAVIOR_UNSPECIFIED"),
    "enableStructuredLogging": (None, False),
    "pubsubTopic": (None, ""),
}


class SupplyChainError(RuntimeError):
    """Fail-closed Phase 4 contract violation."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_full_sha(value: str, label: str) -> str:
    if not FULL_SHA.fullmatch(value):
        raise SupplyChainError(f"{label}_SHA_INVALID")
    return value


def _require_google_api_context(
    request_category: str,
    workflow_run_id: str,
    preserved_build_id: str,
) -> None:
    if request_category not in GOOGLE_API_REQUEST_CATEGORIES:
        raise SupplyChainError("GOOGLE_API_REQUEST_CATEGORY_INVALID")
    if not WORKFLOW_RUN_ID.fullmatch(workflow_run_id):
        raise SupplyChainError("GOOGLE_API_WORKFLOW_RUN_ID_INVALID")
    if not BUILD_ID.fullmatch(preserved_build_id):
        raise SupplyChainError("GOOGLE_API_BUILD_ID_INVALID")


def _read_bounded_bytes(path: str, maximum: int, label: str) -> bytes:
    candidate = Path(path)
    try:
        if candidate.is_symlink() or not candidate.is_file():
            raise SupplyChainError(f"{label}_FILE_INVALID")
        size = candidate.stat().st_size
        if size <= 0 or size > maximum:
            raise SupplyChainError(f"{label}_SIZE_INVALID")
        value = candidate.read_bytes()
    except OSError as exc:
        raise SupplyChainError(f"{label}_FILE_INVALID") from exc
    if len(value) != size or len(value) > maximum:
        raise SupplyChainError(f"{label}_SIZE_INVALID")
    return value


def _message_category(status: str | None, reasons: set[str]) -> str:
    if "SERVICE_DISABLED" in reasons:
        return "SERVICE_DISABLED"
    if any(reason.startswith("QUOTA_") or reason == "RATE_LIMIT_EXCEEDED" for reason in reasons):
        return "QUOTA_OR_RATE_LIMIT"
    return GOOGLE_MESSAGE_CATEGORIES.get(status or "", "GOOGLE_API_ERROR")


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"non-JSON constant: {value}")


def sanitize_google_api_error(
    response_json: str,
    http_code: int,
    request_category: str,
    workflow_run_id: str,
    preserved_build_id: str,
) -> dict[str, Any]:
    """Return a closed, non-secret diagnostic for a Google JSON error envelope."""
    _require_google_api_context(request_category, workflow_run_id, preserved_build_id)
    if http_code < 300 or http_code > 599:
        raise SupplyChainError("GOOGLE_API_HTTP_CODE_INVALID")
    raw = _read_bounded_bytes(
        response_json, GOOGLE_API_RESPONSE_MAX_BYTES, "GOOGLE_API_RESPONSE",
    )
    try:
        payload = json.loads(raw.decode("utf-8"), parse_constant=_reject_non_json_constant)
    except ValueError as exc:
        raise SupplyChainError("GOOGLE_API_RESPONSE_JSON_INVALID") from exc
    if not isinstance(payload, dict) or set(payload) != GOOGLE_ERROR_ROOT_FIELDS:
        raise SupplyChainError("GOOGLE_API_ERROR_ENVELOPE_INVALID")
    error = payload.get("error")
    if not isinstance(error, dict) or not set(error).issubset(GOOGLE_ERROR_FIELDS):
        raise SupplyChainError("GOOGLE_API_ERROR_STRUCTURE_INVALID")

    code = error.get("code")
    if code is not None and (isinstance(code, bool) or not isinstance(code, int) or code != http_code):
        raise SupplyChainError("GOOGLE_API_ERROR_CODE_INVALID")
    status = error.get("status")
    if status is not None and (not isinstance(status, str) or not GOOGLE_ERROR_STATUS.fullmatch(status)):
        raise SupplyChainError("GOOGLE_API_ERROR_STATUS_INVALID")
    message = error.get("message")
    if message is not None and (not isinstance(message, str) or len(message) > 4096):
        raise SupplyChainError("GOOGLE_API_ERROR_MESSAGE_INVALID")

    details = error.get("details", [])
    if not isinstance(details, list) or len(details) > 16:
        raise SupplyChainError("GOOGLE_API_ERROR_DETAILS_INVALID")
    reasons: set[str] = set()
    domains: set[str] = set()
    metadata_keys: set[str] = set()
    safe_metadata_values: dict[str, set[str]] = {}
    for detail in details:
        if (
            not isinstance(detail, dict)
            or set(detail).difference(GOOGLE_ERROR_INFO_FIELDS)
            or detail.get("@type") != GOOGLE_ERROR_INFO_TYPE
        ):
            raise SupplyChainError("GOOGLE_API_ERROR_DETAIL_UNSUPPORTED")
        reason = detail.get("reason")
        if reason is not None:
            if not isinstance(reason, str) or not GOOGLE_ERROR_REASON.fullmatch(reason):
                raise SupplyChainError("GOOGLE_API_ERROR_REASON_INVALID")
            reasons.add(reason)
        domain = detail.get("domain")
        if domain is not None:
            if not isinstance(domain, str) or not GOOGLE_ERROR_DOMAIN.fullmatch(domain):
                raise SupplyChainError("GOOGLE_API_ERROR_DOMAIN_INVALID")
            domains.add(domain)
        metadata = detail.get("metadata", {})
        if not isinstance(metadata, dict) or len(metadata) > 64:
            raise SupplyChainError("GOOGLE_API_ERROR_METADATA_INVALID")
        for key, value in metadata.items():
            if not isinstance(key, str) or not GOOGLE_METADATA_KEY.fullmatch(key):
                raise SupplyChainError("GOOGLE_API_ERROR_METADATA_KEY_INVALID")
            if not isinstance(value, str):
                raise SupplyChainError("GOOGLE_API_ERROR_METADATA_VALUE_INVALID")
            metadata_keys.add(key)
            if key == "service" and value in GOOGLE_SAFE_SERVICE_VALUES:
                safe_metadata_values.setdefault(key, set()).add(value)
            elif key == "permission" and GOOGLE_PERMISSION_VALUE.fullmatch(value):
                safe_metadata_values.setdefault(key, set()).add(value)

    diagnostic: dict[str, Any] = {
        "contract": "resilio-phase4-google-api-diagnostic/v1",
        "request_category": request_category,
        "http_code": http_code,
        "message_category": _message_category(status, reasons),
        "metadata_keys": sorted(metadata_keys),
        "workflow_run_id": workflow_run_id,
        "preserved_build_id": preserved_build_id,
    }
    if code is not None:
        diagnostic["google_error_code"] = code
    if status is not None:
        diagnostic["google_error_status"] = status
    if reasons:
        diagnostic["error_info_reasons"] = sorted(reasons)
    if domains:
        diagnostic["error_info_domains"] = sorted(domains)
    if safe_metadata_values:
        diagnostic["safe_metadata_values"] = {
            key: sorted(values) for key, values in sorted(safe_metadata_values.items())
        }
    return diagnostic


def google_api_response_disposition(
    response_json: str,
    http_status_file: str,
    curl_exit_code: int,
    request_category: str,
    workflow_run_id: str,
    preserved_build_id: str,
) -> tuple[int, dict[str, Any] | None]:
    """Return workflow exit disposition and an optional safe diagnostic."""
    _require_google_api_context(request_category, workflow_run_id, preserved_build_id)
    if curl_exit_code < 0 or curl_exit_code > 255:
        raise SupplyChainError("GOOGLE_API_CURL_EXIT_CODE_INVALID")
    if curl_exit_code != 0:
        return 1, {
            "contract": "resilio-phase4-google-api-diagnostic/v1",
            "request_category": request_category,
            "message_category": "TRANSPORT_FAILURE",
            "curl_exit_code": curl_exit_code,
            "workflow_run_id": workflow_run_id,
            "preserved_build_id": preserved_build_id,
        }
    status_bytes = _read_bounded_bytes(http_status_file, 16, "GOOGLE_API_HTTP_STATUS")
    try:
        status_text = status_bytes.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise SupplyChainError("GOOGLE_API_HTTP_STATUS_INVALID") from exc
    if not re.fullmatch(r"[1-5][0-9]{2}", status_text):
        raise SupplyChainError("GOOGLE_API_HTTP_STATUS_INVALID")
    http_code = int(status_text)
    if 200 <= http_code < 300:
        return 0, None
    return 1, sanitize_google_api_error(
        response_json,
        http_code,
        request_category,
        workflow_run_id,
        preserved_build_id,
    )


def image_tag(source_sha: str) -> str:
    require_full_sha(source_sha, "SOURCE")
    return f"{IMAGE_PREFIX}:{source_sha}"


def build_tags(source_sha: str, workflow_sha: str) -> list[str]:
    require_full_sha(source_sha, "SOURCE")
    require_full_sha(workflow_sha, "WORKFLOW")
    return ["resilio-phase4", f"source-{source_sha}", f"control-{workflow_sha}"]


def build_request(source_sha: str, workflow_sha: str) -> dict[str, Any]:
    """Return the only Build request accepted by the Phase 4 proof."""
    target = image_tag(source_sha)
    tags = build_tags(source_sha, workflow_sha)
    return {
        "source": {"gitSource": {"url": SOURCE_URL, "revision": source_sha}},
        "steps": [
            {
                "name": PYTHON_RUNTIME_IMAGE,
                "entrypoint": "/usr/bin/python3",
                "args": ["/workspace/services/phase4-proof/test_app.py"],
            },
            {
                "name": DOCKER_BUILDER_IMAGE,
                "args": [
                    "build", "--network=none",
                    "-f", "services/phase4-proof/Dockerfile",
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
        "tags": tags,
        "timeout": "600s",
        "queueTtl": "600s",
    }


def build_request_digest(source_sha: str, workflow_sha: str) -> str:
    return sha256_bytes(canonical_json_bytes(build_request(source_sha, workflow_sha)))


def _resolved_revision(build: dict[str, Any]) -> str:
    provenance = build.get("sourceProvenance") or {}
    resolved = provenance.get("resolvedGitSource") or {}
    return resolved.get("revision") or ""


def _requested_revision(build: dict[str, Any]) -> str:
    source = build.get("source") or {}
    git_source = source.get("gitSource") or {}
    return git_source.get("revision") or ""


def _requested_url(build: dict[str, Any]) -> str:
    return ((build.get("source") or {}).get("gitSource") or {}).get("url") or ""


def _require_default(value: Any, allowed: tuple[Any, ...], label: str) -> None:
    if value not in allowed:
        raise SupplyChainError(label)


def _validate_build_source(build: dict[str, Any], expected: dict[str, Any]) -> None:
    source = build.get("source")
    if not isinstance(source, dict) or set(source) != {"gitSource"}:
        raise SupplyChainError("BUILD_SOURCE_SHAPE_MISMATCH")
    git_source = source.get("gitSource")
    if not isinstance(git_source, dict):
        raise SupplyChainError("BUILD_SOURCE_SHAPE_MISMATCH")
    if git_source.get("url") != expected["source"]["gitSource"]["url"]:
        raise SupplyChainError("BUILD_SOURCE_URL_MISMATCH")
    if git_source.get("revision") != expected["source"]["gitSource"]["revision"]:
        raise SupplyChainError("BUILD_REQUESTED_SOURCE_MISMATCH")
    if set(git_source) - {"url", "revision", "dir"}:
        raise SupplyChainError("BUILD_SOURCE_SHAPE_MISMATCH")
    if git_source.get("dir") not in (None, ""):
        raise SupplyChainError("BUILD_SOURCE_SHAPE_MISMATCH")


def _validate_build_steps(build: dict[str, Any], expected: dict[str, Any]) -> None:
    actual_steps = build.get("steps") or []
    wanted_steps = expected["steps"]
    if not isinstance(actual_steps, list) or len(actual_steps) != len(wanted_steps):
        raise SupplyChainError("BUILD_STEPS_MISMATCH")
    allowed_keys = {"name", "entrypoint", "args", *STEP_DEFAULTS, *STEP_OUTPUT_ONLY_FIELDS}
    for actual, wanted in zip(actual_steps, wanted_steps, strict=True):
        if not isinstance(actual, dict):
            raise SupplyChainError("BUILD_STEPS_MISMATCH")
        if set(actual) - allowed_keys:
            raise SupplyChainError("BUILD_STEPS_MISMATCH")
        for key in ("name", "entrypoint", "args"):
            if actual.get(key) != wanted.get(key):
                raise SupplyChainError("BUILD_STEPS_MISMATCH")
        for key, allowed in STEP_DEFAULTS.items():
            _require_default(actual.get(key), allowed, "BUILD_STEPS_MISMATCH")


def _validate_build_options(build: dict[str, Any], expected: dict[str, Any]) -> None:
    options = build.get("options") or {}
    if not isinstance(options, dict):
        raise SupplyChainError("BUILD_OPTIONS_MISMATCH")
    allowed_keys = set(expected["options"]) | set(OPTION_DEFAULTS)
    if set(options) - allowed_keys:
        raise SupplyChainError("BUILD_OPTIONS_MISMATCH")
    for key, value in expected["options"].items():
        if key == "substitutionOption" and value == "MUST_MATCH" and key not in options:
            continue
        if options.get(key) != value:
            raise SupplyChainError("BUILD_OPTIONS_MISMATCH")
    for key, allowed in OPTION_DEFAULTS.items():
        if key not in expected["options"]:
            _require_default(options.get(key), allowed, "BUILD_OPTIONS_MISMATCH")


def build_output_digest(build: dict[str, Any]) -> str:
    results = ((build.get("results") or {}).get("images") or [])
    matching: list[str] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or ""
        digest = row.get("digest") or ""
        if name.startswith(IMAGE_PREFIX + ":") and SHA256.fullmatch(digest):
            matching.append(digest)
    if len(matching) != 1:
        raise SupplyChainError("BUILD_OUTPUT_DIGEST_AMBIGUOUS")
    return matching[0]


def validate_build(build: dict[str, Any], source_sha: str, workflow_sha: str) -> dict[str, str]:
    require_full_sha(source_sha, "SOURCE")
    require_full_sha(workflow_sha, "WORKFLOW")
    if not isinstance(build, dict):
        raise SupplyChainError("BUILD_INVALID")
    unknown = set(build) - BUILD_OUTPUT_ONLY_FIELDS - BUILD_BEHAVIOUR_FIELDS
    if unknown:
        raise SupplyChainError("BUILD_STRUCTURE_UNRECOGNISED")
    if build.get("status") not in ALLOWED_BUILD_STATUSES:
        raise SupplyChainError("BUILD_NOT_SUCCESS")
    expected = build_request(source_sha, workflow_sha)
    _validate_build_source(build, expected)
    if _resolved_revision(build) != source_sha:
        raise SupplyChainError("BUILD_RESOLVED_SOURCE_MISMATCH")
    _validate_build_steps(build, expected)
    if build.get("images") != expected["images"]:
        raise SupplyChainError("BUILD_IMAGES_MISMATCH")
    if build.get("serviceAccount") != expected["serviceAccount"]:
        raise SupplyChainError("BUILD_SERVICEACCOUNT_MISMATCH")
    _validate_build_options(build, expected)
    if set(build.get("tags") or []) != set(expected["tags"]):
        raise SupplyChainError("BUILD_TAGS_MISMATCH")
    if build.get("timeout") != expected["timeout"]:
        raise SupplyChainError("BUILD_TIMEOUT_MISMATCH")
    if build.get("queueTtl") != expected["queueTtl"]:
        raise SupplyChainError("BUILD_QUEUE_TTL_MISMATCH")
    for key, allowed in EMPTY_BUILD_BEHAVIOUR.items():
        _require_default(build.get(key), allowed, "BUILD_BEHAVIOUR_MISMATCH")
    digest = build_output_digest(build)
    return {
        "build_id": str(build.get("id") or ""),
        "source_sha": source_sha,
        "workflow_sha": workflow_sha,
        "build_request_sha256": build_request_digest(source_sha, workflow_sha),
        "image_digest": digest,
        "image": f"{IMAGE_PREFIX}@{digest}",
    }


def select_existing_build(builds: list[dict[str, Any]], source_sha: str, workflow_sha: str) -> str | None:
    expected_tags = set(build_tags(source_sha, workflow_sha))
    matches = []
    for build in builds:
        if not isinstance(build, dict) or build.get("status") != "SUCCESS":
            continue
        if set(build.get("tags") or []) != expected_tags:
            continue
        try:
            validate_build(build, source_sha, workflow_sha)
        except SupplyChainError:
            continue
        build_id = str(build.get("id") or "")
        if not BUILD_ID.fullmatch(build_id):
            raise SupplyChainError("BUILD_ID_INVALID")
        matches.append(build_id)
    if len(matches) > 1:
        raise SupplyChainError("REUSABLE_BUILD_AMBIGUOUS")
    return matches[0] if matches else None


def merge_paged_responses(pages: list[dict[str, Any]], item_key: str) -> dict[str, Any]:
    if item_key not in {"builds", "occurrences"}:
        raise SupplyChainError("PAGINATION_ITEM_KEY_INVALID")
    if not isinstance(pages, list) or not pages:
        raise SupplyChainError("PAGINATION_PAGES_INVALID")
    merged: list[Any] = []
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise SupplyChainError("PAGINATION_PAGE_INVALID")
        unreachable = page.get("unreachable") or []
        if unreachable:
            raise SupplyChainError("PAGINATION_UNREACHABLE")
        items = page.get(item_key) or []
        if not isinstance(items, list):
            raise SupplyChainError("PAGINATION_ITEMS_INVALID")
        merged.extend(items)
        next_token = str(page.get("nextPageToken") or "")
        if index < len(pages) - 1 and not next_token:
            raise SupplyChainError("PAGINATION_PAGE_CHAIN_INVALID")
        if index == len(pages) - 1 and next_token:
            raise SupplyChainError("PAGINATION_INCOMPLETE")
    return {item_key: merged}


def vulnerability_disposition(occurrences: list[dict[str, Any]]) -> str:
    severities: list[int] = []
    for occurrence in occurrences:
        vulnerability = occurrence.get("vulnerability") or {}
        sev = vulnerability.get("effectiveSeverity") or vulnerability.get("severity") or "SEVERITY_UNSPECIFIED"
        severities.append(SEVERITY_RANK.get(sev, 0))
    if not severities:
        return "PASS"
    if max(severities) >= SEVERITY_RANK["CRITICAL"]:
        return "FAIL_CRITICAL"
    if max(severities) >= SEVERITY_RANK["HIGH"]:
        return "HIGH_REVIEW_REQUIRED"
    return "PASS"


def identity_from_build(build: dict[str, Any]) -> tuple[str, str]:
    tags = build.get("tags") or []
    source = [tag[7:] for tag in tags if isinstance(tag, str) and tag.startswith("source-")]
    control = [tag[8:] for tag in tags if isinstance(tag, str) and tag.startswith("control-")]
    if len(source) != 1 or len(control) != 1:
        raise SupplyChainError("BUILD_IDENTITY_TAGS_INVALID")
    require_full_sha(source[0], "SOURCE")
    require_full_sha(control[0], "WORKFLOW")
    return source[0], control[0]


def scan_disposition(discovery_response: dict[str, Any], vulnerability_response: dict[str, Any]) -> str:
    discoveries = discovery_response.get("occurrences") or []
    complete = False
    for occurrence in discoveries:
        discovery = occurrence.get("discovery") or {}
        # Artifact Analysis v1 reports completed analyzer/ecosystem types here;
        # the successful analysisStatus is the authoritative completion signal.
        if discovery.get("analysisStatus") in {"FINISHED_SUCCESS", "COMPLETE"}:
            complete = True
    if not complete:
        raise SupplyChainError("VULNERABILITY_SCAN_UNAVAILABLE")
    return vulnerability_disposition(vulnerability_response.get("occurrences") or [])


def owner_high_acceptance(comments_payload: Any, image: str) -> None:
    if not IMAGE_DIGEST_REF.fullmatch(image):
        raise SupplyChainError("HIGH_ACCEPTANCE_IMAGE_INVALID")
    if not isinstance(comments_payload, list):
        raise SupplyChainError("HIGH_ACCEPTANCE_COMMENTS_INVALID")
    comments: list[Any] = []
    for row in comments_payload:
        if isinstance(row, list):
            comments.extend(row)
        else:
            comments.append(row)
    expected_body = f"PHASE4_HIGH_ACCEPTED image={image}"
    matches = []
    for comment in comments:
        if not isinstance(comment, dict) or comment.get("body") != expected_body:
            continue
        user = comment.get("user") or {}
        if user.get("login") == OWNER_LOGIN and user.get("id") == OWNER_ID:
            matches.append(comment)
    if len(matches) != 1:
        raise SupplyChainError("HIGH_ACCEPTANCE_OWNER_DISPOSITION_INVALID")


def transition_object(build_id: str) -> str:
    if not BUILD_ID.fullmatch(build_id):
        raise SupplyChainError("BUILD_ID_INVALID")
    return f"transitions/{build_id}.json"


def _parse_gs_location(location: str) -> tuple[str, str]:
    parsed = urlparse(location)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path or parsed.params or parsed.query or parsed.fragment:
        raise SupplyChainError("SBOM_LOCATION_INVALID")
    object_name = parsed.path.lstrip("/")
    if not object_name:
        raise SupplyChainError("SBOM_LOCATION_INVALID")
    return parsed.netloc, object_name


def bind_sbom_storage(sbom: dict[str, Any], metadata: dict[str, Any], content: bytes) -> dict[str, str]:
    if not isinstance(sbom, dict) or not isinstance(metadata, dict) or not isinstance(content, bytes):
        raise SupplyChainError("SBOM_STORAGE_METADATA_INVALID")
    location = str(sbom.get("location") or "")
    bucket, object_name = _parse_gs_location(location)
    generation = str(metadata.get("generation") or "")
    expected_digest = str(sbom.get("sha256") or "")
    if metadata.get("bucket") != bucket or metadata.get("name") != object_name:
        raise SupplyChainError("SBOM_STORAGE_OBJECT_MISMATCH")
    if not generation.isdigit() or int(generation) <= 0:
        raise SupplyChainError("SBOM_STORAGE_GENERATION_INVALID")
    if not SHA256_HEX.fullmatch(expected_digest):
        raise SupplyChainError("SBOM_STORAGE_DIGEST_INVALID")
    if sha256_bytes(content) != expected_digest:
        raise SupplyChainError("SBOM_STORAGE_DIGEST_MISMATCH")
    bound = dict(sbom)
    bound["generation"] = generation
    return bound


def validate_transition_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    required = {
        "contract", "build_id", "source_sha", "source_tree_sha", "workflow_sha",
        "build_request_sha256", "image", "provenance", "vulnerability", "sbom",
        "adjudication",
    }
    if set(manifest) != required:
        raise SupplyChainError("TRANSITION_MANIFEST_SHAPE_INVALID")
    if manifest["contract"] != "resilio-phase4-transition/v1":
        raise SupplyChainError("TRANSITION_CONTRACT_INVALID")
    source_sha = require_full_sha(str(manifest["source_sha"]), "SOURCE")
    require_full_sha(str(manifest["source_tree_sha"]), "SOURCE_TREE")
    workflow_sha = require_full_sha(str(manifest["workflow_sha"]), "WORKFLOW")
    if not BUILD_ID.fullmatch(str(manifest["build_id"])):
        raise SupplyChainError("BUILD_ID_INVALID")
    request_digest = str(manifest["build_request_sha256"] or "")
    if not SHA256_HEX.fullmatch(request_digest):
        raise SupplyChainError("TRANSITION_BUILD_REQUEST_DIGEST_INVALID")
    if request_digest != build_request_digest(source_sha, workflow_sha):
        raise SupplyChainError("TRANSITION_BUILD_REQUEST_DIGEST_MISMATCH")
    if not IMAGE_DIGEST_REF.fullmatch(str(manifest["image"])):
        raise SupplyChainError("TRANSITION_IMAGE_INVALID")
    if manifest["adjudication"] != "PASS":
        raise SupplyChainError("TRANSITION_NOT_DEPLOYMENT_ELIGIBLE")
    if (manifest["vulnerability"] or {}).get("result") != "PASS":
        raise SupplyChainError("TRANSITION_VULNERABILITY_NOT_PASS")
    if not (manifest["provenance"] or {}).get("occurrence"):
        raise SupplyChainError("TRANSITION_PROVENANCE_MISSING")
    sbom = manifest["sbom"] or {}
    if (
        not sbom.get("occurrence")
        or not sbom.get("location")
        or not SHA256_HEX.fullmatch(str(sbom.get("sha256") or ""))
        or not str(sbom.get("generation") or "").isdigit()
        or int(str(sbom.get("generation") or "0")) <= 0
    ):
        raise SupplyChainError("TRANSITION_SBOM_INVALID")
    return manifest


def provenance_occurrence(response: dict[str, Any], build_id: str) -> str:
    if not BUILD_ID.fullmatch(build_id):
        raise SupplyChainError("BUILD_ID_INVALID")
    rows = response.get("occurrences") or []
    matches = [
        str(row.get("name") or "")
        for row in rows
        if build_id in str(((row.get("build") or {}).get("provenance") or {}).get("id") or "")
    ]
    if len(matches) != 1 or not matches[0]:
        raise SupplyChainError("PROVENANCE_OCCURRENCE_AMBIGUOUS")
    return matches[0]


def sbom_reference(response: dict[str, Any]) -> dict[str, str]:
    rows = response.get("occurrences") or []
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise SupplyChainError("SBOM_REFERENCE_UNAVAILABLE")
    row = rows[0]
    payload = (row.get("sbomReference") or {}).get("payload") or {}
    predicate = payload.get("predicate") or {}
    location = str(predicate.get("location") or "")
    digest = str((predicate.get("digest") or {}).get("sha256") or "")
    occurrence = str(row.get("name") or "")
    if not occurrence or not location or not SHA256_HEX.fullmatch(digest):
        raise SupplyChainError("SBOM_REFERENCE_UNAVAILABLE")
    _parse_gs_location(location)
    return {"occurrence": occurrence, "location": location, "sha256": digest}


def transition_manifest(
    build_result: dict[str, Any],
    source_tree_sha: str,
    provenance: str,
    sbom: dict[str, str],
) -> dict[str, Any]:
    require_full_sha(source_tree_sha, "SOURCE_TREE")
    manifest = {
        "contract": "resilio-phase4-transition/v1",
        "build_id": build_result.get("build_id"),
        "source_sha": build_result.get("source_sha"),
        "source_tree_sha": source_tree_sha,
        "workflow_sha": build_result.get("workflow_sha"),
        "build_request_sha256": build_result.get("build_request_sha256"),
        "image": build_result.get("image"),
        "provenance": {"occurrence": provenance},
        "vulnerability": {"result": "PASS"},
        "sbom": dict(sbom),
        "adjudication": "PASS",
    }
    return validate_transition_manifest(manifest)


def cloud_run_service_request(image: str, source_sha: str) -> dict[str, Any]:
    if not IMAGE_DIGEST_REF.fullmatch(image):
        raise SupplyChainError("TRANSITION_IMAGE_INVALID")
    require_full_sha(source_sha, "SOURCE")
    return {
        "name": f"projects/{REFERENCE_PROJECT}/locations/{REGION}/services/{CLOUD_RUN_SERVICE}",
        "ingress": "INGRESS_TRAFFIC_ALL",
        "template": {
            "serviceAccount": RUNTIME,
            "timeout": "10s",
            "maxInstanceRequestConcurrency": 10,
            "scaling": {"minInstanceCount": 0, "maxInstanceCount": 1},
            "containers": [{
                "image": image,
                "env": [{"name": "SOURCE_SHA", "value": source_sha}],
                "resources": {"limits": {"cpu": "1", "memory": "256Mi"}},
            }],
        },
    }


def verify_cloud_run_service(
    service: dict[str, Any],
    policy: dict[str, Any],
    expected_image: str,
    expected_source: str,
) -> dict[str, str]:
    expected = cloud_run_service_request(expected_image, expected_source)
    if service.get("ingress") != expected["ingress"] or service.get("invokerIamDisabled") is True:
        raise SupplyChainError("RUN_ACCESS_POSTURE_MISMATCH")
    template = service.get("template") or {}
    wanted = expected["template"]
    for key in ("serviceAccount", "timeout", "maxInstanceRequestConcurrency"):
        if template.get(key) != wanted[key]:
            raise SupplyChainError("RUN_TEMPLATE_MISMATCH")
    scaling = template.get("scaling") or {}
    if scaling.get("minInstanceCount", 0) != 0 or scaling.get("maxInstanceCount") != 1:
        raise SupplyChainError("RUN_SCALING_MISMATCH")
    containers = template.get("containers") or []
    if len(containers) != 1 or not isinstance(containers[0], dict):
        raise SupplyChainError("RUN_CONTAINER_MISMATCH")
    container = containers[0]
    if container.get("image") != expected_image:
        raise SupplyChainError("RUN_IMAGE_MISMATCH")
    env = {
        row.get("name"): row.get("value")
        for row in container.get("env") or []
        if isinstance(row, dict)
    }
    if env.get("SOURCE_SHA") != expected_source:
        raise SupplyChainError("RUN_SOURCE_MISMATCH")
    for binding in policy.get("bindings") or []:
        members = set(binding.get("members") or []) if isinstance(binding, dict) else set()
        if {"allUsers", "allAuthenticatedUsers"} & members:
            raise SupplyChainError("RUN_PUBLIC_PRINCIPAL_FORBIDDEN")
    revision = str(service.get("latestReadyRevision") or "")
    uri = str(service.get("uri") or "")
    if not revision or not uri.startswith("https://"):
        raise SupplyChainError("RUN_READBACK_INCOMPLETE")
    return {"revision": revision, "uri": uri}


def verify_cloud_run_revision(revision: dict[str, Any], expected_image: str) -> None:
    containers = revision.get("containers") or []
    if (
        len(containers) != 1
        or not isinstance(containers[0], dict)
        or containers[0].get("image") != expected_image
    ):
        raise SupplyChainError("RUN_REVISION_IMAGE_MISMATCH")


def verify_health_response(response: dict[str, Any], expected_source: str) -> None:
    require_full_sha(expected_source, "SOURCE")
    if response != {"status": "ok", "source_sha": expected_source}:
        raise SupplyChainError("RUN_HEALTH_RESPONSE_MISMATCH")


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("build-request"); p.add_argument("--source-sha", required=True); p.add_argument("--workflow-sha", required=True)
    p = commands.add_parser("validate-build"); p.add_argument("--build-json", required=True); p.add_argument("--source-sha", required=True); p.add_argument("--workflow-sha", required=True)
    p = commands.add_parser("select-build"); p.add_argument("--builds-json", required=True); p.add_argument("--source-sha", required=True); p.add_argument("--workflow-sha", required=True)
    p = commands.add_parser("merge-pages"); p.add_argument("--pages-json", required=True); p.add_argument("--items-key", required=True, choices=("builds", "occurrences"))
    p = commands.add_parser("build-identity"); p.add_argument("--build-json", required=True)
    p = commands.add_parser("scan-disposition"); p.add_argument("--discovery-json", required=True); p.add_argument("--vulnerability-json", required=True)
    p = commands.add_parser("check-high-acceptance"); p.add_argument("--comments-json", required=True); p.add_argument("--image", required=True)
    p = commands.add_parser("provenance-occurrence"); p.add_argument("--occurrences-json", required=True); p.add_argument("--build-id", required=True)
    p = commands.add_parser("sbom-reference"); p.add_argument("--occurrences-json", required=True)
    p = commands.add_parser("bind-sbom"); p.add_argument("--sbom-json", required=True); p.add_argument("--metadata-json", required=True); p.add_argument("--content-file", required=True)
    p = commands.add_parser("make-transition"); p.add_argument("--build-result", required=True); p.add_argument("--source-tree-sha", required=True); p.add_argument("--provenance-occurrence", required=True); p.add_argument("--sbom-json", required=True); p.add_argument("--output", required=True)
    p = commands.add_parser("validate-transition"); p.add_argument("--manifest", required=True)
    p = commands.add_parser("service-request"); p.add_argument("--image", required=True); p.add_argument("--source-sha", required=True); p.add_argument("--output", required=True)
    p = commands.add_parser("verify-service"); p.add_argument("--service-json", required=True); p.add_argument("--policy-json", required=True); p.add_argument("--expected-image", required=True); p.add_argument("--expected-source", required=True)
    p = commands.add_parser("verify-revision"); p.add_argument("--revision-json", required=True); p.add_argument("--expected-image", required=True)
    p = commands.add_parser("verify-health"); p.add_argument("--response-json", required=True); p.add_argument("--expected-source", required=True)
    p = commands.add_parser("google-api-response"); p.add_argument("--response-json", required=True); p.add_argument("--http-status-file", required=True); p.add_argument("--curl-exit-code", required=True, type=int); p.add_argument("--request-category", required=True, choices=sorted(GOOGLE_API_REQUEST_CATEGORIES)); p.add_argument("--workflow-run-id", required=True); p.add_argument("--preserved-build-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "build-request":
            print(json.dumps(build_request(args.source_sha, args.workflow_sha), sort_keys=True, separators=(",", ":")))
        elif args.command == "validate-build":
            print(json.dumps(validate_build(_load_json(args.build_json), args.source_sha, args.workflow_sha), sort_keys=True, separators=(",", ":")))
        elif args.command == "select-build":
            payload = _load_json(args.builds_json)
            print(select_existing_build(payload.get("builds") or [], args.source_sha, args.workflow_sha) or "")
        elif args.command == "merge-pages":
            print(json.dumps(merge_paged_responses(_load_json(args.pages_json), args.items_key), sort_keys=True, separators=(",", ":")))
        elif args.command == "build-identity":
            source, workflow = identity_from_build(_load_json(args.build_json))
            print(json.dumps({"source_sha": source, "workflow_sha": workflow}, sort_keys=True, separators=(",", ":")))
        elif args.command == "scan-disposition":
            print(scan_disposition(_load_json(args.discovery_json), _load_json(args.vulnerability_json)))
        elif args.command == "check-high-acceptance":
            owner_high_acceptance(_load_json(args.comments_json), args.image)
        elif args.command == "provenance-occurrence":
            print(provenance_occurrence(_load_json(args.occurrences_json), args.build_id))
        elif args.command == "sbom-reference":
            print(json.dumps(sbom_reference(_load_json(args.occurrences_json)), sort_keys=True, separators=(",", ":")))
        elif args.command == "bind-sbom":
            print(json.dumps(bind_sbom_storage(_load_json(args.sbom_json), _load_json(args.metadata_json), Path(args.content_file).read_bytes()), sort_keys=True, separators=(",", ":")))
        elif args.command == "make-transition":
            result = _load_json(args.build_result)
            sbom = _load_json(args.sbom_json)
            manifest = transition_manifest(result, args.source_tree_sha, args.provenance_occurrence, sbom)
            Path(args.output).write_bytes(canonical_json_bytes(manifest) + b"\n")
        elif args.command == "validate-transition":
            validate_transition_manifest(_load_json(args.manifest))
        elif args.command == "service-request":
            Path(args.output).write_bytes(canonical_json_bytes(cloud_run_service_request(args.image, args.source_sha)) + b"\n")
        elif args.command == "verify-service":
            print(json.dumps(verify_cloud_run_service(_load_json(args.service_json), _load_json(args.policy_json), args.expected_image, args.expected_source), sort_keys=True, separators=(",", ":")))
        elif args.command == "verify-revision":
            verify_cloud_run_revision(_load_json(args.revision_json), args.expected_image)
        elif args.command == "verify-health":
            verify_health_response(_load_json(args.response_json), args.expected_source)
        else:
            exit_code, diagnostic = google_api_response_disposition(
                args.response_json,
                args.http_status_file,
                args.curl_exit_code,
                args.request_category,
                args.workflow_run_id,
                args.preserved_build_id,
            )
            if diagnostic is not None:
                print(canonical_json_bytes(diagnostic).decode("utf-8"))
            return exit_code
        return 0
    except (SupplyChainError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"PHASE4_SUPPLY_CHAIN_STOPPED:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
