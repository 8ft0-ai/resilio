#!/usr/bin/env python3
"""Durable GitHub release-record binding for Phase 5 product evidence."""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any

from phase5_supply_chain import (
    COMMENT_ID, GENERATION, GOVERNING_ISSUE, Phase5Error,
    canonical_json_bytes, load_json, validate_release,
)

RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")
RECORD = re.compile(
    r"PHASE5_RELEASE_RECORD_V1 release_id=([0-9a-f]{64}) "
    r"release_generation=([1-9][0-9]{0,19}) run_id=([1-9][0-9]{0,19}) "
    r"run_attempt=1 envelope_b64=([A-Za-z0-9_-]+)"
)


def record_body(envelope: Any, generation: str, run_id: str, run_attempt: int) -> str:
    release_id = validate_release(envelope)
    if not GENERATION.fullmatch(generation) or not RUN_ID.fullmatch(run_id) or run_attempt != 1:
        raise Phase5Error("RELEASE_RECORD_IDENTITY_INVALID")
    encoded = base64.urlsafe_b64encode(canonical_json_bytes(envelope)).decode("ascii").rstrip("=")
    return (
        f"PHASE5_RELEASE_RECORD_V1 release_id={release_id} release_generation={generation} "
        f"run_id={run_id} run_attempt=1 envelope_b64={encoded}"
    )


def validate_record(comment: Any, comment_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    if not COMMENT_ID.fullmatch(comment_id) or not isinstance(comment, dict) or str(comment.get("id")) != comment_id:
        raise Phase5Error("RELEASE_RECORD_COMMENT_INVALID")
    if not str(comment.get("issue_url") or "").endswith(f"/issues/{GOVERNING_ISSUE}"):
        raise Phase5Error("RELEASE_RECORD_ISSUE_MISMATCH")
    match = RECORD.fullmatch(str(comment.get("body") or ""))
    if not match:
        raise Phase5Error("RELEASE_RECORD_BODY_INVALID")
    release_id, generation, run_id, encoded = match.groups()
    try:
        padded = encoded + "=" * ((4 - len(encoded) % 4) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        envelope = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase5Error("RELEASE_RECORD_ENVELOPE_INVALID") from exc
    if canonical_json_bytes(envelope) != raw:
        raise Phase5Error("RELEASE_RECORD_ENVELOPE_NONCANONICAL")
    validate_release(envelope, release_id)
    return envelope, {
        "release_id": release_id,
        "release_generation": generation,
        "run_id": run_id,
        "comment_id": comment_id,
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    commands=parser.add_subparsers(dest="command",required=True)
    p=commands.add_parser("body"); p.add_argument("--release",required=True); p.add_argument("--generation",required=True); p.add_argument("--run-id",required=True); p.add_argument("--run-attempt",type=int,required=True)
    p=commands.add_parser("validate"); p.add_argument("--comment-json",required=True); p.add_argument("--comment-id",required=True); p.add_argument("--output",required=True)
    args=parser.parse_args()
    try:
        if args.command=="body":
            print(record_body(load_json(args.release),args.generation,args.run_id,args.run_attempt))
        else:
            envelope,meta=validate_record(load_json(args.comment_json),args.comment_id)
            Path(args.output).write_bytes(canonical_json_bytes(envelope)+b"\n")
            print(json.dumps(meta,sort_keys=True,separators=(",",":")))
        return 0
    except Phase5Error as exc:
        print(f"PHASE5_RELEASE_RECORD_STOPPED:{exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
