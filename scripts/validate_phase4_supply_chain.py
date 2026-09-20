#!/usr/bin/env python3
"""Credential-free structural validation of the Phase 4 supply-chain controls."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"
AUTH_SHA = "7c6bc770dae815cd3e89ee6cdf493a5fab2cc093"
PHASE4_CONTROL_SEED_SHA = "10e7a938046e2d2d28ffa08a470bf9dfeda40dac"
PHASE4_BUILD_WORKFLOW_SHA = "5a800f8216f52effc216b3ef77f2c95aa20010a5"
PHASE4_EVIDENCE_WORKFLOW_SHA = "b3aebc9b2069b09b0d972a5319df0b1f97a8d8f2"
BUILD_TEST_PYTHON_DIGEST = "ed3a4beb46f8f8baac068743ba1b1f95ea3f793422129cf6dd23967f779b6018"
PROOF_RUNTIME_DIGEST = "f2b206661cee3edb44f132d7f054a9ced96f671d8a973de0db750895c9acb2fb"
DOCKER_BUILDER_DIGEST = "154fcd4d2d65c6a35b06b98053a0829c581e223d530be5719326f5d85d680e8d"
SYFT_VERSION = "1.51.1"
SYFT_ARCHIVE_SHA256 = "8fcb33017a0dc1058298c923c436d19dfa68ae93968e0b423248542e3afb9fc3"

REUSABLE = (
    ".github/workflows/phase4-build-reusable.yml",
    ".github/workflows/phase4-evidence-reusable.yml",
    ".github/workflows/phase4-deploy-reusable.yml",
    ".github/workflows/phase4-deploy-reconcile-reusable.yml",
)
CALLERS = (
    ".github/workflows/phase4-build.yml",
    ".github/workflows/phase4-evidence.yml",
)
DEPLOY_CALLER = ".github/workflows/phase4-deploy.yml"
DEPLOY_RECONCILE_CALLER = ".github/workflows/phase4-deploy-reconcile.yml"
REQUIRED = REUSABLE + CALLERS + (DEPLOY_CALLER, DEPLOY_RECONCILE_CALLER) + (
    "scripts/phase4_supply_chain.py",
    "scripts/phase4_repository_sbom.py",
    "tests/test_phase4_supply_chain.py",
    "tests/test_phase4_repository_sbom.py",
    "tests/test_phase4_evidence_workflow.py",
    "services/phase4-proof/app.py",
    "services/phase4-proof/test_app.py",
    "services/phase4-proof/Dockerfile",
)


def workflow_events(text: str) -> list[str]:
    lines = text.splitlines()
    if lines.count("on:") != 1:
        return ["<invalid>"]
    start = lines.index("on:")
    events = []
    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            break
        if indent == 2 and ":" in line:
            events.append(line.strip().split(":", 1)[0])
    return events


def indented_block(text: str, header: str, indent: int) -> str | None:
    lines = text.splitlines()
    target = " " * indent + header + ":"
    matches = [index for index, line in enumerate(lines) if line == target]
    if len(matches) != 1:
        return None
    start = matches[0]
    block = [lines[start]]
    for line in lines[start + 1:]:
        if line.strip():
            current_indent = len(line) - len(line.lstrip(" "))
            if current_indent <= indent:
                break
        block.append(line)
    return "\n".join(block)


def direct_mapping_keys(block: str | None, indent: int) -> list[str] | None:
    if block is None:
        return None
    keys: list[str] = []
    for line in block.splitlines()[1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        current_indent = len(line) - len(line.lstrip(" "))
        if current_indent == indent + 2 and ":" in line:
            keys.append(line.strip().split(":", 1)[0])
    return keys


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f"missing Phase 4 path: {relative}")

    for relative in REUSABLE:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if workflow_events(text) != ["workflow_call"]:
            errors.append(f"{relative} must remain workflow_call-only")
        if f"actions/checkout@{CHECKOUT_SHA}" not in text:
            errors.append(f"{relative} must pin checkout")
        if f"google-github-actions/auth@{AUTH_SHA}" not in text:
            errors.append(f"{relative} must pin auth")
        if "repository: ${{ job.workflow_repository }}" not in text or "ref: ${{ job.workflow_sha }}" not in text:
            errors.append(f"{relative} must execute trusted code from immutable reusable-workflow identity")
        if "persist-credentials: false" not in text:
            errors.append(f"{relative} must disable persisted checkout credentials")
        if "${{ secrets." in text or "workflow_dispatch:" in text or "pull_request:" in text or "push:" in text:
            errors.append(f"{relative} contains an unauthorised trigger/secret surface")
        if "<<'PY'" in text or '<<"PY"' in text:
            errors.append(f"{relative} must keep embedded decision logic in the reviewed helper, not YAML heredocs")

    caller_text: dict[str, str] = {}
    for relative in CALLERS:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        caller_text[relative] = text
        if workflow_events(text) != ["workflow_dispatch"]:
            errors.append(f"{relative} must remain workflow_dispatch-only")
        if 'run: test "$GITHUB_REF" = "refs/heads/main"' not in text:
            errors.append(f"{relative} must fail closed outside refs/heads/main")
        if "permissions:\n  contents: read" not in text:
            errors.append(f"{relative} must declare least-privilege contents: read permissions")
        if "id-token: write" not in text:
            errors.append(f"{relative} must grant OIDC only to the trusted reusable-workflow job")
        if "${{ secrets." in text or "pull_request:" in text or "push:" in text or "schedule:" in text:
            errors.append(f"{relative} contains an unauthorised trigger/secret surface")

    build_caller = caller_text.get(".github/workflows/phase4-build.yml", "")
    expected_build_use = (
        "uses: 8ft0-ai/resilio/.github/workflows/phase4-build-reusable.yml@"
        + PHASE4_BUILD_WORKFLOW_SHA
    )
    if expected_build_use not in build_caller:
        errors.append("Phase 4 build caller must pin the reviewed immutable build reusable workflow")
    if "inputs:" in build_caller or "with:" in build_caller:
        errors.append("Phase 4 build caller must expose no caller-controlled build inputs")
    for forbidden in ("source_sha", "ref:", "service_account", "image", "substitution", "build_id"):
        if forbidden in build_caller:
            errors.append(f"Phase 4 build caller contains forbidden decision-critical input surface: {forbidden}")

    evidence_caller = caller_text.get(".github/workflows/phase4-evidence.yml", "")
    expected_evidence_use = (
        "uses: 8ft0-ai/resilio/.github/workflows/phase4-evidence-reusable.yml@"
        + PHASE4_EVIDENCE_WORKFLOW_SHA
    )
    if expected_evidence_use not in evidence_caller:
        errors.append("Phase 4 evidence caller must pin the reviewed immutable evidence reusable workflow")

    dispatch_block = indented_block(evidence_caller, "workflow_dispatch", 2)
    if direct_mapping_keys(dispatch_block, 2) != ["inputs"]:
        errors.append("Phase 4 evidence caller workflow_dispatch must expose only the inputs mapping")
    inputs_block = indented_block(dispatch_block or "", "inputs", 4)
    if direct_mapping_keys(inputs_block, 4) != ["build_id"]:
        errors.append("Phase 4 evidence caller must expose exactly one build_id input")
    build_id_block = indented_block(inputs_block or "", "build_id", 6)
    build_id_properties = direct_mapping_keys(build_id_block, 6)
    if (
        build_id_properties is None
        or build_id_properties.count("required") != 1
        or build_id_properties.count("type") != 1
        or build_id_properties.count("description") > 1
        or any(key not in {"description", "required", "type"} for key in build_id_properties)
    ):
        errors.append("Phase 4 evidence build_id input may contain only description, required and type properties")
    if build_id_block is None or "        required: true" not in build_id_block.splitlines():
        errors.append("Phase 4 evidence build_id input must remain required")
    if build_id_block is None or "        type: string" not in build_id_block.splitlines():
        errors.append("Phase 4 evidence build_id input must remain a string")

    with_block = indented_block(evidence_caller, "with", 4)
    if direct_mapping_keys(with_block, 4) != ["build_id"]:
        errors.append("Phase 4 evidence reusable call must pass only build_id")
    if with_block is None or "      build_id: ${{ inputs.build_id }}" not in with_block.splitlines():
        errors.append("Phase 4 evidence caller must pass only the selected existing Build ID")
    for forbidden in ("image_digest:", "source_sha:", "service_account:", "cloudbuild.googleapis.com", "phase4-build-reusable.yml"):
        if forbidden in evidence_caller:
            errors.append(f"Phase 4 evidence caller contains forbidden build/digest authority surface: {forbidden}")

    deploy_caller_path = ROOT / DEPLOY_CALLER
    deploy_caller = deploy_caller_path.read_text(encoding="utf-8") if deploy_caller_path.is_file() else ""
    if workflow_events(deploy_caller) != ["workflow_dispatch"]:
        errors.append("Phase 4 deploy caller must remain workflow_dispatch-only")
    deploy_dispatch = indented_block(deploy_caller, "workflow_dispatch", 2)
    if direct_mapping_keys(deploy_dispatch, 2) != ["inputs"]:
        errors.append("Phase 4 deploy caller workflow_dispatch must expose only the inputs mapping")
    deploy_inputs = indented_block(deploy_dispatch or "", "inputs", 4)
    if direct_mapping_keys(deploy_inputs, 4) != ["authority_comment_id"]:
        errors.append("Phase 4 deploy caller must expose exactly one authority_comment_id input")
    authority_input = indented_block(deploy_inputs or "", "authority_comment_id", 6)
    authority_properties = direct_mapping_keys(authority_input, 6)
    if (
        authority_properties is None
        or authority_properties.count("required") != 1
        or authority_properties.count("type") != 1
        or authority_properties.count("description") > 1
        or any(key not in {"description", "required", "type"} for key in authority_properties)
    ):
        errors.append("Phase 4 deploy authority_comment_id may contain only description, required and type properties")
    if authority_input is None or "        required: true" not in authority_input.splitlines():
        errors.append("Phase 4 deploy authority_comment_id must remain required")
    if authority_input is None or "        type: string" not in authority_input.splitlines():
        errors.append("Phase 4 deploy authority_comment_id must remain a string")
    if "run-name: phase4-deploy-authority-" not in deploy_caller or "inputs.authority_comment_id" not in deploy_caller:
        errors.append("Phase 4 deploy caller run name must bind the authority comment ID")
    for token in (
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$GITHUB_REF_PROTECTED" = "true"',
        'test "$GITHUB_RUN_ATTEMPT" = "1"',
        "group: phase4-deployment-authority-control",
        "cancel-in-progress: false",
        "deployment-consumption-available",
        "deployment-consumption-body",
        "verify-deployment-consumption",
        "gh api --paginate --slurp",
        "DEPLOYMENT_CONSUMPTION_CREATE_OUTCOME_AMBIGUOUS_RECONCILE",
    ):
        if token not in deploy_caller:
            errors.append(f"Phase 4 deploy caller missing authority/replay control: {token}")
    if deploy_caller.count("gh api --paginate --slurp") != 2:
        errors.append("Phase 4 deploy caller must completely enumerate comments before and after the one consumption attempt")
    if deploy_caller.count("--method POST") != 1:
        errors.append("Phase 4 deploy caller must attempt exactly one durable authority-consumption POST")
    control_block = indented_block(deploy_caller, "control", 2)
    if control_block is None:
        errors.append("Phase 4 deploy caller control job is missing")
    else:
        for token in ("contents: read", "issues: write"):
            if token not in control_block:
                errors.append(f"Phase 4 deploy control job missing permission: {token}")
        if "id-token: write" in control_block:
            errors.append("Phase 4 deploy authority-control job must not receive OIDC")
        if f"actions/checkout@{CHECKOUT_SHA}" not in control_block or "persist-credentials: false" not in control_block:
            errors.append("Phase 4 deploy authority-control job must use credential-free pinned checkout")
    deploy_call_block = indented_block(deploy_caller, "deploy", 2)
    if deploy_call_block is None:
        errors.append("Phase 4 deploy reusable-call job is missing")
    else:
        expected_deploy_use = (
            "uses: 8ft0-ai/resilio/.github/workflows/phase4-deploy-reusable.yml@"
            "6c630f34e3594600acd51164530d1400554dbc5f"
        )
        if expected_deploy_use not in deploy_call_block:
            errors.append("Phase 4 deploy caller must pin the exact immutable reviewed-candidate reusable identity")
        for token in ("contents: read", "issues: read", "id-token: write"):
            if token not in deploy_call_block:
                errors.append(f"Phase 4 deploy reusable-call job missing permission: {token}")
        with_block = indented_block(deploy_call_block, "with", 4)
        if direct_mapping_keys(with_block, 4) != [
            "authority_comment_id", "release_id", "envelope_commit", "consumption_comment_id"
        ]:
            errors.append("Phase 4 deploy reusable call must pass only validated authority/release/consumption identities")
    for forbidden in (
        "image_digest:",
        "source_sha:",
        "service_account:",
        "runtime_service_account:",
        "region:",
        "traffic:",
        "build_id:",
        "evidence_object:",
        "allowMissing=true",
        "phase4-build-reusable.yml",
    ):
        if forbidden in deploy_caller:
            errors.append(f"Phase 4 deploy caller contains forbidden mutable deployment input/surface: {forbidden}")
    if deploy_caller.count("id-token: write") != 1:
        errors.append("Phase 4 deploy caller must grant OIDC only to the immutable reusable-workflow call")
    if "${{ secrets." in deploy_caller or "pull_request:" in deploy_caller or "push:" in deploy_caller or "schedule:" in deploy_caller:
        errors.append("Phase 4 deploy caller contains an unauthorised trigger/secret surface")

    reconcile_caller_path = ROOT / DEPLOY_RECONCILE_CALLER
    reconcile_caller = reconcile_caller_path.read_text(encoding="utf-8") if reconcile_caller_path.is_file() else ""
    if workflow_events(reconcile_caller) != ["workflow_dispatch"]:
        errors.append("Phase 4 verifier reconciliation caller must remain workflow_dispatch-only")
    reconcile_dispatch = indented_block(reconcile_caller, "workflow_dispatch", 2)
    if direct_mapping_keys(reconcile_dispatch, 2) not in ([], None):
        errors.append("Phase 4 verifier reconciliation caller must expose no inputs")
    for token in (
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$GITHUB_REF_PROTECTED" = "true"',
        'test "$GITHUB_RUN_ATTEMPT" = "1"',
        "group: phase4-deployment-verifier-reconciliation-caller",
        "cancel-in-progress: false",
        "uses: 8ft0-ai/resilio/.github/workflows/phase4-deploy-reconcile-reusable.yml@8ac2f9125d68048a4a86e4edc6ed2fbc544dd738",
        "contents: read",
        "issues: read",
        "id-token: write",
    ):
        if token not in reconcile_caller:
            errors.append(f"Phase 4 verifier reconciliation caller missing fixed control: {token}")
    if "inputs:" in reconcile_caller or "with:" in reconcile_caller:
        errors.append("Phase 4 verifier reconciliation caller must accept no caller-controlled values")
    if reconcile_caller.count("id-token: write") != 1:
        errors.append("Phase 4 verifier reconciliation caller must grant OIDC only to the immutable verifier reusable")
    for forbidden in ("github-p4-deployer@", "serviceId=phase4-proof", "-X POST", "-X PATCH", "-X DELETE", "allowMissing=true", "setIamPolicy", "terraform"):
        if forbidden in reconcile_caller:
            errors.append(f"Phase 4 verifier reconciliation caller contains mutation/recovery surface: {forbidden}")

    reconcile = (ROOT / ".github/workflows/phase4-deploy-reconcile-reusable.yml").read_text(encoding="utf-8") if (ROOT / ".github/workflows/phase4-deploy-reconcile-reusable.yml").is_file() else ""
    reconcile_call = indented_block(reconcile, "workflow_call", 2)
    if direct_mapping_keys(reconcile_call, 2) not in ([], None):
        errors.append("Phase 4 verifier reconciliation reusable must expose no inputs")
    for token in (
        "github-p4-verifier@resilio-reference-e882d4.iam.gserviceaccount.com",
        "5749669816", "5749673554", "35509520357",
        "6d5cd26e-5c76-4f17-9d13-3cf1f22a60f4",
        "phase4-proof-00001-9lh",
        "verify-deployment-consumption-comment",
        "validate-deployment-envelope",
        "verify-deployment-service",
        "verify-revision",
        "verify-health",
        "token_format: id_token",
        "PHASE4_DEPLOYMENT_RECONCILIATION_VERIFIED",
        "phase4-deployment-verifier-reconciliation",
    ):
        if token not in reconcile:
            errors.append(f"Phase 4 verifier reconciliation reusable missing read-only control: {token}")
    for forbidden in ("github-p4-deployer@", "serviceId=phase4-proof", "-X POST", "-X PATCH", "-X DELETE", "allowMissing=true", "setIamPolicy", "terraform ", "cloudbuild.googleapis.com"):
        if forbidden in reconcile:
            errors.append(f"Phase 4 verifier reconciliation reusable contains mutation/recovery surface: {forbidden}")

    build = (ROOT / ".github/workflows/phase4-build-reusable.yml").read_text(encoding="utf-8") if (ROOT / ".github/workflows/phase4-build-reusable.yml").is_file() else ""
    for token in (
        "github-p4-build@resilio-control-e882d4.iam.gserviceaccount.com",
        "cloudbuild.googleapis.com/v1/projects/resilio-control-e882d4/builds",
        "select-build", "build-request", "validate-build",
    ):
        if token not in build:
            errors.append(f"build reusable missing fixed control: {token}")

    evidence = (ROOT / ".github/workflows/phase4-evidence-reusable.yml").read_text(encoding="utf-8") if (ROOT / ".github/workflows/phase4-evidence-reusable.yml").is_file() else ""
    for token in (
        "github-p4-evidence@", "scan-disposition", "provenance-occurrence",
        "phase4_repository_sbom.py", "generator-spec", "verify-archive", "verify-version",
        'SYFT_REGISTRY_AUTH_AUTHORITY="us-central1-docker.pkg.dev"',
        'SYFT_REGISTRY_AUTH_USERNAME="oauth2accesstoken"',
        '"$SYFT_BIN" "$IMAGE" \\',
        '-o "spdx-json=$SBOM_CONTENT"',
        '-o "syft-json=$SBOM_SYFT_JSON"',
        "verify-resolved-digest",
        "phase4_repository_sbom.py generation",
        "SBOM_READBACK_METADATA", "SBOM_READBACK_CONTENT",
        "generation=$SBOM_GENERATION",
        "download/storage/v1/b/resilio-control-e882d4-phase4-evidence/o/",
        'SBOM_OBJECT="$(python3 scripts/phase4_repository_sbom.py object --build-id "$BUILD_ID")"',
        "transitions/$BUILD_ID.json", "ifGenerationMatch=0",
        "artifact_analysis_request", "--write-out '%{http_code}'",
        "google-api-response", "--http-status-file", "--curl-exit-code",
        "CURL_STDERR_FILE", '2> "$CURL_STDERR_FILE"',
        "DISCOVERY", "VULNERABILITY", "PROVENANCE",
    ):
        if token not in evidence:
            errors.append(f"evidence reusable missing fail-closed evidence control: {token}")
    for forbidden in (":exportSBOM", "EXPORT_SBOM", "SBOM_REFERENCE", "cloudStorageLocation"):
        if forbidden in evidence:
            errors.append(f"evidence reusable retains provider-native SBOM path: {forbidden}")
    occurrence_helpers = evidence.count("collect_occurrences() {")
    if occurrence_helpers != 2:
        errors.append("Phase 4 evidence must keep occurrence collection in adjudication and evidence jobs")
    if evidence.count('artifact_analysis_request "$REQUEST_CATEGORY"') != occurrence_helpers * 2:
        errors.append("Artifact Analysis occurrence-list calls must use the diagnostic request wrapper")
    if 'RESOURCE_URL="https://$IMAGE"' not in evidence:
        errors.append("Artifact Analysis resource URL must remain bound to the validated immutable image")
    if evidence.count("ifGenerationMatch=0") != 2:
        errors.append("SBOM and transition uploads must both preserve immutable-create semantics")
    if evidence.count('"$SYFT_BIN" "$IMAGE" \\') != 1:
        errors.append("Phase 4 evidence must perform exactly one governed Syft scan")
    if evidence.count("generation=$SBOM_GENERATION") != 2:
        errors.append("SBOM readback metadata and bytes must both target the exact created generation")
    if "syft:latest" in evidence.lower() or "releases/latest" in evidence.lower():
        errors.append("Phase 4 evidence reusable must not contain mutable Syft latest authority")

    repository_sbom = (ROOT / "scripts/phase4_repository_sbom.py").read_text(encoding="utf-8") if (ROOT / "scripts/phase4_repository_sbom.py").is_file() else ""
    for token in (
        f'GENERATOR_VERSION = "{SYFT_VERSION}"',
        f'GENERATOR_ARCHIVE_SHA256 = "{SYFT_ARCHIVE_SHA256}"',
        'GENERATOR_OUTPUT_FORMAT = "spdx-json"',
        'return f"transitions/{build_id}.sbom.spdx.json"',
        "SBOM_IMAGE_DIGEST_INVALID",
        "SBOM_GENERATOR_CHECKSUM_MISMATCH",
        "SBOM_GENERATOR_VERSION_MISMATCH",
        "SBOM_STORAGE_OBJECT_MISMATCH",
        "SBOM_CONTENT_DIGEST_MISMATCH",
        "SBOM_BINDING_DIGEST_MISMATCH",
        "resolved_manifest_digest",
        "SBOM_GENERATOR_MANIFEST_DIGEST_INVALID",
        "SBOM_GENERATOR_MANIFEST_DIGEST_AMBIGUOUS",
        "SBOM_GENERATOR_MANIFEST_DIGEST_MISMATCH",
        "SBOM_STORAGE_READBACK_IDENTITY_MISMATCH",
        "SBOM_STORAGE_READBACK_DIGEST_MISMATCH",
        '"contract": "resilio-phase4-sbom-binding/v2"',
    ):
        if token not in repository_sbom:
            errors.append(f"repository SBOM helper missing immutable/fail-closed control: {token}")
    if ":latest" in repository_sbom or re.search(r'"latest"', repository_sbom):
        errors.append("repository SBOM helper must not contain mutable latest authority")

    deploy = (ROOT / ".github/workflows/phase4-deploy-reusable.yml").read_text(encoding="utf-8") if (ROOT / ".github/workflows/phase4-deploy-reusable.yml").is_file() else ""
    for forbidden in (
        "allowMissing=true",
        "git/ref/heads/main",
        "docker build",
        "cloudbuild.googleapis.com",
        "setIamPolicy",
        "-X PATCH",
        "-X DELETE",
    ):
        if forbidden in deploy:
            errors.append(f"deploy reusable contains superseded/forbidden deployment path: {forbidden}")
    for required in (
        "validate-deployment-envelope",
        "verify-deployment-risk-comments",
        "verify-deployment-consumption-comment",
        "verify-deployment-transition",
        "deployment-create-request",
        "verify-deployment-service",
        "phase4-cloud-run-provider-mutation",
        "GITHUB_RUN_ATTEMPT",
        "serviceId=phase4-proof",
        "-X POST",
        "github-p4-deployer@",
        "github-p4-verifier@",
        "id_token",
        "CREATE_OUTCOME_UNKNOWN",
        "NO_MUTATION_CONFIRMED",
        "deployment-operation-outcome",
        "Reconcile exact known provider operation without mutation",
        "steps.reconcile.outputs.provider_operation",
    ):
        if required not in deploy:
            errors.append(f"deploy reusable missing accepted deployment-architecture control: {required}")
    if deploy.count("serviceId=phase4-proof") != 1:
        errors.append("deploy reusable must expose exactly one create-only Cloud Run mutation endpoint")
    if deploy.count("-X POST") != 1:
        errors.append("deploy reusable must contain exactly one provider mutation POST")
    if deploy.count("https://run.googleapis.com/v2/$OPERATION") != 1:
        errors.append("deploy reusable must perform exactly one bounded read-only known-operation reconciliation path")
    if "steps.reconcile.outputs.provider_mutation_disposition" not in deploy or "steps.reconcile.outputs.revision" not in deploy:
        errors.append("deploy reusable job outputs must bind the read-only reconciled operation outcome")
    if "cancel-in-progress: false" not in deploy:
        errors.append("deploy reusable must preserve non-cancelling provider-mutation concurrency")

    helper = (ROOT / "scripts/phase4_supply_chain.py").read_text(encoding="utf-8") if (ROOT / "scripts/phase4_supply_chain.py").is_file() else ""
    if f"sha256:{BUILD_TEST_PYTHON_DIGEST}" not in helper:
        errors.append("Phase 4 Python build-test runtime must remain at the reviewed digest")
    if f"sha256:{DOCKER_BUILDER_DIGEST}" not in helper:
        errors.append("Cloud Build Docker builder must remain at the reviewed digest")
    if "requestedVerifyOption" not in helper or '"VERIFIED"' not in helper or '"E2_STANDARD_2"' not in helper:
        errors.append("Build request must require provenance on the bounded free-tier machine")
    if ':latest' in helper or re.search(r'"latest"', helper):
        errors.append("Phase 4 helper must not contain mutable latest authority")
    for required in (
        "resilio-phase4-deployment-envelope/v1",
        "PHASE4_DEPLOYMENT_AUTHORISED_V1",
        "PHASE4_DEPLOYMENT_AUTHORITY_CONSUMED_V2",
        "DEPLOYMENT_ENVELOPE_NOT_CANONICAL",
        "DEPLOYMENT_RELEASE_ID_MISMATCH",
        "DEPLOYMENT_RUN_ATTEMPT_NOT_FIRST",
        "DEPLOYMENT_CONSUMPTION_NOT_UNIQUE",
        "DEPLOYMENT_TRANSITION_BINDING_MISMATCH",
        "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST",
        "DEPLOYMENT_TRAFFIC_MISMATCH",
        "DEPLOYMENT_RECONCILIATION_MISMATCH",
        "DEPLOYMENT_PUBLIC_PRINCIPAL_FORBIDDEN",
    ):
        if required not in helper:
            errors.append(f"Phase 4 helper missing deployment-envelope/authority control: {required}")

    dockerfile = (ROOT / "services/phase4-proof/Dockerfile").read_text(encoding="utf-8") if (ROOT / "services/phase4-proof/Dockerfile").is_file() else ""
    if not dockerfile.startswith("FROM gcr.io/distroless/python3-debian13@sha256:" + PROOF_RUNTIME_DIGEST + "\n"):
        errors.append("proof Dockerfile must use the exact reviewed distroless digest")
    for forbidden in (" apt ", "apk ", "pip ", "curl ", ":latest"):
        if forbidden in dockerfile.lower():
            errors.append(f"proof Dockerfile contains mutable/package-install surface: {forbidden}")
    if "USER 65532:65532" not in dockerfile:
        errors.append("proof image must run non-root")

    validate = ROOT / ".github/workflows/validate.yml"
    if not validate.is_file():
        errors.append("repository validation workflow is missing")
    else:
        validate_text = validate.read_text(encoding="utf-8")
        for command in (
            "python3 scripts/validate_phase4_supply_chain.py",
            "python3 services/phase4-proof/test_app.py",
        ):
            if command not in validate_text:
                errors.append(f"repository validation is missing Phase 4 command: {command}")
        if "id-token: write" in validate_text or "${{ secrets." in validate_text:
            errors.append("ordinary repository validation must remain credential-free")

    if errors:
        print("Phase 4 supply-chain validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Phase 4 supply-chain control validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
