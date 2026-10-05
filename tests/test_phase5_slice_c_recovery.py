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


def successor_state_raw():
    resources=[]
    for address in recovery.SUCCESSOR_EXPECTED_ADDRESSES:
        typ,name=address.split('.',1)
        resources.append({"mode":"managed","type":typ,"name":name,"instances":[{"schema_version":0,"attributes":{}}]})
    return {"version":4,"terraform_version":"1.15.8","serial":4,"lineage":recovery.SUCCESSOR_EXPECTED_LINEAGE,"outputs":{},"resources":resources}


def successor_no_change_plan(with_drift=True):
    resources=[{"address":a,"mode":"managed","type":a.split('.',1)[0],"name":a.split('.',1)[1],"values":{}} for a in recovery.SUCCESSOR_EXPECTED_ADDRESSES]
    changes=[{"address":a,"mode":"managed","type":a.split('.',1)[0],"name":a.split('.',1)[1],"change":{"actions":["no-op"],"before":{},"after":{}}} for a in recovery.SUCCESSOR_EXPECTED_ADDRESSES]
    drift=[]
    if with_drift:
        drift=[{"address":"google_firestore_database.operational","mode":"managed","type":"google_firestore_database","name":"operational","change":{"actions":["update"],"before":{"earliest_version_time":"a","etag":"x","name":"(default)"},"after":{"earliest_version_time":"b","etag":"y","name":"(default)"}}}]
    return {"format_version":"1.2","terraform_version":"1.15.8","planned_values":{"root_module":{"resources":resources}},"resource_changes":changes,"resource_drift":drift,"deferred_changes":[],"deferred_action_invocations":[],"action_invocations":[],"output_changes":{},"applyable":False,"complete":True,"errored":False}


def successor_review_body(pr_number, head, control):
    return "\n".join((
        "COMPLETELY_FRESH_SUBSTANTIVE_SUCCESSOR_RECOVERY_IMPLEMENTATION_SECURITY_AUTHORITY_REVIEW",
        "DISPOSITION=APPROVED",f"PR=8ft0-ai/resilio#{pr_number}",f"EXACT_HEAD={head}",f"EXACT_BASE={control}",
        "GOVERNING_ISSUE=8ft0-ai/resilio#109",f"SUCCESSOR_ARCHITECTURE={recovery.SUCCESSOR_ARCHITECTURE_COMMENT_ID}",f"S1_TERMINAL={recovery.S1_TERMINAL_COMMENT_ID}","MATERIAL_BLOCKERS=NONE"))


def successor_boundary_fixture():
    control="4"*40; activation="5"*40; reviewed="6"*40; pr_number=130
    review_id=401; authority_id=402; activation_id=403; repin_review_id=404; repin_authority_id=405; repin_terminal_id=406; dispatch_id=407
    failure_body="\n".join((
        "SLICE_C_RECOVERY_ATTEMPT_1_CONSUMED_FAILED_NO_RETRY",
        f"RECOVERY_CONTROL_SHA={recovery.PREDECESSOR_CONTROL_SHA}",f"RECOVERY_ACTIVATION_MAIN={recovery.PREDECESSOR_ACTIVATION_SHA}",
        f"RECOVERY_RUN={recovery.PREDECESSOR_RECOVERY_RUN}",f"RECOVERY_JOB={recovery.PREDECESSOR_RECOVERY_JOB}",
        f"RECOVERY_CLAIM_GENERATION={recovery.PREDECESSOR_CLAIM_GENERATION}","RECOVERY_RESULT_OBJECT=ABSENT","FIRESTORE_STATE_INSTANCE_STATUS=tainted","RETRY_THIS_CONTROL=FORBIDDEN"))
    failure_sha=recovery.sha256(failure_body.encode())
    s1_body="\n".join((
        "PHASE5_SLICE_C_S1_STATE_REPAIR_TERMINAL_V1",f"STATE_GENERATION_AFTER={recovery.SUCCESSOR_EXPECTED_GENERATION}",
        f"STATE_BODY_SHA256_AFTER={recovery.SUCCESSOR_EXPECTED_STATE_BODY_SHA256}",f"STATE_SERIAL_AFTER={recovery.SUCCESSOR_EXPECTED_SERIAL}",
        f"STATE_LINEAGE={recovery.SUCCESSOR_EXPECTED_LINEAGE}","ALL_INSTANCE_STATUSES=normal","LIVE_CLOUD_SEMANTICS_CHANGED=NO","TERMINAL_NORMAL_PLAN_EXIT=0","TERMINAL_MATERIAL_RESOURCE_CHANGES=0","TERMINAL_MATERIAL_OUTPUT_CHANGES=0","TERMINAL_DEFERRED_ACTION_CONSEQUENCES=0","TERMINAL_RESIDUAL_DRIFT=google_firestore_database.operational__earliest_version_time+etag_only","FINAL_PRODUCT_LOCK=ABSENT","S1_TERMINAL_DISPOSITION=RECONCILED"))
    s1_sha=recovery.sha256(s1_body.encode())

    # Historical failed C2 activation layer.
    superseded_failure_body="\n".join((
        "S3_SUCCESSOR_ACTIVATION_MERGED_BUT_RUNTIME_UNREACHABLE",
        "STATUS=POST_MERGE_AUTHORITY_GRAMMAR_DEFECT",
        f"PR=8ft0-ai/resilio#{recovery.SUPERSEDED_ACTIVATION_PR}",
        f"SUCCESSOR_CONTROL_C2={recovery.SUPERSEDED_CONTROL_SHA}",
        f"EXACT_REVIEWED_HEAD={recovery.SUPERSEDED_ACTIVATION_REVIEWED_HEAD}",
        f"EXACT_REVIEWED_TREE={recovery.SUPERSEDED_ACTIVATION_REVIEWED_TREE}",
        f"FRESH_REVIEW={recovery.SUPERSEDED_ACTIVATION_REVIEW_ID}__APPROVED",
        f"OWNER_MERGE_AUTHORITY_COMMENT_ID={recovery.SUPERSEDED_ACTIVATION_AUTHORITY_ID}",
        "OWNER_MERGE_AUTHORITY_BODY_SHA256=fixture-authority-sha",
        f"MERGE_SHA={recovery.SUPERSEDED_ACTIVATION_MERGE_SHA}",
        "MERGED_TREE_EQUALS_REVIEWED_TREE=TRUE",
        "DEFECT=C2_RUNTIME_REQUIRES_EXACT_MACHINE_GRAMMAR_FOR_SUCCESSOR_MERGE_AUTHORITY",
        "C2_ACTIVATION_RECORD=NOT_CREATABLE_AS_VALID_RUNTIME_EVIDENCE",
        "LIVE_RECOVERY_WIF=C1_ONLY","LIVE_RECOVERY_WIF_C2=ABSENT","C2_RECOVERY_CLAIM=ABSENT","C2_RECOVERY_RESULT=ABSENT",
        "SUCCESSOR_DISPATCH=NOT_PERFORMED","SAFETY_DISPOSITION=FAIL_CLOSED","NEXT_PHASE=SUCCESSOR_CONTROL_RECONSTRUCTION_C3",
    ))
    superseded_review_body="historical-c2-reviewed-body"
    superseded_review_sha=recovery.sha256(superseded_review_body.encode())
    superseded_authority_body="historical-c2-human-readable-authority"
    superseded_authority_sha=recovery.sha256(superseded_authority_body.encode())
    superseded_failure_body=superseded_failure_body.replace("fixture-authority-sha",superseded_authority_sha)
    superseded_failure_sha=recovery.sha256(superseded_failure_body.encode())

    # Historical C3 architecture layer.
    c3_architecture_body="\n".join((
        "SLICE_C_SUCCESSOR_RECOVERY_C3_ARCHITECTURE_CLOSURE_V1",
        "STATUS=C3_ARCHITECTURE_COMPLETE_PENDING_FRESH_REVIEW",
        f"CURRENT_MAIN={recovery.SUPERSEDED_ACTIVATION_MERGE_SHA}",
        f"IMMUTABLE_CONTROL_C2={recovery.SUPERSEDED_CONTROL_SHA}",
        f"FAILED_C2_ACTIVATION_PR={recovery.SUPERSEDED_ACTIVATION_PR}",
        f"FAILED_C2_ACTIVATION_RECORD={recovery.SUPERSEDED_ACTIVATION_FAILURE_RECORD_ID}",
        f"S1_TERMINAL={recovery.S1_TERMINAL_COMMENT_ID}",
        "LIVE_RECOVERY_WIF=C1_ONLY","C2_LIVE_WIF=ABSENT","C2_CLAIM=ABSENT","C2_RESULT=ABSENT",
    ))
    c3_architecture_sha=recovery.sha256(c3_architecture_body.encode())
    c3_architecture_review_body="\n".join((
        "COMPLETELY_FRESH_SUBSTANTIVE_C3_ARCHITECTURE_SECURITY_AUTHORITY_REVIEW",
        f"REVIEW_TARGET={recovery.C3_ARCHITECTURE_COMMENT_ID}",
        "DISPOSITION=APPROVED","MATERIAL_BLOCKERS=NONE","FAILED_C2_SUPERSESSION=PASS",
        "CURRENT_SAFETY_STATE=PASS","C3_INERTNESS=PASS","AUTHORITY_PROTOCOL_CLOSURE=PASS",
        "C3_ACTIVATION_REACHABILITY=PASS","LIVE_WIF_REPIN_REACHABILITY=PASS","C3_ONE_SHOT_RECOVERY_REACHABILITY=PASS",
    ))
    c3_architecture_review_sha=recovery.sha256(c3_architecture_review_body.encode())

    # Failed C3 activation: exact review + CRLF-stored authority + fail-closed record.
    failed_c3_review_body="\n".join((
        "COMPLETELY_FRESH_SUBSTANTIVE_SUCCESSOR_RECOVERY_IMPLEMENTATION_SECURITY_AUTHORITY_REVIEW",
        "DISPOSITION=APPROVED",
        f"PR=8ft0-ai/resilio#{recovery.FAILED_C3_ACTIVATION_PR}",
        f"EXACT_HEAD={recovery.FAILED_C3_ACTIVATION_REVIEWED_HEAD}",
        f"EXACT_BASE={recovery.FAILED_C3_CONTROL_SHA}",
        "GOVERNING_ISSUE=8ft0-ai/resilio#109",
        f"SUCCESSOR_ARCHITECTURE={recovery.C3_ARCHITECTURE_COMMENT_ID}",
        f"S1_TERMINAL={recovery.S1_TERMINAL_COMMENT_ID}",
        "MATERIAL_BLOCKERS=NONE",
    ))
    failed_c3_review_sha=recovery.sha256(failed_c3_review_body.encode())
    failed_c3_authority_lf=recovery._activation_merge_authority_body_for_architecture(
        recovery.C3_ARCHITECTURE_COMMENT_ID,recovery.FAILED_C3_CONTROL_SHA,
        recovery.FAILED_C3_ACTIVATION_PR,recovery.FAILED_C3_ACTIVATION_REVIEWED_HEAD,
        recovery.FAILED_C3_ACTIVATION_REVIEW_ID,failed_c3_review_sha,
    )
    failed_c3_authority_body=failed_c3_authority_lf.replace("\n","\r\n")
    failed_c3_authority_sha=recovery.sha256(failed_c3_authority_body.encode())
    failed_c3_failure_body=(
        f"C3 activation fail-closed before merge: PR #{recovery.FAILED_C3_ACTIVATION_PR} authority comment "
        f"{recovery.FAILED_C3_ACTIVATION_AUTHORITY_ID} is owner-authored and unedited, but GitHub stored its body with CRLF line endings "
        "while immutable C3's exact authority grammar is LF and performs byte-exact comparison. Therefore the C3 pre-merge authority "
        "contract is not satisfiable by this posted comment and PR #126 must not merge. No live WIF/IAM change, recovery dispatch, "
        "claim/result creation, Terraform apply, or cloud consequence occurred. NEXT_PHASE=AUTHORITY_SERIALIZATION_COMPATIBILITY_CLOSURE"
    )
    failed_c3_failure_sha=recovery.sha256(failed_c3_failure_body.encode())

    # Current C4 architecture layer.
    architecture_body="\n".join((
        "SLICE_C_SUCCESSOR_AUTHORITY_SERIALIZATION_COMPATIBILITY_CLOSURE_V1",
        "STATUS=C4_ARCHITECTURE_REVISION_2_COMPLETE_PENDING_FRESH_REVIEW",
        "SUPERSEDES=5975200771",
        f"CURRENT_MAIN={recovery.FAILED_C3_CONTROL_SHA}",
        f"IMMUTABLE_C3_CONTROL={recovery.FAILED_C3_CONTROL_SHA}",
        f"FAILED_C3_ACTIVATION_PR={recovery.FAILED_C3_ACTIVATION_PR}",
        f"FAILED_C3_ACTIVATION_REVIEW={recovery.FAILED_C3_ACTIVATION_REVIEW_ID}",
        f"FAILED_C3_AUTHORITY_COMMENT={recovery.FAILED_C3_ACTIVATION_AUTHORITY_ID}",
        f"FAILED_C3_AUTHORITY_RECORD={recovery.FAILED_C3_ACTIVATION_FAILURE_RECORD_ID}",
        "REPOSITORY_CALLER=C2","REPOSITORY_DESIRED_WIF=C2","LIVE_RECOVERY_WIF=C1",
        "C4_IMPLEMENTATION=NOT_PERFORMED","LIVE_WIF_REPIN=NOT_PERFORMED","RECOVERY_DISPATCH=NOT_PERFORMED",
    ))
    architecture_sha=recovery.sha256(architecture_body.encode())
    architecture_review_body="\n".join((
        "COMPLETELY_FRESH_SUBSTANTIVE_C4_ARCHITECTURE_SECURITY_AUTHORITY_REVIEW",
        f"REVIEW_TARGET={recovery.SUCCESSOR_ARCHITECTURE_COMMENT_ID}",
        "DISPOSITION=APPROVED","MATERIAL_BLOCKERS=NONE",
        "REPOSITORY_STATE_MODEL=PASS","DIRECT_SUCCESSOR_REACHABILITY=PASS",
        "TRANSPORT_NORMALIZATION_BOUNDARY=PASS","RAW_PROVENANCE=PASS","FAILED_C3_PROVENANCE=PASS",
        "INERT_C4_CONTROL=PASS","C4_ACTIVATION_AND_WIF_TRANSITIONS=PASS","ANTI_RECURRENCE=PASS",
    ))
    architecture_review_sha=recovery.sha256(architecture_review_body.encode())

    patches=(
        patch.object(recovery,"PREDECESSOR_FAILURE_RECORD_BODY_SHA256",failure_sha),
        patch.object(recovery,"S1_TERMINAL_BODY_SHA256",s1_sha),
        patch.object(recovery,"SUPERSEDED_ACTIVATION_FAILURE_RECORD_BODY_SHA256",superseded_failure_sha),
        patch.object(recovery,"SUPERSEDED_ACTIVATION_REVIEW_BODY_SHA256",superseded_review_sha),
        patch.object(recovery,"SUPERSEDED_ACTIVATION_AUTHORITY_BODY_SHA256",superseded_authority_sha),
        patch.object(recovery,"C3_ARCHITECTURE_BODY_SHA256",c3_architecture_sha),
        patch.object(recovery,"C3_ARCHITECTURE_REVIEW_BODY_SHA256",c3_architecture_review_sha),
        patch.object(recovery,"FAILED_C3_ACTIVATION_REVIEW_BODY_SHA256",failed_c3_review_sha),
        patch.object(recovery,"FAILED_C3_ACTIVATION_AUTHORITY_RAW_BODY_SHA256",failed_c3_authority_sha),
        patch.object(recovery,"FAILED_C3_ACTIVATION_FAILURE_RECORD_BODY_SHA256",failed_c3_failure_sha),
        patch.object(recovery,"SUCCESSOR_ARCHITECTURE_BODY_SHA256",architecture_sha),
        patch.object(recovery,"SUCCESSOR_ARCHITECTURE_REVIEW_BODY_SHA256",architecture_review_sha),
    )
    for item in patches: item.start()
    try:
        review_body=successor_review_body(pr_number,reviewed,control); review_sha=recovery.sha256(review_body.encode())
        authority_body=recovery.successor_activation_merge_authority_body(control,pr_number,reviewed,review_id,review_sha); authority_sha=recovery.sha256(authority_body.encode())
        activation_body=recovery.successor_activation_record_body(control,activation,pr_number,reviewed,review_id,review_sha,authority_id,authority_sha); activation_sha=recovery.sha256(activation_body.encode())
        activation_record={"comment_id":activation_id,"created_at":recovery._timestamp("2026-10-03T03:03:00Z","x"),"body_sha256":activation_sha}
        plan_sha="b"*64; manifest_sha="c"*64; bootstrap_lineage="bootstrap-lineage"; sb=80; sa=81
        repin_review_body=recovery.successor_wif_repin_review_body(control,activation,plan_sha,manifest_sha,bootstrap_lineage,sb); repin_review_sha=recovery.sha256(repin_review_body.encode())
        repin_authority_body=recovery.successor_wif_repin_authority_body(control,activation,plan_sha,manifest_sha,bootstrap_lineage,sb,repin_review_id,repin_review_sha); repin_authority_sha=recovery.sha256(repin_authority_body.encode())
        repin_terminal_body=recovery.successor_wif_repin_terminal_body(control,activation,plan_sha,manifest_sha,bootstrap_lineage,sb,sa,repin_review_id,repin_review_sha,repin_authority_id,repin_authority_sha); repin_terminal_sha=recovery.sha256(repin_terminal_body.encode())
        repin_terminal={"comment_id":repin_terminal_id,"body_sha256":repin_terminal_sha}
        dispatch_body=recovery.successor_dispatch_authority_body(control,activation,activation_record,repin_terminal)
    finally:
        for item in reversed(patches): item.stop()

    comments=[
      owner_comment(recovery.PREDECESSOR_FAILURE_RECORD_ID,failure_body,"2026-10-03T01:00:00Z"),
      owner_comment(recovery.S1_TERMINAL_COMMENT_ID,s1_body,"2026-10-03T02:00:00Z"),
      owner_comment(recovery.SUPERSEDED_ACTIVATION_FAILURE_RECORD_ID,superseded_failure_body,"2026-10-03T02:13:00Z"),
      owner_comment(recovery.C3_ARCHITECTURE_COMMENT_ID,c3_architecture_body,"2026-10-03T02:14:00Z"),
      owner_comment(recovery.C3_ARCHITECTURE_REVIEW_COMMENT_ID,c3_architecture_review_body,"2026-10-03T02:15:00Z"),
      owner_comment(recovery.FAILED_C3_ACTIVATION_FAILURE_RECORD_ID,failed_c3_failure_body,"2026-10-03T02:20:00Z"),
      owner_comment(recovery.SUCCESSOR_ARCHITECTURE_COMMENT_ID,architecture_body,"2026-10-03T02:21:00Z"),
      owner_comment(recovery.SUCCESSOR_ARCHITECTURE_REVIEW_COMMENT_ID,architecture_review_body,"2026-10-03T02:22:00Z"),
      owner_comment(activation_id,activation_body,"2026-10-03T03:03:00Z"),
      owner_comment(repin_review_id,repin_review_body,"2026-10-03T03:04:00Z"),
      owner_comment(repin_authority_id,repin_authority_body,"2026-10-03T03:05:00Z"),
      owner_comment(repin_terminal_id,repin_terminal_body,"2026-10-03T03:06:00Z"),
      owner_comment(dispatch_id,dispatch_body,"2026-10-03T03:07:00Z"),
    ]
    boundary_body="\n".join(("STATUS=SLICE_C_BASE_RESOURCES_APPLIED_BUT_TERMINAL_NO_CHANGE_PROOF_FAILED",f"EXACT_REVIEWED_HEAD={recovery.REVIEWED_HEAD}",f"REVIEWED_BASE={recovery.REVIEWED_BASE}",f"MERGE_COMMIT={recovery.SLICE_C_MERGE}",f"PRODUCT_APPLY_RUN={recovery.FAILED_APPLY_RUN}",f"PRODUCT_APPLY_JOB={recovery.FAILED_APPLY_JOB}",f"PRODUCT_STATE_GENERATION={recovery.EXPECTED_GENERATION}",f"PRODUCT_STATE_SERIAL={recovery.EXPECTED_SERIAL}",f"PRODUCT_STATE_LINEAGE={recovery.EXPECTED_LINEAGE}","Retry prohibition","do **not** rerun the existing product apply workflow"))
    boundary_sha=recovery.sha256(boundary_body.encode())
    candidate_raw=recovery.canonical(recovery.expected_candidate())+b"\n"; wrapped=base64.encodebytes(candidate_raw).decode()
    fixtures={
      f"/repos/{recovery.REPOSITORY}/branches/{recovery.DEFAULT_BRANCH}":{"commit":{"sha":activation}},
      f"/repos/{recovery.REPOSITORY}/issues/{recovery.GOVERNING_ISSUE}":{"state":"open"},
      f"/repos/{recovery.REPOSITORY}/issues/comments/{recovery.SOURCE_BOUNDARY_COMMENT_ID}":owner_comment(recovery.SOURCE_BOUNDARY_COMMENT_ID,boundary_body,"2026-10-02T01:00:00Z"),
      f"/repos/{recovery.REPOSITORY}/pulls/{recovery.SLICE_C_PR}":{"number":recovery.SLICE_C_PR,"state":"closed","merged_at":"2026-10-02T00:00:00Z","merge_commit_sha":recovery.SLICE_C_MERGE,"head":{"sha":recovery.REVIEWED_HEAD,"repo":{"id":recovery.REPOSITORY_ID,"full_name":recovery.REPOSITORY}},"base":{"ref":"main","sha":recovery.REVIEWED_BASE}},
      f"/repos/{recovery.REPOSITORY}/pulls/{recovery.SLICE_C_PR}/files?per_page=100":[{"filename":recovery.CANDIDATE_PATH}],
      f"/repos/{recovery.REPOSITORY}/actions/runs/{recovery.FAILED_APPLY_RUN}":{"id":recovery.FAILED_APPLY_RUN,"run_attempt":1,"status":"completed","conclusion":"failure","head_branch":"main","head_sha":recovery.SLICE_C_MERGE,"event":"workflow_dispatch","path":recovery.NORMAL_APPLY_CALLER_PATH+"@refs/heads/main","repository":{"full_name":recovery.REPOSITORY},"head_repository":{"full_name":recovery.REPOSITORY},"referenced_workflows":[{"path":f"{recovery.REPOSITORY}/{recovery.NORMAL_APPLY_REUSABLE_PATH}@{recovery.NORMAL_CONTROL_SHA}","sha":recovery.NORMAL_CONTROL_SHA}]},
      f"/repos/{recovery.REPOSITORY}/actions/jobs/{recovery.FAILED_APPLY_JOB}":{"id":recovery.FAILED_APPLY_JOB,"run_id":recovery.FAILED_APPLY_RUN,"status":"completed","conclusion":"failure","name":"apply / product-apply"},
      f"/repos/{recovery.REPOSITORY}/actions/runs/{recovery.PREDECESSOR_RECOVERY_RUN}":{"id":recovery.PREDECESSOR_RECOVERY_RUN,"run_attempt":1,"status":"completed","conclusion":"failure","head_branch":"main","head_sha":recovery.PREDECESSOR_ACTIVATION_SHA,"event":"workflow_dispatch","path":".github/workflows/phase5-slice-c-recovery.yml","repository":{"full_name":recovery.REPOSITORY},"head_repository":{"full_name":recovery.REPOSITORY},"referenced_workflows":[{"path":f"{recovery.REPOSITORY}/{recovery.RECOVERY_REUSABLE_PATH}@{recovery.PREDECESSOR_CONTROL_SHA}","sha":recovery.PREDECESSOR_CONTROL_SHA}]},
      f"/repos/{recovery.REPOSITORY}/actions/jobs/{recovery.PREDECESSOR_RECOVERY_JOB}":{"id":recovery.PREDECESSOR_RECOVERY_JOB,"run_id":recovery.PREDECESSOR_RECOVERY_RUN,"status":"completed","conclusion":"failure","name":"recover / slice-c-recovery"},
      f"/repos/{recovery.REPOSITORY}/issues/{recovery.GOVERNING_ISSUE}/comments?per_page=100&page=1":comments,
      f"/repos/{recovery.REPOSITORY}/pulls/{recovery.SUPERSEDED_ACTIVATION_PR}":{"number":recovery.SUPERSEDED_ACTIVATION_PR,"state":"closed","merged_at":"2026-10-03T02:12:00Z","merge_commit_sha":recovery.SUPERSEDED_ACTIVATION_MERGE_SHA,"head":{"sha":recovery.SUPERSEDED_ACTIVATION_REVIEWED_HEAD,"repo":{"id":recovery.REPOSITORY_ID,"full_name":recovery.REPOSITORY}},"base":{"ref":"main","sha":recovery.SUPERSEDED_CONTROL_SHA}},
      f"/repos/{recovery.REPOSITORY}/pulls/{recovery.SUPERSEDED_ACTIVATION_PR}/reviews/{recovery.SUPERSEDED_ACTIVATION_REVIEW_ID}":{"id":recovery.SUPERSEDED_ACTIVATION_REVIEW_ID,"state":"COMMENTED","commit_id":recovery.SUPERSEDED_ACTIVATION_REVIEWED_HEAD,"body":superseded_review_body,"submitted_at":"2026-10-03T02:10:00Z","user":{"login":"8ft0-ai","id":130460431}},
      f"/repos/{recovery.REPOSITORY}/issues/comments/{recovery.SUPERSEDED_ACTIVATION_AUTHORITY_ID}":owner_comment(recovery.SUPERSEDED_ACTIVATION_AUTHORITY_ID,superseded_authority_body,"2026-10-03T02:11:00Z",recovery.SUPERSEDED_ACTIVATION_PR),
      f"/repos/{recovery.REPOSITORY}/commits/{recovery.SUPERSEDED_ACTIVATION_REVIEWED_HEAD}":{"sha":recovery.SUPERSEDED_ACTIVATION_REVIEWED_HEAD,"commit":{"tree":{"sha":recovery.SUPERSEDED_ACTIVATION_REVIEWED_TREE}}},
      f"/repos/{recovery.REPOSITORY}/commits/{recovery.SUPERSEDED_ACTIVATION_MERGE_SHA}":{"sha":recovery.SUPERSEDED_ACTIVATION_MERGE_SHA,"commit":{"tree":{"sha":recovery.SUPERSEDED_ACTIVATION_REVIEWED_TREE}}},
      f"/repos/{recovery.REPOSITORY}/pulls/{recovery.FAILED_C3_ACTIVATION_PR}":{"number":recovery.FAILED_C3_ACTIVATION_PR,"state":"closed","merged_at":None,"head":{"sha":recovery.FAILED_C3_ACTIVATION_REVIEWED_HEAD,"repo":{"id":recovery.REPOSITORY_ID,"full_name":recovery.REPOSITORY}},"base":{"ref":"main","sha":recovery.FAILED_C3_CONTROL_SHA}},
      f"/repos/{recovery.REPOSITORY}/pulls/{recovery.FAILED_C3_ACTIVATION_PR}/reviews/{recovery.FAILED_C3_ACTIVATION_REVIEW_ID}":{"id":recovery.FAILED_C3_ACTIVATION_REVIEW_ID,"state":"COMMENTED","commit_id":recovery.FAILED_C3_ACTIVATION_REVIEWED_HEAD,"body":failed_c3_review_body,"submitted_at":"2026-10-03T02:18:00Z","user":{"login":"8ft0-ai","id":130460431}},
      f"/repos/{recovery.REPOSITORY}/issues/comments/{recovery.FAILED_C3_ACTIVATION_AUTHORITY_ID}":owner_comment(recovery.FAILED_C3_ACTIVATION_AUTHORITY_ID,failed_c3_authority_body,"2026-10-03T02:19:00Z",recovery.FAILED_C3_ACTIVATION_PR),
      f"/repos/{recovery.REPOSITORY}/commits/{recovery.FAILED_C3_ACTIVATION_REVIEWED_HEAD}":{"sha":recovery.FAILED_C3_ACTIVATION_REVIEWED_HEAD,"commit":{"tree":{"sha":recovery.FAILED_C3_ACTIVATION_REVIEWED_TREE}}},
      f"/repos/{recovery.REPOSITORY}/pulls/{pr_number}":{"number":pr_number,"state":"closed","merged_at":"2026-10-03T03:02:00Z","merge_commit_sha":activation,"head":{"sha":reviewed,"repo":{"id":recovery.REPOSITORY_ID,"full_name":recovery.REPOSITORY}},"base":{"ref":"main","sha":control}},
      f"/repos/{recovery.REPOSITORY}/pulls/{pr_number}/reviews/{review_id}":{"id":review_id,"state":"COMMENTED","commit_id":reviewed,"body":review_body,"submitted_at":"2026-10-03T03:00:00Z","user":{"login":"8ft0-ai","id":130460431}},
      f"/repos/{recovery.REPOSITORY}/issues/comments/{authority_id}":owner_comment(authority_id,authority_body,"2026-10-03T03:01:00Z",pr_number),
      f"/repos/{recovery.REPOSITORY}/commits/{reviewed}":{"sha":reviewed,"commit":{"tree":{"sha":"a"*40}}},
      f"/repos/{recovery.REPOSITORY}/commits/{activation}":{"sha":activation,"commit":{"tree":{"sha":"a"*40}}},
    }
    return {
        "control":control,"activation":activation,"failure_sha":failure_sha,"s1_sha":s1_sha,
        "superseded_failure_sha":superseded_failure_sha,"superseded_review_sha":superseded_review_sha,"superseded_authority_sha":superseded_authority_sha,
        "c3_architecture_sha":c3_architecture_sha,"c3_architecture_review_sha":c3_architecture_review_sha,
        "failed_c3_review_sha":failed_c3_review_sha,"failed_c3_authority_sha":failed_c3_authority_sha,"failed_c3_failure_sha":failed_c3_failure_sha,
        "architecture_sha":architecture_sha,"architecture_review_sha":architecture_review_sha,
        "boundary_sha":boundary_sha,"candidate_raw":candidate_raw,"wrapped":wrapped,"fixtures":fixtures,
    }


def run_successor_boundary(fixture):
    def fake_github(path):
        if path.startswith(f"/repos/{recovery.REPOSITORY}/contents/{recovery.CANDIDATE_PATH}?ref="):
            return {"type":"file","path":recovery.CANDIDATE_PATH,"encoding":"base64","content":fixture["wrapped"]}
        if path not in fixture["fixtures"]: raise AssertionError(f"unexpected GitHub path: {path}")
        return copy.deepcopy(fixture["fixtures"][path])
    patches=(
        patch.object(recovery,"SOURCE_BOUNDARY_BODY_SHA256",fixture["boundary_sha"]),
        patch.object(recovery,"PREDECESSOR_FAILURE_RECORD_BODY_SHA256",fixture["failure_sha"]),
        patch.object(recovery,"S1_TERMINAL_BODY_SHA256",fixture["s1_sha"]),
        patch.object(recovery,"SUPERSEDED_ACTIVATION_FAILURE_RECORD_BODY_SHA256",fixture["superseded_failure_sha"]),
        patch.object(recovery,"SUPERSEDED_ACTIVATION_REVIEW_BODY_SHA256",fixture["superseded_review_sha"]),
        patch.object(recovery,"SUPERSEDED_ACTIVATION_AUTHORITY_BODY_SHA256",fixture["superseded_authority_sha"]),
        patch.object(recovery,"C3_ARCHITECTURE_BODY_SHA256",fixture["c3_architecture_sha"]),
        patch.object(recovery,"C3_ARCHITECTURE_REVIEW_BODY_SHA256",fixture["c3_architecture_review_sha"]),
        patch.object(recovery,"FAILED_C3_ACTIVATION_REVIEW_BODY_SHA256",fixture["failed_c3_review_sha"]),
        patch.object(recovery,"FAILED_C3_ACTIVATION_AUTHORITY_RAW_BODY_SHA256",fixture["failed_c3_authority_sha"]),
        patch.object(recovery,"FAILED_C3_ACTIVATION_FAILURE_RECORD_BODY_SHA256",fixture["failed_c3_failure_sha"]),
        patch.object(recovery,"SUCCESSOR_ARCHITECTURE_BODY_SHA256",fixture["architecture_sha"]),
        patch.object(recovery,"SUCCESSOR_ARCHITECTURE_REVIEW_BODY_SHA256",fixture["architecture_review_sha"]),
    )
    with tempfile.TemporaryDirectory() as tmp, patch.object(recovery,"github",side_effect=fake_github):
        for item in patches: item.start()
        try:
            output=Path(tmp)/"candidate.json"
            result=recovery.verify_successor_github_boundary(fixture["activation"],fixture["control"],output)
            return result,output.read_bytes()
        finally:
            for item in reversed(patches): item.stop()


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

    def test_actual_successor_caller_pins_immutable_c4_control(self):
        caller = (
            ROOT / ".github/workflows/phase5-slice-c-recovery.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            r2_caller_structure_errors(
                caller, "03123864097df51e6edafd67acc34702f0819de3"
            ),
            [],
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


    def test_successor_state_identity_requires_all_normal_statuses_and_exact_canonical_state(self):
        raw=successor_state_raw(); expected=recovery.sha256(recovery.canonical(raw))
        with patch.object(recovery,"SUCCESSOR_EXPECTED_STATE_CANONICAL_SHA256",expected):
            identity=recovery.successor_state_identity_from_state(raw,recovery.SUCCESSOR_EXPECTED_GENERATION)
            self.assertEqual(identity["serial"],4)
            self.assertTrue(all(v=="normal" for v in identity["instance_statuses"].values()))
            hostile=copy.deepcopy(raw); hostile["resources"][1]["instances"][0]["status"]="tainted"
            with self.assertRaises(RecoveryError): recovery.successor_state_identity_from_state(hostile,recovery.SUCCESSOR_EXPECTED_GENERATION)
            deposed=copy.deepcopy(raw); deposed["resources"][1]["instances"][0]["deposed"]="deadbeef"
            with self.assertRaises(RecoveryError): recovery.successor_state_identity_from_state(deposed,recovery.SUCCESSOR_EXPECTED_GENERATION)

    def test_successor_plan_accepts_only_firestore_volatile_drift(self):
        good=successor_no_change_plan(); result=recovery.verify_successor_no_change_plan(good)
        self.assertEqual(result["residual_firestore_drift_fields"],["earliest_version_time","etag"])
        stable=successor_no_change_plan(); stable["resource_drift"][0]["change"]["after"]["concurrency_mode"]="OPTIMISTIC"
        with self.assertRaises(RecoveryError): recovery.verify_successor_no_change_plan(stable)
        wrong=successor_no_change_plan(); wrong["resource_drift"][0]["address"]="google_pubsub_topic.deployment_events"
        with self.assertRaises(RecoveryError): recovery.verify_successor_no_change_plan(wrong)
        effect=successor_no_change_plan(False); effect["resource_changes"][0]["change"]["actions"]=["update"]
        with self.assertRaises(RecoveryError): recovery.verify_successor_no_change_plan(effect)
        moved=successor_no_change_plan(False); moved["resource_changes"][0]["previous_address"]="google_storage_bucket.old"
        with self.assertRaises(RecoveryError): recovery.verify_successor_no_change_plan(moved)

    def test_successor_repository_shaped_activation_repin_dispatch_chain_is_reachable(self):
        fixture=successor_boundary_fixture(); result,candidate=run_successor_boundary(fixture)
        self.assertEqual(candidate,fixture["candidate_raw"])
        self.assertEqual(result["predecessor_recovery_run"],recovery.PREDECESSOR_RECOVERY_RUN)
        self.assertEqual(result["s1_terminal_comment_id"],recovery.S1_TERMINAL_COMMENT_ID)
        self.assertEqual(result["control_sha"],fixture["control"])
        self.assertEqual(result["activation_sha"],fixture["activation"])
        self.assertRegex(result["governance_chain_sha256"],r"^[0-9a-f]{64}$")
        patches=(
            patch.object(recovery,"PREDECESSOR_FAILURE_RECORD_BODY_SHA256",fixture["failure_sha"]),
            patch.object(recovery,"S1_TERMINAL_BODY_SHA256",fixture["s1_sha"]),
            patch.object(recovery,"SUPERSEDED_ACTIVATION_FAILURE_RECORD_BODY_SHA256",fixture["superseded_failure_sha"]),
            patch.object(recovery,"SUPERSEDED_ACTIVATION_REVIEW_BODY_SHA256",fixture["superseded_review_sha"]),
            patch.object(recovery,"SUPERSEDED_ACTIVATION_AUTHORITY_BODY_SHA256",fixture["superseded_authority_sha"]),
            patch.object(recovery,"C3_ARCHITECTURE_BODY_SHA256",fixture["c3_architecture_sha"]),
            patch.object(recovery,"C3_ARCHITECTURE_REVIEW_BODY_SHA256",fixture["c3_architecture_review_sha"]),
            patch.object(recovery,"FAILED_C3_ACTIVATION_REVIEW_BODY_SHA256",fixture["failed_c3_review_sha"]),
            patch.object(recovery,"FAILED_C3_ACTIVATION_AUTHORITY_RAW_BODY_SHA256",fixture["failed_c3_authority_sha"]),
            patch.object(recovery,"FAILED_C3_ACTIVATION_FAILURE_RECORD_BODY_SHA256",fixture["failed_c3_failure_sha"]),
            patch.object(recovery,"SUCCESSOR_ARCHITECTURE_BODY_SHA256",fixture["architecture_sha"]),
            patch.object(recovery,"SUCCESSOR_ARCHITECTURE_REVIEW_BODY_SHA256",fixture["architecture_review_sha"]),
        )
        for item in patches: item.start()
        try:
            self.assertEqual(recovery.verify_successor_github_boundary_document(result,fixture["control"],fixture["activation"]),result)
        finally:
            for item in reversed(patches): item.stop()

    def test_successor_rejects_activation_merge_tree_mismatch(self):
        fixture=successor_boundary_fixture()
        path=f"/repos/{recovery.REPOSITORY}/commits/{fixture['activation']}"
        fixture["fixtures"][path]["commit"]["tree"]["sha"]="b"*40
        with self.assertRaises(RecoveryError):
            run_successor_boundary(fixture)

    def test_successor_rejects_failed_c3_authority_transport_rewrite(self):
        fixture=successor_boundary_fixture()
        path=f"/repos/{recovery.REPOSITORY}/issues/comments/{recovery.FAILED_C3_ACTIVATION_AUTHORITY_ID}"
        fixture["fixtures"][path]["body"]=recovery.canonical_comment_text(fixture["fixtures"][path]["body"])
        with self.assertRaises(RecoveryError): run_successor_boundary(fixture)

    def test_successor_rejects_edited_c4_architecture_evidence(self):
        fixture=successor_boundary_fixture()
        path=f"/repos/{recovery.REPOSITORY}/issues/{recovery.GOVERNING_ISSUE}/comments?per_page=100&page=1"
        row=next(x for x in fixture["fixtures"][path] if x["id"]==recovery.SUCCESSOR_ARCHITECTURE_COMMENT_ID)
        row["updated_at"]="2026-10-03T02:14:30Z"
        with self.assertRaises(RecoveryError):
            run_successor_boundary(fixture)

    def test_successor_rejects_superseded_activation_tree_mismatch(self):
        fixture=successor_boundary_fixture()
        path=f"/repos/{recovery.REPOSITORY}/commits/{recovery.SUPERSEDED_ACTIVATION_MERGE_SHA}"
        fixture["fixtures"][path]["commit"]["tree"]["sha"]="0"*40
        with self.assertRaises(RecoveryError):
            run_successor_boundary(fixture)

    def test_successor_claim_namespace_cannot_reuse_c1_c2_or_failed_c3(self):
        control="4"*40
        for obj in (
            recovery.PREDECESSOR_CLAIM_OBJECT,recovery.PREDECESSOR_RESULT_OBJECT,
            recovery.SUPERSEDED_CLAIM_OBJECT,recovery.SUPERSEDED_RESULT_OBJECT,
            recovery.FAILED_C3_CLAIM_OBJECT,recovery.FAILED_C3_RESULT_OBJECT,
        ):
            self.assertNotEqual(recovery.evidence_object("claim",control),obj)
            self.assertNotEqual(recovery.evidence_object("result",control),obj)
        with self.assertRaises(RecoveryError): recovery.verify_successor_cloud_boundary(recovery.SUPERSEDED_CONTROL_SHA)
        with self.assertRaises(RecoveryError): recovery.verify_successor_cloud_boundary(recovery.FAILED_C3_CONTROL_SHA)


    def test_successor_premerge_accepts_lf_crlf_and_lone_cr_but_binds_raw_hash(self):
        control="7"*40; reviewed="8"*40; pr_number=131; review_id=501; authority_id=502
        review_body=successor_review_body(pr_number,reviewed,control)
        review_sha=recovery.sha256(review_body.encode())
        authority_lf=recovery.successor_activation_merge_authority_body(control,pr_number,reviewed,review_id,review_sha)
        base={
            f"/repos/{recovery.REPOSITORY}/branches/{recovery.DEFAULT_BRANCH}":{"commit":{"sha":control}},
            f"/repos/{recovery.REPOSITORY}/pulls/{pr_number}":{"number":pr_number,"state":"open","merged_at":None,"draft":False,"head":{"sha":reviewed,"repo":{"id":recovery.REPOSITORY_ID,"full_name":recovery.REPOSITORY}},"base":{"ref":"main","sha":control}},
            f"/repos/{recovery.REPOSITORY}/pulls/{pr_number}/reviews/{review_id}":{"id":review_id,"state":"COMMENTED","commit_id":reviewed,"body":review_body,"submitted_at":"2026-10-03T04:00:00Z","user":{"login":"8ft0-ai","id":130460431}},
        }
        observed=[]
        for stored in (authority_lf,authority_lf.replace("\n","\r\n"),authority_lf.replace("\n","\r")):
            fixtures=copy.deepcopy(base)
            fixtures[f"/repos/{recovery.REPOSITORY}/issues/comments/{authority_id}"]=owner_comment(authority_id,stored,"2026-10-03T04:01:00Z",pr_number)
            with patch.object(recovery,"github",side_effect=lambda path: copy.deepcopy(fixtures[path])):
                result=recovery.verify_successor_activation_premerge(control,pr_number,reviewed,review_id,review_sha,authority_id)
            self.assertTrue(result["verified"])
            raw_sha=recovery.sha256(stored.encode())
            self.assertEqual(result["authority_body_sha256"],raw_sha)
            observed.append(raw_sha)
        self.assertEqual(len(set(observed)),3)

    def test_successor_premerge_rejects_content_order_extra_and_edited_authority(self):
        control="7"*40; reviewed="8"*40; pr_number=131; review_id=501; authority_id=502
        review_body=successor_review_body(pr_number,reviewed,control); review_sha=recovery.sha256(review_body.encode())
        authority=recovery.successor_activation_merge_authority_body(control,pr_number,reviewed,review_id,review_sha)
        base={
            f"/repos/{recovery.REPOSITORY}/branches/{recovery.DEFAULT_BRANCH}":{"commit":{"sha":control}},
            f"/repos/{recovery.REPOSITORY}/pulls/{pr_number}":{"number":pr_number,"state":"open","merged_at":None,"draft":False,"head":{"sha":reviewed,"repo":{"id":recovery.REPOSITORY_ID,"full_name":recovery.REPOSITORY}},"base":{"ref":"main","sha":control}},
            f"/repos/{recovery.REPOSITORY}/pulls/{pr_number}/reviews/{review_id}":{"id":review_id,"state":"COMMENTED","commit_id":reviewed,"body":review_body,"submitted_at":"2026-10-03T04:00:00Z","user":{"login":"8ft0-ai","id":130460431}},
        }
        lines=authority.split("\n")
        cases=(
            authority.replace("MERGE_EXACT_REVIEWED_SUCCESSOR_ACTIVATION_ONLY","MERGE_SOMETHING_ELSE"),
            "\n".join([lines[0],lines[2],lines[1],*lines[3:]]),
            authority+"\nUNEXPECTED=VALUE",
            "\n".join(lines[:-1]),
            authority+"\n"+lines[-1],
        )
        for stored in cases:
            fixtures=copy.deepcopy(base)
            fixtures[f"/repos/{recovery.REPOSITORY}/issues/comments/{authority_id}"]=owner_comment(authority_id,stored,"2026-10-03T04:01:00Z",pr_number)
            with patch.object(recovery,"github",side_effect=lambda path: copy.deepcopy(fixtures[path])):
                with self.assertRaises(RecoveryError):
                    recovery.verify_successor_activation_premerge(control,pr_number,reviewed,review_id,review_sha,authority_id)
        fixtures=copy.deepcopy(base)
        edited=owner_comment(authority_id,authority.replace("\n","\r\n"),"2026-10-03T04:01:00Z",pr_number)
        edited["updated_at"]="2026-10-03T04:01:01Z"
        fixtures[f"/repos/{recovery.REPOSITORY}/issues/comments/{authority_id}"]=edited
        with patch.object(recovery,"github",side_effect=lambda path: copy.deepcopy(fixtures[path])):
            with self.assertRaises(RecoveryError):
                recovery.verify_successor_activation_premerge(control,pr_number,reviewed,review_id,review_sha,authority_id)

    def test_successor_review_contract_accepts_crlf_with_exact_raw_review_hash(self):
        control="7"*40; reviewed="8"*40; pr_number=131; review_id=501; authority_id=502
        review_lf=successor_review_body(pr_number,reviewed,control)
        review_crlf=review_lf.replace("\n","\r\n"); review_sha=recovery.sha256(review_crlf.encode())
        authority=recovery.successor_activation_merge_authority_body(control,pr_number,reviewed,review_id,review_sha)
        fixtures={
            f"/repos/{recovery.REPOSITORY}/branches/{recovery.DEFAULT_BRANCH}":{"commit":{"sha":control}},
            f"/repos/{recovery.REPOSITORY}/pulls/{pr_number}":{"number":pr_number,"state":"open","merged_at":None,"draft":False,"head":{"sha":reviewed,"repo":{"id":recovery.REPOSITORY_ID,"full_name":recovery.REPOSITORY}},"base":{"ref":"main","sha":control}},
            f"/repos/{recovery.REPOSITORY}/pulls/{pr_number}/reviews/{review_id}":{"id":review_id,"state":"COMMENTED","commit_id":reviewed,"body":review_crlf,"submitted_at":"2026-10-03T04:00:00Z","user":{"login":"8ft0-ai","id":130460431}},
            f"/repos/{recovery.REPOSITORY}/issues/comments/{authority_id}":owner_comment(authority_id,authority,"2026-10-03T04:01:00Z",pr_number),
        }
        with patch.object(recovery,"github",side_effect=lambda path: copy.deepcopy(fixtures[path])):
            result=recovery.verify_successor_activation_premerge(control,pr_number,reviewed,review_id,review_sha,authority_id)
        self.assertEqual(result["review_body_sha256"],review_sha)

    def test_successor_runtime_binds_raw_authority_hash_after_canonical_grammar(self):
        control="7"*40; activation="9"*40; reviewed="8"*40; pr_number=131; review_id=501; authority_id=502
        review_body=successor_review_body(pr_number,reviewed,control); review_sha=recovery.sha256(review_body.encode())
        authority_lf=recovery.successor_activation_merge_authority_body(control,pr_number,reviewed,review_id,review_sha)
        authority_crlf=authority_lf.replace("\n","\r\n"); authority_sha=recovery.sha256(authority_crlf.encode())
        record={
            "pr_number":pr_number,"reviewed_head":reviewed,"review_id":review_id,
            "review_body_sha256":review_sha,"authority_id":authority_id,
            "authority_body_sha256":authority_sha,"created_at":recovery._timestamp("2026-10-03T04:03:00Z","record"),
        }
        pr={"number":pr_number,"state":"closed","merged_at":"2026-10-03T04:02:00Z","merge_commit_sha":activation,"head":{"sha":reviewed,"repo":{"id":recovery.REPOSITORY_ID,"full_name":recovery.REPOSITORY}},"base":{"ref":"main","sha":control}}
        review={"id":review_id,"state":"COMMENTED","commit_id":reviewed,"body":review_body,"submitted_at":"2026-10-03T04:00:00Z","user":{"login":"8ft0-ai","id":130460431}}
        authority=owner_comment(authority_id,authority_crlf,"2026-10-03T04:01:00Z",pr_number)
        reviewed_commit={"sha":reviewed,"commit":{"tree":{"sha":"a"*40}}}; merge_commit={"sha":activation,"commit":{"tree":{"sha":"a"*40}}}
        recovery.validate_successor_activation_transaction(pr,review,authority,reviewed_commit,merge_commit,record,control,activation)
        authority_lf_comment=owner_comment(authority_id,authority_lf,"2026-10-03T04:01:00Z",pr_number)
        with self.assertRaises(RecoveryError):
            recovery.validate_successor_activation_transaction(pr,review,authority_lf_comment,reviewed_commit,merge_commit,record,control,activation)


    def test_successor_activation_record_accepts_crlf_and_binds_raw_hash(self):
        control="7"*40; activation="9"*40; reviewed="8"*40
        review_sha="a"*64; authority_sha="b"*64
        body_lf=recovery.successor_activation_record_body(control,activation,131,reviewed,501,review_sha,502,authority_sha)
        body_crlf=body_lf.replace("\n","\r\n")
        row=owner_comment(503,body_crlf,"2026-10-03T04:03:00Z")
        result=recovery.validate_successor_activation_record([row],control,activation)
        self.assertEqual(result["body_sha256"],recovery.sha256(body_crlf.encode()))
        self.assertEqual(result["authority_body_sha256"],authority_sha)

    def test_successor_wif_chain_accepts_crlf_but_binds_each_raw_hash(self):
        control="7"*40; activation="9"*40; plan="b"*64; manifest="c"*64
        lineage="bootstrap-lineage"; sb=80; sa=81; review_id=601; authority_id=602; terminal_id=603
        review_lf=recovery.successor_wif_repin_review_body(control,activation,plan,manifest,lineage,sb)
        review_crlf=review_lf.replace("\n","\r\n"); review_sha=recovery.sha256(review_crlf.encode())
        authority_lf=recovery.successor_wif_repin_authority_body(control,activation,plan,manifest,lineage,sb,review_id,review_sha)
        authority_crlf=authority_lf.replace("\n","\r\n"); authority_sha=recovery.sha256(authority_crlf.encode())
        terminal_lf=recovery.successor_wif_repin_terminal_body(control,activation,plan,manifest,lineage,sb,sa,review_id,review_sha,authority_id,authority_sha)
        terminal_crlf=terminal_lf.replace("\n","\r\n")
        comments=[
            owner_comment(review_id,review_crlf,"2026-10-03T04:04:00Z"),
            owner_comment(authority_id,authority_crlf,"2026-10-03T04:05:00Z"),
            owner_comment(terminal_id,terminal_crlf,"2026-10-03T04:06:00Z"),
        ]
        result=recovery.validate_successor_wif_repin_terminal(
            comments,control,activation,recovery._timestamp("2026-10-03T04:03:00Z","activation")
        )
        self.assertEqual(result["review_sha256"],review_sha)
        self.assertEqual(result["authority_sha256"],authority_sha)
        self.assertEqual(result["body_sha256"],recovery.sha256(terminal_crlf.encode()))

    def test_successor_dispatch_accepts_crlf_and_binds_raw_hash(self):
        control="7"*40; activation="9"*40
        activation_record={"comment_id":701,"created_at":recovery._timestamp("2026-10-03T04:03:00Z","a"),"body_sha256":"a"*64}
        repin_terminal={"comment_id":702,"created_at":recovery._timestamp("2026-10-03T04:06:00Z","w"),"body_sha256":"b"*64}
        body_lf=recovery.successor_dispatch_authority_body(control,activation,activation_record,repin_terminal)
        body_crlf=body_lf.replace("\n","\r\n")
        row=owner_comment(703,body_crlf,"2026-10-03T04:07:00Z")
        result=recovery.validate_successor_dispatch_authority([row],control,activation,activation_record,repin_terminal)
        self.assertEqual(result["body_sha256"],recovery.sha256(body_crlf.encode()))

    def test_successor_authority_and_activation_bodies_are_deterministic(self):
        control="7"*40; activation="9"*40; reviewed="8"*40
        review_body=successor_review_body(131,reviewed,control); review_sha=recovery.sha256(review_body.encode())
        authority=recovery.successor_activation_merge_authority_body(control,131,reviewed,501,review_sha)
        authority_sha=recovery.sha256(authority.encode())
        self.assertEqual(authority,recovery.successor_activation_merge_authority_body(control,131,reviewed,501,review_sha))
        record=recovery.successor_activation_record_body(control,activation,131,reviewed,501,review_sha,502,authority_sha)
        self.assertEqual(record,recovery.successor_activation_record_body(control,activation,131,reviewed,501,review_sha,502,authority_sha))
        self.assertIn(f"SUCCESSOR_ARCHITECTURE={recovery.SUCCESSOR_ARCHITECTURE_COMMENT_ID}",authority)

    def test_successor_cloud_boundary_closes_predecessor_claim_state_and_lock(self):
        control="4"*40
        state=successor_state_raw(); state_sha=recovery.sha256(recovery.canonical(state))
        claim={"contract":"resilio-phase5-slice-c-recovery-claim/v1","workflow_run_id":str(recovery.PREDECESSOR_RECOVERY_RUN),"governance_chain_sha256":recovery.PREDECESSOR_GOVERNANCE_CHAIN_SHA256,"control_sha":recovery.PREDECESSOR_CONTROL_SHA,"activation_sha":recovery.PREDECESSOR_ACTIVATION_SHA,"claim_sha256":"z"*64}
        claim["claim_sha256"]=recovery.sha256(recovery.canonical({k:v for k,v in claim.items() if k!="claim_sha256"}))
        claim_body_sha=recovery.sha256(recovery.canonical(claim)+b"\n")
        metadata={
            recovery.PREDECESSOR_CLAIM_OBJECT:{"generation":recovery.PREDECESSOR_CLAIM_GENERATION},
            recovery.PREDECESSOR_RESULT_OBJECT:None,
            recovery.SUPERSEDED_CLAIM_OBJECT:None,
            recovery.SUPERSEDED_RESULT_OBJECT:None,
            recovery.FAILED_C3_CLAIM_OBJECT:None,
            recovery.FAILED_C3_RESULT_OBJECT:None,
            recovery.evidence_object("claim",control):None,
            recovery.evidence_object("result",control):None,
            recovery.STATE_OBJECT:{"generation":recovery.SUCCESSOR_EXPECTED_GENERATION},
            recovery.LOCK_OBJECT:None,
        }
        def meta(name,allow_absent=False):
            value=metadata.get(name)
            if value is None and not allow_absent and name not in metadata: raise AssertionError(name)
            return copy.deepcopy(value)
        def obj(name):
            if name==recovery.PREDECESSOR_CLAIM_OBJECT: return copy.deepcopy(claim)
            if name==recovery.STATE_OBJECT: return copy.deepcopy(state)
            raise AssertionError(name)
        with patch.object(recovery,"PREDECESSOR_CLAIM_SHA256",claim["claim_sha256"]), patch.object(recovery,"PREDECESSOR_CLAIM_BODY_SHA256",claim_body_sha), patch.object(recovery,"SUCCESSOR_EXPECTED_STATE_CANONICAL_SHA256",state_sha), patch.object(recovery,"_successor_gcs_metadata",side_effect=meta), patch.object(recovery,"_successor_gcs_json",side_effect=obj):
            result=recovery.verify_successor_cloud_boundary(control)
            self.assertTrue(result["successor_claim_absent"])
            self.assertTrue(result["superseded_claim_absent"])
            self.assertTrue(result["superseded_result_absent"])
            self.assertTrue(result["failed_c3_claim_absent"])
            self.assertTrue(result["failed_c3_result_absent"])
            self.assertTrue(result["product_lock_absent"])
            metadata[recovery.PREDECESSOR_RESULT_OBJECT]={"generation":"1"}
            with self.assertRaises(RecoveryError): recovery.verify_successor_cloud_boundary(control)
            metadata[recovery.PREDECESSOR_RESULT_OBJECT]=None
            metadata[recovery.SUPERSEDED_CLAIM_OBJECT]={"generation":"1"}
            with self.assertRaises(RecoveryError): recovery.verify_successor_cloud_boundary(control)
            metadata[recovery.SUPERSEDED_CLAIM_OBJECT]=None
            metadata[recovery.FAILED_C3_RESULT_OBJECT]={"generation":"1"}
            with self.assertRaises(RecoveryError): recovery.verify_successor_cloud_boundary(control)


class C5RetainedEffectProtocolTests(unittest.TestCase):
    def _precondition(self):
        control = "d" * 40
        return {
            "successor_control_sha": control,
            "successor_activation_main": "e" * 40,
            "saved_plan_sha256": "a" * 64,
            "structural_manifest_sha256": "b" * 64,
            "state_lineage": recovery.C5_BOOTSTRAP_STATE_LINEAGE,
            "state_serial": recovery.C5_BOOTSTRAP_STATE_SERIAL,
            "fresh_review_comment_id": 701,
            "fresh_review_body_sha256": "c" * 64,
            "owner_apply_authority_comment_id": 702,
            "owner_apply_authority_body_sha256": "d" * 64,
            "old_recovery_control_sha": recovery.C5_OLD_RECOVERY_CONTROL_SHA,
            "new_recovery_control_sha": control,
        }

    def _classify_outcome(self, **changes):
        values = {
            "observation_complete": True,
            "old_wif_count": 0,
            "new_wif_count": 1,
            "forbidden_wif_counts": (0, 0, 0),
            "lineage_before": recovery.C5_BOOTSTRAP_STATE_LINEAGE,
            "lineage_after": recovery.C5_BOOTSTRAP_STATE_LINEAGE,
            "serial_before": 71,
            "serial_after": 72,
            "claim_result_states": ("ABSENT", "ABSENT", "ABSENT", "ABSENT"),
            "bootstrap_lock_absent": True,
            "exact_no_change": True,
            "exact_pending_effect": False,
            "getmetadata_unchanged": True,
            "normal_identities_unchanged": True,
            "observation_1_sha256": None,
            "observation_2_sha256": None,
            "observation_separation_seconds": 0,
        }
        values.update(changes)
        return recovery.c5_classify_wif_repin_outcome(**values)

    def test_c5_use_time_currentness_is_exact_and_stale_facts_fail(self):
        body = recovery.c5_use_time_currentness_body(
            recovery.C5_BASE_MAIN,
            recovery.C5_OLD_RECOVERY_CONTROL_SHA,
            recovery.C5_OLD_RECOVERY_CONTROL_SHA,
            "C4_ONLY",
            recovery.C5_BOOTSTRAP_STATE_LINEAGE,
            recovery.C5_BOOTSTRAP_STATE_SERIAL,
            "ABSENT",
            "ABSENT",
            "ABSENT",
            "EXACT_NO_CHANGE",
            "PRESENT",
            "PRESENT",
            "UNCHANGED",
            "ABSENT",
            0,
        )
        self.assertTrue(body.startswith("PHASE5_SLICE_C_C5_USE_TIME_CURRENTNESS_V1\n"))
        self.assertTrue(body.endswith("CURRENTNESS=PASS"))
        with self.assertRaises(RecoveryError):
            recovery.c5_use_time_currentness_body(
                recovery.C5_BASE_MAIN,
                recovery.C5_OLD_RECOVERY_CONTROL_SHA,
                recovery.C5_OLD_RECOVERY_CONTROL_SHA,
                "C4_ONLY",
                recovery.C5_BOOTSTRAP_STATE_LINEAGE,
                72,
                "ABSENT",
                "ABSENT",
                "ABSENT",
                "EXACT_NO_CHANGE",
                "PRESENT",
                "PRESENT",
                "UNCHANGED",
                "ABSENT",
                0,
            )

    def test_c5_precondition_snapshot_exact_order_no_trailing_lf_and_digest(self):
        kwargs = self._precondition()
        snapshot = recovery.c5_precondition_snapshot(**kwargs)
        self.assertFalse(snapshot.endswith("\n"))
        self.assertEqual(
            snapshot.splitlines()[0],
            "PHASE5_SLICE_C_WIF_REPIN_PRECONDITION_SNAPSHOT_V1",
        )
        self.assertEqual(
            snapshot.splitlines()[-1],
            "OUTPUT_CHANGES=0",
        )
        self.assertEqual(
            recovery.c5_precondition_digest_sha256(**kwargs),
            recovery.sha256(snapshot.encode("utf-8")),
        )
        self.assertIn(
            "PLAN_EFFECTS=EXACT_ONE_RECOVERY_WIF_SUBJECT_REPIN_OLD_TO_NEW",
            snapshot,
        )

    def test_c5_precondition_constructor_rejects_hostile_identity_inputs(self):
        cases = (
            ("successor_control_sha", "a" * 39),
            ("successor_control_sha", "A" * 40),
            ("saved_plan_sha256", "b" * 63),
            ("saved_plan_sha256", "B" * 64),
            ("fresh_review_comment_id", 0),
            ("owner_apply_authority_comment_id", -1),
            ("state_lineage", ""),
            ("state_serial", -1),
        )
        for key, value in cases:
            kwargs = self._precondition()
            kwargs[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RecoveryError):
                recovery.c5_precondition_snapshot(**kwargs)
        kwargs = self._precondition()
        kwargs["new_recovery_control_sha"] = recovery.C5_OLD_RECOVERY_CONTROL_SHA
        kwargs["successor_control_sha"] = recovery.C5_OLD_RECOVERY_CONTROL_SHA
        with self.assertRaises(RecoveryError):
            recovery.c5_precondition_snapshot(**kwargs)
        kwargs = self._precondition()
        kwargs["new_recovery_control_sha"] = recovery.FAILED_C3_CONTROL_SHA
        kwargs["successor_control_sha"] = recovery.FAILED_C3_CONTROL_SHA
        with self.assertRaises(RecoveryError):
            recovery.c5_precondition_snapshot(**kwargs)

    def test_c5_review_and_authority_reject_one_nibble_or_uppercase_hashes(self):
        control = "d" * 40
        review = recovery.c5_wif_repin_review_body(
            control,
            "e" * 40,
            "a" * 64,
            "b" * 64,
            recovery.C5_BOOTSTRAP_STATE_LINEAGE,
            71,
        )
        self.assertIn("REVIEW_DISPOSITION=APPROVED", review)
        with self.assertRaises(RecoveryError):
            recovery.c5_wif_repin_authority_body(
                control,
                "e" * 40,
                "a" * 64,
                "b" * 64,
                recovery.C5_BOOTSTRAP_STATE_LINEAGE,
                71,
                701,
                "c" * 63,
            )
        with self.assertRaises(RecoveryError):
            recovery.c5_wif_repin_authority_body(
                control,
                "e" * 40,
                "a" * 64,
                "b" * 64,
                recovery.C5_BOOTSTRAP_STATE_LINEAGE,
                71,
                701,
                "C" * 64,
            )

    def test_c5_attempt_series_is_exact_deterministic_and_acyclic(self):
        control = "d" * 40
        args = (
            control,
            "e" * 40,
            recovery.C5_OLD_RECOVERY_CONTROL_SHA,
            control,
        )
        body = recovery.c5_attempt_series_body(*args)
        series = recovery.c5_attempt_series_id_sha256(*args)
        self.assertEqual(series, recovery.sha256(body.encode("utf-8")))
        self.assertFalse(body.endswith("\n"))
        self.assertEqual(len(series), 64)
        with self.assertRaises(RecoveryError):
            recovery.c5_attempt_series_body(
                recovery.C5_OLD_RECOVERY_CONTROL_SHA,
                "e" * 40,
                recovery.C5_OLD_RECOVERY_CONTROL_SHA,
                recovery.C5_OLD_RECOVERY_CONTROL_SHA,
            )

    def test_c5_attempt_history_requires_unique_contiguous_generations(self):
        control = "d" * 40
        activation = "e" * 40
        old = recovery.C5_OLD_RECOVERY_CONTROL_SHA
        series = recovery.c5_attempt_series_id_sha256(control, activation, old, control)
        claim1 = recovery.c5_attempt_claim_body(
            control, activation, old, control, 1,
            "a" * 64, "b" * 64, "c" * 64, 701, "d" * 64, 702, "e" * 64,
        )
        claim2 = recovery.c5_attempt_claim_body(
            control, activation, old, control, 2,
            "a" * 64, "b" * 64, "c" * 64, 703, "f" * 64, 704, "1" * 64,
        )
        comments = [
            owner_comment(801, claim1, "2026-10-05T02:30:00Z"),
            owner_comment(802, claim2, "2026-10-05T02:31:00Z"),
        ]
        result = recovery.validate_c5_attempt_history(
            comments, control, activation, old, control
        )
        self.assertEqual(result["attempt_series_id_sha256"], series)
        self.assertEqual(result["next_generation"], 3)

        duplicate = copy.deepcopy(comments)
        duplicate.append(owner_comment(803, claim2, "2026-10-05T02:32:00Z"))
        with self.assertRaises(RecoveryError):
            recovery.validate_c5_attempt_history(
                duplicate, control, activation, old, control
            )

        gap = [comments[1]]
        with self.assertRaises(RecoveryError):
            recovery.validate_c5_attempt_history(
                gap, control, activation, old, control
            )

        edited = copy.deepcopy(comments)
        edited[0]["updated_at"] = "2026-10-05T02:30:01Z"
        with self.assertRaises(RecoveryError):
            recovery.validate_c5_attempt_history(
                edited, control, activation, old, control
            )

    def test_c5_posted_claim_revalidation_binds_raw_body_and_chronology(self):
        control = "d" * 40
        activation = "e" * 40
        body = recovery.c5_attempt_claim_body(
            control,
            activation,
            recovery.C5_OLD_RECOVERY_CONTROL_SHA,
            control,
            1,
            "a" * 64,
            "b" * 64,
            "c" * 64,
            701,
            "d" * 64,
            702,
            "e" * 64,
        )
        row = owner_comment(801, body, "2026-10-05T02:31:00Z")
        authority_time = recovery._timestamp(
            "2026-10-05T02:30:00Z", "authority"
        )
        result = recovery.validate_c5_posted_attempt_claim(
            row, authority_time, body
        )
        self.assertEqual(result["generation"], 1)
        with self.assertRaises(RecoveryError):
            recovery.validate_c5_posted_attempt_claim(
                row,
                recovery._timestamp("2026-10-05T02:32:00Z", "authority"),
                body,
            )

    def test_c5_outcome_algebra_effect_success(self):
        self.assertEqual(self._classify_outcome(), "EFFECT_SUCCEEDED")

    def test_c5_outcome_algebra_no_effect_requires_two_observations_60_seconds(self):
        common = {
            "old_wif_count": 1,
            "new_wif_count": 0,
            "serial_after": 71,
            "exact_no_change": False,
            "exact_pending_effect": True,
            "observation_1_sha256": "a" * 64,
            "observation_2_sha256": "b" * 64,
        }
        self.assertEqual(
            self._classify_outcome(**common, observation_separation_seconds=60),
            "NO_EFFECT_STABLE",
        )
        self.assertEqual(
            self._classify_outcome(**common, observation_separation_seconds=59),
            "INCONSISTENT_EFFECT",
        )

    def test_c5_outcome_algebra_unknown_is_nonterminal_and_presence_is_inconsistent(self):
        self.assertEqual(
            self._classify_outcome(observation_complete=False),
            "PROCESS_OUTCOME_UNKNOWN",
        )
        self.assertEqual(
            self._classify_outcome(
                claim_result_states=("ABSENT", "PRESENT", "ABSENT", "ABSENT")
            ),
            "INCONSISTENT_EFFECT",
        )

    def _effect_terminal_body(self):
        control = "d" * 40
        activation = "e" * 40
        series = recovery.c5_attempt_series_id_sha256(
            control,
            activation,
            recovery.C5_OLD_RECOVERY_CONTROL_SHA,
            control,
        )
        body = recovery.c5_wif_repin_terminal_body(
            successor_control_sha=control,
            successor_activation_main=activation,
            saved_plan_sha256="a" * 64,
            structural_manifest_sha256="b" * 64,
            fresh_review_comment_id=701,
            fresh_review_body_sha256="c" * 64,
            owner_apply_authority_comment_id=702,
            owner_apply_authority_body_sha256="d" * 64,
            attempt_claim_comment_id=703,
            attempt_claim_body_sha256="e" * 64,
            attempt_series_id_sha256=series,
            attempt_generation=1,
            precondition_digest_sha256="f" * 64,
            lineage_before=recovery.C5_BOOTSTRAP_STATE_LINEAGE,
            lineage_after=recovery.C5_BOOTSTRAP_STATE_LINEAGE,
            serial_before=71,
            serial_after=72,
            old_wif_count=0,
            new_wif_count=1,
            forbidden_wif_counts=(0, 0, 0),
            claim_result_states=("ABSENT", "ABSENT", "ABSENT", "ABSENT"),
            bootstrap_lock_absent=True,
            exact_no_change=True,
            exact_pending_effect=False,
            getmetadata_unchanged=True,
            normal_identities_unchanged=True,
            observation_complete=True,
        )
        return control, activation, body

    def test_c5_terminal_binds_total_effect_evidence_and_enables_only_effect_dispatch(self):
        control, activation, body = self._effect_terminal_body()
        self.assertIn("OUTCOME=EFFECT_SUCCEEDED", body)
        terminal = recovery.c5_terminal_record_summary(
            901, body, "EFFECT_SUCCEEDED"
        )
        authority = recovery.c5_dispatch_authority_body(
            control, activation, terminal
        )
        self.assertIn(
            "AUTHORITY=DISPATCH_EXACTLY_ONE_C5_RECONCILIATION_ONLY_RECOVERY",
            authority,
        )

        no_effect = dict(terminal)
        no_effect["outcome"] = "NO_EFFECT_STABLE"
        with self.assertRaises(RecoveryError):
            recovery.c5_dispatch_authority_body(control, activation, no_effect)

        with self.assertRaises(RecoveryError):
            recovery.c5_dispatch_authority_body(
                recovery.C5_OLD_RECOVERY_CONTROL_SHA, activation, terminal
            )

    def test_c5_process_unknown_cannot_be_emitted_as_terminal(self):
        control = "d" * 40
        activation = "e" * 40
        series = recovery.c5_attempt_series_id_sha256(
            control,
            activation,
            recovery.C5_OLD_RECOVERY_CONTROL_SHA,
            control,
        )
        with self.assertRaises(RecoveryError):
            recovery.c5_wif_repin_terminal_body(
                successor_control_sha=control,
                successor_activation_main=activation,
                saved_plan_sha256="a" * 64,
                structural_manifest_sha256="b" * 64,
                fresh_review_comment_id=701,
                fresh_review_body_sha256="c" * 64,
                owner_apply_authority_comment_id=702,
                owner_apply_authority_body_sha256="d" * 64,
                attempt_claim_comment_id=703,
                attempt_claim_body_sha256="e" * 64,
                attempt_series_id_sha256=series,
                attempt_generation=1,
                precondition_digest_sha256="f" * 64,
                lineage_before=recovery.C5_BOOTSTRAP_STATE_LINEAGE,
                lineage_after=recovery.C5_BOOTSTRAP_STATE_LINEAGE,
                serial_before=71,
                serial_after=71,
                old_wif_count=1,
                new_wif_count=0,
                forbidden_wif_counts=(0, 0, 0),
                claim_result_states=("ABSENT", "ABSENT", "ABSENT", "UNKNOWN"),
                bootstrap_lock_absent=True,
                exact_no_change=False,
                exact_pending_effect=True,
                getmetadata_unchanged=True,
                normal_identities_unchanged=True,
                observation_complete=False,
            )

    def test_c5_governance_history_closes_architecture_review_disposition_baseline(self):
        arch_body = "\n".join(
            (
                "PHASE5_SLICE_C_C5_EFFECT_SUCCEEDED_INVALID_AUTHORITY_RECOVERY_ARCHITECTURE_V4",
                "STATUS=C5_ARCHITECTURE_REVISION_4_COMPLETE_PENDING_FRESH_REVIEW",
                f"CURRENT_MAIN={recovery.C5_BASE_MAIN}",
                "CURRENT_REPOSITORY_CALLER=C4",
                "CURRENT_REPOSITORY_DESIRED_WIF=C4",
                "CURRENT_LIVE_RECOVERY_WIF=C4_ONLY",
                f"CURRENT_BOOTSTRAP_STATE_LINEAGE={recovery.C5_BOOTSTRAP_STATE_LINEAGE}",
                f"CURRENT_BOOTSTRAP_STATE_SERIAL={recovery.C5_BOOTSTRAP_STATE_SERIAL}",
                "C4_DISPATCH=PERMANENTLY_FORBIDDEN",
                "C5_IMPLEMENTATION=NOT_AUTHORISED",
            )
        )
        review_body = "\n".join(
            (
                "COMPLETELY_FRESH_SUBSTANTIVE_C5_ARCHITECTURE_SECURITY_AUTHORITY_REVIEW_V4",
                f"REVIEW_TARGET={recovery.C5_ARCHITECTURE_COMMENT_ID}",
                "DISPOSITION=APPROVED",
                "MATERIAL_BLOCKERS=NONE",
                "INCIDENT_TRUTH_AND_NON_RETROACTIVITY=PASS",
                "OWNER_DISPOSITION_AUTHORITY_CLOSURE=PASS",
                "USE_TIME_CURRENTNESS=PASS",
                "RETAINED_EFFECT_BASELINE=PASS",
                "TERMINAL_AND_DISPATCH_GATING=PASS",
                "RETAIN_POSITIVE_REACHABILITY=PASS",
                "REVERT_REACHABILITY=PASS",
            )
        )
        disposition_body = "\n".join(
            (
                "PHASE5_SLICE_C_C4_WIF_INCIDENT_DISPOSITION_V1",
                "GOVERNING_ISSUE=8ft0-ai/resilio#109",
                f"C5_ARCHITECTURE_COMMENT_ID={recovery.C5_ARCHITECTURE_COMMENT_ID}",
                f"C5_ARCHITECTURE_BODY_SHA256={recovery.C5_ARCHITECTURE_BODY_SHA256}",
                f"C5_ARCHITECTURE_REVIEW_COMMENT_ID={recovery.C5_ARCHITECTURE_REVIEW_COMMENT_ID}",
                f"C5_ARCHITECTURE_REVIEW_BODY_SHA256={recovery.C5_ARCHITECTURE_REVIEW_BODY_SHA256}",
                f"INCIDENT_ID={recovery.C5_C4_INCIDENT_ID}",
                f"INCIDENT_BODY_SHA256={recovery.C5_C4_INCIDENT_BODY_SHA256}",
                f"MALFORMED_AUTHORITY_ID={recovery.C5_C4_MALFORMED_AUTHORITY_ID}",
                f"MALFORMED_AUTHORITY_BODY_SHA256={recovery.C5_C4_MALFORMED_AUTHORITY_BODY_SHA256}",
                f"INVALID_TERMINAL_ID={recovery.C5_C4_INVALID_TERMINAL_ID}",
                f"INVALID_TERMINAL_BODY_SHA256={recovery.C5_C4_INVALID_TERMINAL_BODY_SHA256}",
                f"SAVED_PLAN_SHA256={recovery.C5_C4_SAVED_PLAN_SHA256}",
                f"STRUCTURAL_MANIFEST_SHA256={recovery.C5_C4_STRUCTURAL_MANIFEST_SHA256}",
                f"CURRENT_MAIN={recovery.C5_BASE_MAIN}",
                f"BOOTSTRAP_STATE_LINEAGE={recovery.C5_BOOTSTRAP_STATE_LINEAGE}",
                f"BOOTSTRAP_STATE_SERIAL={recovery.C5_BOOTSTRAP_STATE_SERIAL}",
                "LIVE_RECOVERY_WIF=C4_ONLY",
                "POST_APPLY_RECONCILIATION=EXACT_NO_CHANGE",
                "NON_RETROACTIVE_ACK=TRUE",
                "DISPOSITION=RETAIN_EXACT_EFFECT",
                "AUTHORITY_SCOPE=C5_INERT_CONTROL_IMPLEMENTATION_ONLY",
            )
        )
        baseline_body = "\n".join(
            (
                "RETAINED_C4_EFFECT_BASELINE_V1",
                "STATUS=C5_RETAINED_EFFECT_BASELINE_ESTABLISHED",
                "GOVERNING_ISSUE=8ft0-ai/resilio#109",
                f"OWNER_DISPOSITION_COMMENT_ID={recovery.C5_OWNER_DISPOSITION_COMMENT_ID}",
                f"OWNER_DISPOSITION_BODY_SHA256={recovery.C5_OWNER_DISPOSITION_BODY_SHA256}",
                "DISPOSITION=RETAIN_EXACT_EFFECT",
                "AUTHORITY_SCOPE=C5_INERT_CONTROL_IMPLEMENTATION_ONLY",
                f"C5_ARCHITECTURE_COMMENT_ID={recovery.C5_ARCHITECTURE_COMMENT_ID}",
                f"C5_ARCHITECTURE_BODY_SHA256={recovery.C5_ARCHITECTURE_BODY_SHA256}",
                f"C5_ARCHITECTURE_REVIEW_COMMENT_ID={recovery.C5_ARCHITECTURE_REVIEW_COMMENT_ID}",
                f"C5_ARCHITECTURE_REVIEW_BODY_SHA256={recovery.C5_ARCHITECTURE_REVIEW_BODY_SHA256}",
                f"INCIDENT_ID={recovery.C5_C4_INCIDENT_ID}",
                f"MALFORMED_C4_AUTHORITY_ID={recovery.C5_C4_MALFORMED_AUTHORITY_ID}",
                f"INVALID_C4_TERMINAL_ID={recovery.C5_C4_INVALID_TERMINAL_ID}",
                f"CURRENT_MAIN={recovery.C5_BASE_MAIN}",
                "REPOSITORY_CALLER=C4",
                "REPOSITORY_DESIRED_WIF=C4",
                "LIVE_RECOVERY_WIF=C4_ONLY",
                f"BOOTSTRAP_STATE_LINEAGE={recovery.C5_BOOTSTRAP_STATE_LINEAGE}",
                f"BOOTSTRAP_STATE_SERIAL={recovery.C5_BOOTSTRAP_STATE_SERIAL}",
                "BOOTSTRAP_STATE_RESOURCE_COUNT=138",
                "C2_RECOVERY_CLAIM_RESULT=ABSENT",
                "C3_RECOVERY_CLAIM_RESULT=ABSENT",
                "C4_RECOVERY_CLAIM_RESULT=ABSENT",
                "BOOTSTRAP_LOCK=ABSENT",
                "ACTIVE_GITHUB_ACTIONS_RUNS=0",
                "PHASE5_WIF_STATE_RESOURCES=8",
                "ALL_PHASE5_WIF_LIVE_MATCHES=PASS",
                "GETMETADATA_PLAN_ROLE=PRESENT",
                "GETMETADATA_APPLY_ROLE=PRESENT",
                "BOOTSTRAP_RECONCILIATION=EXACT_NO_CHANGE",
                "TERRAFORM_PLAN_EXIT=0",
                "NON_RETROACTIVE_ACK=TRUE",
                "C4_DISPATCH=PERMANENTLY_FORBIDDEN",
                "CLOUD_MUTATION=NOT_AUTHORISED",
                "NEXT_AUTHORISED_SCOPE=C5_INERT_CONTROL_IMPLEMENTATION_ONLY",
            )
        )
        comments = [
            owner_comment(
                recovery.C5_ARCHITECTURE_COMMENT_ID,
                arch_body,
                "2026-10-04T04:16:28Z",
            ),
            owner_comment(
                recovery.C5_ARCHITECTURE_REVIEW_COMMENT_ID,
                review_body,
                "2026-10-04T04:17:21Z",
            ),
            owner_comment(
                recovery.C5_OWNER_DISPOSITION_COMMENT_ID,
                disposition_body,
                "2026-10-05T00:10:02Z",
            ),
            owner_comment(
                recovery.C5_RETAINED_BASELINE_COMMENT_ID,
                baseline_body,
                "2026-10-05T02:25:00Z",
            ),
        ]
        self.assertEqual(
            recovery.sha256(disposition_body.encode()),
            recovery.C5_OWNER_DISPOSITION_BODY_SHA256,
        )
        self.assertEqual(
            recovery.sha256(baseline_body.encode()),
            recovery.C5_RETAINED_BASELINE_BODY_SHA256,
        )
        original_fixed = recovery._successor_fixed_comment

        def synthetic_fixed(rows, comment_id, body_sha256, label):
            if label in {"C5_ARCHITECTURE", "C5_ARCHITECTURE_REVIEW"}:
                row = next(item for item in rows if item["id"] == comment_id)
                created, observed = recovery._require_unedited_owner_comment(
                    row, recovery.GOVERNING_ISSUE, label
                )
                return {
                    "comment_id": comment_id,
                    "created_at": created,
                    "body_sha256": observed,
                    "body": row["body"],
                }
            return original_fixed(rows, comment_id, body_sha256, label)

        with patch.object(
            recovery, "_successor_fixed_comment", side_effect=synthetic_fixed
        ):
            result = recovery.validate_c5_governance_history(comments)
        self.assertEqual(
            result["retained_baseline"]["comment_id"],
            recovery.C5_RETAINED_BASELINE_COMMENT_ID,
        )


    def _c5_wif_plan(self, old_control=None, new_control=None):
        old_control = old_control or recovery.C5_OLD_RECOVERY_CONTROL_SHA
        new_control = new_control or ("d" * 40)
        prefix = (
            "principalSet://iam.googleapis.com/projects/400271474382/"
            "locations/global/workloadIdentityPools/github/"
            "attribute.job_workflow_ref/8ft0-ai/resilio/"
            ".github/workflows/phase5-slice-c-recovery-reusable.yml@"
        )
        before = {
            "id": "old-id",
            "member": prefix + old_control,
            "role": "roles/iam.workloadIdentityUser",
            "service_account_id": (
                "projects/resilio-control-e882d4/serviceAccounts/"
                "github-p5-product-planner@resilio-control-e882d4."
                "iam.gserviceaccount.com"
            ),
        }
        after = dict(before)
        after["id"] = None
        after["member"] = prefix + new_control
        return {
            "format_version": "1.2",
            "terraform_version": "1.15.8",
            "applyable": True,
            "complete": True,
            "errored": False,
            "resource_changes": [
                {
                    "address": (
                        "google_service_account_iam_member."
                        "github_phase5_slice_c_recovery"
                    ),
                    "mode": "managed",
                    "type": "google_service_account_iam_member",
                    "name": "github_phase5_slice_c_recovery",
                    "change": {
                        "actions": ["delete", "create"],
                        "before": before,
                        "after": after,
                    },
                }
            ],
            "resource_drift": [],
            "deferred_changes": [],
            "deferred_action_invocations": [],
            "action_invocations": [],
            "output_changes": {},
        }

    def _c5_structural_manifest(self, new_control=None):
        new_control = new_control or ("d" * 40)
        prefix = (
            "principalSet://iam.googleapis.com/projects/400271474382/"
            "locations/global/workloadIdentityPools/github/"
            "attribute.job_workflow_ref/8ft0-ai/resilio/"
            ".github/workflows/phase5-slice-c-recovery-reusable.yml@"
        )
        service_account = (
            "projects/resilio-control-e882d4/serviceAccounts/"
            "github-p5-product-planner@resilio-control-e882d4.iam.gserviceaccount.com"
        )
        return {
            "applyable": True,
            "complete": True,
            "errored": False,
            "output_change_count": 0,
            "plan_format_version": "1.2",
            "resource_change_count": 1,
            "resource_effects": [
                {
                    "action_reason": "replace_because_cannot_update",
                    "actions": ["delete", "create"],
                    "address": (
                        "google_service_account_iam_member."
                        "github_phase5_slice_c_recovery"
                    ),
                    "after_member": prefix + new_control,
                    "after_role": "roles/iam.workloadIdentityUser",
                    "after_service_account_id": service_account,
                    "before_member": (
                        prefix + recovery.C5_OLD_RECOVERY_CONTROL_SHA
                    ),
                    "before_role": "roles/iam.workloadIdentityUser",
                    "before_service_account_id": service_account,
                    "mode": "managed",
                    "name": "github_phase5_slice_c_recovery",
                    "type": "google_service_account_iam_member",
                }
            ],
            "schema": "resilio-bootstrap-wif-repin-structural-manifest/v1",
            "terraform_version": "1.15.8",
        }

    def _c5_bootstrap_state(self):
        prefix = (
            "principalSet://iam.googleapis.com/projects/400271474382/"
            "locations/global/workloadIdentityPools/github/"
            "attribute.job_workflow_ref/8ft0-ai/resilio/.github/workflows/"
        )
        resources = [
            {
                "mode": "managed",
                "type": "null_resource",
                "name": f"baseline_{index}",
                "instances": [{"attributes": {}}],
            }
            for index in range(
                recovery.C5_EXPECTED_BOOTSTRAP_RESOURCE_COUNT
                - len(recovery.C5_EXPECTED_PHASE5_WIF_ROWS)
            )
        ]
        for name, (email, workflow, sha) in (
            recovery.C5_EXPECTED_PHASE5_WIF_ROWS.items()
        ):
            resources.append(
                {
                    "mode": "managed",
                    "type": "google_service_account_iam_member",
                    "name": name,
                    "instances": [
                        {
                            "attributes": {
                                "service_account_id": (
                                    "projects/resilio-control-e882d4/"
                                    "serviceAccounts/" + email
                                ),
                                "role": "roles/iam.workloadIdentityUser",
                                "member": prefix + workflow + "@" + sha,
                            }
                        }
                    ],
                }
            )
        return {
            "lineage": recovery.C5_BOOTSTRAP_STATE_LINEAGE,
            "serial": recovery.C5_BOOTSTRAP_STATE_SERIAL,
            "resources": resources,
        }

    def test_c5_wif_plan_requires_exact_one_old_to_new_replacement(self):
        control = "d" * 40
        plan = self._c5_wif_plan(new_control=control)
        result = recovery.c5_verify_wif_repin_plan(
            plan, recovery.C5_OLD_RECOVERY_CONTROL_SHA, control
        )
        self.assertEqual(
            result["plan_effects"],
            "EXACT_ONE_RECOVERY_WIF_SUBJECT_REPIN_OLD_TO_NEW",
        )
        hostile = copy.deepcopy(plan)
        hostile["output_changes"] = {"x": {"actions": ["update"]}}
        with self.assertRaises(RecoveryError):
            recovery.c5_verify_wif_repin_plan(
                hostile, recovery.C5_OLD_RECOVERY_CONTROL_SHA, control
            )
        hostile = copy.deepcopy(plan)
        hostile["resource_changes"].append(copy.deepcopy(plan["resource_changes"][0]))
        with self.assertRaises(RecoveryError):
            recovery.c5_verify_wif_repin_plan(
                hostile, recovery.C5_OLD_RECOVERY_CONTROL_SHA, control
            )
        hostile = copy.deepcopy(plan)
        hostile["resource_changes"][0]["change"]["after"]["role"] = "roles/editor"
        with self.assertRaises(RecoveryError):
            recovery.c5_verify_wif_repin_plan(
                hostile, recovery.C5_OLD_RECOVERY_CONTROL_SHA, control
            )
        hostile = copy.deepcopy(plan)
        hostile["applyable"] = False
        with self.assertRaises(RecoveryError):
            recovery.c5_verify_wif_repin_plan(
                hostile, recovery.C5_OLD_RECOVERY_CONTROL_SHA, control
            )

    def test_c5_structural_manifest_exactly_matches_old_to_new_effect(self):
        control = "d" * 40
        manifest = self._c5_structural_manifest(control)
        result = recovery.c5_verify_structural_manifest(
            manifest, recovery.C5_OLD_RECOVERY_CONTROL_SHA, control
        )
        self.assertEqual(result["resource_change_count"], 1)
        hostile = copy.deepcopy(manifest)
        hostile["resource_effects"][0]["after_role"] = "roles/editor"
        with self.assertRaises(RecoveryError):
            recovery.c5_verify_structural_manifest(
                hostile, recovery.C5_OLD_RECOVERY_CONTROL_SHA, control
            )
        hostile = copy.deepcopy(manifest)
        hostile["unexpected"] = True
        with self.assertRaises(RecoveryError):
            recovery.c5_verify_structural_manifest(
                hostile, recovery.C5_OLD_RECOVERY_CONTROL_SHA, control
            )

    def test_c5_bootstrap_live_iam_requires_all_eight_and_c4_only(self):
        state = self._c5_bootstrap_state()
        policies = {}
        for resource in state["resources"]:
            if resource.get("type") != "google_service_account_iam_member":
                continue
            attrs = resource["instances"][0]["attributes"]
            email = attrs["service_account_id"].split("/serviceAccounts/", 1)[1]
            policy = policies.setdefault(email, {"bindings": []})
            binding = next(
                (
                    item
                    for item in policy["bindings"]
                    if item["role"] == attrs["role"]
                ),
                None,
            )
            if binding is None:
                binding = {"role": attrs["role"], "members": []}
                policy["bindings"].append(binding)
            binding["members"].append(attrs["member"])

        with (
            patch.object(
                recovery,
                "_c5_iam_policy",
                side_effect=lambda email: copy.deepcopy(policies[email]),
            ),
            patch.object(
                recovery,
                "_c5_role",
                side_effect=lambda role_id: {
                    "includedPermissions": list(
                        recovery.C5_EXPECTED_ROLE_PERMISSIONS[role_id]
                    )
                },
            ),
        ):
            result = recovery.verify_c5_bootstrap_state_and_live_iam(
                state, "d" * 40
            )
        self.assertEqual(result["phase5_wif_state_resources"], 8)
        self.assertEqual(result["live_recovery_wif"], "OLD_ONLY")

        bad = copy.deepcopy(policies)
        recovery_member = next(
            resource["instances"][0]["attributes"]
            for resource in state["resources"]
            if resource["name"] == "github_phase5_slice_c_recovery"
        )
        email = recovery_member["service_account_id"].split(
            "/serviceAccounts/", 1
        )[1]
        bad[email]["bindings"][0]["members"].append(
            recovery_member["member"].rsplit("@", 1)[0] + "@" + ("d" * 40)
        )
        with (
            patch.object(
                recovery,
                "_c5_iam_policy",
                side_effect=lambda value: copy.deepcopy(bad[value]),
            ),
            patch.object(
                recovery,
                "_c5_role",
                side_effect=lambda role_id: {
                    "includedPermissions": list(
                        recovery.C5_EXPECTED_ROLE_PERMISSIONS[role_id]
                    )
                },
            ),
            self.assertRaises(RecoveryError),
        ):
            recovery.verify_c5_bootstrap_state_and_live_iam(state, "d" * 40)

    def test_c5_repository_activation_requires_exact_caller_and_desired_pin(self):
        control = "d" * 40
        activation = "e" * 40
        values = {
            ".github/workflows/phase5-slice-c-recovery.yml": (
                "uses: 8ft0-ai/resilio/.github/workflows/"
                "phase5-slice-c-recovery-reusable.yml@" + control
            ),
            "infra/bootstrap/phase5_authority.tf": (
                'phase5_slice_c_recovery_workflow_ref = '
                '"8ft0-ai/resilio/.github/workflows/'
                "phase5-slice-c-recovery-reusable.yml@" + control + '"'
            ),
        }
        with patch.object(
            recovery,
            "_c5_fetch_repo_text",
            side_effect=lambda path, ref: values[path],
        ):
            result = recovery.verify_c5_repository_activation(
                activation, control
            )
        self.assertEqual(result["repository_caller"], "NEW_CONTROL")

        hostile = dict(values)
        hostile[".github/workflows/phase5-slice-c-recovery.yml"] = hostile[
            ".github/workflows/phase5-slice-c-recovery.yml"
        ].replace(control, recovery.C5_OLD_RECOVERY_CONTROL_SHA)
        with (
            patch.object(
                recovery,
                "_c5_fetch_repo_text",
                side_effect=lambda path, ref: hostile[path],
            ),
            self.assertRaises(RecoveryError),
        ):
            recovery.verify_c5_repository_activation(activation, control)

    def test_c5_activation_file_transform_is_exact_two_file_sha_repin(self):
        control = "d" * 40
        reviewed = "e" * 40
        base_values = {
            ".github/workflows/phase5-slice-c-recovery.yml": (
                "jobs:\n  recover:\n    uses: repo/reusable.yml@"
                + recovery.C5_OLD_RECOVERY_CONTROL_SHA
                + "\n"
            ),
            "infra/bootstrap/phase5_authority.tf": (
                'x = "workflow@'
                + recovery.C5_OLD_RECOVERY_CONTROL_SHA
                + '"\n'
            ),
        }

        def fetch(path, ref):
            value = base_values[path]
            if ref == reviewed:
                return value.replace(
                    recovery.C5_OLD_RECOVERY_CONTROL_SHA, control
                )
            return value

        with patch.object(
            recovery, "_c5_fetch_repo_text", side_effect=fetch
        ):
            recovery._c5_verify_activation_file_transform(control, reviewed)

        def hostile(path, ref):
            value = fetch(path, ref)
            if ref == reviewed and path.endswith("phase5_authority.tf"):
                return value + "unrelated = true\n"
            return value

        with (
            patch.object(
                recovery, "_c5_fetch_repo_text", side_effect=hostile
            ),
            self.assertRaises(RecoveryError),
        ):
            recovery._c5_verify_activation_file_transform(control, reviewed)

    def test_c5_control_and_activation_authority_constructors_are_strict(self):
        head = "d" * 40
        review = recovery.c5_control_implementation_review_body(140, head)
        review_sha = recovery.sha256(review.encode())
        authority = recovery.c5_control_merge_authority_body(
            140, head, 901, review_sha
        )
        self.assertIn(
            "AUTHORITY=MERGE_EXACT_REVIEWED_C5_INERT_CONTROL_ONLY",
            authority,
        )
        with self.assertRaises(RecoveryError):
            recovery.c5_control_merge_authority_body(
                140, head, 901, review_sha[:-1]
            )

        control = "e" * 40
        activation_review = recovery.c5_activation_review_body(
            control, 141, "f" * 40
        )
        activation_review_sha = recovery.sha256(activation_review.encode())
        activation_authority = recovery.c5_activation_merge_authority_body(
            control, 141, "f" * 40, 902, activation_review_sha
        )
        self.assertIn(
            "AUTHORITY=MERGE_EXACT_REVIEWED_C5_REPOSITORY_ACTIVATION_ONLY",
            activation_authority,
        )
        with self.assertRaises(RecoveryError):
            recovery.c5_activation_review_body(
                recovery.C5_OLD_RECOVERY_CONTROL_SHA, 141, "f" * 40
            )

    def test_c5_pre_effect_verifier_has_distinct_claim_ready_and_effect_ready(self):
        control = "d" * 40
        activation = "e" * 40
        plan = self._c5_wif_plan(new_control=control)
        state_live = {
            "state_lineage": recovery.C5_BOOTSTRAP_STATE_LINEAGE,
            "state_serial": recovery.C5_BOOTSTRAP_STATE_SERIAL,
            "phase5_wif_state_resources": 8,
            "all_phase5_wif_live_matches": True,
            "live_recovery_wif": "OLD_ONLY",
            "getmetadata_unchanged": True,
            "normal_phase5_identities_unchanged": True,
        }
        review_hash = "a" * 64
        authority_hash = "b" * 64
        authority_time = recovery._timestamp(
            "2026-10-05T03:00:00Z", "authority"
        )
        governance = {
            "architecture": {"comment_id": recovery.C5_ARCHITECTURE_COMMENT_ID},
            "architecture_review": {
                "comment_id": recovery.C5_ARCHITECTURE_REVIEW_COMMENT_ID
            },
            "disposition": {
                "comment_id": recovery.C5_OWNER_DISPOSITION_COMMENT_ID
            },
            "retained_baseline": {
                "comment_id": recovery.C5_RETAINED_BASELINE_COMMENT_ID
            },
        }
        activation_record = {
            "comment_id": 950,
            "body_sha256": "c" * 64,
            "control_record_comment_id": 949,
            "control_record_body_sha256": "d" * 64,
        }
        comments = []

        def fake_github(path):
            if path == f"/repos/{recovery.REPOSITORY}/branches/{recovery.DEFAULT_BRANCH}":
                return {"commit": {"sha": activation}}
            if path.startswith(
                f"/repos/{recovery.REPOSITORY}/actions/runs?"
            ):
                return {"total_count": 0}
            raise AssertionError(path)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved = root / "plan.tfplan"
            manifest = root / "manifest.json"
            saved.write_bytes(b"frozen-plan")
            manifest.write_bytes(
                recovery.canonical(self._c5_structural_manifest(control))
            )

            def common_patches():
                return (
                    patch.object(recovery, "github", side_effect=fake_github),
                    patch.object(
                        recovery,
                        "github_issue_comments",
                        side_effect=lambda issue: copy.deepcopy(comments),
                    ),
                    patch.object(
                        recovery,
                        "verify_c5_repository_activation",
                        return_value={"verified": True},
                    ),
                    patch.object(
                        recovery,
                        "_c5_saved_plan_json",
                        return_value=copy.deepcopy(plan),
                    ),
                    patch.object(
                        recovery,
                        "validate_c5_governance_history",
                        return_value=governance,
                    ),
                    patch.object(
                        recovery,
                        "validate_c5_activation_record",
                        return_value=activation_record,
                    ),
                    patch.object(
                        recovery, "_successor_gcs_json", return_value={}
                    ),
                    patch.object(
                        recovery,
                        "verify_c5_bootstrap_state_and_live_iam",
                        return_value=state_live,
                    ),
                    patch.object(
                        recovery,
                        "_successor_gcs_metadata",
                        return_value=None,
                    ),
                    patch.object(
                        recovery,
                        "_c5_validate_plan_review_and_authority",
                        return_value={
                            "review_comment_id": 901,
                            "review_body_sha256": review_hash,
                            "review_created_at": recovery._timestamp(
                                "2026-10-05T02:59:00Z", "review"
                            ),
                            "authority_comment_id": 902,
                            "authority_body_sha256": authority_hash,
                            "authority_created_at": authority_time,
                        },
                    ),
                )

            patches = common_patches()
            for item in patches:
                item.start()
            try:
                first = recovery.verify_c5_wif_repin_pre_effect(
                    successor_control_sha=control,
                    activation_main=activation,
                    saved_plan_path=saved,
                    terraform_workdir=root,
                    structural_manifest_path=manifest,
                    fresh_review_comment_id=901,
                    owner_apply_authority_comment_id=902,
                )
            finally:
                for item in reversed(patches):
                    item.stop()

            self.assertEqual(first["phase"], "CLAIM_READY")
            self.assertFalse(first["ready_for_effect"])
            self.assertEqual(first["attempt_generation"], 1)

            comments.append(
                owner_comment(
                    903,
                    first["attempt_claim_body"],
                    "2026-10-05T03:01:00Z",
                )
            )
            patches = common_patches()
            for item in patches:
                item.start()
            try:
                second = recovery.verify_c5_wif_repin_pre_effect(
                    successor_control_sha=control,
                    activation_main=activation,
                    saved_plan_path=saved,
                    terraform_workdir=root,
                    structural_manifest_path=manifest,
                    fresh_review_comment_id=901,
                    owner_apply_authority_comment_id=902,
                    posted_claim_comment_id=903,
                )
            finally:
                for item in reversed(patches):
                    item.stop()
            self.assertEqual(second["phase"], "EFFECT_READY")
            self.assertTrue(second["ready_for_effect"])
            self.assertEqual(second["attempt_generation"], 1)

            stale = copy.deepcopy(comments)
            stale[0]["body"] = stale[0]["body"].replace(
                "PRECONDITION_DIGEST_SHA256=",
                "PRECONDITION_DIGEST_SHA256=0",
                1,
            )
            comments[:] = stale
            patches = common_patches()
            for item in patches:
                item.start()
            try:
                with self.assertRaises(RecoveryError):
                    recovery.verify_c5_wif_repin_pre_effect(
                        successor_control_sha=control,
                        activation_main=activation,
                        saved_plan_path=saved,
                        terraform_workdir=root,
                        structural_manifest_path=manifest,
                        fresh_review_comment_id=901,
                        owner_apply_authority_comment_id=902,
                        posted_claim_comment_id=903,
                    )
            finally:
                for item in reversed(patches):
                    item.stop()


if __name__ == "__main__":
    unittest.main()
