"""Credential-free tests for the Phase 5 Slice C recovery control."""
from __future__ import annotations

import base64
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import phase5_slice_c_recovery as recovery
from phase5_slice_c_recovery import (
    EXPECTED_ADDRESSES,
    EXPECTED_GENERATION,
    EXPECTED_LINEAGE,
    EXPECTED_SERIAL,
    RecoveryError,
    bootstrap_apply_authority_body,
    bootstrap_terminal_record_body,
    build_result,
    claim_document,
    dispatch_authority_body,
    evidence_object,
    github_issue_comments,
    r2_activation_record_body,
    r2_merge_authority_body,
    validate_r2_activation_record,
    verify_caller_context,
    verify_github_boundary,
    verify_github_boundary_document,
    verify_no_change_plan,
    verify_state_identity,
)
from validate_phase5_slice_c_recovery import (
    r2_caller_structure_errors,
    workflow_structure_errors,
)


def state_identity():
    return {
        "generation": EXPECTED_GENERATION,
        "lineage": EXPECTED_LINEAGE,
        "serial": EXPECTED_SERIAL,
        "managed_addresses": list(EXPECTED_ADDRESSES),
        "state_sha256": "a" * 64,
    }


def no_change_plan():
    resources = [
        {
            "address": address,
            "mode": "managed",
            "type": address.split(".", 1)[0],
            "name": address.split(".", 1)[1],
            "values": {},
        }
        for address in EXPECTED_ADDRESSES
    ]
    changes = [
        {
            "address": address,
            "mode": "managed",
            "type": address.split(".", 1)[0],
            "name": address.split(".", 1)[1],
            "change": {"actions": ["no-op"], "before": {}, "after": {}},
        }
        for address in EXPECTED_ADDRESSES
    ]
    return {
        "format_version": "1.2",
        "terraform_version": "1.15.8",
        "planned_values": {"root_module": {"resources": resources}},
        "resource_changes": changes,
        "resource_drift": [],
        "deferred_changes": [],
        "deferred_action_invocations": [],
        "action_invocations": [],
        "output_changes": {},
        "applyable": False,
        "complete": True,
        "errored": False,
    }


def owner_comment(comment_id, body, when, issue=109):
    return {
        "id": comment_id,
        "body": body,
        "created_at": when,
        "updated_at": when,
        "issue_url": f"https://api.github.com/repos/{recovery.REPOSITORY}/issues/{issue}",
        "user": {"login": "8ft0-ai", "id": 130460431},
    }


def fresh_review_body(pr_number, head, control):
    return "\n".join(
        (
            "COMPLETELY_FRESH_SUBSTANTIVE_IMPLEMENTATION_SECURITY_AUTHORITY_RE_REVIEW",
            "DISPOSITION=APPROVED",
            f"PR=8ft0-ai/resilio#{pr_number}",
            f"EXACT_HEAD={head}",
            f"EXACT_BASE={control}",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"RECOVERY_DESIGN={recovery.RECOVERY_DESIGN_COMMENT_ID}",
            f"SOURCE_BOUNDARY={recovery.SOURCE_BOUNDARY_COMMENT_ID}",
            "MATERIAL_BLOCKERS=NONE",
        )
    )


def bootstrap_review_body(
    control,
    activation,
    saved_plan_sha,
    manifest_sha,
    state_lineage,
    state_serial,
):
    return "\n".join(
        (
            "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_PLAN_FRESH_REVIEW_V1",
            "REVIEW_TARGET=PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_ACTIVATION_SAVED_PLAN",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"SOURCE_BOUNDARY={recovery.SOURCE_BOUNDARY_COMMENT_ID}",
            f"RECOVERY_CONTROL_SHA={control}",
            f"RECOVERY_ACTIVATION_MAIN={activation}",
            f"SAVED_PLAN_SHA256={saved_plan_sha}",
            f"STRUCTURAL_MANIFEST_SHA256={manifest_sha}",
            f"BOOTSTRAP_STATE_LINEAGE={state_lineage}",
            f"BOOTSTRAP_STATE_SERIAL={state_serial}",
            "TERRAFORM_VERSION=1.15.8",
            "PLAN_FORMAT_VERSION=1.2",
            "PLAN_APPLYABLE=true",
            "PLAN_COMPLETE=true",
            "PLAN_ERRORED=false",
            "PLAN_EFFECTS=EXACT_TWO_GETMETADATA_ADDITIONS_PLUS_ONE_RECOVERY_WIF_BINDING",
            "OUTPUT_CHANGES=0",
            "REVIEW_DISPOSITION=APPROVED",
            "MATERIAL_BLOCKERS=NONE",
            "APPLY_AUTHORITY=NOT_GRANTED",
            "",
            "Fresh exact-effect/security/authority review reconstructed from the exact "
            "saved plan and structural manifest.",
        )
    )


def rehash_boundary(value):
    value = copy.deepcopy(value)
    value.pop("governance_chain_sha256", None)
    value["governance_chain_sha256"] = recovery.sha256(recovery.canonical(value))
    return value


def github_boundary_fixture():
    control = "1" * 40
    activation = "2" * 40
    reviewed_r2 = "3" * 40
    r2_pr_number = 120
    review_id = 301
    merge_authority_id = 302
    activation_record_id = 303
    bootstrap_review_id = 304
    bootstrap_authority_id = 305
    bootstrap_id = 306
    dispatch_id = 307

    saved_plan_sha = "b" * 64
    manifest_sha = "c" * 64
    bootstrap_lineage = "ae08b2f4-f18f-204c-72aa-53e17f12eea7"
    bootstrap_serial_before = 70
    bootstrap_serial_after = 73

    review_body = fresh_review_body(r2_pr_number, reviewed_r2, control)
    review_sha = recovery.sha256(review_body.encode("utf-8"))
    merge_authority_body = r2_merge_authority_body(
        control, r2_pr_number, reviewed_r2, review_id, review_sha
    )
    merge_authority_sha = recovery.sha256(merge_authority_body.encode("utf-8"))
    activation_body = r2_activation_record_body(
        control,
        activation,
        r2_pr_number,
        reviewed_r2,
        review_id,
        review_sha,
        merge_authority_id,
        merge_authority_sha,
    )
    activation_sha = recovery.sha256(activation_body.encode("utf-8"))

    bootstrap_review = bootstrap_review_body(
        control,
        activation,
        saved_plan_sha,
        manifest_sha,
        bootstrap_lineage,
        bootstrap_serial_before,
    )
    bootstrap_review_sha = recovery.sha256(bootstrap_review.encode("utf-8"))
    bootstrap_authority_body = bootstrap_apply_authority_body(
        control,
        activation,
        saved_plan_sha,
        manifest_sha,
        bootstrap_lineage,
        bootstrap_serial_before,
        bootstrap_review_id,
        bootstrap_review_sha,
    )
    bootstrap_authority_sha = recovery.sha256(
        bootstrap_authority_body.encode("utf-8")
    )
    bootstrap_body = bootstrap_terminal_record_body(
        control,
        activation,
        saved_plan_sha,
        manifest_sha,
        bootstrap_lineage,
        bootstrap_serial_before,
        bootstrap_serial_after,
        bootstrap_review_id,
        bootstrap_review_sha,
        bootstrap_authority_id,
        bootstrap_authority_sha,
    )
    bootstrap_sha = recovery.sha256(bootstrap_body.encode("utf-8"))
    dispatch_body = dispatch_authority_body(
        control,
        activation,
        activation_record_id,
        activation_sha,
        bootstrap_id,
        bootstrap_sha,
    )

    activation_record = owner_comment(
        activation_record_id, activation_body, "2026-10-03T02:03:30Z"
    )
    bootstrap_review_record = owner_comment(
        bootstrap_review_id, bootstrap_review, "2026-10-03T02:04:00Z"
    )
    bootstrap_authority = owner_comment(
        bootstrap_authority_id, bootstrap_authority_body, "2026-10-03T02:05:00Z"
    )
    bootstrap_record = owner_comment(
        bootstrap_id, bootstrap_body, "2026-10-03T02:08:00Z"
    )
    dispatch = owner_comment(dispatch_id, dispatch_body, "2026-10-03T02:09:00Z")

    boundary_body = "\n".join(
        (
            "STATUS=SLICE_C_BASE_RESOURCES_APPLIED_BUT_TERMINAL_NO_CHANGE_PROOF_FAILED",
            f"EXACT_REVIEWED_HEAD={recovery.REVIEWED_HEAD}",
            f"REVIEWED_BASE={recovery.REVIEWED_BASE}",
            f"MERGE_COMMIT={recovery.SLICE_C_MERGE}",
            f"PRODUCT_APPLY_RUN={recovery.FAILED_APPLY_RUN}",
            f"PRODUCT_APPLY_JOB={recovery.FAILED_APPLY_JOB}",
            f"PRODUCT_STATE_GENERATION={recovery.EXPECTED_GENERATION}",
            f"PRODUCT_STATE_SERIAL={recovery.EXPECTED_SERIAL}",
            f"PRODUCT_STATE_LINEAGE={recovery.EXPECTED_LINEAGE}",
            "Retry prohibition",
            "do **not** rerun the existing product apply workflow",
        )
    )
    boundary = owner_comment(
        recovery.SOURCE_BOUNDARY_COMMENT_ID,
        boundary_body,
        "2026-10-02T01:00:00Z",
    )

    candidate_raw = recovery.canonical(recovery.expected_candidate()) + b"\n"
    wrapped_candidate = base64.encodebytes(candidate_raw).decode("ascii")

    comments = [
        activation_record,
        bootstrap_review_record,
        bootstrap_authority,
        bootstrap_record,
        dispatch,
    ]
    fixtures = {
        f"/repos/{recovery.REPOSITORY}/branches/{recovery.DEFAULT_BRANCH}": {
            "commit": {"sha": activation}
        },
        f"/repos/{recovery.REPOSITORY}/issues/{recovery.GOVERNING_ISSUE}": {
            "state": "open"
        },
        f"/repos/{recovery.REPOSITORY}/issues/comments/{recovery.SOURCE_BOUNDARY_COMMENT_ID}": boundary,
        f"/repos/{recovery.REPOSITORY}/pulls/{recovery.SLICE_C_PR}": {
            "number": recovery.SLICE_C_PR,
            "state": "closed",
            "merged_at": "2026-10-02T00:00:00Z",
            "merge_commit_sha": recovery.SLICE_C_MERGE,
            "head": {
                "sha": recovery.REVIEWED_HEAD,
                "repo": {
                    "id": recovery.REPOSITORY_ID,
                    "full_name": recovery.REPOSITORY,
                },
            },
            "base": {"ref": "main", "sha": recovery.REVIEWED_BASE},
        },
        f"/repos/{recovery.REPOSITORY}/pulls/{recovery.SLICE_C_PR}/files?per_page=100": [
            {"filename": recovery.CANDIDATE_PATH}
        ],
        f"/repos/{recovery.REPOSITORY}/actions/runs/{recovery.FAILED_APPLY_RUN}": {
            "id": recovery.FAILED_APPLY_RUN,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": "failure",
            "head_branch": "main",
            "head_sha": recovery.SLICE_C_MERGE,
            "event": "workflow_dispatch",
            "path": recovery.NORMAL_APPLY_CALLER_PATH + "@refs/heads/main",
            "repository": {"full_name": recovery.REPOSITORY},
            "head_repository": {"full_name": recovery.REPOSITORY},
            "referenced_workflows": [
                {
                    "path": (
                        f"{recovery.REPOSITORY}/"
                        f"{recovery.NORMAL_APPLY_REUSABLE_PATH}@"
                        f"{recovery.NORMAL_CONTROL_SHA}"
                    ),
                    "sha": recovery.NORMAL_CONTROL_SHA,
                }
            ],
        },
        f"/repos/{recovery.REPOSITORY}/actions/jobs/{recovery.FAILED_APPLY_JOB}": {
            "id": recovery.FAILED_APPLY_JOB,
            "run_id": recovery.FAILED_APPLY_RUN,
            "status": "completed",
            "conclusion": "failure",
            "name": "apply / product-apply",
        },
        f"/repos/{recovery.REPOSITORY}/issues/{recovery.GOVERNING_ISSUE}/comments?per_page=100&page=1": comments,
        f"/repos/{recovery.REPOSITORY}/pulls/{r2_pr_number}": {
            "number": r2_pr_number,
            "state": "closed",
            "merged_at": "2026-10-03T02:03:00Z",
            "merge_commit_sha": activation,
            "head": {
                "sha": reviewed_r2,
                "repo": {
                    "id": recovery.REPOSITORY_ID,
                    "full_name": recovery.REPOSITORY,
                },
            },
            "base": {"ref": "main", "sha": control},
        },
        f"/repos/{recovery.REPOSITORY}/pulls/{r2_pr_number}/reviews/{review_id}": {
            "id": review_id,
            "state": "COMMENTED",
            "commit_id": reviewed_r2,
            "body": review_body,
            "submitted_at": "2026-10-03T02:01:00Z",
            "user": {"login": "8ft0-ai", "id": 130460431},
        },
        f"/repos/{recovery.REPOSITORY}/issues/comments/{merge_authority_id}": owner_comment(
            merge_authority_id,
            merge_authority_body,
            "2026-10-03T02:02:00Z",
            r2_pr_number,
        ),
    }
    return {
        "control": control,
        "activation": activation,
        "reviewed_r2": reviewed_r2,
        "r2_pr_number": r2_pr_number,
        "review_id": review_id,
        "merge_authority_id": merge_authority_id,
        "activation_record_id": activation_record_id,
        "bootstrap_review_id": bootstrap_review_id,
        "bootstrap_authority_id": bootstrap_authority_id,
        "bootstrap_id": bootstrap_id,
        "dispatch_id": dispatch_id,
        "saved_plan_sha": saved_plan_sha,
        "manifest_sha": manifest_sha,
        "bootstrap_lineage": bootstrap_lineage,
        "bootstrap_serial_before": bootstrap_serial_before,
        "bootstrap_serial_after": bootstrap_serial_after,
        "boundary_body": boundary_body,
        "boundary_sha": recovery.sha256(boundary_body.encode("utf-8")),
        "candidate_raw": candidate_raw,
        "wrapped_candidate": wrapped_candidate,
        "fixtures": fixtures,
    }

def run_boundary(fixture):
    def fake_github(path):
        if path.startswith(
            f"/repos/{recovery.REPOSITORY}/contents/{recovery.CANDIDATE_PATH}?ref="
        ):
            return {
                "type": "file",
                "path": recovery.CANDIDATE_PATH,
                "encoding": "base64",
                "content": fixture["wrapped_candidate"],
            }
        if path not in fixture["fixtures"]:
            raise AssertionError(f"unexpected GitHub path: {path}")
        return copy.deepcopy(fixture["fixtures"][path])

    with tempfile.TemporaryDirectory() as tmp, patch.object(
        recovery, "github", side_effect=fake_github
    ), patch.object(
        recovery, "SOURCE_BOUNDARY_BODY_SHA256", fixture["boundary_sha"]
    ):
        output = Path(tmp) / "candidate.json"
        result = verify_github_boundary(
            fixture["activation"], fixture["control"], output
        )
        return result, output.read_bytes()


class SliceCRecoveryTests(unittest.TestCase):
    def test_exact_state_identity_is_accepted(self):
        self.assertEqual(verify_state_identity(state_identity())["serial"], 2)

    def test_state_identity_fails_closed_on_each_bound_identity(self):
        for key, value in (
            ("generation", "1790344068764583"),
            ("lineage", "wrong"),
            ("serial", 3),
            ("managed_addresses", list(EXPECTED_ADDRESSES[:-1])),
            ("state_sha256", "not-a-hash"),
        ):
            candidate = state_identity()
            candidate[key] = value
            with self.subTest(key=key), self.assertRaises(RecoveryError):
                verify_state_identity(candidate)

    def test_exact_no_change_plan_is_accepted(self):
        result = verify_no_change_plan(no_change_plan())
        self.assertTrue(result["no_change"])
        self.assertEqual(tuple(result["addresses"]), EXPECTED_ADDRESSES)

    def test_plan_rejects_material_effects_drift_and_address_change(self):
        for action in (["create"], ["update"], ["delete"], ["delete", "create"]):
            candidate = no_change_plan()
            candidate["resource_changes"][0]["change"]["actions"] = action
            with self.subTest(action=action), self.assertRaises(RecoveryError):
                verify_no_change_plan(candidate)
        drift = no_change_plan()
        drift["resource_drift"] = [{"address": EXPECTED_ADDRESSES[0]}]
        with self.assertRaises(RecoveryError):
            verify_no_change_plan(drift)
        extra = no_change_plan()
        extra["planned_values"]["root_module"]["resources"].append(
            {
                "address": "google_pubsub_subscription.unexpected",
                "mode": "managed",
                "type": "google_pubsub_subscription",
                "name": "unexpected",
                "values": {},
            }
        )
        with self.assertRaises(RecoveryError):
            verify_no_change_plan(extra)

    def test_caller_requires_protected_main_first_attempt_and_distinct_control(self):
        verify_caller_context(
            "8ft0-ai/resilio",
            "refs/heads/main",
            "true",
            "1",
            "2" * 40,
            "1" * 40,
        )
        hostile = (
            ("other/repo", "refs/heads/main", "true", "1", "2" * 40, "1" * 40),
            ("8ft0-ai/resilio", "refs/heads/feature", "true", "1", "2" * 40, "1" * 40),
            ("8ft0-ai/resilio", "refs/heads/main", "false", "1", "2" * 40, "1" * 40),
            ("8ft0-ai/resilio", "refs/heads/main", "true", "2", "2" * 40, "1" * 40),
            ("8ft0-ai/resilio", "refs/heads/main", "true", "1", "1" * 40, "1" * 40),
        )
        for args in hostile:
            with self.subTest(args=args), self.assertRaises(RecoveryError):
                verify_caller_context(*args)

    def test_workflow_permissions_triggers_and_action_pins_are_closed(self):
        workflow = (
            ROOT / ".github/workflows/phase5-slice-c-recovery-reusable.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(workflow_structure_errors(workflow), [])

        missing_permission = workflow.replace("      pull-requests: read\n", "", 1)
        self.assertIn(
            "RECOVERY_WORKFLOW_JOB_PERMISSION_SET_INVALID",
            workflow_structure_errors(missing_permission),
        )
        extra_trigger = workflow.replace(
            "on:\n  workflow_call:\n",
            "on:\n  workflow_call:\n  issues:\n    types: [opened]\n",
            1,
        )
        self.assertIn(
            "RECOVERY_WORKFLOW_TRIGGER_SET_NOT_EXACT_WORKFLOW_CALL",
            workflow_structure_errors(extra_trigger),
        )
        mutable_action = workflow.replace(
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "actions/checkout@main",
            1,
        )
        self.assertIn(
            "RECOVERY_WORKFLOW_UNPINNED_USE:actions/checkout@main",
            workflow_structure_errors(mutable_action),
        )

    def test_future_r2_caller_cannot_reduce_permission_envelope_or_add_inputs(self):
        control = "1" * 40
        caller = f"""name: Recovery caller
on:
  workflow_dispatch:
jobs:
  recover:
    permissions:
      contents: read
      issues: read
      actions: read
      pull-requests: read
      id-token: write
    uses: 8ft0-ai/resilio/.github/workflows/phase5-slice-c-recovery-reusable.yml@{control}
"""
        self.assertEqual(r2_caller_structure_errors(caller, control), [])
        reduced = caller.replace("      pull-requests: read\n", "")
        self.assertIn(
            "RECOVERY_R2_CALLER_PERMISSION_SET_INVALID",
            r2_caller_structure_errors(reduced, control),
        )
        mutable = caller.replace(
            "  workflow_dispatch:\n", "  workflow_dispatch:\n    inputs:\n      incident:\n"
        )
        self.assertIn(
            "RECOVERY_R2_CALLER_MUTABLE_INPUTS_FORBIDDEN",
            r2_caller_structure_errors(mutable, control),
        )

    def test_repository_shaped_r2_to_dispatch_chain_is_reachable(self):
        fixture = github_boundary_fixture()
        result, candidate = run_boundary(fixture)
        self.assertEqual(candidate, fixture["candidate_raw"])
        self.assertEqual(result["r2_activation_record_comment_id"], 303)
        self.assertEqual(result["bootstrap_fresh_review_comment_id"], 304)
        self.assertEqual(result["bootstrap_owner_apply_authority_comment_id"], 305)
        self.assertEqual(result["bootstrap_terminal_record_comment_id"], 306)
        self.assertEqual(result["dispatch_authority_comment_id"], 307)
        self.assertEqual(result["r2_reviewed_head"], fixture["reviewed_r2"])
        self.assertRegex(result["governance_chain_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            verify_github_boundary_document(
                result, fixture["control"], fixture["activation"]
            ),
            result,
        )

    def test_review_body_cannot_change_after_owner_authority(self):
        fixture = github_boundary_fixture()
        review_path = (
            f"/repos/{recovery.REPOSITORY}/pulls/{fixture['r2_pr_number']}/reviews/"
            f"{fixture['review_id']}"
        )
        fixture["fixtures"][review_path]["body"] += "\nretroactive edit"
        with self.assertRaises(RecoveryError):
            run_boundary(fixture)

    def test_authority_activation_and_dispatch_comments_are_not_editable(self):
        for target in (
            "merge",
            "activation",
            "bootstrap_review",
            "bootstrap_authority",
            "bootstrap_terminal",
            "dispatch",
        ):
            fixture = github_boundary_fixture()
            if target == "merge":
                path = (
                    f"/repos/{recovery.REPOSITORY}/issues/comments/"
                    f"{fixture['merge_authority_id']}"
                )
                fixture["fixtures"][path]["updated_at"] = "2026-10-03T02:02:30Z"
            else:
                comments_path = (
                    f"/repos/{recovery.REPOSITORY}/issues/"
                    f"{recovery.GOVERNING_ISSUE}/comments?per_page=100&page=1"
                )
                ids = {
                    "activation": fixture["activation_record_id"],
                    "bootstrap_review": fixture["bootstrap_review_id"],
                    "bootstrap_authority": fixture["bootstrap_authority_id"],
                    "bootstrap_terminal": fixture["bootstrap_id"],
                    "dispatch": fixture["dispatch_id"],
                }
                row = next(
                    x for x in fixture["fixtures"][comments_path]
                    if x["id"] == ids[target]
                )
                row["updated_at"] = "2026-10-03T02:10:00Z"
            with self.subTest(target=target), self.assertRaises(RecoveryError):
                run_boundary(fixture)

    def test_bootstrap_owner_local_saved_plan_chain_is_exact(self):
        fixture = github_boundary_fixture()
        result, _ = run_boundary(fixture)
        self.assertEqual(result["bootstrap_saved_plan_sha256"], fixture["saved_plan_sha"])
        self.assertEqual(
            result["bootstrap_structural_manifest_sha256"], fixture["manifest_sha"]
        )
        self.assertEqual(
            result["bootstrap_state_lineage"], fixture["bootstrap_lineage"]
        )
        self.assertEqual(
            result["bootstrap_state_serial_before"], fixture["bootstrap_serial_before"]
        )
        self.assertEqual(
            result["bootstrap_state_serial_after"], fixture["bootstrap_serial_after"]
        )
        self.assertFalse(
            any(
                "/actions/runs/401" in path or "/actions/jobs/402" in path
                for path in fixture["fixtures"]
            )
        )

    def test_bootstrap_terminal_and_predecessor_records_are_required(self):
        for key in ("bootstrap_review_id", "bootstrap_authority_id", "bootstrap_id"):
            fixture = github_boundary_fixture()
            comments_path = (
                f"/repos/{recovery.REPOSITORY}/issues/"
                f"{recovery.GOVERNING_ISSUE}/comments?per_page=100&page=1"
            )
            fixture["fixtures"][comments_path] = [
                row
                for row in fixture["fixtures"][comments_path]
                if row["id"] != fixture[key]
            ]
            with self.subTest(key=key), self.assertRaises(RecoveryError):
                run_boundary(fixture)

    def test_bootstrap_saved_plan_manifest_and_state_cannot_be_replaced(self):
        replacements = (
            ("SAVED_PLAN_SHA256", "d" * 64),
            ("STRUCTURAL_MANIFEST_SHA256", "e" * 64),
            ("BOOTSTRAP_STATE_LINEAGE", "replacement-lineage"),
            ("BOOTSTRAP_STATE_SERIAL_BEFORE", "71"),
        )
        for field, value in replacements:
            fixture = github_boundary_fixture()
            comments_path = (
                f"/repos/{recovery.REPOSITORY}/issues/"
                f"{recovery.GOVERNING_ISSUE}/comments?per_page=100&page=1"
            )
            terminal = next(
                row
                for row in fixture["fixtures"][comments_path]
                if row["id"] == fixture["bootstrap_id"]
            )
            lines = terminal["body"].splitlines()
            terminal["body"] = "\n".join(
                field + "=" + value if line.startswith(field + "=") else line
                for line in lines
            )
            with self.subTest(field=field), self.assertRaises(RecoveryError):
                run_boundary(fixture)

    def test_bootstrap_terminal_requires_no_change_no_unrelated_effect_and_no_lock(self):
        replacements = (
            (
                "BOOTSTRAP_RECONCILIATION=EXACT_NO_CHANGE",
                "BOOTSTRAP_RECONCILIATION=CHANGES_PRESENT",
            ),
            (
                "UNRELATED_BOOTSTRAP_AUTHORITY_CONSEQUENCE=NONE",
                "UNRELATED_BOOTSTRAP_AUTHORITY_CONSEQUENCE=PRESENT",
            ),
            ("FINAL_BOOTSTRAP_LOCK=ABSENT", "FINAL_BOOTSTRAP_LOCK=PRESENT"),
            (
                "IAM_CORRECTION=EXACT_TWO_GETMETADATA_ADDITIONS_LIVE",
                "IAM_CORRECTION=PARTIAL",
            ),
            (
                "RECOVERY_WIF_BINDING=EXACT_R1_RECOVERY_REUSABLE_LIVE",
                "RECOVERY_WIF_BINDING=MISSING",
            ),
        )
        for old, new in replacements:
            fixture = github_boundary_fixture()
            comments_path = (
                f"/repos/{recovery.REPOSITORY}/issues/"
                f"{recovery.GOVERNING_ISSUE}/comments?per_page=100&page=1"
            )
            terminal = next(
                row
                for row in fixture["fixtures"][comments_path]
                if row["id"] == fixture["bootstrap_id"]
            )
            terminal["body"] = terminal["body"].replace(old, new)
            with self.subTest(old=old), self.assertRaises(RecoveryError):
                run_boundary(fixture)

    def test_bootstrap_apply_authority_must_forbid_replan_replacement_and_retry(self):
        for token in (
            "REPLAN=NOT_AUTHORISED",
            "PLAN_REPLACEMENT=NOT_AUTHORISED",
            "BLIND_RETRY_AFTER_AMBIGUOUS_OUTCOME=NOT_AUTHORISED",
        ):
            fixture = github_boundary_fixture()
            comments_path = (
                f"/repos/{recovery.REPOSITORY}/issues/"
                f"{recovery.GOVERNING_ISSUE}/comments?per_page=100&page=1"
            )
            authority = next(
                row
                for row in fixture["fixtures"][comments_path]
                if row["id"] == fixture["bootstrap_authority_id"]
            )
            authority["body"] = authority["body"].replace(token, token.replace("NOT_AUTHORISED", "AUTHORISED"))
            with self.subTest(token=token), self.assertRaises(RecoveryError):
                run_boundary(fixture)


    def test_current_main_must_remain_exact_activation(self):
        fixture = github_boundary_fixture()
        fixture["fixtures"][
            f"/repos/{recovery.REPOSITORY}/branches/{recovery.DEFAULT_BRANCH}"
        ] = {"commit": {"sha": "4" * 40}}
        with self.assertRaises(RecoveryError):
            run_boundary(fixture)

    def test_comment_pagination_is_total_and_duplicate_safe(self):
        first = [
            {"id": i, "body": "", "user": {}}
            for i in range(1, 101)
        ]
        second = [{"id": 101, "body": "", "user": {}}]
        paths = {
            f"/repos/{recovery.REPOSITORY}/issues/109/comments?per_page=100&page=1": first,
            f"/repos/{recovery.REPOSITORY}/issues/109/comments?per_page=100&page=2": second,
        }
        with patch.object(recovery, "github", side_effect=lambda path: copy.deepcopy(paths[path])):
            rows = github_issue_comments(109)
        self.assertEqual(len(rows), 101)
        self.assertEqual(rows[-1]["id"], 101)

        duplicate = copy.deepcopy(second)
        duplicate[0]["id"] = 100
        paths[f"/repos/{recovery.REPOSITORY}/issues/109/comments?per_page=100&page=2"] = duplicate
        with patch.object(recovery, "github", side_effect=lambda path: copy.deepcopy(paths[path])):
            with self.assertRaises(RecoveryError):
                github_issue_comments(109)

    def test_boundary_document_closes_every_authority_hash_and_id(self):
        fixture = github_boundary_fixture()
        boundary, _ = run_boundary(fixture)

        hash_fields = (
            "source_boundary_body_sha256",
            "r2_fresh_review_body_sha256",
            "r2_merge_authority_body_sha256",
            "r2_activation_record_body_sha256",
            "bootstrap_saved_plan_sha256",
            "bootstrap_structural_manifest_sha256",
            "bootstrap_fresh_review_body_sha256",
            "bootstrap_owner_apply_authority_body_sha256",
            "bootstrap_terminal_record_body_sha256",
            "dispatch_authority_body_sha256",
        )
        for field in hash_fields:
            hostile = copy.deepcopy(boundary)
            hostile[field] = "not-a-sha256"
            hostile = rehash_boundary(hostile)
            with self.subTest(hash_field=field), self.assertRaises(RecoveryError):
                verify_github_boundary_document(
                    hostile, fixture["control"], fixture["activation"]
                )

        id_fields = (
            "r2_pr",
            "r2_fresh_review_id",
            "r2_merge_authority_comment_id",
            "r2_activation_record_comment_id",
            "bootstrap_fresh_review_comment_id",
            "bootstrap_owner_apply_authority_comment_id",
            "bootstrap_terminal_record_comment_id",
            "dispatch_authority_comment_id",
        )
        for field in id_fields:
            hostile = copy.deepcopy(boundary)
            hostile[field] = 0
            hostile = rehash_boundary(hostile)
            with self.subTest(id_field=field), self.assertRaises(RecoveryError):
                verify_github_boundary_document(
                    hostile, fixture["control"], fixture["activation"]
                )

    def test_boundary_document_closes_bootstrap_state_and_schema(self):
        fixture = github_boundary_fixture()
        boundary, _ = run_boundary(fixture)

        for field, value in (
            ("bootstrap_state_lineage", ""),
            ("bootstrap_state_serial_before", -1),
            ("bootstrap_state_serial_after", fixture["bootstrap_serial_before"] - 1),
        ):
            hostile = copy.deepcopy(boundary)
            hostile[field] = value
            hostile = rehash_boundary(hostile)
            with self.subTest(field=field), self.assertRaises(RecoveryError):
                verify_github_boundary_document(
                    hostile, fixture["control"], fixture["activation"]
                )

        hostile = copy.deepcopy(boundary)
        hostile["unexpected"] = True
        hostile = rehash_boundary(hostile)
        with self.assertRaises(RecoveryError):
            verify_github_boundary_document(
                hostile, fixture["control"], fixture["activation"]
            )


    def test_immutable_claim_and_result_snapshot_governance_chain(self):
        fixture = github_boundary_fixture()
        boundary, _ = run_boundary(fixture)
        claim = claim_document(
            fixture["control"], fixture["activation"], "123", boundary
        )
        self.assertEqual(
            claim["governance_chain_sha256"], boundary["governance_chain_sha256"]
        )
        self.assertEqual(claim["github_boundary"], boundary)
        self.assertRegex(claim["claim_sha256"], r"^[0-9a-f]{64}$")

        private, public = build_result(
            state_identity(),
            state_identity(),
            no_change_plan(),
            fixture["control"],
            fixture["activation"],
            "123",
            boundary,
        )
        self.assertEqual(private["github_boundary"], boundary)
        self.assertEqual(
            private["governance_chain_sha256"], boundary["governance_chain_sha256"]
        )
        self.assertEqual(public["claim_sha256"], claim["claim_sha256"])
        self.assertEqual(
            public["governance_chain_sha256"], boundary["governance_chain_sha256"]
        )
        self.assertNotIn("github_boundary", public)
        self.assertNotIn("state_before", public)

    def test_claim_and_result_object_names_are_fixed(self):
        control = "1" * 40
        self.assertEqual(
            evidence_object("claim", control),
            "plan-evidence/product/recovery-claim-5833629251-" + control + ".json",
        )
        self.assertEqual(
            evidence_object("result", control),
            "plan-evidence/product/recovery-result-5833629251-" + control + ".json",
        )
        with self.assertRaises(RecoveryError):
            evidence_object("other", control)

    def test_activation_record_cannot_be_replaced_by_later_main(self):
        fixture = github_boundary_fixture()
        comments_path = (
            f"/repos/{recovery.REPOSITORY}/issues/"
            f"{recovery.GOVERNING_ISSUE}/comments?per_page=100&page=1"
        )
        activation_record = next(
            x
            for x in fixture["fixtures"][comments_path]
            if x["id"] == fixture["activation_record_id"]
        )
        record = validate_r2_activation_record(
            [activation_record], fixture["control"], fixture["activation"]
        )
        self.assertEqual(record["comment_id"], fixture["activation_record_id"])
        replacement = copy.deepcopy(activation_record)
        replacement["id"] = 999
        replacement["body"] = replacement["body"].replace(
            f"R2_MERGE={fixture['activation']}", f"R2_MERGE={'4' * 40}"
        )
        with self.assertRaises(RecoveryError):
            validate_r2_activation_record(
                [activation_record, replacement], fixture["control"], "4" * 40
            )


if __name__ == "__main__":
    unittest.main()
