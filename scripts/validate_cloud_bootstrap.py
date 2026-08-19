#!/usr/bin/env python3
"""Credential-free validation of the canonical Gate C cloud bootstrap contract."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BACKEND = ROOT / "infra/bootstrap/backend.tf"
SMOKE = ROOT / ".github/workflows/federation-smoke.yml"
EVIDENCE = ROOT / "docs/gcp-bootstrap-evidence.md"

CONTROL_SEED_SHA = "cbfe9821ec07ca6c0c869ebe75100bc500c92a04"
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
GITHUB_SUBJECT = (
    "repo:8ft0-ai@130460431/resilio@1335801159:ref:refs/heads/main"
)

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
    "  id-token: write\n"
    "\n"
    "jobs:\n"
    "  authenticate:\n"
    "    name: trusted-main-auth\n"
    "    if: github.ref == 'refs/heads/main'\n"
    f"    uses: 8ft0-ai/resilio/.github/workflows/terraform-federation-reusable.yml@{CONTROL_SEED_SHA}\n"
    "    with:\n"
    f"      service_account: {PROBE_SERVICE_ACCOUNT}\n"
    "      token_lifetime: 300s\n"
)


def require_file(path: Path, errors: list[str]) -> str:
    if not path.is_file():
        errors.append(f"required Gate C path is missing: {path.relative_to(ROOT)}")
        return ""
    return path.read_text(encoding="utf-8")


def check_backend(errors: list[str]) -> None:
    text = require_file(BACKEND, errors)
    if not text:
        return

    if text != EXPECTED_BACKEND:
        errors.append(
            "canonical backend must contain exactly the approved GCS bucket/prefix and no other backend settings"
        )


def check_smoke(errors: list[str]) -> None:
    text = require_file(SMOKE, errors)
    if not text:
        return

    if text != EXPECTED_SMOKE:
        errors.append(
            "federation smoke must exactly match the approved manual trusted-main authentication-only reusable-workflow caller pinned to the immutable control seed"
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

    forbidden = (
        "billingAccounts/",
        "application_default_credentials",
        '"private_key"',
        '"access_token"',
    )
    for token in forbidden:
        if token in text:
            errors.append(f"Gate C evidence contains forbidden private material marker: {token}")


def main() -> int:
    errors: list[str] = []
    check_backend(errors)
    check_smoke(errors)
    check_evidence(errors)

    validate_workflow = ROOT / ".github/workflows/validate.yml"
    validate_text = require_file(validate_workflow, errors)
    if "python3 scripts/validate_cloud_bootstrap.py" not in validate_text:
        errors.append("repository workflow must invoke Gate C cloud bootstrap validation")
    if "${{ secrets." in validate_text or "id-token: write" in validate_text:
        errors.append("repository pull-request validation must remain credential-free")

    if errors:
        print("Gate C cloud bootstrap validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Gate C cloud bootstrap validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
