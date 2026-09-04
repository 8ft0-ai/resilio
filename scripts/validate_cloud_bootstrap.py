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
PHASE4_AUTHORITY = BOOTSTRAP_DIR / "phase4_authority.tf"
OUTPUTS = BOOTSTRAP_DIR / "outputs.tf"
SMOKE = ROOT / ".github/workflows/federation-smoke.yml"
FOUNDATION_PLAN = ROOT / ".github/workflows/terraform-foundation-plan.yml"
FOUNDATION_APPLY = ROOT / ".github/workflows/terraform-foundation-apply.yml"
FOUNDATION_DRIFT = ROOT / ".github/workflows/terraform-foundation-drift.yml"
EVIDENCE = ROOT / "docs/gcp-bootstrap-evidence.md"

PHASE3_CONTROL_SEED_SHA = "cbfe9821ec07ca6c0c869ebe75100bc500c92a04"
PHASE3_DRIFT_WORKFLOW_SHA = "2acbc425f688383375f724da7a4d80025dd9cc23"
PHASE4_CONTROL_SEED_SHA = "10e7a938046e2d2d28ffa08a470bf9dfeda40dac"
PHASE4_EVIDENCE_WORKFLOW_SHA = "a9e4832b48cac4ad2e4f916e37aceafe7f93b9aa"
FOUNDATION_DRIFT_CONTROL_SEED_SHA = "af6d0fe6765a1eea36d6000f6a3e465bffc32e50"
PHASE4_DEPLOY_WORKFLOW_SHA = "c70afa19c487f6f8d18720028db8e6379fbeed44"
CONTROL_PROJECT_ID = "resilio-control-e882d4"
CONTROL_PROJECT_NUMBER = "400271474382"
REFERENCE_PROJECT_ID = "resilio-reference-e882d4"
REFERENCE_PROJECT_NUMBER = "144158187163"
STATE_BUCKET = "resilio-control-e882d4-tfstate"
STATE_PREFIX = "bootstrap"
PHASE4_REPOSITORY = "resilio-phase4"
PHASE4_REGION = "us-central1"
PHASE4_EVIDENCE_BUCKET = "resilio-control-e882d4-phase4-evidence"
PHASE4_TRANSITION_PREFIX = (
    "projects/_/buckets/resilio-control-e882d4-phase4-evidence/objects/transitions/"
)
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
    + PHASE4_CONTROL_SEED_SHA
)
APPLIER_WORKFLOW_REF = (
    "8ft0-ai/resilio/.github/workflows/terraform-apply-reusable.yml@"
    + PHASE4_CONTROL_SEED_SHA
)
DRIFT_WORKFLOW_REF = (
    "8ft0-ai/resilio/.github/workflows/terraform-drift-reusable.yml@"
    + FOUNDATION_DRIFT_CONTROL_SEED_SHA
)
PHASE4_BUILD_WORKFLOW_REF = (
    "8ft0-ai/resilio/.github/workflows/phase4-build-reusable.yml@"
    + PHASE4_CONTROL_SEED_SHA
)
PHASE4_EVIDENCE_WORKFLOW_REF = (
    "8ft0-ai/resilio/.github/workflows/phase4-evidence-reusable.yml@"
    + PHASE4_EVIDENCE_WORKFLOW_SHA
)
PHASE4_DEPLOY_WORKFLOW_REF = (
    "8ft0-ai/resilio/.github/workflows/phase4-deploy-reusable.yml@"
    + PHASE4_DEPLOY_WORKFLOW_SHA
)

EXPECTED_BOOTSTRAP_TERRAFORM_BLOBS = {
    "backend.tf": "97127a22fed31347ecadd6bea5f8b097deb6c517",
    "main.tf": "80b0a697e3735c9e0568511dcef58d4c8abdc183",
    "outputs.tf": "7543e62223d83b69e5beeee7c8326cf41f6deedb",
    "phase3_authority.tf": "1a860a038522bad437905e30c1a0fcdb49db000f",
    "phase4_authority.tf": "7b28b02e294bf09411926e07f8fc03d781f7e2bc",
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
    f"    uses: 8ft0-ai/resilio/.github/workflows/terraform-federation-reusable.yml@{PHASE3_CONTROL_SEED_SHA}\n"
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


def resource_block(text: str, resource_type: str, resource_name: str) -> str | None:
    header = f'resource "{resource_type}" "{resource_name}"'
    start = text.find(header)
    if start < 0:
        return None
    end = text.find('\nresource "', start + len(header))
    return text[start:] if end < 0 else text[start:end]


def require_tokens(
    block: str | None, tokens: tuple[str, ...], label: str, errors: list[str]
) -> None:
    if block is None:
        errors.append(f"missing required bootstrap resource: {label}")
        return
    for token in tokens:
        if token not in block:
            errors.append(f"{label} is missing exact contract token: {token}")


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
    block = resource_block(text, "google_project_iam_custom_role", resource_name)
    if block is None:
        return None
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
        f'phase3_control_seed_sha             = "{PHASE3_CONTROL_SEED_SHA}"',
        f'phase3_drift_workflow_sha           = "{PHASE3_DRIFT_WORKFLOW_SHA}"',
        f'foundation_drift_control_seed_sha   = "{FOUNDATION_DRIFT_CONTROL_SEED_SHA}"',
        'account_id   = "github-foundation-planner"',
        'account_id   = "github-foundation-applier"',
        '"8ft0-ai/resilio/.github/workflows/terraform-plan-reusable.yml@${local.phase4_control_seed_sha}"',
        '"8ft0-ai/resilio/.github/workflows/terraform-apply-reusable.yml@${local.phase4_control_seed_sha}"',
        '"8ft0-ai/resilio/.github/workflows/terraform-drift-reusable.yml@${local.foundation_drift_control_seed_sha}"',
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
        "foundation_drift_workflow_ref",
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


def check_phase4_authority(errors: list[str]) -> None:
    text = require_file(PHASE4_AUTHORITY, errors)
    outputs_text = require_file(OUTPUTS, errors)
    if not text or not outputs_text:
        return

    exact_locals = (
        f'phase4_control_seed_sha                  = "{PHASE4_CONTROL_SEED_SHA}"',
        f'phase4_evidence_workflow_sha             = "{PHASE4_EVIDENCE_WORKFLOW_SHA}"',
        'phase4_build_workflow_ref                = "8ft0-ai/resilio/.github/workflows/phase4-build-reusable.yml@${local.phase4_control_seed_sha}"',
        'phase4_evidence_workflow_ref             = "8ft0-ai/resilio/.github/workflows/phase4-evidence-reusable.yml@${local.phase4_evidence_workflow_sha}"',
        f'phase4_deploy_workflow_ref               = "8ft0-ai/resilio/.github/workflows/phase4-deploy-reusable.yml@{PHASE4_DEPLOY_WORKFLOW_SHA}"',
        f'phase4_transition_object_resource_prefix = "{PHASE4_TRANSITION_PREFIX}"',
    )
    for token in exact_locals:
        if token not in text:
            errors.append(f"Phase 4 authority is missing exact activation local: {token}")

    expected_accounts = (
        "github-p4-build",
        "cloudbuild-p4-builder",
        "github-p4-evidence",
        "github-p4-deployer",
        "p4-proof-runtime",
        "github-p4-verifier",
    )
    if text.count('resource "google_service_account"') != len(expected_accounts):
        errors.append("Phase 4 must declare exactly six delivery/runtime service accounts")
    for account_id in expected_accounts:
        if text.count(f'account_id   = "{account_id}"') != 1:
            errors.append(f"Phase 4 authority must declare service account exactly once: {account_id}")

    expected_roles = {
        "phase4_foundation_control_reader": (
            "artifactregistry.locations.get",
            "artifactregistry.locations.list",
            "artifactregistry.repositories.get",
            "artifactregistry.repositories.list",
            "resourcemanager.projects.get",
            "serviceusage.services.get",
            "serviceusage.services.list",
            "storage.buckets.get",
            "storage.buckets.list",
        ),
        "phase4_foundation_control_applier": (
            "artifactregistry.locations.get",
            "artifactregistry.locations.list",
            "artifactregistry.repositories.create",
            "artifactregistry.repositories.get",
            "artifactregistry.repositories.list",
            "artifactregistry.repositories.update",
            "resourcemanager.projects.get",
            "serviceusage.services.enable",
            "serviceusage.services.get",
            "serviceusage.services.list",
            "storage.buckets.create",
            "storage.buckets.get",
            "storage.buckets.list",
            "storage.buckets.update",
        ),
        "phase4_foundation_reference_reader": (
            "resourcemanager.projects.get",
            "serviceusage.services.get",
            "serviceusage.services.list",
        ),
        "phase4_foundation_reference_applier": (
            "resourcemanager.projects.get",
            "serviceusage.services.enable",
            "serviceusage.services.get",
            "serviceusage.services.list",
        ),
        "phase4_build_initiator": (
            "cloudbuild.builds.create",
            "cloudbuild.builds.get",
            "cloudbuild.builds.list",
        ),
        "phase4_builder_logging": (
            "logging.logEntries.create",
            "logging.logEntries.route",
        ),
        "phase4_builder_registry": (
            "artifactregistry.dockerimages.get",
            "artifactregistry.dockerimages.list",
            "artifactregistry.files.download",
            "artifactregistry.files.get",
            "artifactregistry.files.list",
            "artifactregistry.files.update",
            "artifactregistry.files.upload",
            "artifactregistry.packages.get",
            "artifactregistry.packages.list",
            "artifactregistry.packages.update",
            "artifactregistry.repositories.downloadArtifacts",
            "artifactregistry.repositories.get",
            "artifactregistry.repositories.uploadArtifacts",
            "artifactregistry.tags.create",
            "artifactregistry.tags.get",
            "artifactregistry.tags.list",
            "artifactregistry.tags.update",
            "artifactregistry.versions.get",
            "artifactregistry.versions.list",
        ),
        "phase4_evidence_analysis": (
            "cloudbuild.builds.get",
            "containeranalysis.occurrences.create",
            "containeranalysis.occurrences.list",
            "serviceusage.services.use",
        ),
        "phase4_deployer": (
            "run.operations.get",
            "run.services.create",
            "run.services.get",
            "run.services.update",
        ),
        "phase4_verifier": (
            "run.revisions.get",
            "run.routes.invoke",
            "run.services.get",
            "run.services.getIamPolicy",
        ),
        "phase4_evidence_object_creator": ("storage.objects.create",),
        "phase4_evidence_object_reader": ("storage.objects.get",),
    }
    for role_name, expected in expected_roles.items():
        actual = custom_role_permissions(text, role_name)
        if actual != expected:
            errors.append(
                f"Phase 4 custom role {role_name} permissions must exactly match {expected}; found {actual}"
            )

    project_bindings = {
        "foundation_planner_phase4_control": (
            "project = google_project.control.project_id",
            "role    = google_project_iam_custom_role.phase4_foundation_control_reader.name",
            'member  = "serviceAccount:${google_service_account.foundation_planner.email}"',
        ),
        "foundation_applier_phase4_control": (
            "project = google_project.control.project_id",
            "role    = google_project_iam_custom_role.phase4_foundation_control_applier.name",
            'member  = "serviceAccount:${google_service_account.foundation_applier.email}"',
        ),
        "foundation_planner_phase4_reference": (
            "project = google_project.reference.project_id",
            "role    = google_project_iam_custom_role.phase4_foundation_reference_reader.name",
            'member  = "serviceAccount:${google_service_account.foundation_planner.email}"',
        ),
        "foundation_applier_phase4_reference": (
            "project = google_project.reference.project_id",
            "role    = google_project_iam_custom_role.phase4_foundation_reference_applier.name",
            'member  = "serviceAccount:${google_service_account.foundation_applier.email}"',
        ),
        "phase4_build_initiator": (
            "project = google_project.control.project_id",
            "role    = google_project_iam_custom_role.phase4_build_initiator.name",
            'member  = "serviceAccount:${google_service_account.phase4_build_initiator.email}"',
        ),
        "phase4_builder_logging": (
            "project = google_project.control.project_id",
            "role    = google_project_iam_custom_role.phase4_builder_logging.name",
            'member  = "serviceAccount:${google_service_account.phase4_builder.email}"',
        ),
        "phase4_evidence_analysis": (
            "project = google_project.control.project_id",
            "role    = google_project_iam_custom_role.phase4_evidence_analysis.name",
            'member  = "serviceAccount:${google_service_account.phase4_evidence.email}"',
        ),
        "phase4_deployer": (
            "project = google_project.reference.project_id",
            "role    = google_project_iam_custom_role.phase4_deployer.name",
            'member  = "serviceAccount:${google_service_account.phase4_deployer.email}"',
        ),
        "phase4_verifier": (
            "project = google_project.reference.project_id",
            "role    = google_project_iam_custom_role.phase4_verifier.name",
            'member  = "serviceAccount:${google_service_account.phase4_verifier.email}"',
        ),
    }
    for name, tokens in project_bindings.items():
        require_tokens(
            resource_block(text, "google_project_iam_member", name),
            tokens,
            f"google_project_iam_member.{name}",
            errors,
        )
    if text.count('resource "google_project_iam_member"') != len(project_bindings):
        errors.append("Phase 4 must contain exactly nine project IAM bindings")
    if 'member  = "serviceAccount:${google_service_account.phase4_runtime.email}"' in text:
        errors.append("Phase 4 runtime identity must receive zero project roles")

    wif_bindings = {
        "github_phase4_build": (
            "service_account_id = google_service_account.phase4_build_initiator.name",
            'role               = "roles/iam.workloadIdentityUser"',
            "attribute.job_workflow_ref/${local.phase4_build_workflow_ref}",
        ),
        "github_phase4_evidence": (
            "service_account_id = google_service_account.phase4_evidence.name",
            'role               = "roles/iam.workloadIdentityUser"',
            "attribute.job_workflow_ref/${local.phase4_evidence_workflow_ref}",
        ),
        "github_phase4_deployer": (
            "service_account_id = google_service_account.phase4_deployer.name",
            'role               = "roles/iam.workloadIdentityUser"',
            "attribute.job_workflow_ref/${local.phase4_deploy_workflow_ref}",
        ),
        "github_phase4_verifier": (
            "service_account_id = google_service_account.phase4_verifier.name",
            'role               = "roles/iam.workloadIdentityUser"',
            "attribute.job_workflow_ref/${local.phase4_deploy_workflow_ref}",
        ),
    }
    for name, tokens in wif_bindings.items():
        require_tokens(
            resource_block(text, "google_service_account_iam_member", name),
            tokens,
            f"google_service_account_iam_member.{name}",
            errors,
        )

    act_as_bindings = {
        "phase4_build_act_as_builder": (
            "service_account_id = google_service_account.phase4_builder.name",
            'role               = "roles/iam.serviceAccountUser"',
            'member             = "serviceAccount:${google_service_account.phase4_build_initiator.email}"',
        ),
        "phase4_deployer_act_as_runtime": (
            "service_account_id = google_service_account.phase4_runtime.name",
            'role               = "roles/iam.serviceAccountUser"',
            'member             = "serviceAccount:${google_service_account.phase4_deployer.email}"',
        ),
    }
    for name, tokens in act_as_bindings.items():
        require_tokens(
            resource_block(text, "google_service_account_iam_member", name),
            tokens,
            f"google_service_account_iam_member.{name}",
            errors,
        )
    if text.count('resource "google_service_account_iam_member"') != 6:
        errors.append("Phase 4 must contain exactly four WIF and two service-account-user bindings")
    if text.count('role               = "roles/iam.workloadIdentityUser"') != 4:
        errors.append("Phase 4 must contain exactly four immutable reusable-workflow WIF bindings")
    if text.count('role               = "roles/iam.serviceAccountUser"') != 2:
        errors.append("Phase 4 must contain exactly two narrowly scoped serviceAccountUser bindings")

    repository_bindings = {
        "phase4_builder_registry": (
            f'project    = "{CONTROL_PROJECT_ID}"',
            f'location   = "{PHASE4_REGION}"',
            f'repository = "{PHASE4_REPOSITORY}"',
            "role       = google_project_iam_custom_role.phase4_builder_registry.name",
            'member     = "serviceAccount:${google_service_account.phase4_builder.email}"',
        ),
        "phase4_evidence_reader": (
            f'project    = "{CONTROL_PROJECT_ID}"',
            f'location   = "{PHASE4_REGION}"',
            f'repository = "{PHASE4_REPOSITORY}"',
            'role       = "roles/artifactregistry.reader"',
            'member     = "serviceAccount:${google_service_account.phase4_evidence.email}"',
        ),
        "phase4_deployer_reader": (
            f'project    = "{CONTROL_PROJECT_ID}"',
            f'location   = "{PHASE4_REGION}"',
            f'repository = "{PHASE4_REPOSITORY}"',
            'role       = "roles/artifactregistry.reader"',
            'member     = "serviceAccount:${google_service_account.phase4_deployer.email}"',
        ),
        "phase4_cloud_run_service_agent_reader": (
            f'project    = "{CONTROL_PROJECT_ID}"',
            f'location   = "{PHASE4_REGION}"',
            f'repository = "{PHASE4_REPOSITORY}"',
            'role       = "roles/artifactregistry.reader"',
            f'member     = "serviceAccount:service-{REFERENCE_PROJECT_NUMBER}@serverless-robot-prod.iam.gserviceaccount.com"',
        ),
    }
    for name, tokens in repository_bindings.items():
        require_tokens(
            resource_block(text, "google_artifact_registry_repository_iam_member", name),
            tokens,
            f"google_artifact_registry_repository_iam_member.{name}",
            errors,
        )
    if text.count('resource "google_artifact_registry_repository_iam_member"') != 4:
        errors.append("Phase 4 must contain exactly four repository-scoped Artifact Registry bindings")

    bucket_bindings = {
        "phase4_evidence_creator": (
            f'bucket = "{PHASE4_EVIDENCE_BUCKET}"',
            "role   = google_project_iam_custom_role.phase4_evidence_object_creator.name",
            'member = "serviceAccount:${google_service_account.phase4_evidence.email}"',
            'expression  = "resource.name.startsWith(\\"${local.phase4_transition_object_resource_prefix}\\")"',
        ),
        "phase4_evidence_reader": (
            f'bucket = "{PHASE4_EVIDENCE_BUCKET}"',
            "role   = google_project_iam_custom_role.phase4_evidence_object_reader.name",
            'member = "serviceAccount:${google_service_account.phase4_evidence.email}"',
            'expression  = "resource.name.startsWith(\\"${local.phase4_transition_object_resource_prefix}\\")"',
        ),
        "phase4_deployer_evidence_reader": (
            f'bucket = "{PHASE4_EVIDENCE_BUCKET}"',
            "role   = google_project_iam_custom_role.phase4_evidence_object_reader.name",
            'member = "serviceAccount:${google_service_account.phase4_deployer.email}"',
            'expression  = "resource.name.startsWith(\\"${local.phase4_transition_object_resource_prefix}\\")"',
        ),
    }
    for name, tokens in bucket_bindings.items():
        require_tokens(
            resource_block(text, "google_storage_bucket_iam_member", name),
            tokens,
            f"google_storage_bucket_iam_member.{name}",
            errors,
        )
    if text.count('resource "google_storage_bucket_iam_member"') != 3:
        errors.append("Phase 4 must contain exactly three transition-prefix evidence-bucket bindings")

    forbidden = (
        'resource "google_service_account_key"',
        "roles/owner",
        "roles/editor",
        "roles/storage.admin",
        "roles/storage.objectAdmin",
        "roles/storage.objectUser",
        "roles/storage.objectCreator",
        "roles/iam.serviceAccountAdmin",
        "roles/iam.serviceAccountTokenCreator",
        "roles/artifactregistry.admin",
        "roles/artifactregistry.repoAdmin",
        "roles/artifactregistry.writer",
        "roles/run.admin",
        "iam.serviceAccounts.delete",
        "iam.serviceAccountKeys.create",
        "iam.serviceAccountKeys.delete",
        "iam.serviceAccounts.setIamPolicy",
        "iam.serviceAccounts.getAccessToken",
        "iam.serviceAccounts.getOpenIdToken",
        "resourcemanager.projects.setIamPolicy",
        "artifactregistry.repositories.setIamPolicy",
        "artifactregistry.repositories.delete",
        "storage.buckets.setIamPolicy",
        "storage.buckets.delete",
        "storage.objects.delete",
        "run.services.delete",
        "cloudbuild.builds.update",
    )
    lowered = text.lower()
    for token in forbidden:
        if token.lower() in lowered:
            errors.append(f"Phase 4 activation contains forbidden broad or destructive authority: {token}")

    for output_name in (
        "phase4_control_seed_sha",
        "phase4_build_workflow_ref",
        "phase4_evidence_workflow_ref",
        "phase4_deploy_workflow_ref",
        "phase4_build_initiator_service_account",
        "phase4_builder_service_account",
        "phase4_evidence_service_account",
        "phase4_deployer_service_account",
        "phase4_runtime_service_account",
        "phase4_verifier_service_account",
    ):
        if f'output "{output_name}"' not in outputs_text:
            errors.append(f"bootstrap outputs must expose non-sensitive Phase 4 identity: {output_name}")

    for workflow_ref in (
        PHASE4_BUILD_WORKFLOW_REF,
        PHASE4_EVIDENCE_WORKFLOW_REF,
        PHASE4_DEPLOY_WORKFLOW_REF,
    ):
        if workflow_ref.split("@", 1)[0] not in text:
            errors.append(f"Phase 4 activation must preserve immutable workflow path: {workflow_ref}")


def check_foundation_callers(errors: list[str]) -> None:
    expected = {
        FOUNDATION_PLAN: PLANNER_WORKFLOW_REF,
        FOUNDATION_APPLY: APPLIER_WORKFLOW_REF,
        FOUNDATION_DRIFT: DRIFT_WORKFLOW_REF,
    }
    for path, workflow_ref in expected.items():
        text = require_file(path, errors)
        if not text:
            continue
        if f"uses: {workflow_ref}" not in text:
            errors.append(f"{path.relative_to(ROOT)} must call the exact Phase 4 control seed")
        for stale_sha in (PHASE3_CONTROL_SEED_SHA, PHASE3_DRIFT_WORKFLOW_SHA):
            if f"@{stale_sha}" in text:
                errors.append(f"{path.relative_to(ROOT)} still references stale foundation workflow seed {stale_sha}")


def main() -> int:
    errors: list[str] = []
    check_bootstrap_terraform_identity(errors)
    check_backend(errors)
    check_smoke(errors)
    check_evidence(errors)
    check_phase3_authority(errors)
    check_phase4_authority(errors)
    check_foundation_callers(errors)

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