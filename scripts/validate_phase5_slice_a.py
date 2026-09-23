"""Credential-free exact-Slice-A structural safety checks."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
WORKFLOWS={
    "phase5-build-reusable.yml":"github-p5-build@resilio-control-e882d4.iam.gserviceaccount.com",
    "phase5-evidence-reusable.yml":"github-p5-evidence@resilio-control-e882d4.iam.gserviceaccount.com",
    "phase5-deploy-reusable.yml":"github-p5-deployer@resilio-reference-e882d4.iam.gserviceaccount.com",
    "phase5-verify-reusable.yml":"github-p5-acceptance@resilio-reference-e882d4.iam.gserviceaccount.com",
    "phase5-acceptance-reusable.yml":"github-p5-acceptance@resilio-reference-e882d4.iam.gserviceaccount.com",
    "phase5-terraform-plan-reusable.yml":"github-p5-product-planner@resilio-control-e882d4.iam.gserviceaccount.com",
    "phase5-terraform-apply-reusable.yml":"github-p5-product-applier@resilio-control-e882d4.iam.gserviceaccount.com",
}
PHASE4_BLOBS={
".github/workflows/phase4-build-reusable.yml":"0c9666dbd3d8b3aaf6b4e912a09515da4cea4ec7",
".github/workflows/phase4-build.yml":"5f3f66722bef1df3475c371b2459ae92a06774b0",
".github/workflows/phase4-deploy-reconcile-reusable.yml":"3379df57453c57b17dfde1f28e70642bef56e4eb",
".github/workflows/phase4-deploy-reconcile.yml":"89cd8a9700d80bd1d2e28e0a6f9afb3a76c19afc",
".github/workflows/phase4-deploy-reusable.yml":"bbbaf475cba3eeac8aa63bc8909751f7e46c10ac",
".github/workflows/phase4-deploy.yml":"77a2d7b97ec45560ab2f1fdc2024a42e500bafbc",
".github/workflows/phase4-evidence-reusable.yml":"b7cf5d1a345c26a0073e670b1b5bd58a782ea5b5",
".github/workflows/phase4-evidence.yml":"c52e0f3f60a7ff36e7bac91f28e03ccd524ebaf2",
".github/workflows/phase4-revision-transition.yml":"5c9713162ff3ad374e147a34514d66d651c27f18",
".github/workflows/phase4-revision-update-reusable.yml":"7201d7aadd48d1c7f4e84916ee6f611be5f79b9a",
".github/workflows/phase4-revision-verify-reusable.yml":"dc2c0079df21c7dec7f9ab7cdcad8a6488915db6",
"infra/bootstrap/phase4_authority.tf":"dfeec737d25b48a10967085f5f7a9ad8ce63bfa6",
"infra/foundation/resources.tf.json":"4242a7e8f32e713268d53e1baa9afc69fed4ce8d",
"services/phase4-proof/Dockerfile":"fce20f77922b303773b4302d1b421c0aea4d3de9",
"services/phase4-proof/app.py":"1faf98e8cc2d67905c9c896cbc3ae30dccfe6b34",
"services/phase4-proof/test_app.py":"387f5203c9201a84dcabee119c06981f5eb1605d"}
def check():
    errors=[];actual={p.name for p in (ROOT/".github/workflows").glob("phase5-*.yml")}
    if actual != set(WORKFLOWS): errors.append("PHASE5_REUSABLE_SET_MISMATCH")
    for name,principal in WORKFLOWS.items():
        text=(ROOT/".github/workflows"/name).read_text(encoding="utf-8")
        for required in ("on:\n  workflow_call:","actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
                         "repository: ${{ job.workflow_repository }}","ref: ${{ job.workflow_sha }}",
                         "persist-credentials: false",principal):
            if required not in text: errors.append(f"PHASE5_REUSABLE_REQUIRED:{name}:{required}")
        for forbidden in ("\n  workflow_dispatch:","\n  pull_request:","\n  push:","\n  schedule:",
                          "\n  repository_dispatch:","${{ secrets.","permissions: write-all","google_service_account_key"):
            if forbidden in text: errors.append(f"PHASE5_REUSABLE_ACTIVE_OR_SECRET_SURFACE:{name}:{forbidden}")
    build=(ROOT/".github/workflows/phase5-build-reusable.yml").read_text()
    for required in ("group: phase5-product-build-initiation","GITHUB_RUN_ATTEMPT",
                     "PHASE5_BUILD_CREATE_OUTCOME_AMBIGUOUS_RECONCILING",
                     "PHASE5_BUILD_CREATE_OUTCOME_AMBIGUOUS_RECOVERY_REQUIRED"):
        if required not in build: errors.append(f"PHASE5_BUILD_ONCE_BOUNDARY_MISSING:{required}")
    if build.count("phase5_build_select.py") < 2:
        errors.append("PHASE5_BUILD_AMBIGUOUS_RECONCILIATION_MISSING")
    if build.count('-X POST -H "Authorization: Bearer $TOKEN"') != 1:
        errors.append("PHASE5_BUILD_CREATE_PATH_NOT_SINGLE")

    deploy=(ROOT/".github/workflows/phase5-deploy-reusable.yml").read_text()
    for name in ("phase5-terraform-plan-reusable.yml","phase5-terraform-apply-reusable.yml"):
        text=(ROOT/".github/workflows"/name).read_text(encoding="utf-8")
        for required in ("verify-caller","verify-routing-binding","issues: read",
                         "GITHUB_REF","GITHUB_REF_PROTECTED","GITHUB_RUN_ATTEMPT"):
            if required not in text: errors.append(f"PHASE5_TERRAFORM_CALLER_BOUNDARY_MISSING:{name}:{required}")
    verifier=(ROOT/".github/workflows/phase5-verify-reusable.yml").read_text(encoding="utf-8")
    for required in ("routing-binding-body","issues: write","GITHUB_RUN_ATTEMPT",
                     "d5_reconciliation_comment_id","validate-d5-reconciliation"):
        if required not in verifier: errors.append(f"PHASE5_VERIFIER_EVIDENCE_BOUNDARY_MISSING:{required}")
    docker=(ROOT/"services/resilio_app/Dockerfile").read_text(encoding="utf-8")
    if 'ENTRYPOINT ["/usr/bin/python3", "-m", "resilio_app.server"]' not in docker:
        errors.append("PHASE5_PRODUCT_ENTRYPOINT_NOT_MODULE_EXECUTION")
    validation=(ROOT/".github/workflows/validate.yml").read_text(encoding="utf-8")
    if "Smoke-test the built Phase 5 product image" not in validation:
        errors.append("PHASE5_BUILT_IMAGE_SMOKE_MISSING")
    for forbidden in ("run.services.update","run.services.delete","setIamPolicy","PATCH ","DELETE "):
        if forbidden in deploy: errors.append(f"PHASE5_DEPLOY_FORBIDDEN_OPERATION:{forbidden}")
    for service in ("resilio-ingest","resilio-processor","resilio-api"):
        if service not in deploy: errors.append(f"PHASE5_DEPLOY_SERVICE_MISSING:{service}")
    if "serviceId=$SERVICE" not in deploy: errors.append("PHASE5_DEPLOY_CREATE_ID_NOT_BOUND")
    if (ROOT/"infra/product").exists(): errors.append("PHASE5_LIVE_PRODUCT_ROOT_FORBIDDEN_IN_SLICE_A")
    for path,sha in PHASE4_BLOBS.items():
        file=ROOT/path
        if not file.is_file(): errors.append(f"RETAINED_PHASE4_FILE_MISSING:{path}");continue
        actual_sha=subprocess.run(["git","hash-object",str(file)],cwd=ROOT,check=True,text=True,capture_output=True).stdout.strip()
        if actual_sha != sha: errors.append(f"RETAINED_PHASE4_BLOB_CHANGED:{path}")
    required=("scripts/phase5_supply_chain.py","scripts/phase5_release_record.py","scripts/phase5_build_select.py",
              "scripts/phase5_terraform_control.py","scripts/phase5_acceptance_fixture.py","services/resilio_app/server.py",
              "tests/test_phase5_product.py","tests/test_phase5_control.py","controls/phase5-product-terraform/backend.tf",
              "controls/phase5-product-terraform/provider.tf","controls/phase5-product-terraform/versions.tf",
              "controls/phase5-product-terraform/.terraform.lock.hcl")
    for path in required:
        if not (ROOT/path).is_file(): errors.append(f"PHASE5_REQUIRED_PATH_MISSING:{path}")
    schema=json.loads((ROOT/"schemas/phase5/deployment-observed-v1.schema.json").read_text())
    if schema.get("additionalProperties") is not False: errors.append("PHASE5_SCHEMA_NOT_CLOSED")
    if errors: raise SystemExit("\n".join(errors))
    print("Phase 5 Slice A trusted-control validation passed.")
if __name__=="__main__": check()
