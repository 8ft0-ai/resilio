#!/usr/bin/env python3
"""Credential-free validation of the canonical cloud bootstrap control contract."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BOOTSTRAP_DIR = ROOT / "infra/bootstrap"
BACKEND = BOOTSTRAP_DIR / "backend.tf"
BOOTSTRAP_MAIN = BOOTSTRAP_DIR / "main.tf"
AUTHORITY = BOOTSTRAP_DIR / "phase3_authority.tf"
OUTPUTS = BOOTSTRAP_DIR / "outputs.tf"
SMOKE = ROOT / ".github/workflows/federation-smoke.yml"
EVIDENCE = ROOT / "docs/gcp-bootstrap-evidence.md"

CONTROL_SEED_SHA = "cbfe9821ec07ca6c0c869ebe75100bc500c92a04"
DRIFT_WORKFLOW_SHA = "2acbc425f688383375f724da7a4d80025dd9cc23"
CONTROL_PROJECT_ID = "resilio-control-e882d4"
CONTROL_PROJECT_NUMBER = "400271474382"
REFERENCE_PROJECT_ID = "resilio-reference-e882d4"
REFERENCE_PROJECT_NUMBER = "144158187163"
STATE_BUCKET = "resilio-control-e882d4-tfstate"
STATE_PREFIX = "bootstrap"
WIF_PROVIDER = (
    "projects/400271474382/locations/global/"
    "workloadIdentityPools/github/providers/resilio"
)
PROBE_SERVICE_ACCOUNT = (
    "github-federation-probe@resilio-control-e882d4.iam.gserviceaccount.com"
)
PLANNER_SERVICE_ACCOUNT = (
    "github-foundation-planner@resilio-control-e882d4.iam.gserviceaccount.com"
)
APPLIER_SERVICE_ACCOUNT = (
    "github-foundation-applier@resilio-control-e882d4.iam.gserviceaccount.com"
)
GITHUB_SUBJECT = (
    "repo:8ft0-ai@130460431/resilio@1335801159:ref:refs/heads/main"
)
PLANNER_WORKFLOW_REF = (
    "8ft0-ai/resilio/.github/workflows/terraform-plan-reusable.yml@"
    + CONTROL_SEED_SHA
)
APPLIER_WORKFLOW_REF = (
    "8ft0-ai/resilio/.github/workflows/terraform-apply-reusable.yml@"
    + CONTROL_SEED_SHA
)
DRIFT_WORKFLOW_REF = (
    "8ft0-ai/resilio/.github/workflows/terraform-drift-reusable.yml@"
    + DRIFT_WORKFLOW_SHA
)

# These are Git blob identities for the complete reviewed bootstrap Terraform
# configuration. Any Terraform configuration drift must therefore update this
# validator and pass a new substantive review rather than silently widening the
# authority envelope while retaining the same required tokens.
EXPECTED_BOOTSTRAP_TERRAFORM_BLOBS = {
    "backend.tf": "97127a22fed31347ecadd6bea5f8b097deb6c517",
    "main.tf": "80b0a697e3735c9e0568511dcef58d4c8abdc183",
    "outputs.tf": "68691c38ea5e4b34729448b43b469e42ef3f5acc",
    "phase3_authority.tf": "4020e190ea0816d962b5b3ffe1b1e74f828aea4b",
    "variables.tf": "8be4636d1493e949f5e8218f559ce1139e862e61",
    "versions.tf": "7d3dff03f38303dd7616b1ad949e440a6d51f1f3",
}

EXPECTED_BACKEND = (
    "terraform {\n"
    '  backend "gcs" {\n'
    f'    bucket = "{STATE_BUCKET}"\n'
    f'    prefix = "{STATE_PREFIX}"\n'
    "  }\n"
    "}\n"
)

EXPECTED_SMOKE = (
    "name: Federation smoke\n"
    "\n"
    "on:\n"
    "  workflow_dispatch:\n"
    "\n"
    "permissions:\n"
    "  contents: read\n"
    "\n"
    "jobs:\n"
    "  require-main:\n"
    "    name: require-trusted-main\n"
    "    runs-on: ubuntu-latest\n"
    "    timeout-minutes: 2\n"
    "    steps:\n"
    "      - name: Require trusted main\n"
    '        run: test "$GITHUB_REF" = "refs/heads/main"\n'
    "\n"
    "  authenticate:\n"
    "    name: trusted-main-auth\n"
    "    needs: require-main\n"
    "    if: github.ref == 'refs/heads/main'\n"
    "    permissions:\n"
    "      contents: read\n"
    "      id-token: write\n"
    f"    uses: 8ft0-ai/resilio/.github/workflows/terraform-federation-reusable.yml@{CONTROL_SEED_SHA}\n"
    "    with:\n"
    f"      service_account: {PROBE_SERVICE_ACCOUNT}\n"
    "      token_lifetime: 300s\n"
)


def require_file(path: Path, errors: list[str]) -> str:
    if not path.is_file():
        errors.append(f"required cloud bootstrap path is missing: {path.relative_to(ROOT)}")
        return ""
    return path.read_text(encoding="utf-8")


def git_blob_sha(path: Path) -> str:
    content = path.read_bytes()
    prefix = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(prefix + content).hexdigest()


def check_bootstrap_terraform_identity(errors: list[str]) -> None:
    expected_names = tuple(sorted(EXPECTED_BOOTSTRAP_TERRAFORM_BLOBS))
    actual_names = tuple(
        sorted(
            path.name
            for path in BOOTSTRAP_DIR.iterdir()
            if path.is_file()
            and (path.name.endswith(".tf") or path.name.endswith(".tf.json"))
        )
    )
    if actual_names != expected_names:
        errors.append(
            "bootstrap Terraform configuration file set must exactly match "
            f"{expected_names}; found {actual_names}"
        )
        return

    for name, expected_sha in EXPECTED_BOOTSTRAP_TERRAFORM_BLOBS.items():
        path = BOOTSTRAP_DIR / name
        actual_sha = git_blob_sha(path)
        if actual_sha != expected_sha:
            errors.append(
                f"bootstrap Terraform configuration {name} must remain at reviewed "
                f"blob {expected_sha}; found {actual_sha}"
            )


def check_backend(errors: list[str]) -> None:
    text = require_file(BACKEND, errors)
    if text and text != EXPECTED_BACKEND:
        errors.append(
            "canonical backend must contain exactly the approved GCS bucket/prefix and no other backend settings"
        )


def check_smoke(errors: list[str]) -> None:
    text = require_file(SMOKE, errors)
    if text and text != EXPECTED_SMOKE:
        errors.append(
            "federation smoke must exactly match the approved manual trusted-main immutable reusable-auth contract"
        )


def check_evidence(errors: list[str]) -> None:
    text = require_file(EVIDENCE, errors)
    if not text:
        return

    for item in (
        CONTROL_PROJECT_ID,
        CONTROL_PROJECT_NUMBER,
        REFERENCE_PROJECT_ID,
        REFERENCE_PROJECT_NUMBER,
        STATE_BUCKET,
        f"{STATE_PREFIX}/default.tfstate",
        WIF_PROVIDER,
        PROBE_SERVICE_ACCOUNT,
        GITHUB_SUBJECT,
        "5328190302",
        "remote-backed Terraform plan returned `NO_CHANGE`",
        "No billing-account ID",
    ):
        if item not in text:
            errors.append(f"Gate C evidence is missing canonical public evidence: {item}")

    for token in (
        "billingAccounts/",
        "application_default_credentials",
        '"private_key"',
        '"access_token"',
    ):
        if token in text:
            errors.append(f"Gate C evidence contains forbidden private material marker: {token}")


def custom_role_permissions(text: str, resource_name: str) -> tuple[str, ...] | None:
    header = f'resource "google_project_iam_custom_role" "{resource_name}"'
    start = text.find(header)
    if start < 0:
        return None
    end = text.find('\nresource "', start + len(header))
    block = text[start:] if end < 0 else text[start:end]
    marker = "permissions = ["
    pstart = block.find(marker)
    if pstart < 0:
        return None
    pend = block.find("\n  ]", pstart)
    if pend < 0:
        return None
    lines = block[pstart + len(marker):pend].splitlines()
    return tuple(
        line.strip().rstrip(",").strip('"')
        for line in lines
        if line.strip()
    )


def check_phase3_authority(errors: list[str]) -> None:
    main_text = require_file(BOOTSTRAP_MAIN, errors)
    authority_text = require_file(AUTHORITY, errors)
    outputs_text = require_file(OUTPUTS, errors)
    if not main_text or not authority_text or not outputs_text:
        return

    exact_subject = f'  github_main_subject = "{GITHUB_SUBJECT}"'
    if exact_subject not in main_text:
        errors.append("WIF provider must preserve the exact immutable repository/main subject value")

    expected_mapping = (
        '  attribute_mapping = {\n'
        '    "google.subject"             = "assertion.sub"\n'
        '    "attribute.job_workflow_ref" = "assertion.job_workflow_ref"\n'
        '    "attribute.job_workflow_sha" = "assertion.job_workflow_sha"\n'
        '  }\n'
    )
    if expected_mapping not in main_text:
        errors.append("WIF provider must map subject plus reusable-workflow ref/SHA claims exactly")
    expected_condition = 'attribute_condition = "assertion.sub == \\"${local.github_main_subject}\\""'
    if expected_condition not in main_text:
        errors.append("WIF provider must preserve the exact immutable repository/main subject condition")
    if 'issuer_uri = "https://token.actions.githubusercontent.com"' not in main_text:
        errors.append("WIF provider must preserve the GitHub Actions OIDC issuer")

    required_authority = (
        f'phase3_control_seed_sha             = "{CONTROL_SEED_SHA}"',
        f'phase3_drift_workflow_sha           = "{DRIFT_WORKFLOW_SHA}"',
        'account_id   = "github-foundation-planner"',
        'account_id   = "github-foundation-applier"',
        '"8ft0-ai/resilio/.github/workflows/terraform-plan-reusable.yml@${local.phase3_control_seed_sha}"',
        '"8ft0-ai/resilio/.github/workflows/terraform-apply-reusable.yml@${local.phase3_control_seed_sha}"',
        '"8ft0-ai/resilio/.github/workflows/terraform-drift-reusable.yml@${local.phase3_drift_workflow_sha}"',
        'role               = "roles/iam.workloadIdentityUser"',
        'attribute.job_workflow_ref/${local.foundation_plan_workflow_ref}',
        'attribute.job_workflow_ref/${local.foundation_apply_workflow_ref}',
        'attribute.job_workflow_ref/${local.foundation_drift_workflow_ref}',
        'foundation/default.tfstate',
        'foundation/default.tflock',
        'plan-evidence/foundation/',
        'resource.name == \\"${local.foundation_state_resource_name}\\"',
        'resource.name == \\"${local.foundation_lock_resource_name}\\"',
        'resource.name.startsWith(\\"${local.foundation_evidence_resource_prefix}\\")',
    )
    for token in required_authority:
        if token not in authority_text:
            errors.append(f"Phase 3 authority envelope is missing required exact contract token: {token}")

    if authority_text.count('resource "google_service_account_iam_member"') != 3:
        errors.append("Phase 3 authority envelope must contain exactly planner, drift and applier WIF service-account bindings")
    if authority_text.count('role               = "roles/iam.workloadIdentityUser"') != 3:
        errors.append("Phase 3 authority envelope must contain exactly three workloadIdentityUser bindings")

    expected_roles = {
        "foundation_planner": (
            "iam.serviceAccountKeys.list",
            "iam.serviceAccounts.get",
            "iam.serviceAccounts.getIamPolicy",
            "resourcemanager.projects.getIamPolicy",
        ),
        "foundation_applier": (
            "iam.serviceAccounts.create",
            "iam.serviceAccounts.get",
            "iam.serviceAccounts.update",
        ),
        "foundation_state_list": ("storage.objects.list",),
        "foundation_object_reader": ("storage.objects.get",),
        "foundation_lock": (
            "storage.objects.create",
            "storage.objects.delete",
            "storage.objects.get",
        ),
        "foundation_state_writer": (
            "storage.objects.create",
            "storage.objects.delete",
        ),
        "foundation_evidence_creator": ("storage.objects.create",),
    }
    for role_name, expected in expected_roles.items():
        actual = custom_role_permissions(authority_text, role_name)
        if actual != expected:
            errors.append(
                f"custom role {role_name} permissions must exactly match {expected}; found {actual}"
            )

    forbidden_authority = (
        'resource "google_service_account_key"',
        "roles/owner",
        "roles/editor",
        "roles/storage.admin",
        "roles/storage.objectAdmin",
        "roles/storage.objectUser",
        "roles/storage.objectCreator",
        "roles/iam.serviceAccountAdmin",
        "roles/iam.serviceAccountTokenCreator",
        "iam.serviceAccounts.delete",
        "iam.serviceAccountKeys.create",
        "iam.serviceAccountKeys.delete",
        "iam.serviceAccounts.setIamPolicy",
        "iam.serviceAccounts.actAs",
        "iam.serviceAccounts.getAccessToken",
        "resourcemanager.projects.setIamPolicy",
    )
    lowered = authority_text.lower()
    for token in forbidden_authority:
        if token.lower() in lowered:
            errors.append(f"Phase 3 authority envelope contains forbidden broad authority: {token}")

    for output_name in (
        "foundation_planner_service_account",
        "foundation_applier_service_account",
        "foundation_plan_workflow_ref",
        "foundation_apply_workflow_ref",
    ):
        if f'output "{output_name}"' not in outputs_text:
            errors.append(f"bootstrap outputs must expose non-sensitive Phase 3 identity: {output_name}")

    if PLANNER_SERVICE_ACCOUNT.split("@", 1)[0] not in authority_text:
        errors.append("foundation planner identity must remain the approved dedicated service account")
    if APPLIER_SERVICE_ACCOUNT.split("@", 1)[0] not in authority_text:
        errors.append("foundation applier identity must remain the approved dedicated service account")
    if PLANNER_WORKFLOW_REF.split("@", 1)[0] not in authority_text:
        errors.append("foundation planner binding must remain tied to the approved reusable workflow path")
    if APPLIER_WORKFLOW_REF.split("@", 1)[0] not in authority_text:
        errors.append("foundation applier binding must remain tied to the approved reusable workflow path")
    if DRIFT_WORKFLOW_REF.split("@", 1)[0] not in authority_text:
        errors.append("foundation drift binding must remain tied to the approved reusable workflow path")


def main() -> int:
    errors: list[str] = []
    check_bootstrap_terraform_identity(errors)
    check_backend(errors)
    check_smoke(errors)
    check_evidence(errors)
    check_phase3_authority(errors)

    validate_workflow = ROOT / ".github/workflows/validate.yml"
    validate_text = require_file(validate_workflow, errors)
    if "python3 scripts/validate_cloud_bootstrap.py" not in validate_text:
        errors.append("repository workflow must invoke cloud bootstrap validation")
    if "${{ secrets." in validate_text or "id-token: write" in validate_text:
        errors.append("repository pull-request validation must remain credential-free")

    if errors:
        print("Cloud bootstrap validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Cloud bootstrap validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
