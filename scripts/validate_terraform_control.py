#!/usr/bin/env python3
"""Credential-free structural validation for the Resilio Phase 3 Terraform control seed."""

from __future__ import annotations

import sys
from pathlib import Path

import terraform_control as control

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"
SETUP_TERRAFORM_SHA = "dfe3c3f87815947d99a8997f908cb6525fc44e9e"
AUTH_SHA = "7c6bc770dae815cd3e89ee6cdf493a5fab2cc093"

EXPECTED_TRUSTED_FILES = {
    "backend.tf": '''terraform {
  backend "gcs" {
    bucket = "resilio-control-e882d4-tfstate"
    prefix = "foundation"
  }
}
''',
    "versions.tf": '''terraform {
  required_version = "= 1.15.8"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.42.0"
    }
  }
}
''',
    "provider.tf": '''provider "google" {
  project = "resilio-reference-e882d4"
}
''',
}

REUSABLE_WORKFLOWS = {
    ".github/workflows/terraform-federation-reusable.yml": {"required": ("workflow_call:", f"actions/checkout@{CHECKOUT_SHA}", f"google-github-actions/auth@{AUTH_SHA}", "repository: ${{ job.workflow_repository }}", "ref: ${{ job.workflow_sha }}")},
    ".github/workflows/terraform-plan-reusable.yml": {"required": ("workflow_call:", f"actions/checkout@{CHECKOUT_SHA}", f"hashicorp/setup-terraform@{SETUP_TERRAFORM_SHA}", f"google-github-actions/auth@{AUTH_SHA}", "repository: ${{ job.workflow_repository }}", "ref: ${{ job.workflow_sha }}", "fetch-candidate", "assemble", "build-effect")},
    ".github/workflows/terraform-apply-reusable.yml": {"required": ("workflow_call:", f"actions/checkout@{CHECKOUT_SHA}", f"hashicorp/setup-terraform@{SETUP_TERRAFORM_SHA}", f"google-github-actions/auth@{AUTH_SHA}", "repository: ${{ job.workflow_repository }}", "ref: ${{ job.workflow_sha }}", "fetch-candidate", "assemble", "compare-effect")},
}
FORBIDDEN_TRIGGERS = ("workflow_dispatch:", "pull_request:", "pull_request_target:", "workflow_run:", "\npush:", "\nschedule:")


def check_foundation_contract(errors: list[str]) -> None:
    root = ROOT / control.FOUNDATION_ROOT
    for name, expected in EXPECTED_TRUSTED_FILES.items():
        path = root / name
        if not path.is_file():
            errors.append(f"foundation trusted file missing: {name}")
        elif path.read_text(encoding="utf-8") != expected:
            errors.append(f"foundation trusted file drifted from closed contract: {name}")
    lock_path = root / ".terraform.lock.hcl"
    if not lock_path.is_file():
        errors.append("foundation provider lock file missing")
    else:
        text = lock_path.read_text(encoding="utf-8")
        if 'provider "registry.terraform.io/hashicorp/google"' not in text or text.count('provider "registry.terraform.io/') != 1:
            errors.append("foundation lock file may contain only the approved Google provider")
        if 'version     = "7.42.0"' not in text or 'constraints = "~> 7.42.0"' not in text:
            errors.append("foundation lock file must select Google provider 7.42.0")
        if "h1:" not in text or "zh:" not in text:
            errors.append("foundation lock file must retain provider integrity hashes")
    candidate = root / "resources.tf.json"
    if not candidate.is_file():
        errors.append("foundation candidate payload file missing")
    else:
        try:
            control.validate_candidate_file(candidate)
        except control.ControlError as exc:
            errors.append(f"foundation candidate payload invalid: {exc}")


def check_reusable_workflows(errors: list[str]) -> None:
    for relative, contract in REUSABLE_WORKFLOWS.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"trusted reusable workflow missing: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for required in contract["required"]:
            if required not in text:
                errors.append(f"{relative} missing required trusted-workflow token: {required}")
        for forbidden in FORBIDDEN_TRIGGERS:
            if forbidden in text:
                errors.append(f"{relative} must remain workflow_call-only; found {forbidden.strip()}")
        if "persist-credentials: false" not in text:
            errors.append(f"{relative} must disable persisted checkout credentials")
        if "permissions:\n  contents: read\n  id-token: write" not in text:
            errors.append(f"{relative} must declare only contents:read plus id-token:write")
        if "${{ secrets." in text:
            errors.append(f"{relative} must not consume long-lived repository/environment secrets")
    federation = ROOT / ".github/workflows/terraform-federation-reusable.yml"
    if federation.is_file():
        text = federation.read_text(encoding="utf-8")
        if any(account not in text for account in control.ALLOWED_SERVICE_ACCOUNTS):
            errors.append("federation reusable workflow must fail closed to the explicit service-account allowlist")
    for name in (".github/workflows/terraform-plan-reusable.yml", ".github/workflows/terraform-apply-reusable.yml"):
        path = ROOT / name
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if "github-foundation-" not in text:
                errors.append(f"{name} must bind to the dedicated foundation automation identity")
            if "gha-creds-" in text and "rm -f" not in text:
                errors.append(f"{name} must explicitly clean generated WIF credential files")


def check_script_contract(errors: list[str]) -> None:
    paths = [ROOT / "scripts/terraform_control.py", ROOT / "scripts/terraform_control_core.py", ROOT / "scripts/terraform_control_remote.py"]
    for path in paths + [ROOT / "scripts/validate_terraform_control.py"]:
        if not path.is_file():
            errors.append(f"Terraform control script missing: {path.relative_to(ROOT)}")
    if not all(path.is_file() for path in paths):
        return
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for forbidden in ("subprocess.run(", "os.system(", "shell=True", "eval(", "exec("):
        if forbidden in text:
            errors.append(f"Terraform control code must not execute candidate-controlled code: {forbidden}")
    for required in ("object_pairs_hook=_reject_duplicate_pairs", "CANDIDATE_PATH", "SENTINEL_CONFIGURATION_MISMATCH", "MATERIAL_EFFECT_MISMATCH", "ifGenerationMatch"):
        if required not in text:
            errors.append(f"Terraform control code missing required fail-closed control: {required}")


def check_documentation(errors: list[str]) -> None:
    path = ROOT / "docs/terraform-control-model.md"
    if not path.is_file():
        errors.append("Terraform control model documentation missing")
        return
    text = path.read_text(encoding="utf-8").lower()
    for required in ("slice a", "workflow_call", "resources.tf.json", "job.workflow_sha", "private", "foundation/default.tfstate", "no cloud authority"):
        if required not in text:
            errors.append(f"Terraform control model documentation missing required concept: {required}")


def main() -> int:
    errors: list[str] = []
    check_foundation_contract(errors)
    check_reusable_workflows(errors)
    check_script_contract(errors)
    check_documentation(errors)
    if errors:
        print("Terraform control validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Terraform control validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
