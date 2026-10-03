#!/usr/bin/env python3
"""Fail-closed Phase 5 Slice C reconciliation-only recovery control."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from phase5_supply_chain import OWNER_ID, OWNER_LOGIN
from phase5_terraform_control import (
    BASE_ADDRESSES,
    canonical,
    decode_github_base64,
    validate_candidate,
)

REPOSITORY = "8ft0-ai/resilio"
REPOSITORY_ID = 1335801159
DEFAULT_BRANCH = "main"
GOVERNING_ISSUE = 109
SOURCE_BOUNDARY_COMMENT_ID = 5833629251
SOURCE_BOUNDARY_BODY_SHA256 = "f35b138c15441d8aa6f9e6149f9622a7c8fb936d9159de038d985f34c5a5defa"
RECOVERY_DESIGN_COMMENT_ID = 5963131897
SLICE_C_PR = 112
REVIEWED_HEAD = "f95a8ca2cee97e92617904cf5514c0bf6a708107"
REVIEWED_BASE = "a8c4ed5895fe7333c051bcea2d4bb9994310a62f"
SLICE_C_MERGE = "6b789246337e887fdd57210172a89032cd9ef122"
FAILED_APPLY_RUN = 36143177732
FAILED_APPLY_JOB = 108097723274
NORMAL_CONTROL_SHA = "47b3b17d32ffebf3ce8e9b7d15bc3d3539dc7239"
RECOVERY_REUSABLE_PATH = ".github/workflows/phase5-slice-c-recovery-reusable.yml"
NORMAL_APPLY_CALLER_PATH = ".github/workflows/phase5-terraform-apply.yml"
NORMAL_APPLY_REUSABLE_PATH = ".github/workflows/phase5-terraform-apply-reusable.yml"
CANDIDATE_PATH = "infra/product/candidate.json"

STATE_BUCKET = "resilio-control-e882d4-tfstate"
STATE_OBJECT = "product/default.tfstate"
LOCK_OBJECT = "product/default.tflock"
EXPECTED_GENERATION = "1790344068764582"
EXPECTED_LINEAGE = "d479de40-2c31-d83b-d84b-f55e9301d3a2"
EXPECTED_SERIAL = 2
EXPECTED_ADDRESSES = tuple(sorted(BASE_ADDRESSES))
EVIDENCE_PREFIX = "plan-evidence/product/"

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")


class RecoveryError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryError("JSON_INVALID") from exc


def github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RecoveryError("GITHUB_TOKEN_REQUIRED")
    return token


def google_token() -> str:
    token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN", "")
    if not token:
        raise RecoveryError("GOOGLE_OAUTH_ACCESS_TOKEN_REQUIRED")
    return token


def request_json(
    url: str,
    token: str | None = None,
    method: str = "GET",
    data: bytes | None = None,
    content_type: str | None = None,
) -> Any:
    headers = {"Accept": "application/json", "User-Agent": "resilio-phase5-recovery/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read(512).decode("utf-8", "replace")
        raise RecoveryError(f"HTTP_{exc.code}:{body[:160]}") from exc
    except urllib.error.URLError as exc:
        raise RecoveryError("NETWORK_ERROR") from exc
    return None if not raw else strict_json(raw)


def github(path: str) -> Any:
    return request_json("https://api.github.com" + path, github_token())


def verify_caller_context(
    repository: str,
    ref: str,
    ref_protected: str,
    run_attempt: str,
    activation_sha: str,
    control_sha: str,
) -> None:
    if repository != REPOSITORY:
        raise RecoveryError("CALLER_REPOSITORY_MISMATCH")
    if ref != "refs/heads/main" or ref_protected != "true":
        raise RecoveryError("CALLER_PROTECTED_MAIN_REQUIRED")
    if run_attempt != "1":
        raise RecoveryError("CALLER_FIRST_ATTEMPT_REQUIRED")
    if not FULL_SHA.fullmatch(activation_sha) or not FULL_SHA.fullmatch(control_sha):
        raise RecoveryError("CALLER_SHA_INVALID")
    if activation_sha == control_sha:
        raise RecoveryError("RECOVERY_ACTIVATION_MUST_POSTDATE_CONTROL")


def _record_fields(body: str, header: str, names: tuple[str, ...]) -> dict[str, str]:
    lines = str(body or "").strip().splitlines()
    if len(lines) != len(names) + 1 or lines[0] != header:
        raise RecoveryError(f"{header}_FORMAT_INVALID")
    out: dict[str, str] = {}
    for line, name in zip(lines[1:], names):
        prefix = name + "="
        if not line.startswith(prefix) or not line[len(prefix):]:
            raise RecoveryError(f"{header}_FIELD_INVALID:{name}")
        out[name] = line[len(prefix):]
    return out


def _positive_int(value: str, label: str) -> int:
    if not RUN_ID.fullmatch(value):
        raise RecoveryError(f"{label}_INVALID")
    return int(value)


def _timestamp(value: Any, label: str) -> datetime:
    text = str(value or "")
    if not text:
        raise RecoveryError(f"{label}_TIMESTAMP_MISSING")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecoveryError(f"{label}_TIMESTAMP_INVALID") from exc


def _comment_body_sha256(comment: Any, label: str) -> str:
    if not isinstance(comment, dict):
        raise RecoveryError(f"{label}_COMMENT_INVALID")
    return sha256(str(comment.get("body") or "").encode("utf-8"))


def _owner_issue_comment(comment: Any, issue_number: int) -> bool:
    if not isinstance(comment, dict):
        return False
    user = comment.get("user") or {}
    return (
        user.get("login") == OWNER_LOGIN
        and user.get("id") == OWNER_ID
        and str(comment.get("issue_url") or "").endswith(f"/issues/{issue_number}")
    )


def _require_unedited_owner_comment(
    comment: Any, issue_number: int, label: str
) -> tuple[datetime, str]:
    if not _owner_issue_comment(comment, issue_number):
        raise RecoveryError(f"{label}_OWNER_COMMENT_INVALID")
    created = _timestamp(comment.get("created_at"), f"{label}_CREATED")
    updated = _timestamp(comment.get("updated_at"), f"{label}_UPDATED")
    if created != updated:
        raise RecoveryError(f"{label}_COMMENT_EDITED")
    return created, _comment_body_sha256(comment, label)


def _review_fields(body: str) -> dict[str, str]:
    lines = str(body or "").splitlines()
    if not lines or lines[0].strip() != (
        "COMPLETELY_FRESH_SUBSTANTIVE_IMPLEMENTATION_SECURITY_AUTHORITY_RE_REVIEW"
    ):
        raise RecoveryError("R2_FRESH_REVIEW_HEADER_INVALID")
    wanted = (
        "DISPOSITION",
        "PR",
        "EXACT_HEAD",
        "EXACT_BASE",
        "GOVERNING_ISSUE",
        "RECOVERY_DESIGN",
        "SOURCE_BOUNDARY",
        "MATERIAL_BLOCKERS",
    )
    values: dict[str, list[str]] = {name: [] for name in wanted}
    for line in lines[1:]:
        for name in wanted:
            prefix = name + "="
            if line.startswith(prefix):
                values[name].append(line[len(prefix):].strip())
    if any(len(values[name]) != 1 for name in wanted):
        raise RecoveryError("R2_FRESH_REVIEW_FIELDS_NOT_EXACT")
    return {name: values[name][0] for name in wanted}


def validate_r2_review(
    review: Any,
    review_id: int,
    pr_number: int,
    reviewed_head: str,
    control_sha: str,
) -> dict[str, Any]:
    if not isinstance(review, dict) or review.get("id") != review_id:
        raise RecoveryError("R2_REVIEW_ID_MISMATCH")
    user = review.get("user") or {}
    if user.get("login") != OWNER_LOGIN or user.get("id") != OWNER_ID:
        raise RecoveryError("R2_REVIEW_AUTHOR_MISMATCH")
    if review.get("state") != "COMMENTED" or review.get("commit_id") != reviewed_head:
        raise RecoveryError("R2_FRESH_REVIEW_IDENTITY_MISMATCH")
    fields = _review_fields(str(review.get("body") or ""))
    expected = {
        "DISPOSITION": "APPROVED",
        "PR": f"8ft0-ai/resilio#{pr_number}",
        "EXACT_HEAD": reviewed_head,
        "EXACT_BASE": control_sha,
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "RECOVERY_DESIGN": str(RECOVERY_DESIGN_COMMENT_ID),
        "SOURCE_BOUNDARY": str(SOURCE_BOUNDARY_COMMENT_ID),
        "MATERIAL_BLOCKERS": "NONE",
    }
    if fields != expected:
        raise RecoveryError("R2_FRESH_REVIEW_CONTRACT_MISMATCH")
    submitted = _timestamp(review.get("submitted_at"), "R2_REVIEW_SUBMITTED")
    body_sha = sha256(str(review.get("body") or "").encode("utf-8"))
    return {"submitted_at": submitted, "body_sha256": body_sha}


def r2_merge_authority_body(
    control_sha: str,
    pr_number: int,
    reviewed_head: str,
    fresh_review_id: int,
    fresh_review_body_sha256: str,
) -> str:
    if not FULL_SHA.fullmatch(control_sha) or not FULL_SHA.fullmatch(reviewed_head):
        raise RecoveryError("R2_MERGE_AUTHORITY_SHA_INVALID")
    if pr_number <= 0 or fresh_review_id <= 0:
        raise RecoveryError("R2_MERGE_AUTHORITY_ID_INVALID")
    if not HEX64.fullmatch(fresh_review_body_sha256):
        raise RecoveryError("R2_MERGE_AUTHORITY_REVIEW_HASH_INVALID")
    return "\n".join(
        (
            "PHASE5_SLICE_C_RECOVERY_R2_MERGE_AUTHORITY_V2",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"SOURCE_BOUNDARY={SOURCE_BOUNDARY_COMMENT_ID}",
            f"RECOVERY_CONTROL_SHA={control_sha}",
            f"R2_PR={pr_number}",
            f"R2_REVIEWED_HEAD={reviewed_head}",
            f"R2_BASE={control_sha}",
            f"R2_FRESH_REVIEW_ID={fresh_review_id}",
            f"R2_FRESH_REVIEW_BODY_SHA256={fresh_review_body_sha256}",
            "AUTHORITY=MERGE_EXACT_REVIEWED_R2_ACTIVATION_ONLY",
        )
    )


def r2_activation_record_body(
    control_sha: str,
    activation_sha: str,
    pr_number: int,
    reviewed_head: str,
    fresh_review_id: int,
    fresh_review_body_sha256: str,
    merge_authority_comment_id: int,
    merge_authority_body_sha256: str,
) -> str:
    if not FULL_SHA.fullmatch(control_sha) or not FULL_SHA.fullmatch(activation_sha):
        raise RecoveryError("R2_ACTIVATION_SHA_INVALID")
    if not FULL_SHA.fullmatch(reviewed_head):
        raise RecoveryError("R2_REVIEWED_HEAD_INVALID")
    for value, label in (
        (pr_number, "R2_PR"),
        (fresh_review_id, "R2_FRESH_REVIEW_ID"),
        (merge_authority_comment_id, "R2_OWNER_MERGE_AUTHORITY_COMMENT_ID"),
    ):
        if value <= 0:
            raise RecoveryError(f"{label}_INVALID")
    for value, label in (
        (fresh_review_body_sha256, "R2_FRESH_REVIEW_BODY_SHA256"),
        (merge_authority_body_sha256, "R2_OWNER_MERGE_AUTHORITY_BODY_SHA256"),
    ):
        if not HEX64.fullmatch(value):
            raise RecoveryError(f"{label}_INVALID")
    return "\n".join(
        (
            "PHASE5_SLICE_C_RECOVERY_R2_ACTIVATION_V2",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"SOURCE_BOUNDARY={SOURCE_BOUNDARY_COMMENT_ID}",
            f"RECOVERY_CONTROL_SHA={control_sha}",
            f"R2_PR={pr_number}",
            f"R2_REVIEWED_HEAD={reviewed_head}",
            f"R2_BASE={control_sha}",
            f"R2_MERGE={activation_sha}",
            f"R2_FRESH_REVIEW_ID={fresh_review_id}",
            f"R2_FRESH_REVIEW_BODY_SHA256={fresh_review_body_sha256}",
            f"R2_OWNER_MERGE_AUTHORITY_COMMENT_ID={merge_authority_comment_id}",
            f"R2_OWNER_MERGE_AUTHORITY_BODY_SHA256={merge_authority_body_sha256}",
            "STATUS=R2_ACTIVATION_MERGED_EXACT",
        )
    )


def validate_r2_activation_record(
    comments: Any, control_sha: str, activation_sha: str
) -> dict[str, Any]:
    if not isinstance(comments, list):
        raise RecoveryError("R2_ACTIVATION_COMMENTS_INVALID")
    header = "PHASE5_SLICE_C_RECOVERY_R2_ACTIVATION_V2"
    candidates = [
        comment
        for comment in comments
        if _owner_issue_comment(comment, GOVERNING_ISSUE)
        and str(comment.get("body") or "").strip().startswith(header + "\n")
        and f"RECOVERY_CONTROL_SHA={control_sha}" in str(comment.get("body") or "")
    ]
    if len(candidates) != 1:
        raise RecoveryError("R2_ACTIVATION_RECORD_NOT_UNIQUE")
    comment = candidates[0]
    created, body_sha = _require_unedited_owner_comment(
        comment, GOVERNING_ISSUE, "R2_ACTIVATION"
    )
    fields = _record_fields(
        str(comment.get("body") or ""),
        header,
        (
            "GOVERNING_ISSUE",
            "SOURCE_BOUNDARY",
            "RECOVERY_CONTROL_SHA",
            "R2_PR",
            "R2_REVIEWED_HEAD",
            "R2_BASE",
            "R2_MERGE",
            "R2_FRESH_REVIEW_ID",
            "R2_FRESH_REVIEW_BODY_SHA256",
            "R2_OWNER_MERGE_AUTHORITY_COMMENT_ID",
            "R2_OWNER_MERGE_AUTHORITY_BODY_SHA256",
            "STATUS",
        ),
    )
    if fields["GOVERNING_ISSUE"] != "8ft0-ai/resilio#109":
        raise RecoveryError("R2_ACTIVATION_ISSUE_MISMATCH")
    if fields["SOURCE_BOUNDARY"] != str(SOURCE_BOUNDARY_COMMENT_ID):
        raise RecoveryError("R2_ACTIVATION_BOUNDARY_MISMATCH")
    if fields["RECOVERY_CONTROL_SHA"] != control_sha or fields["R2_BASE"] != control_sha:
        raise RecoveryError("R2_ACTIVATION_CONTROL_MISMATCH")
    if fields["R2_MERGE"] != activation_sha:
        raise RecoveryError("R2_ACTIVATION_MERGE_MISMATCH")
    if not FULL_SHA.fullmatch(fields["R2_REVIEWED_HEAD"]):
        raise RecoveryError("R2_ACTIVATION_REVIEWED_HEAD_INVALID")
    if not HEX64.fullmatch(fields["R2_FRESH_REVIEW_BODY_SHA256"]):
        raise RecoveryError("R2_ACTIVATION_REVIEW_HASH_INVALID")
    if not HEX64.fullmatch(fields["R2_OWNER_MERGE_AUTHORITY_BODY_SHA256"]):
        raise RecoveryError("R2_ACTIVATION_AUTHORITY_HASH_INVALID")
    if fields["STATUS"] != "R2_ACTIVATION_MERGED_EXACT":
        raise RecoveryError("R2_ACTIVATION_STATUS_INVALID")
    return {
        "comment_id": int(comment["id"]),
        "created_at": created,
        "body_sha256": body_sha,
        "pr_number": _positive_int(fields["R2_PR"], "R2_PR"),
        "reviewed_head": fields["R2_REVIEWED_HEAD"],
        "fresh_review_id": _positive_int(fields["R2_FRESH_REVIEW_ID"], "R2_FRESH_REVIEW_ID"),
        "fresh_review_body_sha256": fields["R2_FRESH_REVIEW_BODY_SHA256"],
        "merge_authority_comment_id": _positive_int(
            fields["R2_OWNER_MERGE_AUTHORITY_COMMENT_ID"],
            "R2_OWNER_MERGE_AUTHORITY_COMMENT_ID",
        ),
        "merge_authority_body_sha256": fields[
            "R2_OWNER_MERGE_AUTHORITY_BODY_SHA256"
        ],
    }


def validate_r2_activation_transaction(
    pr: Any,
    review: Any,
    merge_authority_comment: Any,
    record: dict[str, Any],
    control_sha: str,
    activation_sha: str,
) -> dict[str, Any]:
    if not isinstance(pr, dict) or pr.get("number") != record["pr_number"]:
        raise RecoveryError("R2_PR_INVALID")
    if pr.get("state") != "closed" or pr.get("merged_at") is None:
        raise RecoveryError("R2_PR_NOT_MERGED")
    if pr.get("merge_commit_sha") != activation_sha:
        raise RecoveryError("R2_PR_MERGE_MISMATCH")
    if pr.get("head", {}).get("sha") != record["reviewed_head"]:
        raise RecoveryError("R2_PR_HEAD_MISMATCH")
    if pr.get("base", {}).get("ref") != DEFAULT_BRANCH or pr.get("base", {}).get("sha") != control_sha:
        raise RecoveryError("R2_PR_BASE_MISMATCH")
    head_repo = pr.get("head", {}).get("repo") or {}
    if head_repo.get("id") != REPOSITORY_ID or head_repo.get("full_name") != REPOSITORY:
        raise RecoveryError("R2_PR_REPOSITORY_MISMATCH")

    review_result = validate_r2_review(
        review,
        record["fresh_review_id"],
        record["pr_number"],
        record["reviewed_head"],
        control_sha,
    )
    if review_result["body_sha256"] != record["fresh_review_body_sha256"]:
        raise RecoveryError("R2_REVIEW_BODY_HASH_MISMATCH")

    if (
        not isinstance(merge_authority_comment, dict)
        or merge_authority_comment.get("id") != record["merge_authority_comment_id"]
    ):
        raise RecoveryError("R2_MERGE_AUTHORITY_COMMENT_INVALID")
    authority_created, authority_sha = _require_unedited_owner_comment(
        merge_authority_comment, record["pr_number"], "R2_MERGE_AUTHORITY"
    )
    expected_merge_authority = r2_merge_authority_body(
        control_sha,
        record["pr_number"],
        record["reviewed_head"],
        record["fresh_review_id"],
        record["fresh_review_body_sha256"],
    )
    if str(merge_authority_comment.get("body") or "").strip() != expected_merge_authority:
        raise RecoveryError("R2_MERGE_AUTHORITY_BODY_MISMATCH")
    if authority_sha != record["merge_authority_body_sha256"]:
        raise RecoveryError("R2_MERGE_AUTHORITY_BODY_HASH_MISMATCH")

    merge_time = _timestamp(pr.get("merged_at"), "R2_MERGED")
    record_time = record["created_at"]
    review_time = review_result["submitted_at"]
    if not (review_time <= authority_created < merge_time <= record_time):
        raise RecoveryError("R2_ACTIVATION_TIMELINE_INVALID")
    return {
        "review_body_sha256": review_result["body_sha256"],
        "merge_authority_body_sha256": authority_sha,
    }


def _nonnegative_int(value: str, label: str) -> int:
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,19})", str(value or "")):
        raise RecoveryError(f"{label}_INVALID")
    return int(value)


def _bootstrap_review_fields(body: str) -> dict[str, str]:
    lines = str(body or "").splitlines()
    if not lines or lines[0].strip() != (
        "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_PLAN_FRESH_REVIEW_V1"
    ):
        raise RecoveryError("BOOTSTRAP_FRESH_REVIEW_HEADER_INVALID")
    wanted = (
        "REVIEW_TARGET",
        "GOVERNING_ISSUE",
        "SOURCE_BOUNDARY",
        "RECOVERY_CONTROL_SHA",
        "RECOVERY_ACTIVATION_MAIN",
        "SAVED_PLAN_SHA256",
        "STRUCTURAL_MANIFEST_SHA256",
        "BOOTSTRAP_STATE_LINEAGE",
        "BOOTSTRAP_STATE_SERIAL",
        "TERRAFORM_VERSION",
        "PLAN_FORMAT_VERSION",
        "PLAN_APPLYABLE",
        "PLAN_COMPLETE",
        "PLAN_ERRORED",
        "PLAN_EFFECTS",
        "OUTPUT_CHANGES",
        "REVIEW_DISPOSITION",
        "MATERIAL_BLOCKERS",
        "APPLY_AUTHORITY",
    )
    values: dict[str, list[str]] = {name: [] for name in wanted}
    for line in lines[1:]:
        for name in wanted:
            prefix = name + "="
            if line.startswith(prefix):
                values[name].append(line[len(prefix):].strip())
    if any(len(values[name]) != 1 for name in wanted):
        raise RecoveryError("BOOTSTRAP_FRESH_REVIEW_FIELDS_NOT_EXACT")
    return {name: values[name][0] for name in wanted}


def validate_bootstrap_effect_review(
    comment: Any,
    control_sha: str,
    activation_sha: str,
    saved_plan_sha256: str,
    structural_manifest_sha256: str,
    state_lineage: str,
    state_serial: int,
) -> dict[str, Any]:
    created, body_sha = _require_unedited_owner_comment(
        comment, GOVERNING_ISSUE, "BOOTSTRAP_EFFECT_REVIEW"
    )
    fields = _bootstrap_review_fields(str(comment.get("body") or ""))
    expected = {
        "REVIEW_TARGET": "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_ACTIVATION_SAVED_PLAN",
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "SOURCE_BOUNDARY": str(SOURCE_BOUNDARY_COMMENT_ID),
        "RECOVERY_CONTROL_SHA": control_sha,
        "RECOVERY_ACTIVATION_MAIN": activation_sha,
        "SAVED_PLAN_SHA256": saved_plan_sha256,
        "STRUCTURAL_MANIFEST_SHA256": structural_manifest_sha256,
        "BOOTSTRAP_STATE_LINEAGE": state_lineage,
        "BOOTSTRAP_STATE_SERIAL": str(state_serial),
        "TERRAFORM_VERSION": "1.15.8",
        "PLAN_FORMAT_VERSION": "1.2",
        "PLAN_APPLYABLE": "true",
        "PLAN_COMPLETE": "true",
        "PLAN_ERRORED": "false",
        "PLAN_EFFECTS": "EXACT_TWO_GETMETADATA_ADDITIONS_PLUS_ONE_RECOVERY_WIF_BINDING",
        "OUTPUT_CHANGES": "0",
        "REVIEW_DISPOSITION": "APPROVED",
        "MATERIAL_BLOCKERS": "NONE",
        "APPLY_AUTHORITY": "NOT_GRANTED",
    }
    if fields != expected:
        raise RecoveryError("BOOTSTRAP_FRESH_REVIEW_CONTRACT_MISMATCH")
    return {
        "comment_id": int(comment["id"]),
        "created_at": created,
        "body_sha256": body_sha,
    }


def bootstrap_apply_authority_body(
    control_sha: str,
    activation_sha: str,
    saved_plan_sha256: str,
    structural_manifest_sha256: str,
    state_lineage: str,
    state_serial: int,
    review_comment_id: int,
    review_body_sha256: str,
) -> str:
    if not FULL_SHA.fullmatch(control_sha) or not FULL_SHA.fullmatch(activation_sha):
        raise RecoveryError("BOOTSTRAP_AUTHORITY_SHA_INVALID")
    for value, label in (
        (saved_plan_sha256, "BOOTSTRAP_SAVED_PLAN_SHA256"),
        (structural_manifest_sha256, "BOOTSTRAP_STRUCTURAL_MANIFEST_SHA256"),
        (review_body_sha256, "BOOTSTRAP_REVIEW_BODY_SHA256"),
    ):
        if not HEX64.fullmatch(value):
            raise RecoveryError(f"{label}_INVALID")
    if not state_lineage or len(state_lineage) > 128:
        raise RecoveryError("BOOTSTRAP_STATE_LINEAGE_INVALID")
    if state_serial < 0 or review_comment_id <= 0:
        raise RecoveryError("BOOTSTRAP_AUTHORITY_IDENTITY_INVALID")
    return "\n".join(
        (
            "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_APPLY_AUTHORITY_V2",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"SOURCE_BOUNDARY={SOURCE_BOUNDARY_COMMENT_ID}",
            f"RECOVERY_CONTROL_SHA={control_sha}",
            f"RECOVERY_ACTIVATION_MAIN={activation_sha}",
            f"SAVED_PLAN_SHA256={saved_plan_sha256}",
            f"STRUCTURAL_MANIFEST_SHA256={structural_manifest_sha256}",
            f"BOOTSTRAP_STATE_LINEAGE={state_lineage}",
            f"BOOTSTRAP_STATE_SERIAL={state_serial}",
            f"BOOTSTRAP_FRESH_REVIEW_COMMENT_ID={review_comment_id}",
            f"BOOTSTRAP_FRESH_REVIEW_BODY_SHA256={review_body_sha256}",
            "AUTHORITY=APPLY_THIS_EXACT_REVIEWED_SAVED_BOOTSTRAP_PLAN_ONCE",
            "REPLAN=NOT_AUTHORISED",
            "PLAN_REPLACEMENT=NOT_AUTHORISED",
            "BLIND_RETRY_AFTER_AMBIGUOUS_OUTCOME=NOT_AUTHORISED",
            "RECOVERY_DISPATCH_AUTHORITY=NOT_GRANTED",
        )
    )


def validate_bootstrap_apply_authority(
    comment: Any,
    control_sha: str,
    activation_sha: str,
    saved_plan_sha256: str,
    structural_manifest_sha256: str,
    state_lineage: str,
    state_serial: int,
    review: dict[str, Any],
) -> dict[str, Any]:
    created, body_sha = _require_unedited_owner_comment(
        comment, GOVERNING_ISSUE, "BOOTSTRAP_APPLY_AUTHORITY"
    )
    expected = bootstrap_apply_authority_body(
        control_sha,
        activation_sha,
        saved_plan_sha256,
        structural_manifest_sha256,
        state_lineage,
        state_serial,
        review["comment_id"],
        review["body_sha256"],
    )
    if str(comment.get("body") or "").strip() != expected:
        raise RecoveryError("BOOTSTRAP_APPLY_AUTHORITY_BODY_MISMATCH")
    if created < review["created_at"]:
        raise RecoveryError("BOOTSTRAP_APPLY_AUTHORITY_PRECEDES_REVIEW")
    return {
        "comment_id": int(comment["id"]),
        "created_at": created,
        "body_sha256": body_sha,
    }


def bootstrap_terminal_record_body(
    control_sha: str,
    activation_sha: str,
    saved_plan_sha256: str,
    structural_manifest_sha256: str,
    state_lineage: str,
    state_serial_before: int,
    state_serial_after: int,
    review_comment_id: int,
    review_body_sha256: str,
    apply_authority_comment_id: int,
    apply_authority_body_sha256: str,
) -> str:
    if not FULL_SHA.fullmatch(control_sha) or not FULL_SHA.fullmatch(activation_sha):
        raise RecoveryError("BOOTSTRAP_TERMINAL_SHA_INVALID")
    for value, label in (
        (saved_plan_sha256, "BOOTSTRAP_SAVED_PLAN_SHA256"),
        (structural_manifest_sha256, "BOOTSTRAP_STRUCTURAL_MANIFEST_SHA256"),
        (review_body_sha256, "BOOTSTRAP_REVIEW_BODY_SHA256"),
        (apply_authority_body_sha256, "BOOTSTRAP_AUTHORITY_BODY_SHA256"),
    ):
        if not HEX64.fullmatch(value):
            raise RecoveryError(f"{label}_INVALID")
    if not state_lineage or len(state_lineage) > 128:
        raise RecoveryError("BOOTSTRAP_STATE_LINEAGE_INVALID")
    if (
        state_serial_before < 0
        or state_serial_after < state_serial_before
        or review_comment_id <= 0
        or apply_authority_comment_id <= 0
    ):
        raise RecoveryError("BOOTSTRAP_TERMINAL_IDENTITY_INVALID")
    return "\n".join(
        (
            "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_TERMINAL_V3",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"SOURCE_BOUNDARY={SOURCE_BOUNDARY_COMMENT_ID}",
            f"RECOVERY_CONTROL_SHA={control_sha}",
            f"RECOVERY_ACTIVATION_MAIN={activation_sha}",
            f"SAVED_PLAN_SHA256={saved_plan_sha256}",
            f"STRUCTURAL_MANIFEST_SHA256={structural_manifest_sha256}",
            f"BOOTSTRAP_STATE_LINEAGE={state_lineage}",
            f"BOOTSTRAP_STATE_SERIAL_BEFORE={state_serial_before}",
            f"BOOTSTRAP_STATE_SERIAL_AFTER={state_serial_after}",
            f"BOOTSTRAP_FRESH_REVIEW_COMMENT_ID={review_comment_id}",
            f"BOOTSTRAP_FRESH_REVIEW_BODY_SHA256={review_body_sha256}",
            f"BOOTSTRAP_OWNER_APPLY_AUTHORITY_COMMENT_ID={apply_authority_comment_id}",
            f"BOOTSTRAP_OWNER_APPLY_AUTHORITY_BODY_SHA256={apply_authority_body_sha256}",
            "IAM_CORRECTION=EXACT_TWO_GETMETADATA_ADDITIONS_LIVE",
            "RECOVERY_WIF_BINDING=EXACT_R1_RECOVERY_REUSABLE_LIVE",
            "UNRELATED_BOOTSTRAP_AUTHORITY_CONSEQUENCE=NONE",
            "BOOTSTRAP_RECONCILIATION=EXACT_NO_CHANGE",
            "FINAL_BOOTSTRAP_LOCK=ABSENT",
            "TERMINAL_DISPOSITION=RECONCILED",
        )
    )


def validate_bootstrap_terminal_record(
    comments: Any,
    control_sha: str,
    activation_sha: str,
    activation_created_at: datetime,
) -> dict[str, Any]:
    if not isinstance(comments, list):
        raise RecoveryError("BOOTSTRAP_TERMINAL_COMMENTS_INVALID")
    header = "PHASE5_SLICE_C_RECOVERY_BOOTSTRAP_TERMINAL_V3"
    candidates = [
        comment
        for comment in comments
        if _owner_issue_comment(comment, GOVERNING_ISSUE)
        and str(comment.get("body") or "").strip().startswith(header + "\n")
        and f"RECOVERY_CONTROL_SHA={control_sha}" in str(comment.get("body") or "")
        and f"RECOVERY_ACTIVATION_MAIN={activation_sha}" in str(comment.get("body") or "")
    ]
    if len(candidates) != 1:
        raise RecoveryError("BOOTSTRAP_TERMINAL_RECORD_NOT_UNIQUE")
    comment = candidates[0]
    created, body_sha = _require_unedited_owner_comment(
        comment, GOVERNING_ISSUE, "BOOTSTRAP_TERMINAL"
    )
    fields = _record_fields(
        str(comment.get("body") or ""),
        header,
        (
            "GOVERNING_ISSUE",
            "SOURCE_BOUNDARY",
            "RECOVERY_CONTROL_SHA",
            "RECOVERY_ACTIVATION_MAIN",
            "SAVED_PLAN_SHA256",
            "STRUCTURAL_MANIFEST_SHA256",
            "BOOTSTRAP_STATE_LINEAGE",
            "BOOTSTRAP_STATE_SERIAL_BEFORE",
            "BOOTSTRAP_STATE_SERIAL_AFTER",
            "BOOTSTRAP_FRESH_REVIEW_COMMENT_ID",
            "BOOTSTRAP_FRESH_REVIEW_BODY_SHA256",
            "BOOTSTRAP_OWNER_APPLY_AUTHORITY_COMMENT_ID",
            "BOOTSTRAP_OWNER_APPLY_AUTHORITY_BODY_SHA256",
            "IAM_CORRECTION",
            "RECOVERY_WIF_BINDING",
            "UNRELATED_BOOTSTRAP_AUTHORITY_CONSEQUENCE",
            "BOOTSTRAP_RECONCILIATION",
            "FINAL_BOOTSTRAP_LOCK",
            "TERMINAL_DISPOSITION",
        ),
    )
    expected = {
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "SOURCE_BOUNDARY": str(SOURCE_BOUNDARY_COMMENT_ID),
        "RECOVERY_CONTROL_SHA": control_sha,
        "RECOVERY_ACTIVATION_MAIN": activation_sha,
        "IAM_CORRECTION": "EXACT_TWO_GETMETADATA_ADDITIONS_LIVE",
        "RECOVERY_WIF_BINDING": "EXACT_R1_RECOVERY_REUSABLE_LIVE",
        "UNRELATED_BOOTSTRAP_AUTHORITY_CONSEQUENCE": "NONE",
        "BOOTSTRAP_RECONCILIATION": "EXACT_NO_CHANGE",
        "FINAL_BOOTSTRAP_LOCK": "ABSENT",
        "TERMINAL_DISPOSITION": "RECONCILED",
    }
    for name, value in expected.items():
        if fields[name] != value:
            raise RecoveryError(f"BOOTSTRAP_TERMINAL_FIELD_MISMATCH:{name}")
    for name in (
        "SAVED_PLAN_SHA256",
        "STRUCTURAL_MANIFEST_SHA256",
        "BOOTSTRAP_FRESH_REVIEW_BODY_SHA256",
        "BOOTSTRAP_OWNER_APPLY_AUTHORITY_BODY_SHA256",
    ):
        if not HEX64.fullmatch(fields[name]):
            raise RecoveryError(f"BOOTSTRAP_TERMINAL_HASH_INVALID:{name}")
    lineage = fields["BOOTSTRAP_STATE_LINEAGE"]
    if not lineage or len(lineage) > 128:
        raise RecoveryError("BOOTSTRAP_STATE_LINEAGE_INVALID")
    serial_before = _nonnegative_int(
        fields["BOOTSTRAP_STATE_SERIAL_BEFORE"],
        "BOOTSTRAP_STATE_SERIAL_BEFORE",
    )
    serial_after = _nonnegative_int(
        fields["BOOTSTRAP_STATE_SERIAL_AFTER"],
        "BOOTSTRAP_STATE_SERIAL_AFTER",
    )
    if serial_after < serial_before:
        raise RecoveryError("BOOTSTRAP_STATE_SERIAL_REGRESSED")
    review_id = _positive_int(
        fields["BOOTSTRAP_FRESH_REVIEW_COMMENT_ID"],
        "BOOTSTRAP_FRESH_REVIEW_COMMENT_ID",
    )
    authority_id = _positive_int(
        fields["BOOTSTRAP_OWNER_APPLY_AUTHORITY_COMMENT_ID"],
        "BOOTSTRAP_OWNER_APPLY_AUTHORITY_COMMENT_ID",
    )
    by_id = {
        row.get("id"): row for row in comments if isinstance(row, dict)
    }
    review = validate_bootstrap_effect_review(
        by_id.get(review_id),
        control_sha,
        activation_sha,
        fields["SAVED_PLAN_SHA256"],
        fields["STRUCTURAL_MANIFEST_SHA256"],
        lineage,
        serial_before,
    )
    if review["body_sha256"] != fields["BOOTSTRAP_FRESH_REVIEW_BODY_SHA256"]:
        raise RecoveryError("BOOTSTRAP_EFFECT_REVIEW_HASH_MISMATCH")
    authority = validate_bootstrap_apply_authority(
        by_id.get(authority_id),
        control_sha,
        activation_sha,
        fields["SAVED_PLAN_SHA256"],
        fields["STRUCTURAL_MANIFEST_SHA256"],
        lineage,
        serial_before,
        review,
    )
    if authority["body_sha256"] != fields[
        "BOOTSTRAP_OWNER_APPLY_AUTHORITY_BODY_SHA256"
    ]:
        raise RecoveryError("BOOTSTRAP_APPLY_AUTHORITY_HASH_MISMATCH")
    if not (
        activation_created_at <= review["created_at"]
        <= authority["created_at"]
        <= created
    ):
        raise RecoveryError("BOOTSTRAP_TRANSACTION_TIMELINE_INVALID")
    return {
        "comment_id": int(comment["id"]),
        "created_at": created,
        "body_sha256": body_sha,
        "saved_plan_sha256": fields["SAVED_PLAN_SHA256"],
        "structural_manifest_sha256": fields["STRUCTURAL_MANIFEST_SHA256"],
        "state_lineage": lineage,
        "state_serial_before": serial_before,
        "state_serial_after": serial_after,
        "review_comment_id": review["comment_id"],
        "review_body_sha256": review["body_sha256"],
        "apply_authority_comment_id": authority["comment_id"],
        "apply_authority_body_sha256": authority["body_sha256"],
    }


def dispatch_authority_body(
    control_sha: str,
    activation_sha: str,
    activation_record_comment_id: int,
    activation_record_body_sha256: str,
    bootstrap_record_comment_id: int,
    bootstrap_record_body_sha256: str,
) -> str:
    if not FULL_SHA.fullmatch(control_sha) or not FULL_SHA.fullmatch(activation_sha):
        raise RecoveryError("AUTHORITY_SHA_INVALID")
    if activation_record_comment_id <= 0 or bootstrap_record_comment_id <= 0:
        raise RecoveryError("AUTHORITY_RECORD_ID_INVALID")
    if not HEX64.fullmatch(activation_record_body_sha256) or not HEX64.fullmatch(
        bootstrap_record_body_sha256
    ):
        raise RecoveryError("AUTHORITY_RECORD_HASH_INVALID")
    return "\n".join(
        (
            "PHASE5_SLICE_C_RECOVERY_DISPATCH_AUTHORITY_V2",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"SOURCE_BOUNDARY={SOURCE_BOUNDARY_COMMENT_ID}",
            f"RECOVERY_CONTROL_SHA={control_sha}",
            f"RECOVERY_ACTIVATION_MAIN={activation_sha}",
            f"RECOVERY_R2_ACTIVATION_RECORD={activation_record_comment_id}",
            f"RECOVERY_R2_ACTIVATION_RECORD_BODY_SHA256={activation_record_body_sha256}",
            f"RECOVERY_BOOTSTRAP_TERMINAL_RECORD={bootstrap_record_comment_id}",
            f"RECOVERY_BOOTSTRAP_TERMINAL_RECORD_BODY_SHA256={bootstrap_record_body_sha256}",
            f"PRODUCT_STATE_GENERATION={EXPECTED_GENERATION}",
            f"PRODUCT_STATE_LINEAGE={EXPECTED_LINEAGE}",
            f"PRODUCT_STATE_SERIAL={EXPECTED_SERIAL}",
            "AUTHORITY=DISPATCH_EXACTLY_ONE_RECONCILIATION_ONLY_RECOVERY",
        )
    )


def validate_dispatch_authority(
    comments: Any,
    control_sha: str,
    activation_sha: str,
    activation_record: dict[str, Any],
    bootstrap_record: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(comments, list):
        raise RecoveryError("AUTHORITY_COMMENTS_INVALID")
    expected = dispatch_authority_body(
        control_sha,
        activation_sha,
        activation_record["comment_id"],
        activation_record["body_sha256"],
        bootstrap_record["comment_id"],
        bootstrap_record["body_sha256"],
    )
    matches = [
        comment
        for comment in comments
        if _owner_issue_comment(comment, GOVERNING_ISSUE)
        and str(comment.get("body") or "").strip() == expected
    ]
    if len(matches) != 1:
        raise RecoveryError("RECOVERY_DISPATCH_AUTHORITY_NOT_UNIQUE")
    comment = matches[0]
    created, body_sha = _require_unedited_owner_comment(
        comment, GOVERNING_ISSUE, "RECOVERY_DISPATCH_AUTHORITY"
    )
    if created < activation_record["created_at"] or created < bootstrap_record["created_at"]:
        raise RecoveryError("RECOVERY_DISPATCH_AUTHORITY_PRECEDES_PREREQUISITE")
    return {
        "comment_id": int(comment["id"]),
        "created_at": created,
        "body_sha256": body_sha,
    }


def github_issue_comments(issue_number: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    page = 1
    while True:
        value = github(
            f"/repos/{REPOSITORY}/issues/{issue_number}/comments?per_page=100&page={page}"
        )
        if not isinstance(value, list):
            raise RecoveryError("AUTHORITY_COMMENTS_PAGE_INVALID")
        for comment in value:
            if not isinstance(comment, dict) or not isinstance(comment.get("id"), int):
                raise RecoveryError("AUTHORITY_COMMENT_ROW_INVALID")
            if comment["id"] in seen:
                raise RecoveryError("AUTHORITY_COMMENT_ID_DUPLICATE")
            seen.add(comment["id"])
            rows.append(comment)
        if len(value) < 100:
            return rows
        page += 1


def validate_boundary_comment(comment: Any) -> dict[str, Any]:
    if not isinstance(comment, dict) or comment.get("id") != SOURCE_BOUNDARY_COMMENT_ID:
        raise RecoveryError("SOURCE_BOUNDARY_ID_MISMATCH")
    created, body_sha = _require_unedited_owner_comment(
        comment, GOVERNING_ISSUE, "SOURCE_BOUNDARY"
    )
    body = str(comment.get("body") or "")
    required = (
        "STATUS=SLICE_C_BASE_RESOURCES_APPLIED_BUT_TERMINAL_NO_CHANGE_PROOF_FAILED",
        f"EXACT_REVIEWED_HEAD={REVIEWED_HEAD}",
        f"REVIEWED_BASE={REVIEWED_BASE}",
        f"MERGE_COMMIT={SLICE_C_MERGE}",
        f"PRODUCT_APPLY_RUN={FAILED_APPLY_RUN}",
        f"PRODUCT_APPLY_JOB={FAILED_APPLY_JOB}",
        f"PRODUCT_STATE_GENERATION={EXPECTED_GENERATION}",
        f"PRODUCT_STATE_SERIAL={EXPECTED_SERIAL}",
        f"PRODUCT_STATE_LINEAGE={EXPECTED_LINEAGE}",
    )
    for token in required:
        if token not in body:
            raise RecoveryError(f"SOURCE_BOUNDARY_TOKEN_MISSING:{token}")
    lowered = body.lower()
    if "retry prohibition" not in lowered or "do **not** rerun the existing product apply workflow" not in lowered:
        raise RecoveryError("SOURCE_BOUNDARY_RETRY_PROHIBITION_MISSING")
    if body_sha != SOURCE_BOUNDARY_BODY_SHA256:
        raise RecoveryError("SOURCE_BOUNDARY_BODY_HASH_MISMATCH")
    return {
        "created_at": created,
        "body_sha256": body_sha,
    }

def expected_candidate() -> dict[str, Any]:
    return {
        "contract": "resilio-product-terraform-candidate/v1",
        "stage": "base",
        "processor_uri": None,
        "processor_verification_comment_id": None,
    }


def fetch_candidate(sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(sha):
        raise RecoveryError("CANDIDATE_SHA_INVALID")
    path = urllib.parse.quote(CANDIDATE_PATH, safe="/")
    value = github(f"/repos/{REPOSITORY}/contents/{path}?ref={sha}")
    if (
        not isinstance(value, dict)
        or value.get("type") != "file"
        or value.get("path") != CANDIDATE_PATH
        or value.get("encoding") != "base64"
    ):
        raise RecoveryError("CANDIDATE_CONTENT_INVALID")
    try:
        raw = decode_github_base64(value.get("content"))
    except Exception as exc:
        raise RecoveryError("CANDIDATE_BASE64_INVALID") from exc
    candidate = validate_candidate(strict_json(raw))
    if candidate != expected_candidate():
        raise RecoveryError("CANDIDATE_NOT_EXACT_BASE")
    if raw != canonical(candidate) + b"\n":
        raise RecoveryError("CANDIDATE_NOT_CANONICAL")
    return candidate


def validate_pr(pr: Any, files: Any) -> None:
    if not isinstance(pr, dict) or pr.get("number") != SLICE_C_PR:
        raise RecoveryError("SLICE_C_PR_INVALID")
    if pr.get("state") != "closed" or pr.get("merged_at") is None:
        raise RecoveryError("SLICE_C_PR_NOT_MERGED")
    if pr.get("merge_commit_sha") != SLICE_C_MERGE:
        raise RecoveryError("SLICE_C_MERGE_MISMATCH")
    if pr.get("head", {}).get("sha") != REVIEWED_HEAD:
        raise RecoveryError("SLICE_C_HEAD_MISMATCH")
    if pr.get("base", {}).get("ref") != DEFAULT_BRANCH or pr.get("base", {}).get("sha") != REVIEWED_BASE:
        raise RecoveryError("SLICE_C_BASE_MISMATCH")
    head_repo = pr.get("head", {}).get("repo") or {}
    if head_repo.get("id") != REPOSITORY_ID or head_repo.get("full_name") != REPOSITORY:
        raise RecoveryError("SLICE_C_HEAD_REPOSITORY_MISMATCH")
    if not isinstance(files, list) or [row.get("filename") for row in files] != [CANDIDATE_PATH]:
        raise RecoveryError("SLICE_C_FILE_SET_MISMATCH")


def validate_failed_apply(run: Any, job: Any) -> None:
    if not isinstance(run, dict) or run.get("id") != FAILED_APPLY_RUN:
        raise RecoveryError("FAILED_RUN_ID_MISMATCH")
    if (
        run.get("run_attempt") != 1
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or run.get("head_branch") != DEFAULT_BRANCH
        or run.get("head_sha") != SLICE_C_MERGE
        or run.get("event") != "workflow_dispatch"
    ):
        raise RecoveryError("FAILED_RUN_STATE_MISMATCH")
    if str(run.get("path") or "").split("@", 1)[0] != NORMAL_APPLY_CALLER_PATH:
        raise RecoveryError("FAILED_RUN_CALLER_MISMATCH")
    for key in ("repository", "head_repository"):
        value = run.get(key) or {}
        if value.get("full_name") != REPOSITORY:
            raise RecoveryError("FAILED_RUN_REPOSITORY_MISMATCH")
    refs = run.get("referenced_workflows")
    expected_ref = f"{REPOSITORY}/{NORMAL_APPLY_REUSABLE_PATH}@{NORMAL_CONTROL_SHA}"
    if not isinstance(refs, list):
        raise RecoveryError("FAILED_RUN_REUSABLE_IDENTITY_MISSING")
    matches = [
        row
        for row in refs
        if isinstance(row, dict)
        and str(row.get("path") or "").split("@", 1)[0]
        == f"{REPOSITORY}/{NORMAL_APPLY_REUSABLE_PATH}"
    ]
    if (
        len(matches) != 1
        or matches[0].get("path") != expected_ref
        or matches[0].get("sha") != NORMAL_CONTROL_SHA
    ):
        raise RecoveryError("FAILED_RUN_REUSABLE_IDENTITY_MISMATCH")
    if not isinstance(job, dict) or job.get("id") != FAILED_APPLY_JOB:
        raise RecoveryError("FAILED_JOB_ID_MISMATCH")
    if (
        job.get("run_id") != FAILED_APPLY_RUN
        or job.get("status") != "completed"
        or job.get("conclusion") != "failure"
        or job.get("name") != "apply / product-apply"
    ):
        raise RecoveryError("FAILED_JOB_STATE_MISMATCH")


def verify_github_boundary(
    activation_sha: str, control_sha: str, candidate_output: str | Path
) -> dict[str, Any]:
    branch = github(f"/repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}")
    if not isinstance(branch, dict) or branch.get("commit", {}).get("sha") != activation_sha:
        raise RecoveryError("ACTIVATION_MAIN_MISMATCH")

    issue = github(f"/repos/{REPOSITORY}/issues/{GOVERNING_ISSUE}")
    if not isinstance(issue, dict) or issue.get("state") != "open":
        raise RecoveryError("GOVERNING_ISSUE_NOT_OPEN")

    boundary = github(f"/repos/{REPOSITORY}/issues/comments/{SOURCE_BOUNDARY_COMMENT_ID}")
    boundary_result = validate_boundary_comment(boundary)

    pr = github(f"/repos/{REPOSITORY}/pulls/{SLICE_C_PR}")
    files = github(f"/repos/{REPOSITORY}/pulls/{SLICE_C_PR}/files?per_page=100")
    validate_pr(pr, files)

    run = github(f"/repos/{REPOSITORY}/actions/runs/{FAILED_APPLY_RUN}")
    job = github(f"/repos/{REPOSITORY}/actions/jobs/{FAILED_APPLY_JOB}")
    validate_failed_apply(run, job)

    comments = github_issue_comments(GOVERNING_ISSUE)
    activation_record = validate_r2_activation_record(comments, control_sha, activation_sha)
    r2_pr = github(f"/repos/{REPOSITORY}/pulls/{activation_record['pr_number']}")
    r2_review = github(
        f"/repos/{REPOSITORY}/pulls/{activation_record['pr_number']}/reviews/"
        f"{activation_record['fresh_review_id']}"
    )
    merge_authority_comment = github(
        f"/repos/{REPOSITORY}/issues/comments/"
        f"{activation_record['merge_authority_comment_id']}"
    )
    validate_r2_activation_transaction(
        r2_pr,
        r2_review,
        merge_authority_comment,
        activation_record,
        control_sha,
        activation_sha,
    )

    bootstrap_record = validate_bootstrap_terminal_record(
        comments, control_sha, activation_sha, activation_record["created_at"]
    )
    bootstrap_run = github(
        f"/repos/{REPOSITORY}/actions/runs/{bootstrap_record['apply_run']}"
    )
    bootstrap_job = github(
        f"/repos/{REPOSITORY}/actions/jobs/{bootstrap_record['apply_job']}"
    )
    validate_bootstrap_apply_run(
        bootstrap_run, bootstrap_job, bootstrap_record, activation_sha
    )

    dispatch = validate_dispatch_authority(
        comments,
        control_sha,
        activation_sha,
        activation_record,
        bootstrap_record,
    )

    reviewed = fetch_candidate(REVIEWED_HEAD)
    merged = fetch_candidate(SLICE_C_MERGE)
    active = fetch_candidate(activation_sha)
    if reviewed != merged or reviewed != active:
        raise RecoveryError("CANDIDATE_IDENTITY_DRIFT")
    Path(candidate_output).write_bytes(canonical(active) + b"\n")

    document = {
        "contract": "resilio-phase5-slice-c-recovery-github-boundary/v1",
        "governing_issue": GOVERNING_ISSUE,
        "source_boundary_comment_id": SOURCE_BOUNDARY_COMMENT_ID,
        "source_boundary_body_sha256": boundary_result["body_sha256"],
        "slice_c_pr": SLICE_C_PR,
        "slice_c_reviewed_head": REVIEWED_HEAD,
        "slice_c_reviewed_base": REVIEWED_BASE,
        "slice_c_merge": SLICE_C_MERGE,
        "failed_apply_run": FAILED_APPLY_RUN,
        "failed_apply_job": FAILED_APPLY_JOB,
        "control_sha": control_sha,
        "activation_sha": activation_sha,
        "r2_pr": activation_record["pr_number"],
        "r2_reviewed_head": activation_record["reviewed_head"],
        "r2_fresh_review_id": activation_record["fresh_review_id"],
        "r2_fresh_review_body_sha256": activation_record["fresh_review_body_sha256"],
        "r2_merge_authority_comment_id": activation_record[
            "merge_authority_comment_id"
        ],
        "r2_merge_authority_body_sha256": activation_record[
            "merge_authority_body_sha256"
        ],
        "r2_activation_record_comment_id": activation_record["comment_id"],
        "r2_activation_record_body_sha256": activation_record["body_sha256"],
        "bootstrap_fresh_review_comment_id": bootstrap_record["review_comment_id"],
        "bootstrap_fresh_review_body_sha256": bootstrap_record["review_body_sha256"],
        "bootstrap_owner_apply_authority_comment_id": bootstrap_record[
            "apply_authority_comment_id"
        ],
        "bootstrap_owner_apply_authority_body_sha256": bootstrap_record[
            "apply_authority_body_sha256"
        ],
        "bootstrap_terminal_record_comment_id": bootstrap_record["comment_id"],
        "bootstrap_terminal_record_body_sha256": bootstrap_record["body_sha256"],
        "bootstrap_reviewed_effect_sha256": bootstrap_record[
            "reviewed_effect_sha256"
        ],
        "bootstrap_apply_run": bootstrap_record["apply_run"],
        "bootstrap_apply_job": bootstrap_record["apply_job"],
        "dispatch_authority_comment_id": dispatch["comment_id"],
        "dispatch_authority_body_sha256": dispatch["body_sha256"],
    }
    document["governance_chain_sha256"] = sha256(canonical(document))
    return document


def verify_github_boundary_document(
    value: Any, control_sha: str, activation_sha: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_INVALID")
    expected_keys = {
        "contract",
        "governing_issue",
        "source_boundary_comment_id",
        "source_boundary_body_sha256",
        "slice_c_pr",
        "slice_c_reviewed_head",
        "slice_c_reviewed_base",
        "slice_c_merge",
        "failed_apply_run",
        "failed_apply_job",
        "control_sha",
        "activation_sha",
        "r2_pr",
        "r2_reviewed_head",
        "r2_fresh_review_id",
        "r2_fresh_review_body_sha256",
        "r2_merge_authority_comment_id",
        "r2_merge_authority_body_sha256",
        "r2_activation_record_comment_id",
        "r2_activation_record_body_sha256",
        "bootstrap_fresh_review_comment_id",
        "bootstrap_fresh_review_body_sha256",
        "bootstrap_owner_apply_authority_comment_id",
        "bootstrap_owner_apply_authority_body_sha256",
        "bootstrap_terminal_record_comment_id",
        "bootstrap_fresh_review_body_sha256",
        "bootstrap_owner_apply_authority_body_sha256",
        "bootstrap_terminal_record_body_sha256",
        "bootstrap_reviewed_effect_sha256",
        "bootstrap_apply_run",
        "bootstrap_apply_job",
        "dispatch_authority_comment_id",
        "dispatch_authority_body_sha256",
        "governance_chain_sha256",
    }
    if set(value) != expected_keys:
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_FIELDS_INVALID")
    if value["contract"] != "resilio-phase5-slice-c-recovery-github-boundary/v1":
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_CONTRACT_INVALID")
    if value["governing_issue"] != GOVERNING_ISSUE:
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_ISSUE_INVALID")
    if value["source_boundary_comment_id"] != SOURCE_BOUNDARY_COMMENT_ID:
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_SOURCE_INVALID")
    if value["control_sha"] != control_sha or value["activation_sha"] != activation_sha:
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_CONTROL_INVALID")
    for key in (
        "source_boundary_body_sha256",
        "r2_fresh_review_body_sha256",
        "r2_merge_authority_body_sha256",
        "r2_activation_record_body_sha256",
        "bootstrap_terminal_record_body_sha256",
        "bootstrap_reviewed_effect_sha256",
        "dispatch_authority_body_sha256",
        "governance_chain_sha256",
    ):
        if not HEX64.fullmatch(str(value.get(key) or "")):
            raise RecoveryError(f"GITHUB_BOUNDARY_DOCUMENT_HASH_INVALID:{key}")
    chain_sha = value["governance_chain_sha256"]
    unhashed = dict(value)
    del unhashed["governance_chain_sha256"]
    if sha256(canonical(unhashed)) != chain_sha:
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_HASH_MISMATCH")
    if (
        value["slice_c_pr"] != SLICE_C_PR
        or value["slice_c_reviewed_head"] != REVIEWED_HEAD
        or value["slice_c_reviewed_base"] != REVIEWED_BASE
        or value["slice_c_merge"] != SLICE_C_MERGE
        or value["failed_apply_run"] != FAILED_APPLY_RUN
        or value["failed_apply_job"] != FAILED_APPLY_JOB
    ):
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_INCIDENT_MISMATCH")
    for key in (
        "r2_pr",
        "r2_fresh_review_id",
        "r2_merge_authority_comment_id",
        "r2_activation_record_comment_id",
        "bootstrap_fresh_review_comment_id",
        "bootstrap_owner_apply_authority_comment_id",
        "bootstrap_terminal_record_comment_id",
        "bootstrap_apply_run",
        "bootstrap_apply_job",
        "dispatch_authority_comment_id",
    ):
        if not isinstance(value.get(key), int) or value[key] <= 0:
            raise RecoveryError(f"GITHUB_BOUNDARY_DOCUMENT_ID_INVALID:{key}")
    if not FULL_SHA.fullmatch(str(value.get("r2_reviewed_head") or "")):
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_R2_HEAD_INVALID")
    return value

def verify_state_identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RecoveryError("STATE_IDENTITY_INVALID")
    expected_keys = {"generation", "lineage", "serial", "managed_addresses", "state_sha256"}
    if set(value) != expected_keys:
        raise RecoveryError("STATE_IDENTITY_FIELDS_INVALID")
    if value.get("generation") != EXPECTED_GENERATION:
        raise RecoveryError("STATE_GENERATION_MISMATCH")
    if value.get("lineage") != EXPECTED_LINEAGE:
        raise RecoveryError("STATE_LINEAGE_MISMATCH")
    if value.get("serial") != EXPECTED_SERIAL:
        raise RecoveryError("STATE_SERIAL_MISMATCH")
    if tuple(value.get("managed_addresses") or ()) != EXPECTED_ADDRESSES:
        raise RecoveryError("STATE_ADDRESS_SET_MISMATCH")
    if not HEX64.fullmatch(str(value.get("state_sha256") or "")):
        raise RecoveryError("STATE_HASH_INVALID")
    return value


def _planned_addresses(plan: dict[str, Any]) -> tuple[str, ...]:
    root = (plan.get("planned_values") or {}).get("root_module") or {}
    addresses = []

    def walk(module: dict[str, Any]) -> None:
        for resource in module.get("resources") or []:
            if resource.get("mode", "managed") != "managed":
                raise RecoveryError("PLAN_RESOURCE_MODE_INVALID")
            address = resource.get("address")
            if not isinstance(address, str):
                raise RecoveryError("PLAN_RESOURCE_ADDRESS_INVALID")
            addresses.append(address)
        for child in module.get("child_modules") or []:
            if not isinstance(child, dict):
                raise RecoveryError("PLAN_CHILD_MODULE_INVALID")
            walk(child)

    walk(root)
    return tuple(sorted(addresses))


def verify_no_change_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise RecoveryError("PLAN_INVALID")
    if plan.get("format_version") != "1.2" or plan.get("terraform_version") != "1.15.8":
        raise RecoveryError("PLAN_VERSION_INVALID")
    if plan.get("errored") is not False or plan.get("complete") is not True:
        raise RecoveryError("PLAN_NOT_COMPLETE")
    if plan.get("applyable") not in (False, None):
        raise RecoveryError("PLAN_UNEXPECTEDLY_APPLYABLE")
    for key in (
        "resource_drift",
        "deferred_changes",
        "deferred_action_invocations",
        "action_invocations",
        "output_changes",
    ):
        if plan.get(key) not in (None, [], {}):
            raise RecoveryError(f"PLAN_{key.upper()}_FORBIDDEN")
    rows = plan.get("resource_changes")
    if not isinstance(rows, list):
        raise RecoveryError("PLAN_RESOURCE_CHANGES_INVALID")
    observed = []
    for row in rows:
        if not isinstance(row, dict) or row.get("mode", "managed") != "managed":
            raise RecoveryError("PLAN_RESOURCE_ROW_INVALID")
        address = row.get("address")
        if not isinstance(address, str):
            raise RecoveryError("PLAN_ADDRESS_INVALID")
        change = row.get("change") or {}
        if change.get("actions") != ["no-op"]:
            raise RecoveryError(f"PLAN_NON_NOOP_EFFECT_FORBIDDEN:{address}")
        observed.append(address)
    if tuple(sorted(observed)) != EXPECTED_ADDRESSES:
        raise RecoveryError("PLAN_ADDRESS_SET_MISMATCH")
    if _planned_addresses(plan) != EXPECTED_ADDRESSES:
        raise RecoveryError("PLAN_PLANNED_ADDRESS_SET_MISMATCH")
    return {"addresses": list(EXPECTED_ADDRESSES), "no_change": True}


def evidence_object(kind: str, control_sha: str) -> str:
    if kind not in {"claim", "result"} or not FULL_SHA.fullmatch(control_sha):
        raise RecoveryError("EVIDENCE_IDENTITY_INVALID")
    return f"{EVIDENCE_PREFIX}recovery-{kind}-{SOURCE_BOUNDARY_COMMENT_ID}-{control_sha}.json"


def gcs_upload_once(object_name: str, value: dict[str, Any]) -> dict[str, Any]:
    if object_name not in {
        evidence_object("claim", value.get("control_sha", "")),
        evidence_object("result", value.get("control_sha", "")),
    }:
        raise RecoveryError("EVIDENCE_OBJECT_MISMATCH")
    query = urllib.parse.urlencode(
        {"uploadType": "media", "name": object_name, "ifGenerationMatch": "0"}
    )
    url = f"https://storage.googleapis.com/upload/storage/v1/b/{STATE_BUCKET}/o?{query}"
    result = request_json(
        url,
        google_token(),
        "POST",
        canonical(value) + b"\n",
        "application/json",
    )
    if not isinstance(result, dict) or result.get("name") != object_name:
        raise RecoveryError("EVIDENCE_UPLOAD_IDENTITY_INVALID")
    return result


def claim_document(
    control_sha: str,
    activation_sha: str,
    run_id: str,
    github_boundary: Any,
) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(control_sha) or not FULL_SHA.fullmatch(activation_sha):
        raise RecoveryError("CLAIM_SHA_INVALID")
    if not RUN_ID.fullmatch(run_id):
        raise RecoveryError("CLAIM_RUN_ID_INVALID")
    boundary = verify_github_boundary_document(
        github_boundary, control_sha, activation_sha
    )
    value = {
        "contract": "resilio-phase5-slice-c-recovery-claim/v1",
        "governing_issue": GOVERNING_ISSUE,
        "source_boundary_comment_id": SOURCE_BOUNDARY_COMMENT_ID,
        "failed_apply_run": FAILED_APPLY_RUN,
        "failed_apply_job": FAILED_APPLY_JOB,
        "control_sha": control_sha,
        "activation_sha": activation_sha,
        "workflow_run_id": run_id,
        "governance_chain_sha256": boundary["governance_chain_sha256"],
        "github_boundary": boundary,
    }
    value["claim_sha256"] = sha256(canonical(value))
    return value


def create_claim(
    control_sha: str,
    activation_sha: str,
    run_id: str,
    github_boundary: Any,
) -> dict[str, Any]:
    value = claim_document(
        control_sha, activation_sha, run_id, github_boundary
    )
    return gcs_upload_once(evidence_object("claim", control_sha), value)


def build_result(
    before: Any,
    after: Any,
    plan: Any,
    control_sha: str,
    activation_sha: str,
    run_id: str,
    github_boundary: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    before = verify_state_identity(before)
    after = verify_state_identity(after)
    if before != after:
        raise RecoveryError("STATE_IDENTITY_CHANGED")
    verify_no_change_plan(plan)
    if not FULL_SHA.fullmatch(control_sha) or not FULL_SHA.fullmatch(activation_sha):
        raise RecoveryError("RESULT_SHA_INVALID")
    if not RUN_ID.fullmatch(run_id):
        raise RecoveryError("RESULT_RUN_ID_INVALID")
    boundary = verify_github_boundary_document(
        github_boundary, control_sha, activation_sha
    )
    claim = claim_document(control_sha, activation_sha, run_id, boundary)
    plan_sha = sha256(canonical(plan))
    private = {
        "contract": "resilio-phase5-slice-c-recovery-result/v1",
        "governing_issue": GOVERNING_ISSUE,
        "source_boundary_comment_id": SOURCE_BOUNDARY_COMMENT_ID,
        "slice_c_pr": SLICE_C_PR,
        "reviewed_head": REVIEWED_HEAD,
        "reviewed_base": REVIEWED_BASE,
        "slice_c_merge": SLICE_C_MERGE,
        "failed_apply_run": FAILED_APPLY_RUN,
        "failed_apply_job": FAILED_APPLY_JOB,
        "control_sha": control_sha,
        "activation_sha": activation_sha,
        "workflow_run_id": run_id,
        "governance_chain_sha256": boundary["governance_chain_sha256"],
        "github_boundary": boundary,
        "claim_sha256": claim["claim_sha256"],
        "claim_object": evidence_object("claim", control_sha),
        "result_object": evidence_object("result", control_sha),
        "state_before": before,
        "state_after": after,
        "plan_sha256": plan_sha,
        "terraform_reconciliation": "EXACT_NO_CHANGE",
    }
    private["result_sha256"] = sha256(canonical(private))
    public = {
        "contract": "resilio-phase5-slice-c-recovery-manifest/v1",
        "source_boundary_comment_id": SOURCE_BOUNDARY_COMMENT_ID,
        "failed_apply_run": FAILED_APPLY_RUN,
        "control_sha": control_sha,
        "activation_sha": activation_sha,
        "workflow_run_id": run_id,
        "governance_chain_sha256": boundary["governance_chain_sha256"],
        "claim_sha256": claim["claim_sha256"],
        "state_generation": before["generation"],
        "state_lineage": before["lineage"],
        "state_serial": before["serial"],
        "managed_addresses": before["managed_addresses"],
        "plan_sha256": plan_sha,
        "terraform_reconciliation": "EXACT_NO_CHANGE",
        "claim_object": private["claim_object"],
        "result_object": private["result_object"],
        "result_sha256": private["result_sha256"],
    }
    return private, public


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("verify-caller")
    p.add_argument("--repository", required=True)
    p.add_argument("--ref", required=True)
    p.add_argument("--ref-protected", required=True)
    p.add_argument("--run-attempt", required=True)
    p.add_argument("--activation-sha", required=True)
    p.add_argument("--control-sha", required=True)

    p = commands.add_parser("verify-github-boundary")
    p.add_argument("--activation-sha", required=True)
    p.add_argument("--control-sha", required=True)
    p.add_argument("--candidate-output", required=True)

    p = commands.add_parser("claim")
    p.add_argument("--activation-sha", required=True)
    p.add_argument("--control-sha", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--github-boundary", required=True)

    p = commands.add_parser("verify-state")
    p.add_argument("--file", required=True)

    p = commands.add_parser("verify-plan")
    p.add_argument("--file", required=True)

    p = commands.add_parser("build-result")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--plan-json", required=True)
    p.add_argument("--activation-sha", required=True)
    p.add_argument("--control-sha", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--github-boundary", required=True)
    p.add_argument("--private-output", required=True)
    p.add_argument("--public-output", required=True)

    p = commands.add_parser("upload-result")
    p.add_argument("--control-sha", required=True)
    p.add_argument("--file", required=True)

    args = parser.parse_args()
    try:
        if args.command == "verify-caller":
            verify_caller_context(
                args.repository,
                args.ref,
                args.ref_protected,
                args.run_attempt,
                args.activation_sha,
                args.control_sha,
            )
        elif args.command == "verify-github-boundary":
            result = verify_github_boundary(
                args.activation_sha, args.control_sha, args.candidate_output
            )
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        elif args.command == "claim":
            boundary = strict_json(Path(args.github_boundary).read_bytes())
            result = create_claim(
                args.control_sha, args.activation_sha, args.run_id, boundary
            )
            print(
                json.dumps(
                    {key: result.get(key) for key in ("bucket", "name", "generation", "metageneration")},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        elif args.command == "verify-state":
            value = strict_json(Path(args.file).read_bytes())
            verify_state_identity(value)
        elif args.command == "verify-plan":
            value = strict_json(Path(args.file).read_bytes())
            verify_no_change_plan(value)
        elif args.command == "build-result":
            before = strict_json(Path(args.before).read_bytes())
            after = strict_json(Path(args.after).read_bytes())
            plan = strict_json(Path(args.plan_json).read_bytes())
            boundary = strict_json(Path(args.github_boundary).read_bytes())
            private, public = build_result(
                before,
                after,
                plan,
                args.control_sha,
                args.activation_sha,
                args.run_id,
                boundary,
            )
            Path(args.private_output).write_bytes(canonical(private) + b"\n")
            Path(args.public_output).write_bytes(canonical(public) + b"\n")
        elif args.command == "upload-result":
            value = strict_json(Path(args.file).read_bytes())
            if value.get("contract") != "resilio-phase5-slice-c-recovery-result/v1":
                raise RecoveryError("RESULT_CONTRACT_INVALID")
            if value.get("control_sha") != args.control_sha:
                raise RecoveryError("RESULT_CONTROL_MISMATCH")
            result = gcs_upload_once(evidence_object("result", args.control_sha), value)
            print(
                json.dumps(
                    {key: result.get(key) for key in ("bucket", "name", "generation", "metageneration")},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        return 0
    except RecoveryError as exc:
        print(f"PHASE5_SLICE_C_RECOVERY_FAILED:{exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
