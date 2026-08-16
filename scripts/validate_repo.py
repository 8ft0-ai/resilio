#!/usr/bin/env python3
"""Credential-free baseline validation for the Resilio repository."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

TERRAFORM_VERSION = "1.15.8"
GOOGLE_PROVIDER_VERSION = "7.42.0"
SETUP_TERRAFORM_SHA = "dfe3c3f87815947d99a8997f908cb6525fc44e9e"

REQUIRED_PATHS = (
    "AGENTS.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    ".gitignore",
    ".terraform-version",
    ".github/ISSUE_TEMPLATE/change.md",
    ".github/pull_request_template.md",
    ".github/workflows/validate.yml",
    "docs/adr/README.md",
    "docs/architecture.md",
    "docs/cost-model.md",
    "docs/engineering-model.md",
    "docs/gcp-bootstrap.md",
    "docs/repository-governance.md",
    "docs/roadmap.md",
    "docs/security-and-private-state.md",
    "docs/vision.md",
    "infra/bootstrap/.terraform.lock.hcl",
    "infra/bootstrap/main.tf",
    "infra/bootstrap/outputs.tf",
    "infra/bootstrap/variables.tf",
    "infra/bootstrap/versions.tf",
)

FORBIDDEN_TRACKED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "application_default_credentials.json",
    "terraform.tfstate",
    "terraform.tfstate.backup",
    "terraform.tfvars",
}

FORBIDDEN_BOOTSTRAP_TOKENS = (
    'resource "google_service_account_key"',
    'roles/owner',
    'roles/editor',
    'roles/resourcemanager.projectIamAdmin',
    'roles/storage.admin',
    'roles/compute.admin',
)

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def check_required_paths(errors: list[str]) -> None:
    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).is_file():
            errors.append(f"required repository path is missing: {relative}")


def check_sensitive_filenames(files: list[str], errors: list[str]) -> None:
    for relative in files:
        path = Path(relative)
        name = path.name
        if (
            name in FORBIDDEN_TRACKED_NAMES
            or name.endswith(
                (
                    ".tfstate",
                    ".tfstate.backup",
                    ".tfplan",
                    ".tfvars",
                    ".tfvars.json",
                    ".credentials.json",
                )
            )
            or (name.startswith("gha-creds-") and name.endswith(".json"))
            or (name.startswith("gcp-credentials") and name.endswith(".json"))
        ):
            errors.append(f"sensitive state/config filename must not be tracked: {relative}")


def normalise_link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    return unquote(target)


def check_markdown_links(files: list[str], errors: list[str]) -> None:
    for relative in files:
        if not relative.endswith(".md"):
            continue

        source = ROOT / relative
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"markdown file is not valid UTF-8: {relative}")
            continue

        for raw_target in MARKDOWN_LINK.findall(text):
            target = normalise_link_target(raw_target)
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue

            path_part = target.split("#", 1)[0].split("?", 1)[0]
            if not path_part:
                continue

            candidate = (
                (ROOT / path_part.lstrip("/"))
                if path_part.startswith("/")
                else (source.parent / path_part)
            )
            if not candidate.exists():
                errors.append(f"broken local markdown link in {relative}: {raw_target}")


def check_baseline_workflow(errors: list[str]) -> None:
    workflow = ROOT / ".github/workflows/validate.yml"
    if not workflow.is_file():
        return

    text = workflow.read_text(encoding="utf-8")
    if "permissions:\n  contents: read" not in text:
        errors.append("baseline workflow must declare least-privilege contents: read permissions")
    if "${{ secrets." in text:
        errors.append("baseline workflow must not consume repository/environment secrets")
    if "id-token: write" in text:
        errors.append("baseline pull-request workflow must remain credential-free")
    expected_setup = f"hashicorp/setup-terraform@{SETUP_TERRAFORM_SHA}"
    if expected_setup not in text:
        errors.append("Terraform setup action must be pinned to the approved immutable commit")
    for command in (
        "terraform -chdir=infra/bootstrap fmt -check -recursive",
        "terraform -chdir=infra/bootstrap init -backend=false -input=false -lockfile=readonly",
        "terraform -chdir=infra/bootstrap validate",
    ):
        if command not in text:
            errors.append(f"baseline workflow is missing Terraform validation command: {command}")


def check_terraform_contract(errors: list[str]) -> None:
    version_file = ROOT / ".terraform-version"
    if version_file.is_file() and version_file.read_text(encoding="utf-8").strip() != TERRAFORM_VERSION:
        errors.append(f".terraform-version must pin Terraform {TERRAFORM_VERSION}")

    versions = ROOT / "infra/bootstrap/versions.tf"
    if versions.is_file():
        text = versions.read_text(encoding="utf-8")
        if f'required_version = "= {TERRAFORM_VERSION}"' not in text:
            errors.append("bootstrap Terraform version constraint does not match the repository pin")
        if f'version = "~> {GOOGLE_PROVIDER_VERSION}"' not in text:
            errors.append("bootstrap Google provider constraint does not match the approved provider")

    lock_file = ROOT / "infra/bootstrap/.terraform.lock.hcl"
    if lock_file.is_file():
        text = lock_file.read_text(encoding="utf-8")
        if f'version     = "{GOOGLE_PROVIDER_VERSION}"' not in text:
            errors.append("Terraform lock file does not select the approved Google provider")
        if "h1:" not in text or "zh:" not in text:
            errors.append("Terraform lock file must contain provider integrity hashes")

    bootstrap = ROOT / "infra/bootstrap/main.tf"
    if bootstrap.is_file():
        text = bootstrap.read_text(encoding="utf-8")
        lowered = text.lower()
        for token in FORBIDDEN_BOOTSTRAP_TOKENS:
            if token.lower() in lowered:
                errors.append(f"bootstrap configuration contains forbidden authority/resource token: {token}")

        for nonblocking_guard in (
            'check "project_creation_configuration"',
            'check "precreated_import_parent"',
        ):
            if nonblocking_guard in text:
                errors.append("project bootstrap mode/parent guards must be blocking preconditions, not check blocks")
        if "local.project_creation_configuration_valid" not in text or text.count("precondition {") < 2:
            errors.append("both bootstrap project resources must enforce the blocking project mode/parent precondition")


def main() -> int:
    errors: list[str] = []
    files = tracked_files()

    check_required_paths(errors)
    check_sensitive_filenames(files, errors)
    check_markdown_links(files, errors)
    check_baseline_workflow(errors)
    check_terraform_contract(errors)

    if errors:
        print("Repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Repository validation passed for {len(files)} tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
