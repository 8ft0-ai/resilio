#!/usr/bin/env python3
"""Select at most one already-successful exact Phase 5 build."""
from __future__ import annotations
import argparse, json, sys
from phase5_supply_chain import (
    Phase5Error, build_tags, load_json, validate_build_request_identity,
)


def select(payload, source_sha, workflow_sha):
    rows = payload.get("builds") if isinstance(payload, dict) else None
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise Phase5Error("BUILD_LIST_INVALID")
    matches=[]
    wanted=set(build_tags(source_sha,workflow_sha))
    for build in rows:
        if not isinstance(build,dict):
            raise Phase5Error("BUILD_LIST_ENTRY_INVALID")
        if set(build.get("tags") or []) != wanted:
            continue
        result=validate_build_request_identity(build,source_sha,workflow_sha)
        matches.append(result["build_id"])
    if len(matches)>1:
        raise Phase5Error("EXACT_BUILD_AMBIGUOUS")
    return matches[0] if matches else ""


def main():
    p=argparse.ArgumentParser();p.add_argument("--builds-json",required=True);p.add_argument("--source-sha",required=True);p.add_argument("--workflow-sha",required=True)
    a=p.parse_args()
    try:
        print(select(load_json(a.builds_json),a.source_sha,a.workflow_sha))
        return 0
    except Phase5Error as exc:
        print(f"PHASE5_BUILD_SELECT_STOPPED:{exc}",file=sys.stderr);return 2


if __name__=="__main__": raise SystemExit(main())
