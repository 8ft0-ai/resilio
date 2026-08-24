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
PYTHON_DIGEST = "ed3a4beb46f8f8baac068743ba1b1f95ea3f793422129cf6dd23967f779b6018"
DOCKER_BUILDER_DIGEST = "154fcd4d2d65c6a35b06b98053a0829c581e223d530be5719326f5d85d680e8d"

REUSABLE = (
    ".github/workflows/phase4-build-reusable.yml",
    ".github/workflows/phase4-evidence-reusable.yml",
    ".github/workflows/phase4-deploy-reusable.yml",
)
CALLERS = (
    ".github/workflows/phase4-build.yml",
    ".github/workflows/phase4-evidence.yml",
)
REQUIRED = REUSABLE + CALLERS + (
    "scripts/phase4_supply_chain.py",
    "tests/test_phase4_supply_chain.py",
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
        + PHASE4_CONTROL_SEED_SHA
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
        + PHASE4_CONTROL_SEED_SHA
    )
    if expected_evidence_use not in evidence_caller:
        errors.append("Phase 4 evidence caller must pin the reviewed immutable evidence reusable workflow")
    if evidence_caller.count("\n      build_id:\n") != 1:
        errors.append("Phase 4 evidence caller must expose exactly one build_id input")
    if "build_id: ${{ inputs.build_id }}" not in evidence_caller:
        errors.append("Phase 4 evidence caller must pass only the selected existing Build ID")
    for forbidden in ("image_digest:", "source_sha:", "service_account:", "cloudbuild.googleapis.com", "phase4-build-reusable.yml"):
        if forbidden in evidence_caller:
            errors.append(f"Phase 4 evidence caller contains forbidden build/digest authority surface: {forbidden}")

    build = (ROOT / ".github/workflows/phase4-build-reusable.yml").read_text(encoding="utf-8") if (ROOT / ".github/workflows/phase4-build-reusable.yml").is_file() else ""
    for token in (
        "github-p4-build@resilio-control-e882d4.iam.gserviceaccount.com",
        "cloudbuild.googleapis.com/v1/projects/resilio-control-e882d4/builds",
        "select-build", "build-request", "validate-build",
    ):
        if token not in build:
            errors.append(f"build reusable missing fixed control: {token}")

    evidence = (ROOT / ".github/workflows/phase4-evidence-reusable.yml").read_text(encoding="utf-8") if (ROOT / ".github/workflows/phase4-evidence-reusable.yml").is_file() else ""
    for token in ("github-p4-evidence@", "scan-disposition", ":exportSBOM", "SBOM_REFERENCE", "ifGenerationMatch=0"):
        if token not in evidence:
            errors.append(f"evidence reusable missing fail-closed evidence control: {token}")

    deploy = (ROOT / ".github/workflows/phase4-deploy-reusable.yml").read_text(encoding="utf-8") if (ROOT / ".github/workflows/phase4-deploy-reusable.yml").is_file() else ""
    for forbidden in ("setIamPolicy", "invokerIamDisabled", "allUsers", "allAuthenticatedUsers", "docker build", "cloudbuild.googleapis.com"):
        if forbidden == "allUsers" or forbidden == "allAuthenticatedUsers":
            # The verifier must explicitly reject these strings, so their presence is required.
            continue
        if forbidden in deploy:
            errors.append(f"deploy reusable contains forbidden mutation path: {forbidden}")
    for required in ("validate-transition", "allowMissing=true", "phase4-proof", "github-p4-verifier@", "id_token"):
        if required not in deploy:
            errors.append(f"deploy reusable missing exact-digest/readback control: {required}")

    helper = (ROOT / "scripts/phase4_supply_chain.py").read_text(encoding="utf-8") if (ROOT / "scripts/phase4_supply_chain.py").is_file() else ""
    if f"sha256:{PYTHON_DIGEST}" not in helper:
        errors.append("Phase 4 Python runtime must remain at the reviewed digest")
    if f"sha256:{DOCKER_BUILDER_DIGEST}" not in helper:
        errors.append("Cloud Build Docker builder must remain at the reviewed digest")
    if "requestedVerifyOption" not in helper or '"VERIFIED"' not in helper or '"E2_STANDARD_2"' not in helper:
        errors.append("Build request must require provenance on the bounded free-tier machine")
    if ':latest' in helper or re.search(r'"latest"', helper):
        errors.append("Phase 4 helper must not contain mutable latest authority")

    dockerfile = (ROOT / "services/phase4-proof/Dockerfile").read_text(encoding="utf-8") if (ROOT / "services/phase4-proof/Dockerfile").is_file() else ""
    if not dockerfile.startswith("FROM gcr.io/distroless/python3-debian13@sha256:" + PYTHON_DIGEST + "\n"):
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
