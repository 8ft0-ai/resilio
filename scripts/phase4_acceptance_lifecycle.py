#!/usr/bin/env python3
"""Fail-closed one-shot HIGH-risk acceptance lifecycle helpers for Phase 4."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

OWNER_LOGIN = "8ft0-ai"
OWNER_ID = 130460431
GITHUB_ACTIONS_LOGIN = "github-actions[bot]"
IMAGE_PREFIX = (
    "us-central1-docker.pkg.dev/resilio-control-e882d4/"
    "resilio-phase4/phase4-proof"
)

BUILD_ID_RE = re.compile(r"^[0-9a-f-]{8,64}$")
IMAGE_RE = re.compile(
    rf"^{re.escape(IMAGE_PREFIX)}@sha256:[0-9a-f]{{64}}$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RISK_RE = re.compile(r"^RISK-[0-9]{3}$")
COMMENT_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
RUN_ID_RE = COMMENT_ID_RE

ACCEPTANCE_PREFIX = "PHASE4_HIGH_ACCEPTED_V2"
CONSUMPTION_PREFIX = "PHASE4_HIGH_ACCEPTANCE_CONSUMED_V1"

LEGACY_RISK002_TOKEN_ID = 5592539291
LEGACY_RISK002_BUILD_ID = "16251096-2ad8-40b7-a8d4-6a4bbacb0928"
LEGACY_RISK002_IMAGE = (
    f"{IMAGE_PREFIX}@sha256:"
    "409333b0a48bc3d2c1f8fea8f99c66c64c14c8f9db1469f0349807e91329f60e"
)
LEGACY_RISK002_FINDINGS_SHA256 = (
    "27409ddfbd8b822ec5252cfa8396048fbce7d75f83734ce0384f8f47cccc4e12"
)
LEGACY_RISK002_RISK = "RISK-002"
LEGACY_RISK002_DECISION = 5592538417
LEGACY_RISK002_BODY = f"PHASE4_HIGH_ACCEPTED image={LEGACY_RISK002_IMAGE}"

FINDINGS_CONTRACT = "resilio-phase4-high-critical-findings/v1"


class AcceptanceLifecycleError(RuntimeError):
    """Fail-closed acceptance lifecycle contract violation."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _require_id(value: Any, pattern: re.Pattern[str], label: str) -> str:
    text = str(value)
    if not pattern.fullmatch(text):
        raise AcceptanceLifecycleError(f"{label}_INVALID")
    return text


def _flatten_comments(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_COMMENTS_INVALID")
    values: list[Any] = []
    for item in payload:
        if isinstance(item, list):
            values.extend(item)
        else:
            values.append(item)
    if not all(isinstance(item, dict) for item in values):
        raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_COMMENTS_INVALID")
    return values


def _is_owner(comment: dict[str, Any]) -> bool:
    user = comment.get("user") or {}
    return user.get("login") == OWNER_LOGIN and user.get("id") == OWNER_ID


def _is_consumption_actor(comment: dict[str, Any]) -> bool:
    if _is_owner(comment):
        return True
    user = comment.get("user") or {}
    return user.get("login") == GITHUB_ACTIONS_LOGIN


def _parse_fields(body: str, prefix: str, keys: tuple[str, ...]) -> dict[str, str]:
    parts = body.split(" ")
    if len(parts) != len(keys) + 1 or parts[0] != prefix:
        raise AcceptanceLifecycleError(f"{prefix}_FORMAT_INVALID")
    result: dict[str, str] = {}
    for part, key in zip(parts[1:], keys, strict=True):
        if not part.startswith(key + "="):
            raise AcceptanceLifecycleError(f"{prefix}_FORMAT_INVALID")
        value = part[len(key) + 1 :]
        if not value:
            raise AcceptanceLifecycleError(f"{prefix}_FORMAT_INVALID")
        result[key] = value
    return result


def _validate_tuple(
    *,
    build_id: str,
    image: str,
    findings_sha256: str,
    risk: str,
    decision: str,
) -> dict[str, Any]:
    _require_id(build_id, BUILD_ID_RE, "HIGH_ACCEPTANCE_BUILD_ID")
    if not IMAGE_RE.fullmatch(image):
        raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_IMAGE_INVALID")
    _require_id(findings_sha256, SHA256_RE, "HIGH_ACCEPTANCE_FINDINGS_SHA256")
    _require_id(risk, RISK_RE, "HIGH_ACCEPTANCE_RISK")
    decision_text = _require_id(decision, COMMENT_ID_RE, "HIGH_ACCEPTANCE_DECISION")
    return {
        "build_id": build_id,
        "image": image,
        "findings_sha256": findings_sha256,
        "risk": risk,
        "decision": int(decision_text),
    }


def _parse_v2_acceptance(comment: dict[str, Any]) -> dict[str, Any] | None:
    body = comment.get("body")
    if not isinstance(body, str):
        return None
    if not body.startswith(ACCEPTANCE_PREFIX):
        return None
    if not _is_owner(comment):
        return None
    fields = _parse_fields(
        body,
        ACCEPTANCE_PREFIX,
        ("build", "image", "findings_sha256", "risk", "decision"),
    )
    result = _validate_tuple(
        build_id=fields["build"],
        image=fields["image"],
        findings_sha256=fields["findings_sha256"],
        risk=fields["risk"],
        decision=fields["decision"],
    )
    token_id = _require_id(comment.get("id"), COMMENT_ID_RE, "HIGH_ACCEPTANCE_TOKEN")
    result.update(
        {
            "token_id": int(token_id),
            "body": body,
            "version": 2,
            "historically_valid": True,
        }
    )
    return result


def _parse_legacy_risk002(comment: dict[str, Any]) -> dict[str, Any] | None:
    if comment.get("id") != LEGACY_RISK002_TOKEN_ID:
        return None
    if comment.get("body") != LEGACY_RISK002_BODY or not _is_owner(comment):
        raise AcceptanceLifecycleError("LEGACY_RISK002_ACCEPTANCE_IDENTITY_INVALID")
    return {
        "token_id": LEGACY_RISK002_TOKEN_ID,
        "build_id": LEGACY_RISK002_BUILD_ID,
        "image": LEGACY_RISK002_IMAGE,
        "findings_sha256": LEGACY_RISK002_FINDINGS_SHA256,
        "risk": LEGACY_RISK002_RISK,
        "decision": LEGACY_RISK002_DECISION,
        "body": LEGACY_RISK002_BODY,
        "version": 1,
        "historically_valid": True,
    }


def _parse_consumption(comment: dict[str, Any]) -> dict[str, Any] | None:
    body = comment.get("body")
    if not isinstance(body, str):
        return None
    if not body.startswith(CONSUMPTION_PREFIX):
        return None
    if not _is_consumption_actor(comment):
        return None
    fields = _parse_fields(
        body,
        CONSUMPTION_PREFIX,
        ("token", "build", "image", "findings_sha256", "risk", "decision", "run"),
    )
    result = _validate_tuple(
        build_id=fields["build"],
        image=fields["image"],
        findings_sha256=fields["findings_sha256"],
        risk=fields["risk"],
        decision=fields["decision"],
    )
    token_id = _require_id(fields["token"], COMMENT_ID_RE, "HIGH_ACCEPTANCE_TOKEN")
    run_id = _require_id(fields["run"], RUN_ID_RE, "HIGH_ACCEPTANCE_RUN")
    comment_id = _require_id(comment.get("id"), COMMENT_ID_RE, "HIGH_ACCEPTANCE_CONSUMPTION_COMMENT")
    result.update(
        {
            "token_id": int(token_id),
            "run_id": int(run_id),
            "comment_id": int(comment_id),
            "body": body,
        }
    )
    return result


def _acceptances(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for comment in comments:
        parsed = _parse_v2_acceptance(comment)
        if parsed is not None:
            result.append(parsed)
            continue
        legacy = _parse_legacy_risk002(comment)
        if legacy is not None:
            result.append(legacy)
    return result


def _consumptions(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for comment in comments:
        parsed = _parse_consumption(comment)
        if parsed is not None:
            result.append(parsed)
    return result


def lifecycle_state(
    comments_payload: Any,
    *,
    build_id: str,
    image: str,
    findings_sha256: str,
) -> dict[str, Any]:
    _require_id(build_id, BUILD_ID_RE, "HIGH_ACCEPTANCE_BUILD_ID")
    if not IMAGE_RE.fullmatch(image):
        raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_IMAGE_INVALID")
    _require_id(findings_sha256, SHA256_RE, "HIGH_ACCEPTANCE_FINDINGS_SHA256")

    comments = _flatten_comments(comments_payload)
    acceptances = _acceptances(comments)
    consumptions = _consumptions(comments)
    matches = [
        item
        for item in acceptances
        if item["build_id"] == build_id
        and item["image"] == image
        and item["findings_sha256"] == findings_sha256
    ]
    if len(matches) != 1:
        raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_OWNER_DISPOSITION_INVALID")

    acceptance = matches[0]
    token_consumptions = [
        item for item in consumptions if item["token_id"] == acceptance["token_id"]
    ]
    for item in token_consumptions:
        for key in ("build_id", "image", "findings_sha256", "risk", "decision"):
            if item[key] != acceptance[key]:
                raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_CONSUMPTION_BINDING_CONFLICT")
    if len(token_consumptions) > 1:
        raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_CONSUMPTION_AMBIGUOUS")

    result = {
        "token_id": acceptance["token_id"],
        "build_id": acceptance["build_id"],
        "image": acceptance["image"],
        "findings_sha256": acceptance["findings_sha256"],
        "risk": acceptance["risk"],
        "decision": acceptance["decision"],
        "version": acceptance["version"],
        "historically_valid": True,
    }
    if token_consumptions:
        result.update(
            {
                "status": "REJECTED_AS_ALREADY_CONSUMED",
                "consumption_comment_id": token_consumptions[0]["comment_id"],
                "consumption_run_id": token_consumptions[0]["run_id"],
            }
        )
    elif acceptance["version"] == 1:
        # The only supported legacy token is historical RISK-002. It can be
        # recognised as evidence, but never becomes executable merely because
        # its old body still exists.
        result["status"] = "REJECTED_AS_LEGACY_CONSUMPTION_REQUIRED"
    else:
        result["status"] = "ACCEPTED_FOR_ONE_USE"
    return result


def consumption_body(acceptance: dict[str, Any], run_id: str) -> str:
    if acceptance.get("status") != "ACCEPTED_FOR_ONE_USE":
        raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_NOT_AVAILABLE")
    run = _require_id(run_id, RUN_ID_RE, "HIGH_ACCEPTANCE_RUN")
    return (
        f"{CONSUMPTION_PREFIX} "
        f"token={acceptance['token_id']} "
        f"build={acceptance['build_id']} "
        f"image={acceptance['image']} "
        f"findings_sha256={acceptance['findings_sha256']} "
        f"risk={acceptance['risk']} "
        f"decision={acceptance['decision']} "
        f"run={run}"
    )


def verify_consumed(
    comments_payload: Any,
    *,
    acceptance: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    run = int(_require_id(run_id, RUN_ID_RE, "HIGH_ACCEPTANCE_RUN"))
    state = lifecycle_state(
        comments_payload,
        build_id=acceptance["build_id"],
        image=acceptance["image"],
        findings_sha256=acceptance["findings_sha256"],
    )
    if (
        state["status"] != "REJECTED_AS_ALREADY_CONSUMED"
        or state.get("token_id") != acceptance.get("token_id")
        or state.get("consumption_run_id") != run
    ):
        raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_CONSUMPTION_NOT_CONFIRMED")
    return state


def findings_document(vulnerability_payload: Any) -> dict[str, Any]:
    if not isinstance(vulnerability_payload, dict):
        raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_FINDINGS_INVALID")
    occurrences = vulnerability_payload.get("occurrences") or []
    if not isinstance(occurrences, list):
        raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_FINDINGS_INVALID")
    findings: list[dict[str, Any]] = []
    for occurrence in occurrences:
        if not isinstance(occurrence, dict):
            raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_FINDINGS_INVALID")
        vuln = occurrence.get("vulnerability")
        if not isinstance(vuln, dict):
            continue
        severity = vuln.get("effectiveSeverity") or vuln.get("severity")
        if severity not in {"HIGH", "CRITICAL"}:
            continue
        name = occurrence.get("name")
        note_name = occurrence.get("noteName")
        if not isinstance(name, str) or not name or not isinstance(note_name, str) or not note_name:
            raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_FINDING_IDENTITY_INVALID")
        package_issues = vuln.get("packageIssue") or []
        if not isinstance(package_issues, list):
            raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_FINDINGS_INVALID")
        packages: list[dict[str, Any]] = []
        for issue in package_issues:
            if not isinstance(issue, dict):
                raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_FINDINGS_INVALID")
            packages.append(
                {
                    "affectedPackage": issue.get("affectedPackage"),
                    "affectedVersion": issue.get("affectedVersion"),
                    "fixedVersion": issue.get("fixedVersion"),
                }
            )
        packages.sort(key=canonical_json_bytes)
        findings.append(
            {
                "occurrence": name,
                "noteName": note_name,
                "effectiveSeverity": severity,
                "packageIssue": packages,
            }
        )
    findings.sort(key=canonical_json_bytes)
    if not findings:
        raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_FINDINGS_EMPTY")
    return {"contract": FINDINGS_CONTRACT, "findings": findings}


def findings_sha256(vulnerability_payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(findings_document(vulnerability_payload))).hexdigest()


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(value: Any) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("findings-sha256")
    p.add_argument("--vulnerability-json", required=True)

    p = commands.add_parser("check-available")
    p.add_argument("--comments-json", required=True)
    p.add_argument("--build-id", required=True)
    p.add_argument("--image", required=True)
    p.add_argument("--findings-sha256", required=True)

    p = commands.add_parser("consumption-body")
    p.add_argument("--acceptance-json", required=True)
    p.add_argument("--run-id", required=True)

    p = commands.add_parser("verify-consumed")
    p.add_argument("--comments-json", required=True)
    p.add_argument("--acceptance-json", required=True)
    p.add_argument("--run-id", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "findings-sha256":
            print(findings_sha256(_load_json(args.vulnerability_json)))
        elif args.command == "check-available":
            state = lifecycle_state(
                _load_json(args.comments_json),
                build_id=args.build_id,
                image=args.image,
                findings_sha256=args.findings_sha256,
            )
            if state["status"] != "ACCEPTED_FOR_ONE_USE":
                raise AcceptanceLifecycleError(state["status"])
            _write_json(state)
        elif args.command == "consumption-body":
            print(consumption_body(_load_json(args.acceptance_json), args.run_id))
        elif args.command == "verify-consumed":
            _write_json(
                verify_consumed(
                    _load_json(args.comments_json),
                    acceptance=_load_json(args.acceptance_json),
                    run_id=args.run_id,
                )
            )
        else:  # pragma: no cover
            raise AcceptanceLifecycleError("HIGH_ACCEPTANCE_COMMAND_INVALID")
    except (AcceptanceLifecycleError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"PHASE4_HIGH_ACCEPTANCE_STOPPED:{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
