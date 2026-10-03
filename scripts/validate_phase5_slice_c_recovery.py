#!/usr/bin/env python3
"""Credential-free validation for the inert Slice C recovery control seed."""
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
BOUNDARY = "5833629251"
RECOVERY_DESIGN = "5963131897"
GENERATION = "1790344068764582"
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
    for path in (WORKFLOW, HELPER, AUTHORITY, VALIDATE, CANDIDATE):
        if not path.is_file():
            errors.append(f"RECOVERY_REQUIRED_FILE_MISSING:{path.relative_to(ROOT)}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    workflow = WORKFLOW.read_text(encoding="utf-8")
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
            "Consume immutable one-shot recovery claim",
            "Reconcile exact accepted state without apply",
            "phase5_slice_c_recovery.py verify-github-boundary",
            "phase5_slice_c_recovery.py claim",
            "--github-boundary \"$RUNNER_TEMP/recovery-github-boundary.json\"",
            "phase5_slice_c_recovery.py verify-state",
            "phase5_slice_c_recovery.py verify-plan",
            "phase5_slice_c_recovery.py build-result",
            "phase5_slice_c_recovery.py upload-result",
            'test "$GENERATION" = "1790344068764582"',
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
    if CALLER.exists():
        errors.append("RECOVERY_R1_CALLER_MUST_BE_ABSENT")

    require(
        helper,
        (
            f"SOURCE_BOUNDARY_COMMENT_ID = {BOUNDARY}",
            'SOURCE_BOUNDARY_BODY_SHA256 = "f35b138c15441d8aa6f9e6149f9622a7c8fb936d9159de038d985f34c5a5defa"',
            f"RECOVERY_DESIGN_COMMENT_ID = {RECOVERY_DESIGN}",
            f'EXPECTED_GENERATION = "{GENERATION}"',
            f'EXPECTED_LINEAGE = "{LINEAGE}"',
            "PHASE5_SLICE_C_RECOVERY_R2_MERGE_AUTHORITY_V2",
            "PHASE5_SLICE_C_RECOVERY_R2_ACTIVATION_V2",
            "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_EFFECT_REVIEW_V1",
            "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_APPLY_AUTHORITY_V1",
            "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_TERMINAL_V2",
            "PHASE5_SLICE_C_RECOVERY_DISPATCH_AUTHORITY_V2",
            "COMPLETELY_FRESH_SUBSTANTIVE_IMPLEMENTATION_SECURITY_AUTHORITY_RE_REVIEW",
            'review.get("state") != "COMMENTED"',
            "R2_FRESH_REVIEW_BODY_SHA256",
            "R2_OWNER_MERGE_AUTHORITY_BODY_SHA256",
            "BOOTSTRAP_FRESH_REVIEW_BODY_SHA256",
            "BOOTSTRAP_OWNER_APPLY_AUTHORITY_BODY_SHA256",
            "RECOVERY_BOOTSTRAP_TERMINAL_RECORD_BODY_SHA256",
            "governance_chain_sha256",
            "resilio-phase5-slice-c-recovery-github-boundary/v1",
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
    ):
        if token in helper:
            errors.append(f"RECOVERY_HELPER_FORBIDDEN:{token}")

    if f'phase5_control_sha = "{NORMAL_CONTROL_SHA}"' not in authority:
        errors.append("RECOVERY_R1_NORMAL_CONTROL_IDENTITY_CHANGED")
    if "phase5-slice-c-recovery-reusable.yml" in authority:
        errors.append("RECOVERY_R1_WIF_MUST_BE_ABSENT")
    if "datastore.databases.getMetadata" in authority:
        errors.append("RECOVERY_R1_METADATA_PERMISSION_MUST_BE_ABSENT")
    if authority.count('role               = "roles/iam.workloadIdentityUser"') != 7:
        errors.append("RECOVERY_R1_WIF_COUNT_CHANGED")

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
    print("Phase 5 Slice C inert recovery control seed validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
