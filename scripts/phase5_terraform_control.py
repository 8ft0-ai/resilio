#!/usr/bin/env python3
"""Trusted Phase 5 product Terraform control.

The reviewed control commit supplies backend/provider/lock/grammar. Future
infra/product/candidate.json is fetched as data and cannot add Terraform code.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from phase5_supply_chain import d5_reconciliation_comment, validate_d5_reconciliation

REPOSITORY = "8ft0-ai/resilio"
REPOSITORY_ID = 1335801159
DEFAULT_BRANCH = "main"
CANDIDATE_PATH = "infra/product/candidate.json"
CONTROL_ROOT = "controls/phase5-product-terraform"
STATE_BUCKET = "resilio-control-e882d4-tfstate"
STATE_OBJECT = "product/default.tfstate"
LOCK_OBJECT = "product/default.tflock"
EVIDENCE_PREFIX = "plan-evidence/product/"
CONTROL_PROJECT = "resilio-control-e882d4"
REFERENCE_PROJECT = "resilio-reference-e882d4"
REGION = "us-central1"
PLANNER = f"github-p5-product-planner@{CONTROL_PROJECT}.iam.gserviceaccount.com"
APPLIER = f"github-p5-product-applier@{CONTROL_PROJECT}.iam.gserviceaccount.com"
WIF_PROVIDER = "projects/400271474382/locations/global/workloadIdentityPools/github/providers/resilio"
PUSH_IDENTITY = f"p5-pubsub-push@{REFERENCE_PROJECT}.iam.gserviceaccount.com"
GOVERNING_ISSUE = 109
PROCESSOR_RESOURCE = f"projects/{REFERENCE_PROJECT}/locations/{REGION}/services/resilio-processor"
VERIFY_CALLER_PATH = ".github/workflows/phase5-verify.yml"
VERIFY_REUSABLE_PATH = ".github/workflows/phase5-verify-reusable.yml"
GITHUB_ACTIONS_BOT_LOGIN = "github-actions[bot]"
GITHUB_ACTIONS_BOT_ID = 41898282

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PROCESSOR_URI = re.compile(r"^https://[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app$")
SAFE_EVIDENCE = re.compile(r"^plan-evidence/product/pr-[1-9][0-9]*-[0-9a-f]{40}\.json$")
RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")
COMMENT_ID = RUN_ID
TRUSTED_FILES = ("backend.tf", "provider.tf", "versions.tf", ".terraform.lock.hcl")

BASE_ADDRESSES = (
    "google_artifact_registry_repository.product",
    "google_firestore_database.operational",
    "google_project_service.reference_firestore",
    "google_project_service.reference_pubsub",
    "google_pubsub_topic.deployment_events",
    "google_storage_bucket.product_evidence",
)
ROUTING_ADDRESS = "google_pubsub_subscription.deployment_events_push"

PLAN_TOP_LEVEL_KEYS = {
    "format_version", "terraform_version", "variables", "planned_values",
    "resource_drift", "resource_changes", "deferred_changes",
    "deferred_action_invocations", "output_changes", "action_invocations",
    "prior_state", "configuration", "relevant_attributes", "checks",
    "timestamp", "applyable", "complete", "errored",
}


class ProductTerraformError(RuntimeError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, value in pairs:
        if key in out:
            raise ProductTerraformError(f"DUPLICATE_JSON_KEY:{key}")
        out[key] = value
    return out


def strict_bytes(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductTerraformError("JSON_INVALID") from exc


def strict_file(path: str | Path) -> Any:
    return strict_bytes(Path(path).read_bytes())


def validate_candidate(value: Any) -> dict[str, Any]:
    fields = {"contract", "stage", "processor_uri", "processor_verification_comment_id"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ProductTerraformError("CANDIDATE_FIELDS_INVALID")
    if value["contract"] != "resilio-product-terraform-candidate/v1":
        raise ProductTerraformError("CANDIDATE_CONTRACT_INVALID")
    stage = value["stage"]
    uri = value["processor_uri"]
    verification_comment_id = value["processor_verification_comment_id"]
    if stage in {"empty", "base"}:
        if uri is not None or verification_comment_id is not None:
            raise ProductTerraformError(f"{stage.upper()}_ROUTING_BINDING_FORBIDDEN")
    elif stage == "routing":
        if not isinstance(uri, str) or not PROCESSOR_URI.fullmatch(uri):
            raise ProductTerraformError("ROUTING_PROCESSOR_URI_INVALID")
        if (not isinstance(verification_comment_id, str)
                or not COMMENT_ID.fullmatch(verification_comment_id)):
            raise ProductTerraformError("ROUTING_VERIFICATION_COMMENT_ID_INVALID")
    else:
        raise ProductTerraformError("CANDIDATE_STAGE_INVALID")
    return {
        "contract": value["contract"], "stage": stage, "processor_uri": uri,
        "processor_verification_comment_id": verification_comment_id,
    }


def _base_resources() -> dict[str, Any]:
    return {
        "google_project_service": {
            "reference_firestore": {
                "project": REFERENCE_PROJECT,
                "service": "firestore.googleapis.com",
                "disable_on_destroy": False,
            },
            "reference_pubsub": {
                "project": REFERENCE_PROJECT,
                "service": "pubsub.googleapis.com",
                "disable_on_destroy": False,
            },
        },
        "google_artifact_registry_repository": {
            "product": {
                "project": CONTROL_PROJECT,
                "location": REGION,
                "repository_id": "resilio-product",
                "description": "Resilio product images.",
                "format": "DOCKER",
                "cleanup_policy_dry_run": False,
                "cleanup_policies": [
                    {
                        "id": "keep-recent-product",
                        "action": "KEEP",
                        "most_recent_versions": [{
                            "package_name_prefixes": ["resilio-app"],
                            "keep_count": 3,
                        }],
                    },
                    {
                        "id": "delete-old-product",
                        "action": "DELETE",
                        "condition": [{
                            "tag_state": "ANY",
                            "package_name_prefixes": ["resilio-app"],
                            "older_than": "30d",
                        }],
                    },
                ],
                "deletion_policy": "PREVENT",
            },
        },
        "google_storage_bucket": {
            "product_evidence": {
                "project": CONTROL_PROJECT,
                "name": f"{CONTROL_PROJECT}-product-evidence",
                "location": REGION,
                "storage_class": "STANDARD",
                "uniform_bucket_level_access": True,
                "public_access_prevention": "enforced",
                "force_destroy": False,
                "versioning": [{"enabled": True}],
                "soft_delete_policy": [{"retention_duration_seconds": 0}],
                "lifecycle_rule": [{
                    "action": [{"type": "Delete"}],
                    "condition": [{"age": 365, "with_state": "ANY"}],
                }],
                "deletion_policy": "PREVENT",
            },
        },
        "google_firestore_database": {
            "operational": {
                "project": REFERENCE_PROJECT,
                "name": "(default)",
                "location_id": REGION,
                "type": "FIRESTORE_NATIVE",
                "delete_protection_state": "DELETE_PROTECTION_ENABLED",
                "deletion_policy": "PREVENT",
                "depends_on": ["google_project_service.reference_firestore"],
            },
        },
        "google_pubsub_topic": {
            "deployment_events": {
                "project": REFERENCE_PROJECT,
                "name": "resilio-deployment-events",
                "message_retention_duration": "86400s",
                "depends_on": ["google_project_service.reference_pubsub"],
            },
        },
    }


def resource_document(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate = validate_candidate(candidate)
    if candidate["stage"] == "empty":
        return {}
    resources = _base_resources()
    if candidate["stage"] == "routing":
        uri = candidate["processor_uri"]
        resources["google_pubsub_subscription"] = {
            "deployment_events_push": {
                "project": REFERENCE_PROJECT,
                "name": "resilio-deployment-events-push",
                "topic": f"projects/{REFERENCE_PROJECT}/topics/resilio-deployment-events",
                "ack_deadline_seconds": 20,
                "message_retention_duration": "86400s",
                "push_config": [{
                    "push_endpoint": uri,
                    "attributes": {"x-goog-version": "v1"},
                    "oidc_token": [{
                        "service_account_email": PUSH_IDENTITY,
                        "audience": uri,
                    }],
                }],
                "depends_on": ["google_pubsub_topic.deployment_events"],
            },
        }
    return {"resource": resources}


def expected_creates(stage: str) -> tuple[str, ...]:
    if stage == "empty":
        return ()
    if stage == "base":
        return tuple(sorted(BASE_ADDRESSES))
    if stage == "routing":
        return (ROUTING_ADDRESS,)
    raise ProductTerraformError("CANDIDATE_STAGE_INVALID")


def assemble(trusted_root: str | Path, candidate_file: str | Path, output: str | Path) -> dict[str, str]:
    root = Path(trusted_root)
    candidate = validate_candidate(strict_file(candidate_file))
    control = root / CONTROL_ROOT
    if not all((control / name).is_file() for name in TRUSTED_FILES):
        raise ProductTerraformError("TRUSTED_TERRAFORM_CONTROL_MISSING")
    destination = Path(output)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    hashes = {}
    for name in TRUSTED_FILES:
        raw = (control / name).read_bytes()
        (destination / name).write_bytes(raw)
        hashes[name] = sha256(raw)
    resources = canonical(resource_document(candidate)) + b"\n"
    (destination / "resources.tf.json").write_bytes(resources)
    hashes["resources.tf.json"] = sha256(resources)
    candidate_raw = canonical(candidate) + b"\n"
    hashes["candidate.json"] = sha256(candidate_raw)
    return hashes


def state_identity(state: Any, generation: str) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise ProductTerraformError("STATE_IDENTITY_INVALID")
    if generation == "ABSENT":
        if state != {}:
            raise ProductTerraformError("ABSENT_STATE_MUST_BE_EMPTY")
        return {
            "generation": "ABSENT",
            "lineage": "",
            "serial": 0,
            "managed_addresses": [],
            "state_sha256": sha256(canonical({"state": "ABSENT"})),
        }
    if not generation.isdigit() or int(generation) <= 0:
        raise ProductTerraformError("STATE_IDENTITY_INVALID")
    addresses = []
    for resource in state.get("resources") or []:
        if not isinstance(resource, dict) or resource.get("mode", "managed") != "managed":
            continue
        module = resource.get("module")
        prefix = f"{module}." if isinstance(module, str) and module else ""
        rtype, name = resource.get("type"), resource.get("name")
        if not isinstance(rtype, str) or not isinstance(name, str):
            raise ProductTerraformError("STATE_RESOURCE_IDENTITY_INVALID")
        for instance in resource.get("instances") or []:
            if not isinstance(instance, dict):
                raise ProductTerraformError("STATE_INSTANCE_INVALID")
            index = instance.get("index_key")
            suffix = "" if index is None else f"[{json.dumps(index, separators=(',', ':'))}]"
            addresses.append(f"{prefix}{rtype}.{name}{suffix}")
    return {
        "generation": generation,
        "lineage": str(state.get("lineage") or ""),
        "serial": int(state.get("serial") or 0),
        "managed_addresses": sorted(addresses),
        "state_sha256": sha256(canonical(state)),
    }


def material_effect(plan: Any, stage: str) -> list[dict[str, Any]]:
    if not isinstance(plan, dict) or set(plan) - PLAN_TOP_LEVEL_KEYS:
        raise ProductTerraformError("PLAN_STRUCTURE_INVALID")
    if plan.get("format_version") != "1.2" or plan.get("terraform_version") != "1.15.8":
        raise ProductTerraformError("PLAN_VERSION_INVALID")
    if plan.get("errored") is not False or plan.get("complete") is not True:
        raise ProductTerraformError("PLAN_NOT_COMPLETE")
    for key in ("resource_drift", "deferred_changes", "deferred_action_invocations",
                "action_invocations", "output_changes"):
        if plan.get(key) not in (None, [], {}):
            raise ProductTerraformError(f"PLAN_{key.upper()}_FORBIDDEN")
    rows = []
    for row in plan.get("resource_changes") or []:
        if not isinstance(row, dict) or row.get("mode", "managed") != "managed":
            raise ProductTerraformError("PLAN_RESOURCE_ROW_INVALID")
        change = row.get("change") or {}
        actions = change.get("actions")
        if actions == ["no-op"]:
            continue
        if actions != ["create"] or change.get("before") is not None:
            raise ProductTerraformError("PLAN_NON_CREATE_EFFECT_FORBIDDEN")
        address = row.get("address")
        if not isinstance(address, str):
            raise ProductTerraformError("PLAN_ADDRESS_INVALID")
        rows.append({
            "address": address,
            "type": row.get("type"),
            "name": row.get("name"),
            "provider_name": row.get("provider_name"),
            "change": change,
        })
    if tuple(sorted(row["address"] for row in rows)) != expected_creates(stage):
        raise ProductTerraformError("PLAN_CREATE_SET_MISMATCH")
    if stage == "empty" and plan.get("applyable") not in (False, None):
        raise ProductTerraformError("EMPTY_PLAN_UNEXPECTEDLY_APPLYABLE")
    if stage != "empty" and plan.get("applyable") is not True:
        raise ProductTerraformError("PLAN_NOT_APPLYABLE")
    return sorted(rows, key=lambda row: row["address"])


def private_effect(plan: Any, candidate: dict[str, Any], state: dict[str, Any],
                   routing_binding: dict[str, Any], pr_number: int, base_sha: str,
                   candidate_sha: str, control_sha: str, trusted_tree_sha256: str,
                   provider_lock_sha256: str) -> dict[str, Any]:
    if pr_number <= 0 or not FULL_SHA.fullmatch(base_sha) or not FULL_SHA.fullmatch(candidate_sha):
        raise ProductTerraformError("EFFECT_GITHUB_IDENTITY_INVALID")
    if not FULL_SHA.fullmatch(control_sha) or not HEX64.fullmatch(trusted_tree_sha256) or not HEX64.fullmatch(provider_lock_sha256):
        raise ProductTerraformError("EFFECT_CONTROL_IDENTITY_INVALID")
    candidate = validate_candidate(candidate)
    if not isinstance(routing_binding, dict):
        raise ProductTerraformError("ROUTING_BINDING_INVALID")
    if candidate["stage"] == "routing":
        required = {"comment_id", "release_id", "processor_resource", "processor_uri",
                    "control_sha", "d5_reconciliation_comment_id",
                    "d5_reconciliation_run_id", "d5_reconciliation_caller_sha",
                    "verifier_caller_path", "verifier_caller_sha",
                    "verifier_reusable_path", "verifier_reusable_sha",
                    "verifier_run_id", "verifier_run_attempt"}
        if set(routing_binding) != required:
            raise ProductTerraformError("ROUTING_BINDING_FIELDS_INVALID")
        if (routing_binding["comment_id"] != candidate["processor_verification_comment_id"]
                or routing_binding["processor_resource"] != PROCESSOR_RESOURCE
                or routing_binding["processor_uri"] != candidate["processor_uri"]
                or routing_binding["control_sha"] != control_sha
                or routing_binding["verifier_caller_path"] != VERIFY_CALLER_PATH
                or routing_binding["verifier_reusable_sha"] != control_sha
                or routing_binding["verifier_reusable_path"]
                    != f"{REPOSITORY}/{VERIFY_REUSABLE_PATH}@{control_sha}"):
            raise ProductTerraformError("ROUTING_BINDING_EFFECT_MISMATCH")
    elif routing_binding != {}:
        raise ProductTerraformError("NON_ROUTING_BINDING_FORBIDDEN")
    effect = {
        "contract": "resilio-product-terraform-private-effect/v1",
        "stage": candidate["stage"],
        "processor_uri": candidate["processor_uri"],
        "processor_verification_comment_id": candidate["processor_verification_comment_id"],
        "routing_binding": routing_binding,
        "pr_number": pr_number,
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
        "candidate_sha256": sha256(canonical(candidate)),
        "control_sha": control_sha,
        "trusted_tree_sha256": trusted_tree_sha256,
        "provider_lock_sha256": provider_lock_sha256,
        "state": state,
        "material_effect": material_effect(plan, candidate["stage"]),
    }
    effect["effect_sha256"] = sha256(canonical(effect))
    return effect


def compare_effect(expected: Any, actual: Any) -> None:
    if not isinstance(expected, dict) or not isinstance(actual, dict) or expected != actual:
        raise ProductTerraformError("PRIVATE_EFFECT_MISMATCH")


def public_manifest(effect: dict[str, Any], run_id: str, evidence_object: str) -> dict[str, Any]:
    if not RUN_ID.fullmatch(run_id := str(run_id)) or not SAFE_EVIDENCE.fullmatch(evidence_object):
        raise ProductTerraformError("PUBLIC_MANIFEST_IDENTITY_INVALID")
    return {
        "contract": "resilio-product-terraform-plan-manifest/v1",
        "stage": effect["stage"],
        "routing_verification_comment_id": effect["processor_verification_comment_id"],
        "pr_number": effect["pr_number"],
        "candidate_sha": effect["candidate_sha"],
        "state_generation": effect["state"]["generation"],
        "effect_sha256": effect["effect_sha256"],
        "addresses": [row["address"] for row in effect["material_effect"]],
        "evidence_object": evidence_object,
        "workflow_run_id": run_id,
    }


def _request_json(url: str, token: str | None = None, method: str = "GET",
                  data: bytes | None = None, content_type: str | None = None) -> Any:
    headers = {"Accept": "application/json", "User-Agent": "resilio-phase5-terraform/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read(512).decode("utf-8", "replace")
        raise ProductTerraformError(f"HTTP_{exc.code}:{body[:160]}") from exc
    except urllib.error.URLError as exc:
        raise ProductTerraformError("NETWORK_ERROR") from exc
    return None if not raw else strict_bytes(raw)


def github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise ProductTerraformError("GITHUB_TOKEN_REQUIRED")
    return token


def github(path: str) -> Any:
    return _request_json("https://api.github.com" + path, github_token())


def verify_caller_context(repository: str, ref: str, ref_protected: str,
                          run_attempt: str) -> None:
    if repository != REPOSITORY:
        raise ProductTerraformError("CALLER_REPOSITORY_MISMATCH")
    if ref != "refs/heads/main" or ref_protected != "true":
        raise ProductTerraformError("CALLER_PROTECTED_MAIN_REQUIRED")
    if run_attempt != "1":
        raise ProductTerraformError("CALLER_FIRST_ATTEMPT_REQUIRED")


def routing_binding_from_documents(candidate: dict[str, Any], control_sha: str,
                                   comment: Any, run: Any,
                                   d5_comment: Any, d5_run: Any) -> dict[str, str]:
    candidate = validate_candidate(candidate)
    if candidate["stage"] != "routing":
        if any(value not in (None, {}) for value in (comment, run, d5_comment, d5_run)):
            raise ProductTerraformError("NON_ROUTING_VERIFICATION_EVIDENCE_FORBIDDEN")
        return {}
    if not FULL_SHA.fullmatch(control_sha):
        raise ProductTerraformError("ROUTING_CONTROL_SHA_INVALID")
    comment_id = candidate["processor_verification_comment_id"]
    if not isinstance(comment, dict) or str(comment.get("id") or "") != comment_id:
        raise ProductTerraformError("ROUTING_VERIFICATION_COMMENT_MISMATCH")
    if not str(comment.get("issue_url") or "").endswith(f"/issues/{GOVERNING_ISSUE}"):
        raise ProductTerraformError("ROUTING_VERIFICATION_ISSUE_MISMATCH")
    user = comment.get("user") or {}
    if user.get("login") != GITHUB_ACTIONS_BOT_LOGIN or user.get("id") != GITHUB_ACTIONS_BOT_ID:
        raise ProductTerraformError("ROUTING_VERIFICATION_AUTHOR_MISMATCH")
    match = re.fullmatch(
        r"PHASE5_PROCESSOR_ROUTING_BINDING_V1 "
        r"release_id=([0-9a-f]{64}) "
        r"processor_resource=(projects/resilio-reference-e882d4/locations/us-central1/services/resilio-processor) "
        r"processor_uri=(https://[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app) "
        r"control_sha=([0-9a-f]{40}) d5_reconciliation_comment_id=([1-9][0-9]{0,19}) "
        r"verifier_caller_sha=([0-9a-f]{40}) verifier_run_id=([1-9][0-9]{0,19}) verifier_run_attempt=1",
        str(comment.get("body") or ""))
    if not match:
        raise ProductTerraformError("ROUTING_VERIFICATION_BODY_INVALID")
    release_id, resource, uri, recorded_control_sha, d5_comment_id, verifier_caller_sha, run_id = match.groups()
    if resource != PROCESSOR_RESOURCE or uri != candidate["processor_uri"]:
        raise ProductTerraformError("ROUTING_VERIFICATION_RESOURCE_URI_MISMATCH")
    if recorded_control_sha != control_sha:
        raise ProductTerraformError("ROUTING_VERIFICATION_CONTROL_MISMATCH")
    d5 = validate_d5_reconciliation(d5_comment, d5_comment_id, control_sha, d5_run)
    if not isinstance(run, dict) or str(run.get("id") or "") != run_id:
        raise ProductTerraformError("ROUTING_VERIFICATION_RUN_MISMATCH")
    if (run.get("run_attempt") != 1 or run.get("status") != "completed"
            or run.get("conclusion") != "success" or run.get("head_branch") != DEFAULT_BRANCH
            or run.get("head_sha") != verifier_caller_sha or run.get("path") != VERIFY_CALLER_PATH):
        raise ProductTerraformError("ROUTING_VERIFICATION_RUN_NOT_SUCCESSFUL")
    head_repo = run.get("head_repository") or {}
    repository = run.get("repository") or {}
    if head_repo.get("full_name") != REPOSITORY or repository.get("full_name") != REPOSITORY:
        raise ProductTerraformError("ROUTING_VERIFICATION_RUN_REPOSITORY_MISMATCH")
    references = run.get("referenced_workflows")
    if not isinstance(references, list):
        raise ProductTerraformError("ROUTING_VERIFIER_REUSABLE_IDENTITY_MISSING")
    reusable_prefix = f"{REPOSITORY}/{VERIFY_REUSABLE_PATH}"
    matches = [row for row in references if isinstance(row, dict)
               and str(row.get("path") or "").split("@", 1)[0] == reusable_prefix]
    expected_reusable = f"{reusable_prefix}@{control_sha}"
    if (len(matches) != 1 or matches[0].get("path") != expected_reusable
            or matches[0].get("sha") != control_sha):
        raise ProductTerraformError("ROUTING_VERIFIER_REUSABLE_IDENTITY_MISMATCH")
    return {
        "comment_id": comment_id, "release_id": release_id,
        "processor_resource": resource, "processor_uri": uri, "control_sha": recorded_control_sha,
        "d5_reconciliation_comment_id": d5["comment_id"],
        "d5_reconciliation_run_id": d5["reconciliation_run_id"],
        "d5_reconciliation_caller_sha": d5["caller_sha"],
        "verifier_caller_path": VERIFY_CALLER_PATH, "verifier_caller_sha": verifier_caller_sha,
        "verifier_reusable_path": expected_reusable, "verifier_reusable_sha": control_sha,
        "verifier_run_id": run_id, "verifier_run_attempt": "1",
    }


def verify_routing_binding(candidate: dict[str, Any], control_sha: str) -> dict[str, str]:
    candidate = validate_candidate(candidate)
    if candidate["stage"] != "routing":
        return {}
    comment_id = candidate["processor_verification_comment_id"]
    comment = github(f"/repos/{REPOSITORY}/issues/comments/{comment_id}")
    body = str(comment.get("body") or "") if isinstance(comment, dict) else ""
    match = re.search(
        r" d5_reconciliation_comment_id=([1-9][0-9]{0,19}) "
        r"verifier_caller_sha=[0-9a-f]{40} verifier_run_id=([1-9][0-9]{0,19}) verifier_run_attempt=1\Z",
        body)
    if not match:
        raise ProductTerraformError("ROUTING_VERIFICATION_RUN_ID_MISSING")
    d5_comment_id, verifier_run_id = match.groups()
    run = github(f"/repos/{REPOSITORY}/actions/runs/{verifier_run_id}")
    d5_comment = github(f"/repos/{REPOSITORY}/issues/comments/{d5_comment_id}")
    d5 = d5_reconciliation_comment(d5_comment, d5_comment_id, control_sha)
    d5_run = github(f"/repos/{REPOSITORY}/actions/runs/{d5['reconciliation_run_id']}")
    return routing_binding_from_documents(candidate, control_sha, comment, run, d5_comment, d5_run)

def verify_main(expected_sha: str) -> None:
    if not FULL_SHA.fullmatch(expected_sha):
        raise ProductTerraformError("MAIN_SHA_INVALID")
    branch = github(f"/repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}")
    if not isinstance(branch, dict) or branch.get("commit", {}).get("sha") != expected_sha:
        raise ProductTerraformError("MAIN_SHA_MISMATCH")


def verify_pr(pr_number: int, head_sha: str, base_sha: str, require_open: bool,
              require_merged: bool, expected_merge_sha: str | None = None) -> None:
    if pr_number <= 0 or not FULL_SHA.fullmatch(head_sha) or not FULL_SHA.fullmatch(base_sha):
        raise ProductTerraformError("PR_IDENTITY_INVALID")
    pr = github(f"/repos/{REPOSITORY}/pulls/{pr_number}")
    if not isinstance(pr, dict):
        raise ProductTerraformError("PR_INVALID")
    if pr.get("base", {}).get("ref") != DEFAULT_BRANCH or pr.get("base", {}).get("sha") != base_sha:
        raise ProductTerraformError("PR_BASE_MISMATCH")
    if pr.get("head", {}).get("sha") != head_sha:
        raise ProductTerraformError("PR_HEAD_MISMATCH")
    head_repo = pr.get("head", {}).get("repo") or {}
    if head_repo.get("id") != REPOSITORY_ID or head_repo.get("full_name") != REPOSITORY:
        raise ProductTerraformError("PR_REPOSITORY_MISMATCH")
    if require_open and pr.get("state") != "open":
        raise ProductTerraformError("PR_NOT_OPEN")
    if require_merged and pr.get("merged_at") is None:
        raise ProductTerraformError("PR_NOT_MERGED")
    if expected_merge_sha is not None and pr.get("merge_commit_sha") != expected_merge_sha:
        raise ProductTerraformError("PR_MERGE_SHA_MISMATCH")
    rows = github(f"/repos/{REPOSITORY}/pulls/{pr_number}/files?per_page=100")
    if not isinstance(rows, list) or [row.get("filename") for row in rows] != [CANDIDATE_PATH]:
        raise ProductTerraformError("PR_FILE_SET_MISMATCH")


def fetch_candidate(sha: str, output: str | Path) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(sha):
        raise ProductTerraformError("CANDIDATE_SHA_INVALID")
    encoded = urllib.parse.quote(CANDIDATE_PATH, safe="/")
    payload = github(f"/repos/{REPOSITORY}/contents/{encoded}?ref={sha}")
    if not isinstance(payload, dict) or payload.get("type") != "file" or payload.get("path") != CANDIDATE_PATH:
        raise ProductTerraformError("CANDIDATE_PATH_MISMATCH")
    try:
        raw = base64.b64decode(payload.get("content", ""), validate=True)
    except ValueError as exc:
        raise ProductTerraformError("CANDIDATE_CONTENT_INVALID") from exc
    candidate = validate_candidate(strict_bytes(raw))
    canonical_candidate = canonical(candidate) + b"\n"
    Path(output).write_bytes(canonical_candidate)
    return {"blob_sha": payload.get("sha"), "sha256": sha256(canonical_candidate), "stage": candidate["stage"]}


def gcs_token() -> str:
    token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN", "")
    if not token:
        raise ProductTerraformError("GOOGLE_OAUTH_ACCESS_TOKEN_REQUIRED")
    return token


def gcs_url(object_name: str, download: bool = False) -> str:
    encoded = urllib.parse.quote(object_name, safe="")
    prefix = "https://storage.googleapis.com/download/storage/v1" if download else "https://storage.googleapis.com/storage/v1"
    suffix = "?alt=media" if download else ""
    return f"{prefix}/b/{STATE_BUCKET}/o/{encoded}{suffix}"


def gcs_metadata(object_name: str, allow_absent: bool = False) -> dict[str, Any] | None:
    try:
        value = _request_json(gcs_url(object_name), gcs_token())
    except ProductTerraformError as exc:
        if allow_absent and str(exc).startswith("HTTP_404"):
            return None
        raise
    if not isinstance(value, dict):
        raise ProductTerraformError("GCS_METADATA_INVALID")
    return value


def upload_effect_once(object_name: str, effect: dict[str, Any]) -> dict[str, Any]:
    if not SAFE_EVIDENCE.fullmatch(object_name):
        raise ProductTerraformError("EVIDENCE_OBJECT_INVALID")
    query = urllib.parse.urlencode({"uploadType": "media", "name": object_name, "ifGenerationMatch": "0"})
    url = f"https://storage.googleapis.com/upload/storage/v1/b/{STATE_BUCKET}/o?{query}"
    value = _request_json(url, gcs_token(), "POST", canonical(effect) + b"\n", "application/json")
    if not isinstance(value, dict) or value.get("name") != object_name:
        raise ProductTerraformError("EVIDENCE_UPLOAD_IDENTITY_INVALID")
    return value


def download_effect(object_name: str, output: str | Path) -> dict[str, Any]:
    if not SAFE_EVIDENCE.fullmatch(object_name):
        raise ProductTerraformError("EVIDENCE_OBJECT_INVALID")
    value = _request_json(gcs_url(object_name, True), gcs_token())
    if not isinstance(value, dict):
        raise ProductTerraformError("EVIDENCE_DOWNLOAD_INVALID")
    Path(output).write_bytes(canonical(value) + b"\n")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p=commands.add_parser("validate-candidate"); p.add_argument("--file", required=True)
    p=commands.add_parser("verify-caller"); p.add_argument("--repository", required=True); p.add_argument("--ref", required=True); p.add_argument("--ref-protected", required=True); p.add_argument("--run-attempt", required=True)
    p=commands.add_parser("verify-routing-binding"); p.add_argument("--candidate", required=True); p.add_argument("--control-sha", required=True); p.add_argument("--output", required=True)
    p=commands.add_parser("assemble"); p.add_argument("--trusted-root", required=True); p.add_argument("--candidate", required=True); p.add_argument("--output", required=True)
    p=commands.add_parser("verify-pr"); p.add_argument("--pr-number", type=int, required=True); p.add_argument("--head-sha", required=True); p.add_argument("--base-sha", required=True); p.add_argument("--require-open", action="store_true"); p.add_argument("--require-merged", action="store_true"); p.add_argument("--merge-sha")
    p=commands.add_parser("verify-main"); p.add_argument("--sha", required=True)
    p=commands.add_parser("fetch-candidate"); p.add_argument("--sha", required=True); p.add_argument("--output", required=True)
    p=commands.add_parser("state-identity"); p.add_argument("--state-json", required=True); p.add_argument("--generation", required=True); p.add_argument("--output", required=True)
    p=commands.add_parser("build-effect"); p.add_argument("--plan-json", required=True); p.add_argument("--candidate", required=True); p.add_argument("--state-identity", required=True); p.add_argument("--routing-binding", required=True); p.add_argument("--pr-number", type=int, required=True); p.add_argument("--base-sha", required=True); p.add_argument("--candidate-sha", required=True); p.add_argument("--control-sha", required=True); p.add_argument("--trusted-tree-sha256", required=True); p.add_argument("--provider-lock-sha256", required=True); p.add_argument("--private-output", required=True); p.add_argument("--public-output", required=True); p.add_argument("--run-id", required=True); p.add_argument("--evidence-object", required=True)
    p=commands.add_parser("compare-effect"); p.add_argument("--expected", required=True); p.add_argument("--actual", required=True)
    p=commands.add_parser("gcs-metadata"); p.add_argument("--object", required=True); p.add_argument("--allow-absent", action="store_true")
    p=commands.add_parser("upload-effect"); p.add_argument("--object", required=True); p.add_argument("--file", required=True)
    p=commands.add_parser("download-effect"); p.add_argument("--object", required=True); p.add_argument("--output", required=True)
    args=parser.parse_args()
    try:
        if args.command=="validate-candidate":
            print(json.dumps(validate_candidate(strict_file(args.file)), sort_keys=True, separators=(",", ":")))
        elif args.command=="verify-caller":
            verify_caller_context(args.repository,args.ref,args.ref_protected,args.run_attempt)
        elif args.command=="verify-routing-binding":
            binding=verify_routing_binding(strict_file(args.candidate),args.control_sha)
            Path(args.output).write_bytes(canonical(binding)+b"\n")
        elif args.command=="assemble":
            print(json.dumps(assemble(args.trusted_root,args.candidate,args.output),sort_keys=True,separators=(",",":")))
        elif args.command=="verify-pr":
            verify_pr(args.pr_number,args.head_sha,args.base_sha,args.require_open,args.require_merged,args.merge_sha)
        elif args.command=="verify-main":
            verify_main(args.sha)
        elif args.command=="fetch-candidate":
            print(json.dumps(fetch_candidate(args.sha,args.output),sort_keys=True,separators=(",",":")))
        elif args.command=="state-identity":
            state=strict_file(args.state_json); ident=state_identity(state,args.generation)
            Path(args.output).write_bytes(canonical(ident)+b"\n")
        elif args.command=="build-effect":
            effect=private_effect(strict_file(args.plan_json),strict_file(args.candidate),
                                  strict_file(args.state_identity),strict_file(args.routing_binding),
                                  args.pr_number,args.base_sha,args.candidate_sha,args.control_sha,
                                  args.trusted_tree_sha256,args.provider_lock_sha256)
            Path(args.private_output).write_bytes(canonical(effect)+b"\n")
            manifest=public_manifest(effect,args.run_id,args.evidence_object)
            Path(args.public_output).write_bytes(canonical(manifest)+b"\n")
        elif args.command=="compare-effect":
            compare_effect(strict_file(args.expected),strict_file(args.actual))
        elif args.command=="gcs-metadata":
            value=gcs_metadata(args.object,args.allow_absent)
            print("ABSENT" if value is None else json.dumps({k:value.get(k) for k in ("bucket","name","generation","metageneration")},sort_keys=True,separators=(",",":")))
        elif args.command=="upload-effect":
            print(json.dumps(upload_effect_once(args.object,strict_file(args.file)),sort_keys=True,separators=(",",":")))
        elif args.command=="download-effect":
            download_effect(args.object,args.output)
        return 0
    except ProductTerraformError as exc:
        print(f"PHASE5_TERRAFORM_STOPPED:{exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
