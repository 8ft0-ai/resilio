#!/usr/bin/env python3
"""Fail-closed eligibility guard for Phase 4 preserved-build evidence recovery."""
from __future__ import annotations

import argparse
import re
import sys

PRESERVED_RECOVERY_BUILD_ID = "9284412c-6013-4a3b-9a12-30d9cb489dc6"
PRESERVED_RECOVERY_SOURCE_SHA = "58754930316e15c55e1dd25c3ad12df65b011f14"
PRESERVED_RECOVERY_BUILD_CONTROL_SHA = "10e7a938046e2d2d28ffa08a470bf9dfeda40dac"
PRESERVED_RECOVERY_TUPLE = (
    PRESERVED_RECOVERY_BUILD_ID,
    PRESERVED_RECOVERY_SOURCE_SHA,
    PRESERVED_RECOVERY_BUILD_CONTROL_SHA,
)

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
BUILD_ID = re.compile(r"^[0-9a-f-]{8,64}$")


class EvidenceRecoveryError(RuntimeError):
    """Fail-closed evidence-recovery contract violation."""


def require_source_eligibility(
    build_id: str,
    source_sha: str,
    build_control_sha: str,
    current_main_sha: str,
) -> str:
    """Allow current-main evidence or the one explicitly preserved recovery build."""
    if not BUILD_ID.fullmatch(build_id):
        raise EvidenceRecoveryError("BUILD_ID_INVALID")
    for label, value in (
        ("SOURCE", source_sha),
        ("BUILD_CONTROL", build_control_sha),
        ("CURRENT_MAIN", current_main_sha),
    ):
        if not FULL_SHA.fullmatch(value):
            raise EvidenceRecoveryError(f"{label}_SHA_INVALID")

    if source_sha == current_main_sha:
        return "CURRENT_MAIN"

    if (build_id, source_sha, build_control_sha) == PRESERVED_RECOVERY_TUPLE:
        return "PRESERVED_RECOVERY"

    raise EvidenceRecoveryError("STALE_BUILD_NOT_AUTHORISED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--build-control-sha", required=True)
    parser.add_argument("--current-main-sha", required=True)
    args = parser.parse_args()
    try:
        print(
            require_source_eligibility(
                args.build_id,
                args.source_sha,
                args.build_control_sha,
                args.current_main_sha,
            )
        )
        return 0
    except EvidenceRecoveryError as exc:
        print(f"PHASE4_EVIDENCE_RECOVERY_STOPPED:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
