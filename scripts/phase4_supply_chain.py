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

REPOSITORY = "8ft0-ai/resilio"
REPOSITORY_ID = 1335801159
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
BUILD_ID = re.compile(r"^[0-9a-f-]{8,64}$")
IMAGE_DIGEST_REF = re.compile(
    rf"^{re.escape(IMAGE_PREFIX)}@sha256:[0-9a-f]{{64}}$"
)
TRANSITION_OBJECT = re.compile(r"^transitions/[0-9a-f-]{8,64}\.json$")
ALLOWED_BUILD_STATUSES = {"SUCCESS"}
SEVERITY_RANK = {
    "SEVERITY_UNSPECIFIED": 0, "MINIMAL": 1, "LOW": 2, "MEDIUM": 3,
    "HIGH": 4, "CRITICAL": 5,
}


class SupplyChainError(RuntimeError):
    """Fail-closed Phase 4 contract violation."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_full_sha(value: str, label: str) -> str:
    if not FULL_SHA.fullmatch(value):
        raise SupplyChainError(f"{label}_SHA_INVALID")
    return value


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
        "serviceAccount": (
            f"projects/{CONTROL_PROJECT}/serviceAccounts/{BUILDER}"
        ),
        "options": {
            "logging": "CLOUD_LOGGING_ONLY",
            "machineType": "E2_STANDARD_2",
            "requestedVerifyOption": "VERIFIED",
            "sourceProvenanceHash": ["SHA256"],
            "substitutionOption": "MUST_MATCH",
        },
        "tags": tags,
        "timeout": "600s",
    }


def build_request_digest(source_sha: str, workflow_sha: str) -> str:
    return sha256_bytes(canonical_json_bytes(build_request(source_sha, workflow_sha)))


def _resolved_revision(build: dict[str, Any]) -> str:
    provenance = build.get("sourceProvenance") or {}
    resolved = provenance.get("resolvedGitSource") or {}
    revision = resolved.get("revision") or ""
    return revision


def _requested_revision(build: dict[str, Any]) -> str:
    source = build.get("source") or {}
    git_source = source.get("gitSource") or {}
    return git_source.get("revision") or ""


def _requested_url(build: dict[str, Any]) -> str:
    return ((build.get("source") or {}).get("gitSource") or {}).get("url") or ""


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
    if build.get("status") not in ALLOWED_BUILD_STATUSES:
        raise SupplyChainError("BUILD_NOT_SUCCESS")
    if _requested_url(build) != SOURCE_URL:
        raise SupplyChainError("BUILD_SOURCE_URL_MISMATCH")
    if _requested_revision(build) != source_sha:
        raise SupplyChainError("BUILD_REQUESTED_SOURCE_MISMATCH")
    if _resolved_revision(build) != source_sha:
        raise SupplyChainError("BUILD_RESOLVED_SOURCE_MISMATCH")
    expected = build_request(source_sha, workflow_sha)
    # Cloud Build may populate operational/default response fields. Compare the
    # complete decision-critical request surface without treating provider-added
    # status/timing metadata as caller-controlled build semantics.
    actual_steps = build.get("steps") or []
    if not isinstance(actual_steps, list) or len(actual_steps) != len(expected["steps"]):
        raise SupplyChainError("BUILD_STEPS_MISMATCH")
    for actual, wanted in zip(actual_steps, expected["steps"], strict=True):
        if not isinstance(actual, dict):
            raise SupplyChainError("BUILD_STEPS_MISMATCH")
        for key in ("name", "entrypoint", "args"):
            if actual.get(key) != wanted.get(key):
                raise SupplyChainError("BUILD_STEPS_MISMATCH")
        # Any explicitly supplied behaviour-bearing field outside the closed
        # request is a mismatch; provider output-only timing/status is ignored.
        for key in ("env", "secretEnv", "dir", "waitFor", "id", "volumes", "script", "automapSubstitutions"):
            if key in actual and actual.get(key) not in (None, [], "", False):
                raise SupplyChainError("BUILD_STEPS_MISMATCH")
    if build.get("images") != expected["images"]:
        raise SupplyChainError("BUILD_IMAGES_MISMATCH")
    if build.get("serviceAccount") != expected["serviceAccount"]:
        raise SupplyChainError("BUILD_SERVICEACCOUNT_MISMATCH")
    options = build.get("options") or {}
    if not isinstance(options, dict):
        raise SupplyChainError("BUILD_OPTIONS_MISMATCH")
    for key, value in expected["options"].items():
        if options.get(key) != value:
            raise SupplyChainError("BUILD_OPTIONS_MISMATCH")
    if set(build.get("tags") or []) != set(expected["tags"]):
        raise SupplyChainError("BUILD_TAGS_MISMATCH")
    if build.get("timeout") != expected["timeout"]:
        raise SupplyChainError("BUILD_TIMEOUT_MISMATCH")
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
        if build.get("status") != "SUCCESS":
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
        discovered = occurrence.get("discovered") or {}
        if discovered.get("analysisStatus") in {"FINISHED_SUCCESS", "COMPLETE"}:
            completed = ((discovered.get("analysisCompleted") or {}).get("analysisType") or [])
            if not completed or "VULNERABILITY" in completed:
                complete = True
    if not complete:
        raise SupplyChainError("VULNERABILITY_SCAN_UNAVAILABLE")
    return vulnerability_disposition(vulnerability_response.get("occurrences") or [])


def transition_object(build_id: str) -> str:
    if not BUILD_ID.fullmatch(build_id):
        raise SupplyChainError("BUILD_ID_INVALID")
    return f"transitions/{build_id}.json"


def validate_transition_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    required = {
        "contract", "build_id", "source_sha", "workflow_sha", "build_request_sha256",
        "image", "provenance", "vulnerability", "sbom", "adjudication",
    }
    if set(manifest) != required:
        raise SupplyChainError("TRANSITION_MANIFEST_SHAPE_INVALID")
    if manifest["contract"] != "resilio-phase4-transition/v1":
        raise SupplyChainError("TRANSITION_CONTRACT_INVALID")
    require_full_sha(str(manifest["source_sha"]), "SOURCE")
    require_full_sha(str(manifest["workflow_sha"]), "WORKFLOW")
    if not BUILD_ID.fullmatch(str(manifest["build_id"])):
        raise SupplyChainError("BUILD_ID_INVALID")
    if not IMAGE_DIGEST_REF.fullmatch(str(manifest["image"])):
        raise SupplyChainError("TRANSITION_IMAGE_INVALID")
    if manifest["adjudication"] != "PASS":
        raise SupplyChainError("TRANSITION_NOT_DEPLOYMENT_ELIGIBLE")
    if (manifest["vulnerability"] or {}).get("result") != "PASS":
        raise SupplyChainError("TRANSITION_VULNERABILITY_NOT_PASS")
    if not (manifest["provenance"] or {}).get("occurrence"):
        raise SupplyChainError("TRANSITION_PROVENANCE_MISSING")
    sbom = manifest["sbom"] or {}
    if not sbom.get("occurrence") or not sbom.get("location") or not re.fullmatch(r"[0-9a-f]{64}", str(sbom.get("sha256") or "")):
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
    if not occurrence or not location or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SupplyChainError("SBOM_REFERENCE_UNAVAILABLE")
    return {"occurrence": occurrence, "location": location, "sha256": digest}


def transition_manifest(build_result: dict[str, Any], provenance: str, sbom: dict[str, str]) -> dict[str, Any]:
    manifest = {
        "contract": "resilio-phase4-transition/v1",
        "build_id": build_result.get("build_id"),
        "source_sha": build_result.get("source_sha"),
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
        "invokerIamDisabled": False,
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


def verify_cloud_run_service(service: dict[str, Any], policy: dict[str, Any], expected_image: str, expected_source: str) -> dict[str, str]:
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
    env = {row.get("name"): row.get("value") for row in container.get("env") or [] if isinstance(row, dict)}
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
    if len(containers) != 1 or not isinstance(containers[0], dict) or containers[0].get("image") != expected_image:
        raise SupplyChainError("RUN_REVISION_IMAGE_MISMATCH")


def verify_health_response(response: dict[str, Any], expected_source: str) -> None:
    require_full_sha(expected_source, "SOURCE")
    if response != {"status": "ok", "source_sha": expected_source}:
        raise SupplyChainError("RUN_HEALTH_RESPONSE_MISMATCH")


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("build-request"); p.add_argument("--source-sha", required=True); p.add_argument("--workflow-sha", required=True)
    p = commands.add_parser("validate-build"); p.add_argument("--build-json", required=True); p.add_argument("--source-sha", required=True); p.add_argument("--workflow-sha", required=True)
    p = commands.add_parser("select-build"); p.add_argument("--builds-json", required=True); p.add_argument("--source-sha", required=True); p.add_argument("--workflow-sha", required=True)
    p = commands.add_parser("build-identity"); p.add_argument("--build-json", required=True)
    p = commands.add_parser("scan-disposition"); p.add_argument("--discovery-json", required=True); p.add_argument("--vulnerability-json", required=True)
    p = commands.add_parser("provenance-occurrence"); p.add_argument("--occurrences-json", required=True); p.add_argument("--build-id", required=True)
    p = commands.add_parser("sbom-reference"); p.add_argument("--occurrences-json", required=True)
    p = commands.add_parser("make-transition"); p.add_argument("--build-result", required=True); p.add_argument("--provenance-occurrence", required=True); p.add_argument("--sbom-json", required=True); p.add_argument("--output", required=True)
    p = commands.add_parser("validate-transition"); p.add_argument("--manifest", required=True)
    p = commands.add_parser("service-request"); p.add_argument("--image", required=True); p.add_argument("--source-sha", required=True); p.add_argument("--output", required=True)
    p = commands.add_parser("verify-service"); p.add_argument("--service-json", required=True); p.add_argument("--policy-json", required=True); p.add_argument("--expected-image", required=True); p.add_argument("--expected-source", required=True)
    p = commands.add_parser("verify-revision"); p.add_argument("--revision-json", required=True); p.add_argument("--expected-image", required=True)
    p = commands.add_parser("verify-health"); p.add_argument("--response-json", required=True); p.add_argument("--expected-source", required=True)
    args = parser.parse_args()
    try:
        if args.command == "build-request":
            print(json.dumps(build_request(args.source_sha, args.workflow_sha), sort_keys=True, separators=(",", ":")))
        elif args.command == "validate-build":
            build = json.loads(Path(args.build_json).read_text(encoding="utf-8"))
            print(json.dumps(validate_build(build, args.source_sha, args.workflow_sha), sort_keys=True, separators=(",", ":")))
        elif args.command == "select-build":
            payload = json.loads(Path(args.builds_json).read_text(encoding="utf-8"))
            print(select_existing_build(payload.get("builds") or [], args.source_sha, args.workflow_sha) or "")
        elif args.command == "build-identity":
            build = json.loads(Path(args.build_json).read_text(encoding="utf-8")); source, workflow = identity_from_build(build)
            print(json.dumps({"source_sha": source, "workflow_sha": workflow}, sort_keys=True, separators=(",", ":")))
        elif args.command == "scan-disposition":
            discovery = json.loads(Path(args.discovery_json).read_text(encoding="utf-8")); vulnerabilities = json.loads(Path(args.vulnerability_json).read_text(encoding="utf-8"))
            print(scan_disposition(discovery, vulnerabilities))
        elif args.command == "provenance-occurrence":
            response = json.loads(Path(args.occurrences_json).read_text(encoding="utf-8")); print(provenance_occurrence(response, args.build_id))
        elif args.command == "sbom-reference":
            response = json.loads(Path(args.occurrences_json).read_text(encoding="utf-8")); print(json.dumps(sbom_reference(response), sort_keys=True, separators=(",", ":")))
        elif args.command == "make-transition":
            result = json.loads(Path(args.build_result).read_text(encoding="utf-8")); sbom = json.loads(Path(args.sbom_json).read_text(encoding="utf-8"))
            manifest = transition_manifest(result, args.provenance_occurrence, sbom); Path(args.output).write_bytes(canonical_json_bytes(manifest) + b"\n")
        elif args.command == "validate-transition":
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8")); validate_transition_manifest(manifest)
        elif args.command == "service-request":
            Path(args.output).write_bytes(canonical_json_bytes(cloud_run_service_request(args.image, args.source_sha)) + b"\n")
        elif args.command == "verify-service":
            service = json.loads(Path(args.service_json).read_text(encoding="utf-8")); policy = json.loads(Path(args.policy_json).read_text(encoding="utf-8"))
            print(json.dumps(verify_cloud_run_service(service, policy, args.expected_image, args.expected_source), sort_keys=True, separators=(",", ":")))
        elif args.command == "verify-revision":
            revision = json.loads(Path(args.revision_json).read_text(encoding="utf-8")); verify_cloud_run_revision(revision, args.expected_image)
        else:
            response = json.loads(Path(args.response_json).read_text(encoding="utf-8")); verify_health_response(response, args.expected_source)
        return 0
    except (SupplyChainError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"PHASE4_SUPPLY_CHAIN_STOPPED:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
