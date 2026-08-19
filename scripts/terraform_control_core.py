"""Pure, credential-free Terraform control contract primitives."""
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
    """Fail-closed control contract violation."""


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
    if set(document) != {"resource"}:
        raise ControlError("CANDIDATE_TOP_LEVEL_FORBIDDEN")
    resources = document["resource"]
    if not isinstance(resources, dict) or set(resources) != {"google_service_account"}:
        raise ControlError("RESOURCE_TYPE_FORBIDDEN")
    accounts = resources["google_service_account"]
    if not isinstance(accounts, dict) or set(accounts) != {"phase3_terraform_sentinel"}:
        raise ControlError("RESOURCE_NAME_FORBIDDEN")
    sentinel = accounts["phase3_terraform_sentinel"]
    if not isinstance(sentinel, dict) or sentinel != SENTINEL_RESOURCE:
        raise ControlError("SENTINEL_CONFIGURATION_MISMATCH")
    return document


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
    changes: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ControlError("PLAN_RESOURCE_CHANGE_INVALID")
        unknown_row = set(row) - PLAN_RESOURCE_CHANGE_KEYS
        if unknown_row:
            raise ControlError("PLAN_RESOURCE_CHANGE_STRUCTURE_UNRECOGNISED:" + ",".join(sorted(unknown_row)))
        if (row.get("address") != SENTINEL_ADDRESS or row.get("mode") != "managed"
                or row.get("type") != "google_service_account"
                or row.get("name") != "phase3_terraform_sentinel"
                or row.get("provider_name") != "registry.terraform.io/hashicorp/google"):
            raise ControlError("PLAN_RESOURCE_CLASS_FORBIDDEN")
        if row.get("previous_address") not in (None, "") or row.get("module_address") not in (None, ""):
            raise ControlError("PLAN_RESOURCE_MOVE_OR_MODULE_FORBIDDEN")
        if row.get("index") is not None or row.get("index_unknown") not in (None, False) or row.get("deposed") not in (None, ""):
            raise ControlError("PLAN_RESOURCE_INSTANCE_SHAPE_FORBIDDEN")
        identity = {key: row.get(key) for key in (
            "address", "previous_address", "module_address", "mode", "type", "name",
            "index", "index_unknown", "provider_name", "deposed", "action_reason",
        )}
        identity["change"] = _normalise_change(row.get("change"))
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
