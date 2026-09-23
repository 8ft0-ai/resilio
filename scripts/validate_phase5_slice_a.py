"""Credential-free, exact-Slice-A structural safety checks."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REUSABLE_KINDS = {
    "build": "phase5-build-reusable.yml",
    "evidence": "phase5-evidence-reusable.yml",
    "deploy": "phase5-deploy-reusable.yml",
    "verify": "phase5-verify-reusable.yml",
    "acceptance": "phase5-acceptance-reusable.yml",
    "terraform-plan": "phase5-terraform-plan-reusable.yml",
    "terraform-apply": "phase5-terraform-apply-reusable.yml",
}
PHASE4_BLOBS = {
    ".github/workflows/phase4-build-reusable.yml": "0c9666dbd3d8b3aaf6b4e912a09515da4cea4ec7",
    ".github/workflows/phase4-build.yml": "5f3f66722bef1df3475c371b2459ae92a06774b0",
    ".github/workflows/phase4-deploy-reconcile-reusable.yml": "3379df57453c57b17dfde1f28e70642bef56e4eb",
    ".github/workflows/phase4-deploy-reconcile.yml": "89cd8a9700d80bd1d2e28e0a6f9afb3a76c19afc",
    ".github/workflows/phase4-deploy-reusable.yml": "bbbaf475cba3eeac8aa63bc8909751f7e46c10ac",
    ".github/workflows/phase4-deploy.yml": "77a2d7b97ec45560ab2f1fdc2024a42e500bafbc",
    ".github/workflows/phase4-evidence-reusable.yml": "b7cf5d1a345c26a0073e670b1b5bd58a782ea5b5",
    ".github/workflows/phase4-evidence.yml": "c52e0f3f60a7ff36e7bac91f28e03ccd524ebaf2",
    ".github/workflows/phase4-revision-transition.yml": "5c9713162ff3ad374e147a34514d66d651c27f18",
    ".github/workflows/phase4-revision-update-reusable.yml": "7201d7aadd48d1c7f4e84916ee6f611be5f79b9a",
    ".github/workflows/phase4-revision-verify-reusable.yml": "dc2c0079df21c7dec7f9ab7cdcad8a6488915db6",
    "infra/bootstrap/phase4_authority.tf": "dfeec737d25b48a10967085f5f7a9ad8ce63bfa6",
    "infra/foundation/resources.tf.json": "4242a7e8f32e713268d53e1baa9afc69fed4ce8d",
    "services/phase4-proof/Dockerfile": "fce20f77922b303773b4302d1b421c0aea4d3de9",
    "services/phase4-proof/app.py": "1faf98e8cc2d67905c9c896cbc3ae30dccfe6b34",
    "services/phase4-proof/test_app.py": "387f5203c9201a84dcabee119c06981f5eb1605d"
}


def check() -> None:
    failures = []
    expected = set(REUSABLE_KINDS.values())
    actual = {path.name for path in (ROOT / ".github/workflows").glob("phase5-*.yml")}
    if actual != expected:
        failures.append("PHASE5_WORKFLOW_SET_MISMATCH")
    for kind, name in REUSABLE_KINDS.items():
        path = ROOT / ".github/workflows" / name
        if not path.is_file():
            failures.append(f"PHASE5_WORKFLOW_MISSING:{name}")
            continue
        value = path.read_text(encoding="utf-8")
        if ("on:\n  workflow_call:" not in value or
                "permissions:\n  contents: read" not in value or
                "persist-credentials: false" not in value or
                "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" not in value or
                f"python3 scripts/phase5_control_seed.py {kind}" not in value or
                "exit 1" not in value):
            failures.append(f"PHASE5_INERT_CONTROL_INVALID:{name}")
        for forbidden in (
            "id-token: write", "workflow_dispatch:", "pull_request:", "push:",
            "schedule:", "repository_dispatch:", "google-github-actions/auth",
            "secrets:", "gh api", "curl ", "gcloud ", "terraform plan",
            "terraform apply", "uses: ./", "permissions: write-all",
        ):
            if forbidden in value:
                failures.append(f"PHASE5_ACTIVE_SURFACE_FORBIDDEN:{name}:{forbidden}")
    if (ROOT / "infra/product").exists():
        failures.append("PHASE5_LIVE_TERRAFORM_ROOT_FORBIDDEN_IN_SLICE_A")
    for path, expected_sha in PHASE4_BLOBS.items():
        file = ROOT / path
        if not file.is_file():
            failures.append(f"RETAINED_PHASE4_FILE_MISSING:{path}")
            continue
        actual_sha = subprocess.run(
            ["git", "hash-object", str(file)], check=True, capture_output=True,
            text=True, cwd=ROOT,
        ).stdout.strip()
        if actual_sha != expected_sha:
            failures.append(f"RETAINED_PHASE4_BLOB_CHANGED:{path}")
    if not (ROOT / "schemas/phase5/deployment-observed-v1.schema.json").is_file():
        failures.append("PHASE5_SCHEMA_MISSING")
    else:
        schema = json.loads(
            (ROOT / "schemas/phase5/deployment-observed-v1.schema.json").read_text()
        )
        if (schema.get("additionalProperties") is not False or
                schema.get("properties", {}).get("schema_version") != {"const": 1} or
                schema.get("properties", {}).get("event_type") !=
                    {"const": "deployment.observed"}):
            failures.append("PHASE5_CLOSED_SCHEMA_INVALID")
    for required in ("scripts/phase5_control_seed.py", "scripts/phase5_terraform_seed.py",
                     "scripts/phase5_acceptance_fixture.py",
                     "services/resilio_app/server.py", "services/resilio_app/provider.py",
                     "services/resilio_app/core.py", "tests/test_phase5_product.py",
                     "tests/test_phase5_control.py"):
        if not (ROOT / required).is_file():
            failures.append(f"PHASE5_REQUIRED_SEED_PATH_MISSING:{required}")
    if failures:
        raise SystemExit("\n".join(failures))
    print("Phase 5 Slice A inert-seed validation passed.")


if __name__ == "__main__":
    check()
