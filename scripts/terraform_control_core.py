"Pure, credential-free Terraform control contract primitives."
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

REPOSITORY = "8ft0-ai/resilio"
REPOSITORY_ID = 1335801159
DEFAULT_BRANCH = "main"
FOUNDATION_ROOT = "infra/foundation"
CANDIDATE_PATH = f"{FOUNDATION_ROOT}/resources.tf.json"
STATE_BUCKET = "resilio-control-e882d4-tfstate"
STATE_OBJECT = "foundation/default.tfstate"
BACKEND_NAMESPACE = f"gs://{STATE_BUCKET}/{STATE_OBJECT}"
PLAN_EVIDENCE_PREFIX = "plan-evidence/foundation/"
REFERENCE_PROJECT = "resilio-reference-e882d4"
CONTROL_PROJECT = "resilio-control-e882d4"
WIF_PROVIDER = "projects/400271474382/locations/global/workloadIdentityPools/github/providers/resilio"
PLANNER_SERVICE_ACCOUNT = "github-foundation-planner@resilio-control-e882d4.iam.gserviceaccount.com"
APPLIER_SERVICE_ACCOUNT = "github-foundation-applier@resilio-control-e882d4.iam.gserviceaccount.com"
PROBE_SERVICE_ACCOUNT = "github-federation-probe@resilio-control-e882d4.iam.gserviceaccount.com"
ALLOWED_SERVICE_ACCOUNTS = {PROBE_SERVICE_ACCOUNT, PLANNER_SERVICE_ACCOUNT, APPLIER_SERVICE_ACCOUNT}
TRUSTED_FOUNDATION_FILES = ("backend.tf", "versions.tf", "provider.tf", ".terraform.lock.hcl")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
INTERPOLATION = re.compile(r"\$\{|%\{")
SAFE_EVIDENCE_OBJECT = re.compile(r"^plan-evidence/foundation/pr-[1-9][0-9]*-[0-9a-f]{40}\.json$")
SENTINEL_ADDRESS = "google_service_account.phase3_terraform_sentinel"
SENTINEL_RESOURCE = {
    "account_id": "phase3-terraform-sentinel",
    "display_name": "Phase 3 Terraform sentinel",
    "description": "Non-privileged Resilio Phase 3 Terraform control-path sentinel.",
    "project": REFERENCE_PROJECT,
    "deletion_policy": "PREVENT",
}
SAFE_SENTINEL_ACTION_SEQUENCES = {("create",)}

PHASE4_CONTROL_SERVICES = {
    "control_cloudbuild": "cloudbuild.googleapis.com",
    "control_artifactregistry": "artifactregistry.googleapis.com",
    "control_containeranalysis": "containeranalysis.googleapis.com",
    "control_containerscanning": "containerscanning.googleapis.com",
    "control_logging": "logging.googleapis.com",
}
PHASE4_REFERENCE_SERVICES = {"reference_run": "run.googleapis.com"}
PHASE4_SERVICE_RESOURCES = {
    **{name: {"project": CONTROL_PROJECT, "service": service, "disable_on_destroy": False}
       for name, service in PHASE4_CONTROL_SERVICES.items()},
    **{name: {"project": REFERENCE_PROJECT, "service": service, "disable_on_destroy": False}
       for name, service in PHASE4_REFERENCE_SERVICES.items()},
}
PHASE4_REPOSITORY_RESOURCE = {
    "project": CONTROL_PROJECT,
    "location": "us-central1",
    "repository_id": "resilio-phase4",
    "description": "Resilio Phase 4 trusted supply-chain proof images.",
    "format": "DOCKER",
    "cleanup_policy_dry_run": False,
    "cleanup_policies": [
        {
            "id": "keep-recent-proof",
            "action": "KEEP",
            "most_recent_versions": [{
                "package_name_prefixes": ["phase4-proof"],
                "keep_count": 3,
            }],
        },
        {
            "id": "delete-old-proof",
            "action": "DELETE",
            "condition": [{
                "tag_state": "ANY",
                "package_name_prefixes": ["phase4-proof"],
                "older_than": "30d",
            }],
        },
    ],
    "deletion_policy": "PREVENT",
    "depends_on": ["google_project_service.control_artifactregistry"],
}
PHASE4_EVIDENCE_BUCKET_RESOURCE = {
    "project": CONTROL_PROJECT,
    "name": "resilio-control-e882d4-phase4-evidence",
    "location": "us-central1",
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
}
PHASE4_FOUNDATION_RESOURCE = {
    "resource": {
        "google_service_account": {
            "phase3_terraform_sentinel": dict(SENTINEL_RESOURCE),
        },
        "google_project_service": PHASE4_SERVICE_RESOURCES,
        "google_artifact_registry_repository": {
            "phase4": PHASE4_REPOSITORY_RESOURCE,
        },
        "google_storage_bucket": {
            "phase4_evidence": PHASE4_EVIDENCE_BUCKET_RESOURCE,
        },
    }
}
PHASE4_CREATE_ADDRESSES = {
    **{f"google_project_service.{name}": ("google_project_service", name)
       for name in PHASE4_SERVICE_RESOURCES},
    "google_artifact_registry_repository.phase4": ("google_artifact_registry_repository", "phase4"),
    "google_storage_bucket.phase4_evidence": ("google_storage_bucket", "phase4_evidence"),
}
PHASE4_EFFECT_ADDRESSES = {SENTINEL_ADDRESS, *PHASE4_CREATE_ADDRESSES}

# Terraform v1.15.8 internal/command/jsonplan.plan exact top-level JSON fields.
PLAN_TOP_LEVEL_KEYS = {
    "format_version", "terraform_version", "variables", "planned_values",
    "resource_drift", "resource_changes", "deferred_changes",
    "deferred_action_invocations", "output_changes", "action_invocations",
    "prior_state", "configuration", "relevant_attributes", "checks",
    "timestamp", "applyable", "complete", "errored",
}
PLAN_CHANGE_KEYS = {
    "actions", "before", "after", "after_unknown", "before_sensitive",
    "after_sensitive", "replace_paths", "importing", "generated_config",
    "before_identity", "after_identity",
}
PLAN_RESOURCE_CHANGE_KEYS = {
    "address", "previous_address", "module_address", "mode", "type", "name",
    "index", "index_unknown", "provider_name", "deposed", "change", "action_reason",
}


class ControlError(RuntimeError):
    "Fail-closed control contract violation."


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ControlError(f"DUPLICATE_JSON_KEY:{key}")
        result[key] = value
    return result


def load_json_strict_bytes(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ControlError("INVALID_UTF8") from exc
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except ControlError:
        raise
    except json.JSONDecodeError as exc:
        raise ControlError(f"INVALID_JSON:{exc.msg}") from exc


def load_json_strict(path: Path) -> Any:
    return load_json_strict_bytes(path.read_bytes())


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _literal_tree(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ControlError(f"NON_STRING_KEY:{path}")
            _literal_tree(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _literal_tree(item, f"{path}[{index}]")
    elif isinstance(value, str):
        if INTERPOLATION.search(value):
            raise ControlError(f"EXPRESSION_STRING_FORBIDDEN:{path}")
    elif value is None or isinstance(value, (bool, int, float)):
        return
    else:
        raise ControlError(f"UNSUPPORTED_LITERAL_TYPE:{path}")


def validate_candidate_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ControlError("CANDIDATE_ROOT_MUST_BE_OBJECT")
    _literal_tree(document)
    if document == {}:
        return document
    sentinel_only = {"resource": {"google_service_account": {"phase3_terraform_sentinel": dict(SENTINEL_RESOURCE)}}}
    if document == sentinel_only or document == PHASE4_FOUNDATION_RESOURCE:
        return document
    # Retain precise historical sentinel error for existing negative evidence.
    try:
        sentinel = document["resource"]["google_service_account"]["phase3_terraform_sentinel"]
    except (KeyError, TypeError):
        raise ControlError("PHASE4_FOUNDATION_CONFIGURATION_MISMATCH")
    if isinstance(sentinel, dict) and set(document) == {"resource"} and set(document["resource"]) == {"google_service_account"}:
        if sentinel != SENTINEL_RESOURCE:
            raise ControlError("SENTINEL_CONFIGURATION_MISMATCH")
    raise ControlError("PHASE4_FOUNDATION_CONFIGURATION_MISMATCH")


def validate_candidate_file(path: Path) -> dict[str, Any]:
    return validate_candidate_document(load_json_strict(path))


def canonicalise_candidate(path: Path) -> bytes:
    return canonical_json_bytes(validate_candidate_file(path)) + b"\n"


def validate_service_account(value: str) -> str:
    if value not in ALLOWED_SERVICE_ACCOUNTS:
        raise ControlError("SERVICE_ACCOUNT_NOT_APPROVED")
    return value


def assemble_workdir(trusted_root: Path, candidate_path: Path, output: Path) -> dict[str, str]:
    validate_candidate_file(candidate_path)
    source = trusted_root / FOUNDATION_ROOT
    for name in TRUSTED_FOUNDATION_FILES:
        if not (source / name).is_file():
            raise ControlError(f"TRUSTED_FILE_MISSING:{name}")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    digests: dict[str, str] = {}
    for name in TRUSTED_FOUNDATION_FILES:
        shutil.copyfile(source / name, output / name)
        digests[name] = sha256_file(output / name)
    canonical = canonicalise_candidate(candidate_path)
    (output / "resources.tf.json").write_bytes(canonical)
    digests["resources.tf.json"] = sha256_bytes(canonical)
    return digests


def _require_empty(plan: dict[str, Any], key: str, error: str) -> None:
    value = plan.get(key)
    if value not in (None, [], {}):
        raise ControlError(error)


def _normalise_change(change: Any) -> dict[str, Any]:
    if not isinstance(change, dict):
        raise ControlError("PLAN_CHANGE_INVALID")
    unknown = set(change) - PLAN_CHANGE_KEYS
    if unknown:
        raise ControlError("PLAN_CHANGE_STRUCTURE_UNRECOGNISED:" + ",".join(sorted(unknown)))
    return {key: change.get(key) for key in sorted(PLAN_CHANGE_KEYS)}


def _resource_identity(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("previous_address") not in (None, "") or row.get("module_address") not in (None, ""):
        raise ControlError("PLAN_RESOURCE_MOVE_OR_MODULE_FORBIDDEN")
    if row.get("index") is not None or row.get("index_unknown") not in (None, False) or row.get("deposed") not in (None, ""):
        raise ControlError("PLAN_RESOURCE_INSTANCE_SHAPE_FORBIDDEN")
    unknown_row = set(row) - PLAN_RESOURCE_CHANGE_KEYS
    if unknown_row:
        raise ControlError("PLAN_RESOURCE_CHANGE_STRUCTURE_UNRECOGNISED:" + ",".join(sorted(unknown_row)))
    return {key: row.get(key) for key in (
        "address", "previous_address", "module_address", "mode", "type", "name",
        "index", "index_unknown", "provider_name", "deposed", "action_reason",
    )}


def material_effect(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ControlError("PLAN_INVALID")
    unknown = set(plan) - PLAN_TOP_LEVEL_KEYS
    if unknown:
        raise ControlError("PLAN_TOP_LEVEL_STRUCTURE_UNRECOGNISED:" + ",".join(sorted(unknown)))
    if plan.get("format_version") != "1.2" or plan.get("terraform_version") != "1.15.8":
        raise ControlError("PLAN_VERSION_MISMATCH")
    if plan.get("errored") is not False or plan.get("complete") is not True or plan.get("applyable") is not True:
        raise ControlError("PLAN_NOT_APPLYABLE_COMPLETE_SUCCESS")
    _require_empty(plan, "resource_drift", "PLAN_RESOURCE_DRIFT")
    _require_empty(plan, "deferred_changes", "PLAN_DEFERRED_CHANGES")
    _require_empty(plan, "deferred_action_invocations", "PLAN_DEFERRED_ACTION_INVOCATIONS")
    _require_empty(plan, "action_invocations", "PLAN_ACTION_INVOCATIONS")

    rows = plan.get("resource_changes") or []
    if not isinstance(rows, list):
        raise ControlError("PLAN_RESOURCE_CHANGES_INVALID")
    addresses = {row.get("address") for row in rows if isinstance(row, dict)}
    historical_sentinel_create = addresses == {SENTINEL_ADDRESS} and len(rows) == 1
    phase4_create = addresses == PHASE4_EFFECT_ADDRESSES and len(rows) == len(PHASE4_EFFECT_ADDRESSES)
    if not historical_sentinel_create and not phase4_create:
        raise ControlError("PLAN_PROOF_CHANGE_COUNT_INVALID")

    changes: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ControlError("PLAN_RESOURCE_CHANGE_INVALID")
        identity = _resource_identity(row)
        address = row.get("address")
        if row.get("mode") != "managed" or row.get("provider_name") != "registry.terraform.io/hashicorp/google":
            raise ControlError("PLAN_RESOURCE_CLASS_FORBIDDEN")
        change = _normalise_change(row.get("change"))
        actions = change.get("actions")
        if not isinstance(actions, list) or not actions or any(not isinstance(action, str) for action in actions):
            raise ControlError("PLAN_ACTION_SEQUENCE_INVALID")
        if "delete" in actions:
            raise ControlError("PLAN_DESTRUCTIVE_ACTION_FORBIDDEN")
        if historical_sentinel_create:
            if (address != SENTINEL_ADDRESS or row.get("type") != "google_service_account"
                    or row.get("name") != "phase3_terraform_sentinel"
                    or tuple(actions) not in SAFE_SENTINEL_ACTION_SEQUENCES):
                raise ControlError("PLAN_ACTION_SEQUENCE_FORBIDDEN")
        else:
            if address == SENTINEL_ADDRESS:
                if row.get("type") != "google_service_account" or row.get("name") != "phase3_terraform_sentinel" or tuple(actions) != ("no-op",):
                    raise ControlError("PLAN_ACTION_SEQUENCE_FORBIDDEN")
            else:
                expected = PHASE4_CREATE_ADDRESSES.get(str(address))
                if expected is None or (row.get("type"), row.get("name")) != expected:
                    raise ControlError("PLAN_RESOURCE_CLASS_FORBIDDEN")
                if tuple(actions) != ("create",):
                    raise ControlError("PLAN_ACTION_SEQUENCE_FORBIDDEN")
        identity["change"] = change
        changes.append(identity)
    changes.sort(key=canonical_json_bytes)

    outputs = plan.get("output_changes") or {}
    if not isinstance(outputs, dict):
        raise ControlError("PLAN_OUTPUT_CHANGES_INVALID")
    normal_outputs = {name: _normalise_change(change) for name, change in sorted(outputs.items())}
    return {
        "format_version": plan["format_version"],
        "terraform_version": plan["terraform_version"],
        "applyable": True,
        "complete": True,
        "errored": False,
        "resource_changes": changes,
        "output_changes": normal_outputs,
    }


def state_identity_from_state(state: dict[str, Any], generation: str) -> dict[str, Any]:
    lineage, serial, resources = state.get("lineage"), state.get("serial"), state.get("resources")
    if not isinstance(lineage, str) or not lineage or not isinstance(serial, int) or serial < 0:
        raise ControlError("STATE_IDENTITY_INVALID")
    if not isinstance(generation, str) or not generation.isdigit() or not isinstance(resources, list):
        raise ControlError("STATE_IDENTITY_INVALID")
    count = sum(1 for row in resources if isinstance(row, dict) and row.get("mode", "managed") == "managed")
    return {"lineage": lineage, "serial": serial, "generation": generation, "managed_resource_count": count}


def build_private_effect(*, plan: dict[str, Any], state_identity: dict[str, Any], pr_number: int,
                         base_sha: str, candidate_sha: str, candidate_digest: str,
                         trusted_workflow_sha: str, trusted_tree_digest: str,
                         provider_lock_digest: str, root: str = "foundation",
                         backend_namespace: str = BACKEND_NAMESPACE) -> dict[str, Any]:
    if pr_number <= 0:
        raise ControlError("PRIVATE_EFFECT_PR_INVALID")
    if not FULL_SHA.fullmatch(base_sha) or not FULL_SHA.fullmatch(candidate_sha) or not FULL_SHA.fullmatch(trusted_workflow_sha):
        raise ControlError("PRIVATE_EFFECT_SHA_INVALID")
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in (candidate_digest, trusted_tree_digest, provider_lock_digest)):
        raise ControlError("PRIVATE_EFFECT_DIGEST_INVALID")
    if root != "foundation" or backend_namespace != BACKEND_NAMESPACE:
        raise ControlError("PRIVATE_EFFECT_ROOT_INVALID")
    return {
        "contract": "resilio-terraform-plan-effect/v1",
        "pr_number": pr_number,
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
        "root": root,
        "backend_namespace": backend_namespace,
        "candidate_digest": candidate_digest,
        "trusted_workflow_sha": trusted_workflow_sha,
        "trusted_tree_digest": trusted_tree_digest,
        "provider_lock_digest": provider_lock_digest,
        "state": state_identity,
        "effect": material_effect(plan),
    }


def private_effect_digest(effect: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(effect))


def public_manifest(private_effect: dict[str, Any], *, workflow_run_id: str,
                    evidence_object: str | None) -> dict[str, Any]:
    effect, state = private_effect.get("effect"), private_effect.get("state")
    if not isinstance(effect, dict) or not isinstance(state, dict):
        raise ControlError("PRIVATE_EFFECT_INVALID")
    actions = [{"address": row.get("address"), "actions": row.get("change", {}).get("actions")}
               for row in effect.get("resource_changes", [])]
    manifest: dict[str, Any] = {
        "contract": "resilio-terraform-plan-manifest/v1",
        "pr_number": private_effect.get("pr_number"),
        "base_sha": private_effect.get("base_sha"),
        "candidate_sha": private_effect.get("candidate_sha"),
        "root": private_effect.get("root"),
        "backend_namespace": private_effect.get("backend_namespace"),
        "candidate_digest": private_effect.get("candidate_digest"),
        "trusted_workflow_sha": private_effect.get("trusted_workflow_sha"),
        "trusted_tree_digest": private_effect.get("trusted_tree_digest"),
        "provider_lock_digest": private_effect.get("provider_lock_digest"),
        "terraform_version": effect.get("terraform_version"),
        "state": {key: state.get(key) for key in ("lineage", "serial", "generation")},
        "resource_actions": sorted(actions, key=canonical_json_bytes),
        "policy_result": "PASS",
        "cost_class": "known-negligible/control-plane",
        "private_effect_sha256": private_effect_digest(private_effect),
        "workflow_run_id": str(workflow_run_id),
    }
    if evidence_object is not None:
        if not SAFE_EVIDENCE_OBJECT.fullmatch(evidence_object):
            raise ControlError("EVIDENCE_OBJECT_INVALID")
        manifest["private_evidence_object"] = evidence_object
    return manifest


def compare_private_effects(expected: dict[str, Any], actual: dict[str, Any]) -> None:
    if canonical_json_bytes(expected) != canonical_json_bytes(actual):
        raise ControlError("MATERIAL_EFFECT_MISMATCH")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value) + b"\n")
