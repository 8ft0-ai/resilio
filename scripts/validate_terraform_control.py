#!/usr/bin/env python3
"""Credential-free validation of Resilio's inert Phase 3 Terraform control seed."""
from __future__ import annotations
import sys
from pathlib import Path
import terraform_control as tc

ROOT=Path(__file__).resolve().parents[1]
WF=(
 ".github/workflows/reusable-foundation-plan.yml",
 ".github/workflows/reusable-foundation-apply.yml",
 ".github/workflows/reusable-federation-smoke.yml",
)
REQ=(
 "infra/foundation/backend.tf","infra/foundation/versions.tf","infra/foundation/provider.tf",
 "infra/foundation/.terraform.lock.hcl","infra/foundation/resources.tf.json",*WF,
 "scripts/terraform_control.py","scripts/validate_terraform_control.py",
 "tests/test_terraform_control.py","docs/terraform-control-model.md",
)
EXPECTED_BACKEND='''terraform {
  backend "gcs" {
    bucket = "resilio-control-e882d4-tfstate"
    prefix = "foundation"
  }
}
'''
EXPECTED_VERSIONS='''terraform {
  required_version = "= 1.15.8"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.42.0"
    }
  }
}
'''
EXPECTED_PROVIDER='''provider "google" {
  project = "resilio-reference-e882d4"
}
'''
ACTIVE=("workflow_dispatch:","pull_request:","pull_request_target:","push:","workflow_run:","schedule:")

def read(path:str,errors:list[str])->str:
    p=ROOT/path
    if not p.is_file():
        errors.append(f"missing Phase 3 control path: {path}"); return ""
    return p.read_text()

def main()->int:
    errors:list[str]=[]
    for p in REQ:
        if not (ROOT/p).is_file(): errors.append(f"missing Phase 3 control path: {p}")
    if read("infra/foundation/backend.tf",errors)!=EXPECTED_BACKEND: errors.append("foundation backend contract changed")
    if read("infra/foundation/versions.tf",errors)!=EXPECTED_VERSIONS: errors.append("foundation version/provider pin changed")
    if read("infra/foundation/provider.tf",errors)!=EXPECTED_PROVIDER: errors.append("foundation trusted provider contract changed")
    lock=read("infra/foundation/.terraform.lock.hcl",errors)
    if 'version     = "7.42.0"' not in lock or 'constraints = "~> 7.42.0"' not in lock or "h1:" not in lock or "zh:" not in lock:
        errors.append("foundation lock file is not the approved 7.42.0 integrity-pinned provider selection")
    try:
        kind,_=tc.validate_candidate_file(ROOT/"infra/foundation/resources.tf.json")
        if kind!="empty": errors.append("Slice A candidate must remain empty; sentinel belongs to final proof")
    except (OSError,tc.ContractError) as exc:
        errors.append(f"foundation candidate contract failed: {exc}")
    for path in WF:
        text=read(path,errors)
        if "\non:\n  workflow_call:" not in "\n"+text: errors.append(f"{path} must be workflow_call-only")
        for marker in ACTIVE:
            if marker in text: errors.append(f"{path} is not inert; found {marker}")
        if "permissions:" not in text: errors.append(f"{path} must declare permissions")
        if "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in text:
            if "repository: ${{ job.workflow_repository }}" not in text or "ref: ${{ job.workflow_sha }}" not in text:
                errors.append(f"{path} must checkout immutable reusable-workflow source")
    for path in WF[:2]:
        text=read(path,errors)
        for token in ("id-token: write","group: terraform-foundation","cancel-in-progress: false","queue: max","token_format: access_token"):
            if token not in text: errors.append(f"{path} missing control: {token}")
    planner=read(WF[0],errors)
    for token in ('CONTROL_SEED_SHA: ${{ job.workflow_sha }}','"control_seed_sha"','"backend_namespace":"foundation/default.tfstate"'):
        if token not in planner: errors.append(f"reusable planner evidence identity missing: {token}")
    planner_sequence=(
        'state pull >"$RUNNER_TEMP/pre-state.json"',
        'plan -input=false -lock-timeout=60s -out="$RUNNER_TEMP/plan"',
        'state pull >"$RUNNER_TEMP/post-state.json"',
        'Terraform state generation changed while planning',
        '--state-json "$RUNNER_TEMP/pre-state.json"',
        '--state-generation "$PRE_G"',
    )
    positions=[planner.find(token) for token in planner_sequence]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        errors.append("reusable planner must bind evidence to a pre-plan state identity and prove unchanged post-plan state")
    for token in (
        "Terraform state lineage changed while planning",
        "Terraform state serial changed while planning",
        "Terraform state generation changed while planning",
    ):
        if token not in planner: errors.append(f"reusable planner missing state-stability guard: {token}")
    applier=read(WF[1],errors)
    for token in ('CONTROL_SEED_SHA: ${{ job.workflow_sha }}','--control-seed-sha "$CONTROL_SEED_SHA"'):
        if token not in applier: errors.append(f"reusable applier reviewed-control guard missing: {token}")
    if 'test "$RH" = "$SHA"' in applier:
        errors.append("reusable applier must not conflate reviewed PR head with desired/main commit")
    identity_sequence=(
        'fetch-candidate --ref "$RH" --output "$RUNNER_TEMP/reviewed-resources.tf.json"',
        'fetch-candidate --ref "$SHA" --expected-blob-sha "$BLOB" --output "$W/resources.tf.json"',
        'cmp "$RUNNER_TEMP/reviewed-resources.tf.json" "$W/resources.tf.json"',
        'validate-candidate --path "$W/resources.tf.json" --require-sentinel',
    )
    positions=[applier.find(token) for token in identity_sequence]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        errors.append("reusable applier must compare exact reviewed-head and desired/main candidate bytes before authentication")
    setup_sequence=(
        "gcs-assert-absent",
        'state pull >"$RUNNER_TEMP/result-state.json"',
        "Initial foundation state contains unexpected resources",
        "Initial foundation state contains unexpected outputs",
        'gcs-metadata >"$RUNNER_TEMP/result-meta.json"',
    )
    positions=[applier.find(token) for token in setup_sequence]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        errors.append("reusable setup must prove newly initialised foundation state is empty before publishing identity")
    apply_sequence=(
        'state pull >"$RUNNER_TEMP/pre-state.json"',
        'plan -input=false -lock-timeout=60s -out="$RUNNER_TEMP/fresh-plan"',
        'state pull >"$RUNNER_TEMP/post-plan-state.json"',
        "Terraform state generation changed while creating fresh apply plan",
        '--state-json "$RUNNER_TEMP/pre-state.json"',
        '--state-generation "$PRE_G"',
        'apply -input=false "$RUNNER_TEMP/fresh-plan"',
    )
    positions=[applier.find(token) for token in apply_sequence]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        errors.append("reusable applier must prove reviewed state stayed unchanged while creating the fresh apply plan")
    for token in (
        "Terraform state lineage changed while creating fresh apply plan",
        "Terraform state serial changed while creating fresh apply plan",
        "Terraform state generation changed while creating fresh apply plan",
    ):
        if token not in applier: errors.append(f"reusable applier missing fresh-plan state-stability guard: {token}")
    helper=read("scripts/terraform_control.py",errors)
    for token in (
        "resource_drift","deferred_changes","deferred_action_invocations","action_invocations",
        '"applyable"','"errored"',"Terraform plan applyability is missing or invalid",
        "Terraform plan is incomplete","Terraform plan is errored",
        "unrecognised Terraform plan structure","control_seed_sha","backend_namespace",
    ):
        if token not in helper: errors.append(f"Terraform effect/evidence helper missing fail-closed control: {token}")
    smoke=read(WF[2],errors)
    for token in ("github-federation-probe@","create_credentials_file: false","export_environment_variables: false"):
        if token not in smoke: errors.append(f"reusable federation proof missing: {token}")
    doc=read("docs/terraform-control-model.md",errors)
    for token in ("repository-only control seed","workflow_call","plan-evidence/foundation/","foundation/default.tfstate","private plan evidence","control seed","phase3-terraform-sentinel","US$10"):
        if token not in doc: errors.append(f"Terraform control documentation missing: {token}")
    if errors:
        print("Phase 3 Terraform control validation failed:",file=sys.stderr)
        for e in errors: print(f"- {e}",file=sys.stderr)
        return 1
    print("Phase 3 Terraform control validation passed.")
    return 0

if __name__=="__main__": raise SystemExit(main())
