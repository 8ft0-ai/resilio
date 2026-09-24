"""Credential-free Phase 5 Slice B authority/state-domain invariants."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL_SHA = "67e61a6c0d4930f8a5c5db545ef84d8430e437bc"
AUTHORITY = ROOT / "infra/bootstrap/phase5_authority.tf"
PHASE4 = ROOT / "infra/bootstrap/phase4_authority.tf"
CANDIDATE = ROOT / "infra/product/candidate.json"

CALLERS = {
    "phase5-build.yml": "phase5-build-reusable.yml",
    "phase5-evidence.yml": "phase5-evidence-reusable.yml",
    "phase5-deploy.yml": "phase5-deploy-reusable.yml",
    "phase5-verify.yml": "phase5-verify-reusable.yml",
    "phase5-acceptance.yml": "phase5-acceptance-reusable.yml",
    "phase5-terraform-plan.yml": "phase5-terraform-plan-reusable.yml",
    "phase5-terraform-apply.yml": "phase5-terraform-apply-reusable.yml",
}

EXPECTED_ACCOUNTS = (
    "github-p5-build",
    "cloudbuild-p5-builder",
    "github-p5-evidence",
    "github-p5-product-planner",
    "github-p5-product-applier",
    "github-p5-deployer",
    "github-p5-acceptance",
    "p5-ingest-runtime",
    "p5-processor-runtime",
    "p5-api-runtime",
    "p5-pubsub-push",
)


def resource_block(text: str, resource_type: str, name: str) -> str:
    marker = f'resource "{resource_type}" "{name}"'
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find('\nresource "', start + len(marker))
    return text[start:] if end < 0 else text[start:end]


def permissions(block: str) -> tuple[str, ...]:
    marker = "permissions = ["
    start = block.find(marker)
    if start < 0:
        one = block.find("permissions = [")
        if one < 0:
            return ()
    end = block.find("\n  ]", start)
    if end < 0:
        # Single-line exact permission list.
        line = next((line for line in block.splitlines() if "permissions =" in line), "")
        if "[" in line and "]" in line:
            raw = line.split("[", 1)[1].rsplit("]", 1)[0]
            return tuple(piece.strip().strip('"') for piece in raw.split(",") if piece.strip())
        return ()
    return tuple(
        line.strip().rstrip(",").strip('"')
        for line in block[start + len(marker):end].splitlines()
        if line.strip()
    )


def require(text: str, tokens: tuple[str, ...], label: str, errors: list[str]) -> None:
    for token in tokens:
        if token not in text:
            errors.append(f"{label}:{token}")


def check() -> None:
    errors: list[str] = []
    if not AUTHORITY.is_file():
        errors.append("PHASE5_AUTHORITY_DECLARATION_MISSING")
        raise SystemExit("\n".join(errors))
    authority = AUTHORITY.read_text(encoding="utf-8")
    phase4 = PHASE4.read_text(encoding="utf-8")

    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    expected_candidate = {
        "contract": "resilio-product-terraform-candidate/v1",
        "processor_uri": None,
        "processor_verification_comment_id": None,
        "stage": "empty",
    }
    if candidate != expected_candidate:
        errors.append("PHASE5_SLICE_B_PRODUCT_ROOT_NOT_EMPTY_DECLARATION")
    if CANDIDATE.read_text(encoding="utf-8") != json.dumps(
        expected_candidate, sort_keys=True, separators=(",", ":")
    ) + "\n":
        errors.append("PHASE5_SLICE_B_CANDIDATE_NOT_CANONICAL")

    require(authority, (
        f'phase5_control_sha = "{CONTROL_SHA}"',
        "product/default.tfstate",
        "product/default.tflock",
        "plan-evidence/product/",
        'account_id   = "github-p5-acceptance"',
        'account_id   = "p5-pubsub-push"',
        'role_id     = "resilio_p5_acceptance_reader"',
        'phase5_product_topic                = "resilio-deployment-events"',
        'phase5_firestore_document_prefix    = "projects/${google_project.reference.project_id}/databases/(default)/documents/"',
        'expression  = "resource.name == \\"${local.phase5_topic_resource}\\""',
        'expression  = "resource.name.startsWith(\\"${local.phase5_firestore_document_prefix}\\")"',
    ), "PHASE5_AUTHORITY_REQUIRED", errors)

    if authority.count('resource "google_service_account"') != len(EXPECTED_ACCOUNTS):
        errors.append("PHASE5_SERVICE_ACCOUNT_SET_COUNT_MISMATCH")
    for account in EXPECTED_ACCOUNTS:
        if authority.count(f'account_id   = "{account}"') != 1:
            errors.append(f"PHASE5_SERVICE_ACCOUNT_IDENTITY_MISMATCH:{account}")

    wif = {
        "github_phase5_build": "phase5_build_workflow_ref",
        "github_phase5_evidence": "phase5_evidence_workflow_ref",
        "github_phase5_deployer": "phase5_deploy_workflow_ref",
        "github_phase5_verifier": "phase5_verify_workflow_ref",
        "github_phase5_acceptance": "phase5_acceptance_workflow_ref",
        "github_phase5_product_planner": "phase5_product_plan_workflow_ref",
        "github_phase5_product_applier": "phase5_product_apply_workflow_ref",
    }
    for name, local in wif.items():
        block = resource_block(authority, "google_service_account_iam_member", name)
        require(block, (
            'role               = "roles/iam.workloadIdentityUser"',
            f"attribute.job_workflow_ref/${{local.{local}}}",
        ), f"PHASE5_WIF:{name}", errors)
    if authority.count('role               = "roles/iam.workloadIdentityUser"') != len(wif):
        errors.append("PHASE5_WIF_BINDING_COUNT_MISMATCH")

    exact_roles = {
        "phase5_deployer": (
            "run.operations.get",
            "run.services.create",
            "run.services.get",
        ),
        "phase5_acceptance_reader": (
            "run.revisions.get",
            "run.services.get",
            "run.services.getIamPolicy",
        ),
        "phase5_ingest_publisher": ("pubsub.topics.publish",),
        "phase5_processor_store": (
            "datastore.entities.create",
            "datastore.entities.get",
        ),
        "phase5_api_store": ("datastore.entities.get",),
        "phase5_control_act_as": ("iam.serviceAccounts.actAs",),
        "phase5_reference_act_as": ("iam.serviceAccounts.actAs",),
    }
    for name, expected in exact_roles.items():
        actual = permissions(resource_block(authority, "google_project_iam_custom_role", name))
        if actual != expected:
            errors.append(f"PHASE5_ROLE_PERMISSIONS_MISMATCH:{name}:{actual}")

    forbidden = (
        'resource "google_service_account_key"',
        'resource "google_artifact_registry_repository"',
        'resource "google_storage_bucket"',
        'resource "google_firestore_database"',
        'resource "google_pubsub_topic"',
        'resource "google_pubsub_subscription"',
        'resource "google_cloud_run_v2_service"',
        'roles/run.invoker',
        'roles/run.servicesInvoker',
        'roles/iam.serviceAccountTokenCreator',
        "run.services.update",
        "run.services.delete",
        "run.services.setIamPolicy",
        "resourcemanager.projects.setIamPolicy",
        "iam.serviceAccountKeys.create",
        "iam.serviceAccountKeys.delete",
        "${{ secrets.",
    )
    for token in forbidden:
        if token in authority:
            errors.append(f"PHASE5_SLICE_B_FORBIDDEN_AUTHORITY_OR_RESOURCE:{token}")

    # No direct project IAM binding may be given to the future acceptance or
    # push identities. Service-level grants are deliberately deferred to D.5.
    for member in (
        'member  = "serviceAccount:${google_service_account.phase5_acceptance.email}"',
        'member  = "serviceAccount:${google_service_account.phase5_pubsub_push.email}"',
    ):
        if member in authority:
            errors.append(f"PHASE5_PREMATURE_PROJECT_AUTHORITY:{member}")

    require(phase4, (
        'title       = "phase4-proof-verifier-only"',
        'resource.name == \\"projects/resilio-reference-e882d4/locations/us-central1/services/phase4-proof\\"',
        'resource.name.startsWith(\\"projects/resilio-reference-e882d4/locations/us-central1/services/phase4-proof/revisions/\\")',
    ), "PHASE4_VERIFIER_NARROWING", errors)

    workflows = ROOT / ".github/workflows"
    actual_callers = {path.name for path in workflows.glob("phase5-*.yml") if "-reusable" not in path.name}
    if actual_callers != set(CALLERS):
        errors.append(f"PHASE5_CALLER_SET_MISMATCH:{sorted(actual_callers)}")
    for caller, reusable in CALLERS.items():
        text = (workflows / caller).read_text(encoding="utf-8")
        require(text, (
            "\n  workflow_dispatch:",
            f"uses: 8ft0-ai/resilio/.github/workflows/{reusable}@{CONTROL_SHA}",
        ), f"PHASE5_CALLER:{caller}", errors)
        for event in ("\n  push:", "\n  pull_request:", "\n  schedule:", "\n  workflow_run:"):
            if event in text:
                errors.append(f"PHASE5_CALLER_AUTOMATIC_TRIGGER:{caller}:{event.strip()}")
        if "${{ secrets." in text:
            errors.append(f"PHASE5_CALLER_SECRET_SURFACE:{caller}")

    if errors:
        raise SystemExit("\n".join(errors))
    print("Phase 5 Slice B authority/state-domain validation passed.")


if __name__ == "__main__":
    check()
