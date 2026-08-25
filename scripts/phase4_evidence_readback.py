#!/usr/bin/env python3
"""Evidence-only normalization for Cloud Build provider readback."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import phase4_supply_chain as p4


def normalize_build_readback(build: Any) -> dict[str, Any]:
    """Accept only the exact provider mirror of top-level Build.images."""
    if not isinstance(build, dict):
        raise p4.SupplyChainError("BUILD_INVALID")

    artifacts = build.get("artifacts")
    if artifacts in (None, {}):
        return dict(build)

    images = build.get("images")
    if not isinstance(images, list) or not images:
        raise p4.SupplyChainError("BUILD_ARTIFACTS_MIRROR_MISMATCH")
    if artifacts != {"images": images}:
        raise p4.SupplyChainError("BUILD_ARTIFACTS_MIRROR_MISMATCH")

    normalized = dict(build)
    normalized.pop("artifacts", None)
    return normalized


def validate_build_readback(build: Any, source_sha: str, workflow_sha: str) -> dict[str, str]:
    return p4.validate_build(normalize_build_readback(build), source_sha, workflow_sha)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("--build-json", required=True)
    root.add_argument("--source-sha", required=True)
    root.add_argument("--workflow-sha", required=True)
    return root


def main() -> int:
    try:
        args = parser().parse_args()
        with Path(args.build_json).open(encoding="utf-8") as handle:
            build = json.load(handle)
        result = validate_build_readback(build, args.source_sha, args.workflow_sha)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (json.JSONDecodeError, OSError, p4.SupplyChainError) as exc:
        print(f"PHASE4_EVIDENCE_READBACK_STOPPED:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
