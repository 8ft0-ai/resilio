#!/usr/bin/env python3
"""Credential-free sanitisation for read-only foundation drift evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import terraform_control as control

DRIFT_CONTRACT = "resilio-terraform-drift-manifest/v1"
DRIFT_FINGERPRINT_CONTRACT = "resilio-terraform-drift-fingerprint/v1"
SAFE_DRIFT_ACTIONS = {"no-op", "create", "read", "update", "delete", "forget"}


def _normalise_change(change: Any) -> dict[str, Any]:
    if not isinstance(change, dict):
        raise control.ControlError("DRIFT_CHANGE_INVALID")
    unknown = set(change) - control.PLAN_CHANGE_KEYS
    if unknown:
        raise control.ControlError("DRIFT_CHANGE_STRUCTURE_UNRECOGNISED:" + ",".join(sorted(unknown)))
    actions = change.get("actions")
    if (not isinstance(actions, list) or not actions
            or any(not isinstance(action, str) or action not in SAFE_DRIFT_ACTIONS for action in actions)):
        raise control.ControlError("DRIFT_ACTION_SEQUENCE_INVALID")
    return {key: change.get(key) for key in sorted(control.PLAN_CHANGE_KEYS)}


def _safe_address(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or any(ord(char) < 32 for char in value):
        raise control.ControlError("DRIFT_ADDRESS_INVALID")
    return value


def _summarise_rows(rows: Any, source: str, *, ignore_exact_noop: bool) -> list[dict[str, Any]]:
    if rows in (None, []):
        return []
    if not isinstance(rows, list):
        raise control.ControlError("DRIFT_RESOURCE_ROWS_INVALID")
    findings: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise control.ControlError("DRIFT_RESOURCE_ROW_INVALID")
        unknown = set(row) - control.PLAN_RESOURCE_CHANGE_KEYS
        if unknown:
            raise control.ControlError("DRIFT_RESOURCE_STRUCTURE_UNRECOGNISED:" + ",".join(sorted(unknown)))
        address = _safe_address(row.get("address"))
        change = _normalise_change(row.get("change"))
        actions = list(change["actions"])
        exact_sentinel = (
            address == control.SENTINEL_ADDRESS
            and row.get("mode") == "managed"
            and row.get("type") == "google_service_account"
            and row.get("name") == "phase3_terraform_sentinel"
            and row.get("provider_name") == "registry.terraform.io/hashicorp/google"
            and row.get("previous_address") in (None, "")
            and row.get("module_address") in (None, "")
            and row.get("index") is None
            and row.get("index_unknown") in (None, False)
            and row.get("deposed") in (None, "")
        )
        if ignore_exact_noop and exact_sentinel and actions == ["no-op"]:
            continue
        findings.append({
            "source": source,
            "address": address,
            "actions": actions,
            "classification": "sentinel" if exact_sentinel else "unexpected-resource",
        })
    return findings


def _validate_plan(plan: Any) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        raise control.ControlError("DRIFT_PLAN_INVALID")
    unknown = set(plan) - control.PLAN_TOP_LEVEL_KEYS
    if unknown:
        raise control.ControlError("DRIFT_PLAN_STRUCTURE_UNRECOGNISED:" + ",".join(sorted(unknown)))
    if plan.get("format_version") != "1.2" or plan.get("terraform_version") != "1.15.8":
        raise control.ControlError("DRIFT_PLAN_VERSION_MISMATCH")
    if plan.get("errored") is not False or plan.get("complete") is not True or not isinstance(plan.get("applyable"), bool):
        raise control.ControlError("DRIFT_PLAN_INCOMPLETE_OR_ERRORED")
    for key, error in (
        ("deferred_changes", "DRIFT_DEFERRED_CHANGES"),
        ("deferred_action_invocations", "DRIFT_DEFERRED_ACTION_INVOCATIONS"),
        ("action_invocations", "DRIFT_ACTION_INVOCATIONS"),
    ):
        if plan.get(key) not in (None, [], {}):
            raise control.ControlError(error)
    outputs = plan.get("output_changes") or {}
    if not isinstance(outputs, dict):
        raise control.ControlError("DRIFT_OUTPUT_CHANGES_INVALID")
    if outputs:
        raise control.ControlError("DRIFT_OUTPUT_CHANGES_FORBIDDEN")

    findings = _summarise_rows(plan.get("resource_drift"), "resource_drift", ignore_exact_noop=False)
    findings.extend(_summarise_rows(plan.get("resource_changes"), "planned_change", ignore_exact_noop=True))
    unique = {control.canonical_json_bytes(item): item for item in findings}
    return [unique[key] for key in sorted(unique)]


def build_drift_manifest(*, plan: Any, state_identity: Any, main_sha: str, candidate_digest: str,
                         trusted_workflow_sha: str, provider_lock_digest: str,
                         workflow_run_id: str) -> dict[str, Any]:
    if not control.FULL_SHA.fullmatch(main_sha) or not control.FULL_SHA.fullmatch(trusted_workflow_sha):
        raise control.ControlError("DRIFT_SHA_INVALID")
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in (candidate_digest, provider_lock_digest)):
        raise control.ControlError("DRIFT_DIGEST_INVALID")
    if not isinstance(workflow_run_id, str) or not workflow_run_id.isdigit():
        raise control.ControlError("DRIFT_RUN_ID_INVALID")
    if not isinstance(state_identity, dict):
        raise control.ControlError("DRIFT_STATE_IDENTITY_INVALID")
    lineage = state_identity.get("lineage")
    serial = state_identity.get("serial")
    generation = state_identity.get("generation")
    managed_resource_count = state_identity.get("managed_resource_count")
    if (not isinstance(lineage, str) or not lineage or not isinstance(serial, int) or serial < 0
            or not isinstance(generation, str) or not generation.isdigit()
            or not isinstance(managed_resource_count, int) or managed_resource_count < 0):
        raise control.ControlError("DRIFT_STATE_IDENTITY_INVALID")

    findings = _validate_plan(plan)
    fingerprint_payload = {
        "contract": DRIFT_FINGERPRINT_CONTRACT,
        "root": "foundation",
        "candidate_digest": candidate_digest,
        "findings": findings,
    }
    fingerprint = control.sha256_bytes(control.canonical_json_bytes(fingerprint_payload))
    return {
        "contract": DRIFT_CONTRACT,
        "root": "foundation",
        "backend_namespace": control.BACKEND_NAMESPACE,
        "main_sha": main_sha,
        "candidate_digest": candidate_digest,
        "trusted_workflow_sha": trusted_workflow_sha,
        "provider_lock_digest": provider_lock_digest,
        "terraform_version": "1.15.8",
        "state": {"lineage": lineage, "serial": serial, "generation": generation},
        "status": "DRIFT" if findings else "NO_DRIFT",
        "findings": findings,
        "drift_fingerprint": fingerprint,
        "workflow_run_id": workflow_run_id,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("--plan-json", required=True)
    root.add_argument("--state-identity", required=True)
    root.add_argument("--main-sha", required=True)
    root.add_argument("--candidate-digest", required=True)
    root.add_argument("--trusted-workflow-sha", required=True)
    root.add_argument("--provider-lock-digest", required=True)
    root.add_argument("--workflow-run-id", required=True)
    root.add_argument("--public-output", required=True)
    return root


def main() -> int:
    try:
        args = parser().parse_args()
        plan = control.load_json_strict(Path(args.plan_json))
        state = control.load_json_strict(Path(args.state_identity))
        manifest = build_drift_manifest(
            plan=plan,
            state_identity=state,
            main_sha=args.main_sha,
            candidate_digest=args.candidate_digest,
            trusted_workflow_sha=args.trusted_workflow_sha,
            provider_lock_digest=args.provider_lock_digest,
            workflow_run_id=args.workflow_run_id,
        )
        control.write_json(Path(args.public_output), manifest)
        return 0
    except control.ControlError as exc:
        print(f"TERRAFORM_DRIFT_STOPPED:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
