#!/usr/bin/env python3
"""Credential-free validation for the inert Slice C C5 retained-effect recovery control."""
from __future__ import annotations

import ast
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
TESTS = ROOT / "tests/test_phase5_slice_c_recovery.py"

NORMAL_CONTROL_SHA = "47b3b17d32ffebf3ce8e9b7d15bc3d3539dc7239"
RECOVERY_CONTROL_SHA = "ae4960dd8db54849e7aa3698877c877bdb6433fd"
SUCCESSOR_CONTROL_SHA = "03123864097df51e6edafd67acc34702f0819de3"
C5_ARCHITECTURE_COMMENT_ID = "5976498714"
C5_ARCHITECTURE_REVIEW_COMMENT_ID = "5976504154"
C5_OWNER_DISPOSITION_COMMENT_ID = "5985897003"
C5_RETAINED_BASELINE_COMMENT_ID = "5987054333"
C5_BASE_MAIN = "6512a8df49c56ec797f106d02aae4d4114193779"
C5_BOOTSTRAP_STATE_LINEAGE = "ae08b2f4-f18f-204c-72aa-53e17f12eea7"
C5_BOOTSTRAP_STATE_SERIAL = "71"
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



def c5_semantic_errors(helper: str) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(helper)
    except SyntaxError as exc:
        return [f"RECOVERY_C5_HELPER_SYNTAX_INVALID:{exc.lineno}:{exc.offset}"]

    functions: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.setdefault(node.name, []).append(node)

    def latest(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        rows = functions.get(name) or []
        return rows[-1] if rows else None

    def calls(node: ast.AST | None) -> set[str]:
        if node is None:
            return set()
        out: set[str] = set()
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            target = child.func
            if isinstance(target, ast.Name):
                out.add(target.id)
            elif isinstance(target, ast.Attribute):
                out.add(target.attr)
        return out

    runtime = latest("verify_successor_github_boundary")
    runtime_calls = calls(runtime)
    if runtime is None or "verify_c5_github_boundary" not in runtime_calls:
        errors.append("RECOVERY_C5_RUNTIME_DOES_NOT_ENTER_C5_PROTOCOL")
    predecessor_calls = {
        "validate_successor_activation_record",
        "validate_successor_wif_repin_terminal",
        "validate_successor_dispatch_authority",
        "_legacy_verify_successor_github_boundary",
    }
    leaked = sorted(runtime_calls & predecessor_calls)
    if leaked:
        errors.append(
            "RECOVERY_C5_RUNTIME_REACHES_PREDECESSOR_GOVERNANCE:" + ",".join(leaked)
        )

    c5_boundary = latest("verify_c5_github_boundary")
    boundary_calls = calls(c5_boundary)
    for required in (
        "validate_c5_governance_history",
        "validate_c5_activation_record",
        "validate_c5_dispatch_authority",
    ):
        if required not in boundary_calls:
            errors.append(f"RECOVERY_C5_BOUNDARY_MISSING_CALL:{required}")

    dispatch = latest("c5_dispatch_authority_body")
    dispatch_calls = calls(dispatch)
    if "validate_c5_wif_repin_terminal" not in dispatch_calls:
        errors.append("RECOVERY_C5_DISPATCH_DOES_NOT_VALIDATE_TERMINAL")
    if "c5_terminal_record_summary" in dispatch_calls:
        errors.append("RECOVERY_C5_DISPATCH_ACCEPTS_CALLER_TERMINAL_SUMMARY")

    terminal = latest("validate_c5_wif_repin_terminal")
    terminal_calls = calls(terminal)
    for required in (
        "validate_c5_terminal_attempt_claim_chain",
        "validate_c5_wif_repin_observation",
        "validate_c5_activation_record",
    ):
        if required not in terminal_calls:
            errors.append(f"RECOVERY_C5_TERMINAL_MISSING_PROVENANCE_CALL:{required}")

    terminal_claim = latest("validate_c5_terminal_attempt_claim_chain")
    terminal_claim_calls = calls(terminal_claim)
    for required in (
        "validate_c5_attempt_history",
        "_c5_validate_plan_review_and_authority",
        "c5_precondition_digest_sha256",
        "validate_c5_posted_attempt_claim",
    ):
        if required not in terminal_claim_calls:
            errors.append(
                f"RECOVERY_C5_TERMINAL_CLAIM_PROVENANCE_MISSING:{required}"
            )

    observation_validator = latest("validate_c5_wif_repin_observation")
    observation_validator_calls = calls(observation_validator)
    for required in (
        "_require_unedited_c5_observation_comment",
        "_c5_validate_observation_execution",
    ):
        if required not in observation_validator_calls:
            errors.append(
                f"RECOVERY_C5_OBSERVATION_PROVENANCE_MISSING:{required}"
            )

    observation_poster = latest("post_c5_wif_repin_observation")
    observation_poster_calls = calls(observation_poster)
    for required in ("verify_c5_wif_repin_observation", "request_json"):
        if required not in observation_poster_calls:
            errors.append(
                f"RECOVERY_C5_OBSERVATION_DURABLE_POST_MISSING:{required}"
            )

    outcome = latest("_c5_observation_outcome")
    outcome_source = (
        ast.get_source_segment(helper, outcome) or "" if outcome is not None else ""
    )
    if 'second["created_at"] - first["created_at"]' not in outcome_source:
        errors.append("RECOVERY_C5_NO_EFFECT_FENCE_NOT_DURABLE_COMMENT_TIME")
    if 'second["observed_at"] - first["observed_at"]' not in outcome_source:
        errors.append("RECOVERY_C5_NO_EFFECT_FENCE_NOT_VERIFIER_TIME")
    if "durable_separation >= 60" not in outcome_source:
        errors.append("RECOVERY_C5_NO_EFFECT_DURABLE_INTERVAL_NOT_ENFORCED")
    if "verifier_separation >= 60" not in outcome_source:
        errors.append("RECOVERY_C5_NO_EFFECT_VERIFIER_INTERVAL_NOT_ENFORCED")

    observation = latest("verify_c5_wif_repin_observation")
    observation_calls = calls(observation)
    for required in (
        "_c5_post_effect_live_facts",
        "_c5_fresh_reconciliation",
        "_successor_gcs_json",
        "_successor_gcs_metadata",
        "_c5_observation_execution_identity",
    ):
        if required not in observation_calls:
            errors.append(f"RECOVERY_C5_OBSERVATION_NOT_VERIFIER_OWNED:{required}")
    observation_source = (
        ast.get_source_segment(helper, observation) or ""
        if observation is not None
        else ""
    )
    if "datetime.now(timezone.utc)" not in observation_source:
        errors.append("RECOVERY_C5_OBSERVATION_CLOCK_NOT_VERIFIER_OWNED")
    if '"--observed-at"' in helper:
        errors.append("RECOVERY_C5_CALLER_OBSERVATION_CLOCK_REACHABLE")

    reconciliation_digest = latest("_c5_reconciliation_plan_fact_sha256")
    digest_source = (
        ast.get_source_segment(helper, reconciliation_digest) or ""
        if reconciliation_digest is not None
        else ""
    )
    if 'stable.pop("timestamp", None)' not in digest_source:
        errors.append("RECOVERY_C5_RECONCILIATION_DIGEST_NOT_SEMANTIC")

    pre_effect = latest("verify_c5_wif_repin_pre_effect")
    pre_effect_calls = calls(pre_effect)
    if "c5_nonterminal_actions_snapshot" not in pre_effect_calls:
        errors.append("RECOVERY_C5_PRE_EFFECT_INCOMPLETE_ACTIONS_CURRENTNESS")
    if "status=in_progress" in helper:
        errors.append("RECOVERY_C5_IN_PROGRESS_ONLY_ACTIONS_FILTER_REACHABLE")

    effect = latest("execute_c5_wif_repin_effect")
    effect_calls = calls(effect)
    effect_source = (
        ast.get_source_segment(helper, effect) or "" if effect is not None else ""
    )
    if "verify_c5_wif_repin_pre_effect" not in effect_calls:
        errors.append("RECOVERY_C5_EFFECT_MISSING_IMMEDIATE_REVERIFY")
    if "run" not in effect_calls:
        errors.append("RECOVERY_C5_EFFECT_MISSING_TERRAFORM_EXECUTION")
    for required_token in (
        '"apply"',
        '"-input=false"',
        '"-lock=true"',
        '"C5_EFFECT_REVERIFY_NOT_EFFECT_READY"',
        '"C5_EFFECT_APPLY_FAILED__OUTCOME_REQUIRES_OBSERVATION"',
    ):
        if required_token not in effect_source:
            errors.append(
                "RECOVERY_C5_EFFECT_LOCKED_APPLY_CONTRACT_MISSING:"
                + required_token
            )
    for forbidden_token in ("shell=True", '"destroy"', '"-lock=false"'):
        if forbidden_token in effect_source:
            errors.append(
                "RECOVERY_C5_EFFECT_LOCKED_APPLY_CONTRACT_FORBIDDEN:"
                + forbidden_token
            )

    authority_body = latest("c5_wif_repin_authority_body")
    authority_source = (
        ast.get_source_segment(helper, authority_body) or ""
        if authority_body is not None
        else ""
    )
    for required_token in (
        "EFFECT_EXECUTOR=apply-c5-wif-repin-effect",
        "BOOTSTRAP_STATE_LOCKING=CANONICAL_TERRAFORM_LOCK_TRUE_REQUIRED",
    ):
        if required_token not in authority_source:
            errors.append(
                "RECOVERY_C5_EFFECT_AUTHORITY_LOCK_BINDING_MISSING:"
                + required_token
            )

    attempt_claim = latest("c5_attempt_claim_body")
    attempt_claim_source = (
        ast.get_source_segment(helper, attempt_claim) or ""
        if attempt_claim is not None
        else ""
    )
    for required_token in (
        "EFFECT_EXECUTOR=apply-c5-wif-repin-effect",
        "BOOTSTRAP_STATE_LOCKING=CANONICAL_TERRAFORM_LOCK_TRUE_REQUIRED",
    ):
        if required_token not in attempt_claim_source:
            errors.append(
                "RECOVERY_C5_ATTEMPT_LOCK_PROVENANCE_MISSING:"
                + required_token
            )

    control_record = latest("c5_control_merge_record_body")
    control_record_calls = calls(control_record)
    control_record_source = ast.get_source_segment(helper, control_record) or "" if control_record is not None else ""
    if "C5_CONTROL_CURRENTNESS_DIGEST_SHA256" not in control_record_source:
        errors.append("RECOVERY_C5_CONTROL_RECORD_CURRENTNESS_NOT_BOUND")

    premerge = latest("verify_c5_control_premerge")
    if "verify_c5_control_use_time_currentness" not in calls(premerge):
        errors.append("RECOVERY_C5_CONTROL_PREMERGE_CURRENTNESS_NOT_RECHECKED")

    main = latest("main")
    main_calls = calls(main)
    if "verify_successor_github_boundary" not in main_calls:
        errors.append("RECOVERY_C5_CLI_RUNTIME_ENTRYPOINT_NOT_REACHABLE")
    if "execute_c5_wif_repin_effect" not in main_calls:
        errors.append("RECOVERY_C5_CLI_LOCKED_EFFECT_ENTRYPOINT_NOT_REACHABLE")

    if (
        'C5_PROTOCOL_EPOCH_SHA256 = "785fd8bdb53812ebbca31e9d72da66667eb53b3b54925e6bd0a3c788180c600f"'
        not in helper
    ):
        errors.append("RECOVERY_C5_PROTOCOL_EPOCH_IDENTITY_MISSING")

    return errors

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
    for path in (WORKFLOW, CALLER, HELPER, AUTHORITY, VALIDATE, CANDIDATE, TESTS):
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
    tests = TESTS.read_text(encoding="utf-8")
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
            f"C5_ARCHITECTURE_COMMENT_ID = {C5_ARCHITECTURE_COMMENT_ID}",
            f"C5_ARCHITECTURE_REVIEW_COMMENT_ID = {C5_ARCHITECTURE_REVIEW_COMMENT_ID}",
            f"C5_OWNER_DISPOSITION_COMMENT_ID = {C5_OWNER_DISPOSITION_COMMENT_ID}",
            f"C5_RETAINED_BASELINE_COMMENT_ID = {C5_RETAINED_BASELINE_COMMENT_ID}",
            f'C5_BASE_MAIN = "{C5_BASE_MAIN}"',
            f'C5_OLD_RECOVERY_CONTROL_SHA = "{SUCCESSOR_CONTROL_SHA}"',
            f'C5_BOOTSTRAP_STATE_LINEAGE = "{C5_BOOTSTRAP_STATE_LINEAGE}"',
            f"C5_BOOTSTRAP_STATE_SERIAL = {C5_BOOTSTRAP_STATE_SERIAL}",
            "validate_c5_governance_history",
            "PHASE5_SLICE_C_C4_WIF_INCIDENT_DISPOSITION_V1",
            "RETAINED_C4_EFFECT_BASELINE_V1",
            "PHASE5_SLICE_C_C5_USE_TIME_CURRENTNESS_V1",
            "PHASE5_SLICE_C_WIF_REPIN_PRECONDITION_SNAPSHOT_V1",
            "PLAN_EFFECTS=EXACT_ONE_RECOVERY_WIF_SUBJECT_REPIN_OLD_TO_NEW",
            "c5_precondition_digest_sha256",
            "PHASE5_SLICE_C_WIF_REPIN_ATTEMPT_SERIES_V1",
            "WIF_REPIN_ATTEMPT_CLAIM_V1",
            "validate_c5_attempt_history",
            "validate_c5_posted_attempt_claim",
            "PHASE5_SLICE_C_C5_WIF_REPIN_PLAN_FRESH_REVIEW_V1",
            "PHASE5_SLICE_C_C5_WIF_REPIN_APPLY_AUTHORITY_V1",
            "SAME_GENERATION_RETRY=NOT_AUTHORISED",
            "c5_classify_wif_repin_outcome",
            "PROCESS_OUTCOME_UNKNOWN",
            "NO_EFFECT_STABLE",
            "INCONSISTENT_EFFECT",
            "PHASE5_SLICE_C_C5_WIF_REPIN_TERMINAL_V1",
            "PHASE5_SLICE_C_C5_WIF_REPIN_OBSERVATION_V1",
            "PHASE5_SLICE_C_C5_WIF_REPIN_TERMINAL_V2",
            "PHASE5_SLICE_C_C5_DISPATCH_AUTHORITY_V2",
            "C5_PROTOCOL_EPOCH_SHA256",
            "C5_ARCHITECTURE_CLOSURE_COMMENT_ID = 5993056257",
            "c5_nonterminal_actions_snapshot",
            "verify_c5_control_use_time_currentness",
            "C5_CONTROL_CURRENTNESS_DIGEST_SHA256",
            "C5_CONTROL_CURRENTNESS_CAPTURE=FRESH_POST_MERGE",
            "C5_CONTROL_CURRENTNESS_CALLER_NOT_C4",
            "C5_CONTROL_CURRENTNESS_DESIRED_WIF_NOT_C4",
            "validate_c5_wif_repin_observation",
            "validate_c5_wif_repin_terminal",
            "validate_c5_dispatch_authority",
            "verify_c5_github_boundary",
            "verify_c5_wif_repin_observation",
            "_c5_post_effect_live_facts",
            "_c5_fresh_reconciliation",
            "RECONCILIATION_PLAN_SHA256",
            "UNEXPECTED_RECOVERY_WIF_COUNT",
            "BOOTSTRAP_STATE_SERIAL_BEFORE",
            "C5_PROCESS_OUTCOME_UNKNOWN_NOT_TERMINAL",
            "PHASE5_SLICE_C_C5_DISPATCH_AUTHORITY_V1",
            "C5_DISPATCH_REQUIRES_EFFECT_SUCCEEDED",
            "C4_DISPATCH_PERMANENTLY_FORBIDDEN",
            "C5_CONTROL_ALLOWED_FILES",
            "C5_ACTIVATION_ALLOWED_FILES",
            "COMPLETELY_FRESH_SUBSTANTIVE_C5_IMPLEMENTATION_SECURITY_AUTHORITY_REVIEW",
            "PHASE5_SLICE_C_C5_CONTROL_MERGE_AUTHORITY_V1",
            "verify_c5_control_premerge",
            "PHASE5_SLICE_C_C5_CONTROL_MERGE_V1",
            "validate_c5_control_merge_record",
            "COMPLETELY_FRESH_SUBSTANTIVE_C5_ACTIVATION_SECURITY_AUTHORITY_REVIEW",
            "PHASE5_SLICE_C_C5_ACTIVATION_MERGE_AUTHORITY_V1",
            "verify_c5_activation_premerge",
            "PHASE5_SLICE_C_C5_ACTIVATION_V1",
            "validate_c5_activation_record",
            "verify_c5_repository_activation",
            "verify_c5_bootstrap_state_and_live_iam",
            "c5_verify_wif_repin_plan",
            "verify_c5_wif_repin_pre_effect",
            '"phase": phase',
            'phase = "CLAIM_READY"',
            'phase = "EFFECT_READY"',
            '"ready_for_effect": posted_claim_comment_id is not None',
            'method="POST"',
            'data=b"{}"',
            "C5_EXPECTED_BOOTSTRAP_RESOURCE_COUNT = 138",
            "C5_EXPECTED_PHASE5_WIF_ROWS",
            "C5_EXPECTED_ROLE_PERMISSIONS",
            "C5_PHASE5_WIF_LIVE_SET_MISMATCH",
            "C5_ROLE_PERMISSIONS_CHANGED",
            "_c5_saved_plan_json",
            '"terraform",',
            '"show",',
            '"-json",',
            "c5_verify_structural_manifest",
            "resilio-bootstrap-wif-repin-structural-manifest/v1",
            "C5_STRUCTURAL_MANIFEST_EFFECT_MISMATCH",
        ),
        "RECOVERY_HELPER",
        errors,
    )

    require(
        tests,
        (
            "class C5RetainedEffectProtocolTests",
            "test_c5_precondition_constructor_rejects_hostile_identity_inputs",
            "test_c5_review_and_authority_reject_one_nibble_or_uppercase_hashes",
            "test_c5_attempt_history_requires_unique_contiguous_generations",
            "test_c5_posted_claim_revalidation_binds_raw_body_and_chronology",
            "test_c5_outcome_algebra_no_effect_requires_two_observations_60_seconds",
            "test_c5_process_unknown_cannot_be_emitted_as_terminal",
            "test_c5_terminal_binds_total_effect_evidence_and_enables_only_effect_dispatch",
            "test_c5_governance_history_closes_architecture_review_disposition_baseline",
            "test_c5_wif_plan_requires_exact_one_old_to_new_replacement",
            "test_c5_structural_manifest_exactly_matches_old_to_new_effect",
            "test_c5_bootstrap_live_iam_requires_all_eight_and_c4_only",
            "test_c5_repository_activation_requires_exact_caller_and_desired_pin",
            "test_c5_activation_file_transform_is_exact_two_file_sha_repin",
            "test_c5_control_and_activation_authority_constructors_are_strict",
            "test_c5_pre_effect_verifier_has_distinct_claim_ready_and_effect_ready",
            "test_c5_runtime_protocol_epoch_rejects_predecessor_control",
            "test_c5_public_runtime_routes_only_to_c5_protocol",
            "test_c5_arbitrary_effect_label_cannot_create_dispatch_authority",
            "test_c5_terminal_outcome_mismatch_is_rejected",
            "test_c5_edited_observation_raw_body_is_rejected",
            "test_c5_no_effect_requires_two_validated_observations",
            "test_c5_no_effect_rejects_fact_digest_mismatch_or_short_interval",
            "test_c5_no_effect_fence_uses_durable_comment_timestamps",
            "test_c5_reconciliation_digest_ignores_only_run_timestamp",
            "test_c5_locked_effect_executor_requires_effect_ready_and_lock_true",
            "test_c5_complete_nonterminal_actions_set_includes_all_nonterminal_statuses",
            "test_c5_nonterminal_actions_snapshot_is_paginated",
            "test_c5_attempt_claim_binds_protocol_epoch",
            "test_c5_terminal_claim_provenance_rejects_substituted_plan_precondition_and_generation",
            "test_c5_observation_is_emitted_from_live_verifier_not_caller_outcome",
            "test_c5_handcrafted_owner_observation_is_rejected_even_with_valid_digest",
            "test_c5_observation_execution_witness_rejects_substitution",
            "test_c5_observation_poster_requires_actions_bot_durable_comment",
        ),
        "RECOVERY_C5_TESTS",
        errors,
    )
    errors.extend(c5_semantic_errors(helper))

    for token in (
        "github-p5-product-applier@",
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

    require(
        helper,
        (
            'commands.add_parser("emit-c5-control-review")',
            'commands.add_parser("emit-c5-control-merge-authority")',
            'commands.add_parser("verify-c5-control-premerge")',
            'commands.add_parser("emit-c5-control-merge-record")',
            'commands.add_parser("emit-c5-activation-review")',
            'commands.add_parser("emit-c5-activation-merge-authority")',
            'commands.add_parser("verify-c5-activation-premerge")',
            'commands.add_parser("emit-c5-activation-record")',
            'commands.add_parser("emit-c5-wif-repin-review")',
            'commands.add_parser("emit-c5-wif-repin-authority")',
            'commands.add_parser("verify-c5-wif-repin-pre-effect")',
            'commands.add_parser("apply-c5-wif-repin-effect")',
            'commands.add_parser("emit-c5-wif-observation")',
            'commands.add_parser("emit-c5-wif-terminal-v2")',
            'commands.add_parser("emit-c5-dispatch-authority-v2")',
        ),
        "RECOVERY_C5_CLI",
        errors,
    )

    if errors:
        print("Phase 5 Slice C recovery seed validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Phase 5 Slice C inert C5 retained-effect recovery control validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
