#!/usr/bin/env python3
"""CLI and stable import surface for Resilio Phase 3 Terraform control."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from terraform_control_core import *
from terraform_control_remote import *


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    p = commands.add_parser("validate-candidate"); p.add_argument("--file", required=True); p.add_argument("--canonical-output")
    p = commands.add_parser("fetch-candidate"); p.add_argument("--repository", default=REPOSITORY); p.add_argument("--sha", required=True); p.add_argument("--output", required=True)
    p = commands.add_parser("verify-pr"); p.add_argument("--repository", default=REPOSITORY); p.add_argument("--pr-number", type=int, required=True); p.add_argument("--head-sha", required=True); p.add_argument("--base-sha", required=True); p.add_argument("--merge-sha"); p.add_argument("--require-open", action="store_true"); p.add_argument("--require-merged", action="store_true"); p.add_argument("--allowed-file", action="append", required=True)
    p = commands.add_parser("verify-main"); p.add_argument("--repository", default=REPOSITORY); p.add_argument("--sha", required=True)
    p = commands.add_parser("assemble"); p.add_argument("--trusted-root", required=True); p.add_argument("--candidate", required=True); p.add_argument("--output", required=True)
    p = commands.add_parser("state-identity"); p.add_argument("--state-json", required=True); p.add_argument("--generation", required=True); p.add_argument("--output", required=True)
    p = commands.add_parser("build-effect"); p.add_argument("--plan-json", required=True); p.add_argument("--state-identity", required=True); p.add_argument("--pr-number", type=int, required=True); p.add_argument("--base-sha", required=True); p.add_argument("--candidate-sha", required=True); p.add_argument("--candidate-digest", required=True); p.add_argument("--trusted-workflow-sha", required=True); p.add_argument("--trusted-tree-digest", required=True); p.add_argument("--provider-lock-digest", required=True); p.add_argument("--workflow-run-id", required=True); p.add_argument("--evidence-object"); p.add_argument("--private-output", required=True); p.add_argument("--public-output", required=True)
    p = commands.add_parser("compare-effect"); p.add_argument("--expected", required=True); p.add_argument("--actual", required=True)
    p = commands.add_parser("gcs-metadata"); p.add_argument("--bucket", default=STATE_BUCKET); p.add_argument("--object", required=True); p.add_argument("--allow-absent", action="store_true")
    p = commands.add_parser("gcs-upload"); p.add_argument("--bucket", default=STATE_BUCKET); p.add_argument("--object", required=True); p.add_argument("--file", required=True)
    p = commands.add_parser("gcs-download"); p.add_argument("--bucket", default=STATE_BUCKET); p.add_argument("--object", required=True); p.add_argument("--output", required=True)
    return root


def run(args: argparse.Namespace) -> None:
    cmd = args.command
    if cmd == "validate-candidate":
        doc = validate_candidate_file(Path(args.file))
        if args.canonical_output:
            Path(args.canonical_output).write_bytes(canonical_json_bytes(doc) + b"\n")
    elif cmd == "fetch-candidate":
        print(json.dumps(fetch_candidate(args.repository, args.sha, Path(args.output)), sort_keys=True, separators=(",", ":")))
    elif cmd == "verify-pr":
        print(json.dumps(verify_pr(repository=args.repository, pr_number=args.pr_number, head_sha=args.head_sha,
                                   base_sha=args.base_sha, require_open=args.require_open,
                                   require_merged=args.require_merged, allowed_files=args.allowed_file,
                                   expected_merge_sha=args.merge_sha), sort_keys=True, separators=(",", ":")))
    elif cmd == "verify-main":
        verify_main(args.repository, args.sha)
    elif cmd == "assemble":
        print(json.dumps(assemble_workdir(Path(args.trusted_root), Path(args.candidate), Path(args.output)), sort_keys=True, separators=(",", ":")))
    elif cmd == "state-identity":
        state = load_json_strict(Path(args.state_json))
        if not isinstance(state, dict):
            raise ControlError("STATE_JSON_ROOT_INVALID")
        write_json(Path(args.output), state_identity_from_state(state, args.generation))
    elif cmd == "build-effect":
        state, plan = load_json_strict(Path(args.state_identity)), load_json_strict(Path(args.plan_json))
        if not isinstance(state, dict) or not isinstance(plan, dict):
            raise ControlError("EFFECT_INPUT_INVALID")
        effect = build_private_effect(plan=plan, state_identity=state, pr_number=args.pr_number,
                                      base_sha=args.base_sha, candidate_sha=args.candidate_sha,
                                      candidate_digest=args.candidate_digest, trusted_workflow_sha=args.trusted_workflow_sha,
                                      trusted_tree_digest=args.trusted_tree_digest, provider_lock_digest=args.provider_lock_digest)
        write_json(Path(args.private_output), effect)
        write_json(Path(args.public_output), public_manifest(effect, workflow_run_id=args.workflow_run_id,
                                                             evidence_object=args.evidence_object))
    elif cmd == "compare-effect":
        left, right = load_json_strict(Path(args.expected)), load_json_strict(Path(args.actual))
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise ControlError("PRIVATE_EFFECT_INVALID")
        compare_private_effects(left, right)
    elif cmd == "gcs-metadata":
        meta = gcs_metadata(args.bucket, args.object, args.allow_absent)
        print("ABSENT" if meta is None else json.dumps({key: meta.get(key) for key in ("bucket", "name", "generation", "metageneration")}, sort_keys=True, separators=(",", ":")))
    elif cmd == "gcs-upload":
        value = load_json_strict(Path(args.file))
        if not isinstance(value, dict):
            raise ControlError("PRIVATE_EVIDENCE_INVALID")
        meta = gcs_upload_json_once(args.bucket, args.object, value)
        print(json.dumps({key: meta.get(key) for key in ("bucket", "name", "generation")}, sort_keys=True, separators=(",", ":")))
    elif cmd == "gcs-download":
        write_json(Path(args.output), gcs_download_json(args.bucket, args.object))


def main() -> int:
    try:
        run(parser().parse_args())
        return 0
    except ControlError as exc:
        print(f"TERRAFORM_CONTROL_STOPPED:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
