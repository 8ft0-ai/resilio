#!/usr/bin/env python3
"""Credential-free baseline validation for the Resilio repository."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    "AGENTS.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    ".github/ISSUE_TEMPLATE/change.md",
    ".github/pull_request_template.md",
    ".github/workflows/validate.yml",
    "docs/adr/README.md",
    "docs/architecture.md",
    "docs/cost-model.md",
    "docs/engineering-model.md",
    "docs/repository-governance.md",
    "docs/roadmap.md",
    "docs/security-and-private-state.md",
    "docs/vision.md",
)

FORBIDDEN_TRACKED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "terraform.tfstate",
    "terraform.tfstate.backup",
}

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
        if name in FORBIDDEN_TRACKED_NAMES or name.endswith((".tfstate", ".tfstate.backup")):
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

            candidate = (ROOT / path_part.lstrip("/")) if path_part.startswith("/") else (source.parent / path_part)
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


def main() -> int:
    errors: list[str] = []
    files = tracked_files()

    check_required_paths(errors)
    check_sensitive_filenames(files, errors)
    check_markdown_links(files, errors)
    check_baseline_workflow(errors)

    if errors:
        print("Repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Repository validation passed for {len(files)} tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
