#!/usr/bin/env python3
"""Credential-free validation for the inert Slice C C4 successor recovery control."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/phase5-slice-c-recovery-reusable.yml"
CALLER = ROOT / ".github/workflows/phase5-slice-c-recovery.yml"
HELPER = ROOT / "scripts/phase5_slice_c_recovery.py"
AUTHORITY = ROOT / "infra/bootstrap/phase5_authority.tf"
VALIDATE = ROOT / ".github/workflows/validate.yml"
CANDIDATE = ROOT / "infra/product/candidate.json"

NORMAL_CONTROL_SHA = "47b3b17d32ffebf3ce8e9b7d15bc3d3539dc7239"
RECOVERY_CONTROL_SHA = "ae4960dd8db54849e7aa3698877c877bdb6433fd"
SUCCESSOR_CONTROL_SHA = "03123864097df51e6edafd67acc34702f0819de3"
BOUNDARY = "5833629251"
RECOVERY_DESIGN = "5963131897"
GENERATION = "1790344068764582"
SUCCESSOR_GENERATION = "1791024916608689"
LINEAGE = "d479de40-2c31-d83b-d84b-f55e9301d3a2"
EXPECTED_USES = (
    "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
    "hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e",
    "google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093",
)
EXPECTED_TOP_PERMISSIONS = (
    "contents: read",
    "issues: read",
    "actions: read",
    "pull-requests: read",
)
EXPECTED_JOB_PERMISSIONS = EXPECTED_TOP_PERMISSIONS + ("id-token: write",)
USES_LINE = re.compile(r"^\s*(?:-\s*)?uses\s*:\s*(\S+)\s*$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def _root_block(lines: list[str], root: str) -> list[str]:
    indexes = [i for i, line in enumerate(lines) if line == root]
    if len(indexes) != 1:
        return []
    out = [root]
    for line in lines[indexes[0] + 1 :]:
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        if line.strip() and not line.lstrip().startswith("#"):
            out.append(line)
    return out


def _permission_blocks(lines: list[str]) -> list[tuple[int, tuple[str, ...]]]:
    blocks: list[tuple[int, tuple[str, ...]]] = []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped != "permissions:":
            continue
        indent = len(line) - len(stripped)
        values: list[str] = []
        for child in lines[i + 1 :]:
            if not child.strip() or child.lstrip().startswith("#"):
                continue
            child_indent = len(child) - len(child.lstrip())
            if child_indent <= indent:
                break
            if child_indent == indent + 2:
                values.append(child.strip())
        blocks.append((indent, tuple(values)))
    return blocks


def workflow_structure_errors(workflow: str) -> list[str]:
    errors: list[str] = []
    lines = workflow.splitlines()

    if _root_block(lines, "on:") != ["on:", "  workflow_call:"]:
        errors.append("RECOVERY_WORKFLOW_TRIGGER_SET_NOT_EXACT_WORKFLOW_CALL")

    permissions = _permission_blocks(lines)
    top = [values for indent, values in permissions if indent == 0]
    jobs = [values for indent, values in permissions if indent == 4]
    if top != [EXPECTED_TOP_PERMISSIONS]:
        errors.append("RECOVERY_WORKFLOW_TOP_PERMISSION_SET_INVALID")
    if jobs != [EXPECTED_JOB_PERMISSIONS]:
        errors.append("RECOVERY_WORKFLOW_JOB_PERMISSION_SET_INVALID")

    uses: list[str] = []
    for line in lines:
        if "uses" not in line or line.lstrip().startswith("#"):
            continue
        match = USES_LINE.fullmatch(line)
        if match:
            uses.append(match.group(1))
        elif re.search(r"(^|[\s{,-])uses\s*:", line):
            errors.append("RECOVERY_WORKFLOW_USES_SYNTAX_UNSUPPORTED")
    if tuple(uses) != EXPECTED_USES:
        errors.append("RECOVERY_WORKFLOW_USES_SET_OR_PIN_INVALID")
    for value in uses:
        if "@" not in value or not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", value):
            errors.append(f"RECOVERY_WORKFLOW_UNPINNED_USE:{value}")
    return errors


def r2_caller_structure_errors(caller: str, control_sha: str) -> list[str]:
    errors: list[str] = []
    if not FULL_SHA.fullmatch(control_sha):
        return ["RECOVERY_R2_CALLER_CONTROL_SHA_INVALID"]
    lines = caller.splitlines()
    if _root_block(lines, "on:") != ["on:", "  workflow_dispatch:"]:
        errors.append("RECOVERY_R2_CALLER_TRIGGER_NOT_EXACT_WORKFLOW_DISPATCH")
    if "inputs:" in caller:
        errors.append("RECOVERY_R2_CALLER_MUTABLE_INPUTS_FORBIDDEN")
    expected_use = (
        "uses: 8ft0-ai/resilio/.github/workflows/"
        f"phase5-slice-c-recovery-reusable.yml@{control_sha}"
    )
    uses = [line.strip() for line in lines if line.strip().startswith("uses:")]
    if uses != [expected_use]:
        errors.append("RECOVERY_R2_CALLER_REUSABLE_IDENTITY_INVALID")
    permissions = _permission_blocks(lines)
    job_permissions = [values for indent, values in permissions if indent == 4]
    if job_permissions != [EXPECTED_JOB_PERMISSIONS]:
        errors.append("RECOVERY_R2_CALLER_PERMISSION_SET_INVALID")
    for forbidden in (
        "push:",
        "pull_request:",
        "schedule:",
        "workflow_run:",
        "repository_dispatch:",
        "$"+"{{ inputs.",
        "$"+"{{ secrets.",
    ):
        if forbidden in caller:
            errors.append(f"RECOVERY_R2_CALLER_FORBIDDEN:{forbidden}")
    return errors


def require(text: str, tokens: tuple[str, ...], label: str, errors: list[str]) -> None:
    for token in tokens:
        if token not in text:
            errors.append(f"{label}_MISSING:{token}")


def main() -> int:
    errors: list[str] = []
    for path in (WORKFLOW, CALLER, HELPER, AUTHORITY, VALIDATE, CANDIDATE):
        if not path.is_file():
            errors.append(f"RECOVERY_REQUIRED_FILE_MISSING:{path.relative_to(ROOT)}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    workflow = WORKFLOW.read_text(encoding="utf-8")
    caller = CALLER.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    authority = AUTHORITY.read_text(encoding="utf-8")
    validate = VALIDATE.read_text(encoding="utf-8")
    candidate = CANDIDATE.read_text(encoding="utf-8")
    errors.extend(workflow_structure_errors(workflow))

    require(
        workflow,
        (
            "on:\n  workflow_call:",
            "pull-requests: read",
            "Check out immutable recovery control",
            "ref: $"+"{{ job.workflow_sha }}",
            "terraform_version: 1.15.8",
            "Bind exact incident, activation and owner authority before OIDC",
            "Authenticate bounded product planner",
            "github-p5-product-planner@resilio-control-e882d4.iam.gserviceaccount.com",
            "Verify repaired product state and predecessor claim before successor claim",
            "Consume immutable one-shot successor recovery claim",
            "Reconcile exact accepted state without apply",
            "phase5_slice_c_recovery.py verify-successor-github-boundary",
            "phase5_slice_c_recovery.py verify-successor-cloud-boundary",
            "phase5_slice_c_recovery.py successor-claim",
            "--github-boundary \"$RUNNER_TEMP/recovery-github-boundary.json\"",
            "phase5_slice_c_recovery.py successor-state-identity",
            "phase5_slice_c_recovery.py verify-successor-state",
            "phase5_slice_c_recovery.py verify-successor-plan",
            "phase5_slice_c_recovery.py build-successor-result",
            "phase5_slice_c_recovery.py upload-successor-result",
            'test "$GENERATION" = "1791024916608689"',
            'test "$PLAN_RC" -eq 0',
            'test "$POST_META" = "$META"',
            'test "$POST_LOCK" = "ABSENT"',
        ),
        "RECOVERY_WORKFLOW",
        errors,
    )

    for token in (
        "\n  workflow_dispatch:",
        "\n  push:",
        "\n  pull_request:",
        "\n  schedule:",
        "\n  workflow_run:",
        "inputs:",
        "terraform apply",
        "terraform destroy",
        "-destroy",
        "-refresh-only",
        "github-p5-product-applier@",
        "$"+"{{ secrets.",
    ):
        if token in workflow:
            errors.append(f"RECOVERY_WORKFLOW_FORBIDDEN:{token.strip()}")

    if workflow.count("pull-requests: read") != 2:
        errors.append("RECOVERY_WORKFLOW_PULL_REQUESTS_READ_COUNT")
    if workflow.count("google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093") != 1:
        errors.append("RECOVERY_WORKFLOW_AUTH_ACTION_COUNT")
    if workflow.count("id-token: write") != 1:
        errors.append("RECOVERY_WORKFLOW_ID_TOKEN_COUNT")
    if workflow.count('terraform -chdir="$PLAN_WORK" plan') != 1:
        errors.append("RECOVERY_WORKFLOW_PLAN_COUNT")
    errors.extend(r2_caller_structure_errors(caller, SUCCESSOR_CONTROL_SHA))

    require(
        helper,
        (
            f"SOURCE_BOUNDARY_COMMENT_ID = {BOUNDARY}",
            'SOURCE_BOUNDARY_BODY_SHA256 = "f35b138c15441d8aa6f9e6149f9622a7c8fb936d9159de038d985f34c5a5defa"',
            f"RECOVERY_DESIGN_COMMENT_ID = {RECOVERY_DESIGN}",
            f'EXPECTED_GENERATION = "{GENERATION}"',
            f'EXPECTED_LINEAGE = "{LINEAGE}"',
            f'SUCCESSOR_EXPECTED_GENERATION = "{SUCCESSOR_GENERATION}"',
            'SUCCESSOR_EXPECTED_SERIAL = 4',
            'PREDECESSOR_CONTROL_SHA = "ae4960dd8db54849e7aa3698877c877bdb6433fd"',
            'PREDECESSOR_RECOVERY_RUN = 37107984572',
            'PREDECESSOR_FAILURE_RECORD_ID = 5967010836',
            'S1_TERMINAL_COMMENT_ID = 5968501614',
            'C3_ARCHITECTURE_COMMENT_ID = 5974709262',
            'C3_ARCHITECTURE_REVIEW_COMMENT_ID = 5974712806',
            'SUCCESSOR_ARCHITECTURE_COMMENT_ID = 5975291821',
            'SUCCESSOR_ARCHITECTURE_REVIEW_COMMENT_ID = 5975295621',
            'SUPERSEDED_CONTROL_SHA = "af197af2b0c2d2b5a5b949aeb330e9ddf5d07884"',
            'SUPERSEDED_ACTIVATION_PR = 124',
            'SUPERSEDED_ACTIVATION_REVIEW_ID = 5403467252',
            'SUPERSEDED_ACTIVATION_AUTHORITY_ID = 5974684198',
            'SUPERSEDED_ACTIVATION_MERGE_SHA = "81e542ce39f1728eebaa65ae4252499a61c44e53"',
            'SUPERSEDED_ACTIVATION_FAILURE_RECORD_ID = 5974703297',
            'SUPERSEDED_CLAIM_OBJECT',
            'SUPERSEDED_RESULT_OBJECT',
            'FAILED_C3_CONTROL_SHA = "4c9a4fd6f2b5c4cf3cd1d71f6c28053ab5ac5516"',
            'FAILED_C3_ACTIVATION_PR = 126',
            'FAILED_C3_ACTIVATION_REVIEW_ID = 5403643769',
            'FAILED_C3_ACTIVATION_AUTHORITY_ID = 5975180866',
            'FAILED_C3_ACTIVATION_AUTHORITY_RAW_BODY_SHA256 = "2faf35f12b10db23c765fd8b3b2001208234cc1225790b85a20936f11fc9d82d"',
            'FAILED_C3_ACTIVATION_FAILURE_RECORD_ID = 5975194221',
            'FAILED_C3_CLAIM_OBJECT',
            'FAILED_C3_RESULT_OBJECT',
            'canonical_comment_text',
            'canonical_comment_text(c.get("body")).startswith',
            'SUCCESSOR_ACTIVATION_RECORD_NOT_UNIQUE',
            'SUCCESSOR_WIF_REPIN_TERMINAL_NOT_UNIQUE',
            'canonical_comment_text(review.get("body"))!=expected_review',
            'canonical_comment_text(authority.get("body"))!=expected_authority',
            'canonical_comment_text(c.get("body"))==expected',
            'validate_failed_c3_activation_history',
            'SUCCESSOR_C3_ARCHITECTURE_CONTRACT_MISMATCH',
            'SUCCESSOR_C4_ARCHITECTURE_CONTRACT_MISMATCH',
            'SUCCESSOR_C4_ARCHITECTURE_REVIEW_CONTRACT_MISMATCH',
            'SUCCESSOR_C4_ARCHITECTURE_TIMELINE_INVALID',
            'FAILED_C3_ACTIVATION_AUTHORITY_CANONICAL_GRAMMAR_MISMATCH',
            'FAILED_C3_ACTIVATION_AUTHORITY_RAW_HASH_MISMATCH',
            'SUCCESSOR_C3_ARCHITECTURE_REVIEW_CONTRACT_MISMATCH',
            'SUCCESSOR_C3_ARCHITECTURE_TIMELINE_INVALID',
            'SUCCESSOR_ACTIVATION_MERGED_TREE_MISMATCH',
            'SUCCESSOR_VOLATILE_FIRESTORE_FIELDS',
            "PHASE5_SLICE_C_SUCCESSOR_ACTIVATION_MERGE_AUTHORITY_V1",
            "PHASE5_SLICE_C_SUCCESSOR_ACTIVATION_V1",
            "PHASE5_SLICE_C_SUCCESSOR_WIF_REPIN_PLAN_FRESH_REVIEW_V1",
            "PHASE5_SLICE_C_SUCCESSOR_WIF_REPIN_APPLY_AUTHORITY_V1",
            "PHASE5_SLICE_C_SUCCESSOR_WIF_REPIN_TERMINAL_V1",
            "PHASE5_SLICE_C_SUCCESSOR_DISPATCH_AUTHORITY_V1",
            "resilio-phase5-slice-c-successor-github-boundary/v1",
            "resilio-phase5-slice-c-successor-state/v1",
            "resilio-phase5-slice-c-successor-claim/v1",
            "resilio-phase5-slice-c-successor-result/v1",
            "resilio-phase5-slice-c-successor-manifest/v1",
            "verify_successor_cloud_boundary",
            "validate_superseded_activation_history",
            "verify_successor_activation_premerge",
            "emit-successor-activation-merge-authority",
            "verify-successor-activation-premerge",
            "emit-successor-activation-record",
            "resilio-phase5-slice-c-successor-premerge-authority/v1",
            "EXACT_ONE_RECOVERY_WIF_SUBJECT_REPIN_C1_TO_C4",
            "EXACT_C1_TO_C4_LIVE",
            "SUPERSEDED_C2_RECOVERY_WIF=ABSENT",
            "SUPERSEDED_C3_RECOVERY_WIF=ABSENT",
            "NEW_C4_RECOVERY_WIF=EXACT_ONE",
            "successor_state_identity_from_state",
            "verify_successor_no_change_plan",
            "PHASE5_SLICE_C_RECOVERY_R2_MERGE_AUTHORITY_V2",
            "PHASE5_SLICE_C_RECOVERY_R2_ACTIVATION_V2",
            "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_PLAN_FRESH_REVIEW_V1",
            "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_APPLY_AUTHORITY_V2",
            "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_TERMINAL_V3",
            "PHASE5_SLICE_C_RECOVERY_DISPATCH_AUTHORITY_V2",
            "COMPLETELY_FRESH_SUBSTANTIVE_IMPLEMENTATION_SECURITY_AUTHORITY_RE_REVIEW",
            'review.get("state") != "COMMENTED"',
            "R2_FRESH_REVIEW_BODY_SHA256",
            "R2_OWNER_MERGE_AUTHORITY_BODY_SHA256",
            "SAVED_PLAN_SHA256",
            "STRUCTURAL_MANIFEST_SHA256",
            "BOOTSTRAP_FRESH_REVIEW_BODY_SHA256",
            "BOOTSTRAP_OWNER_APPLY_AUTHORITY_BODY_SHA256",
            "RECOVERY_BOOTSTRAP_TERMINAL_RECORD_BODY_SHA256",
            "REPLAN=NOT_AUTHORISED",
            "PLAN_REPLACEMENT=NOT_AUTHORISED",
            "BLIND_RETRY_AFTER_AMBIGUOUS_OUTCOME=NOT_AUTHORISED",
            "UNRELATED_BOOTSTRAP_AUTHORITY_CONSEQUENCE=NONE",
            "FINAL_BOOTSTRAP_LOCK=ABSENT",
            "governance_chain_sha256",
            "resilio-phase5-slice-c-recovery-github-boundary/v2",
            "github_issue_comments",
            "per_page=100&page={page}",
            'AUTHORITY=DISPATCH_EXACTLY_ONE_RECONCILIATION_ONLY_RECOVERY',
            '"ifGenerationMatch": "0"',
            "resilio-phase5-slice-c-recovery-claim/v1",
            "resilio-phase5-slice-c-recovery-result/v1",
            "resilio-phase5-slice-c-recovery-manifest/v1",
            "FAILED_APPLY_RUN = 36143177732",
            "FAILED_APPLY_JOB = 108097723274",
            'SLICE_C_MERGE = "6b789246337e887fdd57210172a89032cd9ef122"',
            'REVIEWED_HEAD = "f95a8ca2cee97e92617904cf5514c0bf6a708107"',
            'REVIEWED_BASE = "a8c4ed5895fe7333c051bcea2d4bb9994310a62f"',
            f'NORMAL_CONTROL_SHA = "{NORMAL_CONTROL_SHA}"',
            "decode_github_base64",
        ),
        "RECOVERY_HELPER",
        errors,
    )
    for token in (
        "github-p5-product-applier@",
        "terraform apply",
        "terraform destroy",
        "serviceAccounts.setIamPolicy",
        "BOOTSTRAP_APPLY_RUN",
        "BOOTSTRAP_APPLY_JOB",
        "validate_bootstrap_apply_run",
    ):
        if token in helper:
            errors.append(f"RECOVERY_HELPER_FORBIDDEN:{token}")

    if f'phase5_control_sha = "{NORMAL_CONTROL_SHA}"' not in authority:
        errors.append("RECOVERY_R2_NORMAL_CONTROL_IDENTITY_CHANGED")
    expected_recovery_ref = (
        'phase5_slice_c_recovery_workflow_ref = '
        f'"8ft0-ai/resilio/.github/workflows/phase5-slice-c-recovery-reusable.yml@{SUCCESSOR_CONTROL_SHA}"'
    )
    if authority.count(expected_recovery_ref) != 1:
        errors.append("RECOVERY_R2_CONTROL_REF_NOT_EXACT")
    if authority.count("${local.phase5_control_sha}") != 7:
        errors.append("RECOVERY_R2_NORMAL_WORKFLOW_REF_COUNT_CHANGED")
    recovery_wif = (
        'resource "google_service_account_iam_member" "github_phase5_slice_c_recovery" {'
        '\n  service_account_id = google_service_account.phase5_product_planner.name'
        '\n  role               = "roles/iam.workloadIdentityUser"'
        '\n  member             = "principalSet://iam.googleapis.com/'
        '${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/'
        '${local.phase5_slice_c_recovery_workflow_ref}"'
        '\n}'
    )
    if authority.count(recovery_wif) != 1:
        errors.append("RECOVERY_R2_WIF_BINDING_NOT_EXACT")
    if authority.count("datastore.databases.getMetadata") != 2:
        errors.append("RECOVERY_R2_METADATA_PERMISSION_COUNT_INVALID")
    if authority.count('role               = "roles/iam.workloadIdentityUser"') != 8:
        errors.append("RECOVERY_R2_WIF_COUNT_INVALID")

    expected_candidate = (
        '{"contract":"resilio-product-terraform-candidate/v1",'
        '"processor_uri":null,"processor_verification_comment_id":null,"stage":"base"}\n'
    )
    if candidate != expected_candidate:
        errors.append("RECOVERY_R1_PRODUCT_CANDIDATE_CHANGED")

    if validate.count("python3 scripts/validate_phase5_slice_c_recovery.py") != 1:
        errors.append("RECOVERY_VALIDATOR_NOT_WIRED_EXACTLY_ONCE")

    if errors:
        print("Phase 5 Slice C recovery seed validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Phase 5 Slice C inert C4 successor recovery control validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
