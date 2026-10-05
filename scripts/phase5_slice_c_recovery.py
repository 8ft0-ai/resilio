#!/usr/bin/env python3
"""Fail-closed Phase 5 Slice C reconciliation-only recovery control."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import tempfile
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

# Successor-v1 is a separate immutable recovery protocol.  The historical C1
# constants/functions above remain intact so predecessor evidence stays
# reconstructable; C2 uses only the SUCCESSOR_* surface below at runtime.
C3_ARCHITECTURE_COMMENT_ID = 5974709262
C3_ARCHITECTURE_BODY_SHA256 = "b944165bd0c5967fbaf623478a27797026b92adda02791a1373183073618279b"
C3_ARCHITECTURE_REVIEW_COMMENT_ID = 5974712806
C3_ARCHITECTURE_REVIEW_BODY_SHA256 = "77bb31e58279401917787b9dddb18ca0b672cfd5e1ea1b7bfd3e67fcb76bdcca"
SUCCESSOR_ARCHITECTURE_COMMENT_ID = 5975291821
SUCCESSOR_ARCHITECTURE_BODY_SHA256 = "6a23a4b4cb6971ec75da96a0698c4bb2f9264f9d9436ccf77a7b895891f2621c"
SUCCESSOR_ARCHITECTURE_REVIEW_COMMENT_ID = 5975295621
SUCCESSOR_ARCHITECTURE_REVIEW_BODY_SHA256 = "47ad26f6d2b1c358290a8c25b0eeeb5fdee7e3671ecf710697cebf1ddce6150a"
SUPERSEDED_CONTROL_SHA = "af197af2b0c2d2b5a5b949aeb330e9ddf5d07884"
SUPERSEDED_ACTIVATION_PR = 124
SUPERSEDED_ACTIVATION_REVIEWED_HEAD = "54a41e0762c357ae5bc9d8a0e558757f8dbeeecf"
SUPERSEDED_ACTIVATION_REVIEWED_TREE = "a97249f7bf2462670008e825804d61a13742b8e3"
SUPERSEDED_ACTIVATION_REVIEW_ID = 5403467252
SUPERSEDED_ACTIVATION_REVIEW_BODY_SHA256 = "02d55025b146e50b271ac89bb1cfcaabd1e024477e644cc3b5268dfe9915ecd7"
SUPERSEDED_ACTIVATION_AUTHORITY_ID = 5974684198
SUPERSEDED_ACTIVATION_AUTHORITY_BODY_SHA256 = "c5f26d1b3235f7a835e5637ac1eb665115ab2b2d4e85fbdbb41bf979a8365dd8"
SUPERSEDED_ACTIVATION_MERGE_SHA = "81e542ce39f1728eebaa65ae4252499a61c44e53"
SUPERSEDED_ACTIVATION_FAILURE_RECORD_ID = 5974703297
SUPERSEDED_ACTIVATION_FAILURE_RECORD_BODY_SHA256 = "aa50f2467a7b0a4d5202a502f2f3511e59be37cd58b2b0e4bb4b0ea0c0befbe5"
SUPERSEDED_CLAIM_OBJECT = (
    "plan-evidence/product/recovery-claim-5833629251-" + SUPERSEDED_CONTROL_SHA + ".json"
)
SUPERSEDED_RESULT_OBJECT = (
    "plan-evidence/product/recovery-result-5833629251-" + SUPERSEDED_CONTROL_SHA + ".json"
)
FAILED_C3_CONTROL_SHA = "4c9a4fd6f2b5c4cf3cd1d71f6c28053ab5ac5516"
FAILED_C3_ACTIVATION_PR = 126
FAILED_C3_ACTIVATION_REVIEWED_HEAD = "dc9a012ee0311f8cacd9d43e474d321999ae03d0"
FAILED_C3_ACTIVATION_REVIEWED_TREE = "1509c2b9dc38ad4166b4a87561432d1bc3f6f8fe"
FAILED_C3_ACTIVATION_REVIEW_ID = 5403643769
FAILED_C3_ACTIVATION_REVIEW_BODY_SHA256 = "bfa59a73f67ec6fdde19cd3676051ce9ee2847e03228c36900af7dc8c2d963f5"
FAILED_C3_ACTIVATION_AUTHORITY_ID = 5975180866
FAILED_C3_ACTIVATION_AUTHORITY_RAW_BODY_SHA256 = "2faf35f12b10db23c765fd8b3b2001208234cc1225790b85a20936f11fc9d82d"
FAILED_C3_ACTIVATION_FAILURE_RECORD_ID = 5975194221
FAILED_C3_ACTIVATION_FAILURE_RECORD_BODY_SHA256 = "4ebd6b87be4686895d38c87466ee7a32404e2e92dab27757c3f2ca14163bf140"
FAILED_C3_CLAIM_OBJECT = (
    "plan-evidence/product/recovery-claim-5833629251-" + FAILED_C3_CONTROL_SHA + ".json"
)
FAILED_C3_RESULT_OBJECT = (
    "plan-evidence/product/recovery-result-5833629251-" + FAILED_C3_CONTROL_SHA + ".json"
)
PREDECESSOR_CONTROL_SHA = "ae4960dd8db54849e7aa3698877c877bdb6433fd"
PREDECESSOR_ACTIVATION_SHA = "bea4af9ba159ff143bab3e695c0d43e1038691b2"
PREDECESSOR_RECOVERY_RUN = 37107984572
PREDECESSOR_RECOVERY_JOB = 111160154532
PREDECESSOR_FAILURE_RECORD_ID = 5967010836
PREDECESSOR_FAILURE_RECORD_BODY_SHA256 = "6fb66ba928b2ad6a7d1881db5494d17c7650e32a509431c460ef93c31471c400"
PREDECESSOR_CLAIM_OBJECT = (
    "plan-evidence/product/recovery-claim-5833629251-"
    + PREDECESSOR_CONTROL_SHA
    + ".json"
)
PREDECESSOR_CLAIM_GENERATION = "1791014163027927"
PREDECESSOR_CLAIM_BODY_SHA256 = "0eadcb520882e0e14361f043ef8119e6dfe2fb6c1cce2d8feb85426bf43639f1"
PREDECESSOR_CLAIM_SHA256 = "21fe2ca77b9bda8820d8336cefeb3940c324aa64762111e183fbc2a856c17624"
PREDECESSOR_GOVERNANCE_CHAIN_SHA256 = "43d9e65c0c16f1b92017615cdeb940c04dea680155167fd985a66f8a4caed80b"
PREDECESSOR_RESULT_OBJECT = (
    "plan-evidence/product/recovery-result-5833629251-"
    + PREDECESSOR_CONTROL_SHA
    + ".json"
)
S1_TERMINAL_COMMENT_ID = 5968501614
S1_TERMINAL_BODY_SHA256 = "958f75a9f533444f20910c33089c0b22146ad9c65826e12b1ed6c587dd7f29bd"
SUCCESSOR_EXPECTED_GENERATION = "1791024916608689"
SUCCESSOR_EXPECTED_STATE_BODY_SHA256 = "b68b0fbfe1d544666342fbc7092f5b7812cb907592c3a738d1e2a749d270c99b"
SUCCESSOR_EXPECTED_STATE_CANONICAL_SHA256 = "a0bd9cbe5a901c2e465ab10a35f9868a90fb0367bb022dd1a72d93f45840bbee"
SUCCESSOR_EXPECTED_LINEAGE = "d479de40-2c31-d83b-d84b-f55e9301d3a2"
SUCCESSOR_EXPECTED_SERIAL = 4
SUCCESSOR_EXPECTED_ADDRESSES = tuple(sorted(BASE_ADDRESSES))
SUCCESSOR_EXPECTED_STATUSES = {address: "normal" for address in SUCCESSOR_EXPECTED_ADDRESSES}
SUCCESSOR_VOLATILE_FIRESTORE_FIELDS = frozenset(("earliest_version_time", "etag"))

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")


class RecoveryError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_comment_text(body: Any) -> str:
    """Canonicalize GitHub comment transport newlines for grammar comparison only."""
    return str(body or "").replace("\r\n", "\n").replace("\r", "\n").strip()


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
        "contract": "resilio-phase5-slice-c-recovery-github-boundary/v2",
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
        "bootstrap_saved_plan_sha256": bootstrap_record["saved_plan_sha256"],
        "bootstrap_structural_manifest_sha256": bootstrap_record[
            "structural_manifest_sha256"
        ],
        "bootstrap_state_lineage": bootstrap_record["state_lineage"],
        "bootstrap_state_serial_before": bootstrap_record["state_serial_before"],
        "bootstrap_state_serial_after": bootstrap_record["state_serial_after"],
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
    expected_keys = (
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
        "bootstrap_saved_plan_sha256",
        "bootstrap_structural_manifest_sha256",
        "bootstrap_state_lineage",
        "bootstrap_state_serial_before",
        "bootstrap_state_serial_after",
        "bootstrap_fresh_review_comment_id",
        "bootstrap_fresh_review_body_sha256",
        "bootstrap_owner_apply_authority_comment_id",
        "bootstrap_owner_apply_authority_body_sha256",
        "bootstrap_terminal_record_comment_id",
        "bootstrap_terminal_record_body_sha256",
        "dispatch_authority_comment_id",
        "dispatch_authority_body_sha256",
        "governance_chain_sha256",
    )
    if len(expected_keys) != len(set(expected_keys)):
        raise RecoveryError("GITHUB_BOUNDARY_SCHEMA_DUPLICATE_KEY")
    if len(value) != len(expected_keys) or set(value) != set(expected_keys):
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_FIELDS_INVALID")
    if value["contract"] != "resilio-phase5-slice-c-recovery-github-boundary/v2":
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_CONTRACT_INVALID")
    if value["governing_issue"] != GOVERNING_ISSUE:
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_ISSUE_INVALID")
    if value["source_boundary_comment_id"] != SOURCE_BOUNDARY_COMMENT_ID:
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_SOURCE_INVALID")
    if value["control_sha"] != control_sha or value["activation_sha"] != activation_sha:
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_CONTROL_INVALID")

    hash_keys = (
        "source_boundary_body_sha256",
        "r2_fresh_review_body_sha256",
        "r2_merge_authority_body_sha256",
        "r2_activation_record_body_sha256",
        "bootstrap_saved_plan_sha256",
        "bootstrap_structural_manifest_sha256",
        "bootstrap_fresh_review_body_sha256",
        "bootstrap_owner_apply_authority_body_sha256",
        "bootstrap_terminal_record_body_sha256",
        "dispatch_authority_body_sha256",
        "governance_chain_sha256",
    )
    for key in hash_keys:
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

    id_keys = (
        "r2_pr",
        "r2_fresh_review_id",
        "r2_merge_authority_comment_id",
        "r2_activation_record_comment_id",
        "bootstrap_fresh_review_comment_id",
        "bootstrap_owner_apply_authority_comment_id",
        "bootstrap_terminal_record_comment_id",
        "dispatch_authority_comment_id",
    )
    for key in id_keys:
        if not isinstance(value.get(key), int) or isinstance(value.get(key), bool) or value[key] <= 0:
            raise RecoveryError(f"GITHUB_BOUNDARY_DOCUMENT_ID_INVALID:{key}")

    if not FULL_SHA.fullmatch(str(value.get("r2_reviewed_head") or "")):
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_R2_HEAD_INVALID")
    lineage = value.get("bootstrap_state_lineage")
    if not isinstance(lineage, str) or not lineage or len(lineage) > 128:
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_BOOTSTRAP_LINEAGE_INVALID")
    serial_before = value.get("bootstrap_state_serial_before")
    serial_after = value.get("bootstrap_state_serial_after")
    if (
        not isinstance(serial_before, int)
        or isinstance(serial_before, bool)
        or serial_before < 0
        or not isinstance(serial_after, int)
        or isinstance(serial_after, bool)
        or serial_after < serial_before
    ):
        raise RecoveryError("GITHUB_BOUNDARY_DOCUMENT_BOOTSTRAP_SERIAL_INVALID")
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



def _successor_fixed_comment(
    comments: list[dict[str, Any]], comment_id: int, body_sha256: str, label: str
) -> dict[str, Any]:
    matches = [row for row in comments if row.get("id") == comment_id]
    if len(matches) != 1:
        raise RecoveryError(f"{label}_NOT_UNIQUE")
    comment = matches[0]
    created, observed = _require_unedited_owner_comment(comment, GOVERNING_ISSUE, label)
    if observed != body_sha256:
        raise RecoveryError(f"{label}_BODY_HASH_MISMATCH")
    return {"comment_id": comment_id, "created_at": created, "body_sha256": observed, "body": str(comment.get("body") or "")}


def validate_successor_predecessor_records(comments: list[dict[str, Any]]) -> dict[str, Any]:
    failure = _successor_fixed_comment(
        comments, PREDECESSOR_FAILURE_RECORD_ID, PREDECESSOR_FAILURE_RECORD_BODY_SHA256,
        "SUCCESSOR_PREDECESSOR_FAILURE",
    )
    required_failure = (
        f"RECOVERY_RUN={PREDECESSOR_RECOVERY_RUN}",
        f"RECOVERY_JOB={PREDECESSOR_RECOVERY_JOB}",
        f"RECOVERY_CONTROL_SHA={PREDECESSOR_CONTROL_SHA}",
        f"RECOVERY_ACTIVATION_MAIN={PREDECESSOR_ACTIVATION_SHA}",
        f"RECOVERY_CLAIM_GENERATION={PREDECESSOR_CLAIM_GENERATION}",
        "RECOVERY_RESULT_OBJECT=ABSENT",
        "FIRESTORE_STATE_INSTANCE_STATUS=tainted",
        "RETRY_THIS_CONTROL=FORBIDDEN",
    )
    if any(token not in failure["body"] for token in required_failure):
        raise RecoveryError("SUCCESSOR_PREDECESSOR_FAILURE_CONTRACT_MISMATCH")

    terminal = _successor_fixed_comment(
        comments, S1_TERMINAL_COMMENT_ID, S1_TERMINAL_BODY_SHA256, "SUCCESSOR_S1_TERMINAL"
    )
    required_terminal = (
        f"STATE_GENERATION_AFTER={SUCCESSOR_EXPECTED_GENERATION}",
        f"STATE_BODY_SHA256_AFTER={SUCCESSOR_EXPECTED_STATE_BODY_SHA256}",
        f"STATE_SERIAL_AFTER={SUCCESSOR_EXPECTED_SERIAL}",
        f"STATE_LINEAGE={SUCCESSOR_EXPECTED_LINEAGE}",
        "ALL_INSTANCE_STATUSES=normal",
        "LIVE_CLOUD_SEMANTICS_CHANGED=NO",
        "TERMINAL_NORMAL_PLAN_EXIT=0",
        "TERMINAL_MATERIAL_RESOURCE_CHANGES=0",
        "TERMINAL_MATERIAL_OUTPUT_CHANGES=0",
        "TERMINAL_DEFERRED_ACTION_CONSEQUENCES=0",
        "TERMINAL_RESIDUAL_DRIFT=google_firestore_database.operational__earliest_version_time+etag_only",
        "FINAL_PRODUCT_LOCK=ABSENT",
        "S1_TERMINAL_DISPOSITION=RECONCILED",
    )
    if any(token not in terminal["body"] for token in required_terminal):
        raise RecoveryError("SUCCESSOR_S1_TERMINAL_CONTRACT_MISMATCH")
    if terminal["created_at"] <= failure["created_at"]:
        raise RecoveryError("SUCCESSOR_S1_TERMINAL_TIMELINE_INVALID")

    c3_architecture = _successor_fixed_comment(
        comments, C3_ARCHITECTURE_COMMENT_ID, C3_ARCHITECTURE_BODY_SHA256,
        "SUCCESSOR_C3_ARCHITECTURE",
    )
    for token in (
        "STATUS=C3_ARCHITECTURE_COMPLETE_PENDING_FRESH_REVIEW",
        f"CURRENT_MAIN={SUPERSEDED_ACTIVATION_MERGE_SHA}",
        f"IMMUTABLE_CONTROL_C2={SUPERSEDED_CONTROL_SHA}",
        f"FAILED_C2_ACTIVATION_PR={SUPERSEDED_ACTIVATION_PR}",
        f"FAILED_C2_ACTIVATION_RECORD={SUPERSEDED_ACTIVATION_FAILURE_RECORD_ID}",
        f"S1_TERMINAL={S1_TERMINAL_COMMENT_ID}",
        "LIVE_RECOVERY_WIF=C1_ONLY", "C2_LIVE_WIF=ABSENT",
        "C2_CLAIM=ABSENT", "C2_RESULT=ABSENT",
    ):
        if token not in c3_architecture["body"]:
            raise RecoveryError("SUCCESSOR_C3_ARCHITECTURE_CONTRACT_MISMATCH")

    c3_architecture_review = _successor_fixed_comment(
        comments, C3_ARCHITECTURE_REVIEW_COMMENT_ID,
        C3_ARCHITECTURE_REVIEW_BODY_SHA256, "SUCCESSOR_C3_ARCHITECTURE_REVIEW",
    )
    for token in (
        f"REVIEW_TARGET={C3_ARCHITECTURE_COMMENT_ID}",
        "DISPOSITION=APPROVED", "MATERIAL_BLOCKERS=NONE",
        "FAILED_C2_SUPERSESSION=PASS", "CURRENT_SAFETY_STATE=PASS",
        "C3_INERTNESS=PASS", "AUTHORITY_PROTOCOL_CLOSURE=PASS",
        "C3_ACTIVATION_REACHABILITY=PASS", "LIVE_WIF_REPIN_REACHABILITY=PASS",
        "C3_ONE_SHOT_RECOVERY_REACHABILITY=PASS",
    ):
        if token not in c3_architecture_review["body"]:
            raise RecoveryError("SUCCESSOR_C3_ARCHITECTURE_REVIEW_CONTRACT_MISMATCH")

    superseded = _successor_fixed_comment(
        comments,
        SUPERSEDED_ACTIVATION_FAILURE_RECORD_ID,
        SUPERSEDED_ACTIVATION_FAILURE_RECORD_BODY_SHA256,
        "SUCCESSOR_SUPERSEDED_ACTIVATION_FAILURE",
    )
    required_superseded = (
        "STATUS=POST_MERGE_AUTHORITY_GRAMMAR_DEFECT",
        f"PR=8ft0-ai/resilio#{SUPERSEDED_ACTIVATION_PR}",
        f"SUCCESSOR_CONTROL_C2={SUPERSEDED_CONTROL_SHA}",
        f"EXACT_REVIEWED_HEAD={SUPERSEDED_ACTIVATION_REVIEWED_HEAD}",
        f"EXACT_REVIEWED_TREE={SUPERSEDED_ACTIVATION_REVIEWED_TREE}",
        f"FRESH_REVIEW={SUPERSEDED_ACTIVATION_REVIEW_ID}__APPROVED",
        f"OWNER_MERGE_AUTHORITY_COMMENT_ID={SUPERSEDED_ACTIVATION_AUTHORITY_ID}",
        f"OWNER_MERGE_AUTHORITY_BODY_SHA256={SUPERSEDED_ACTIVATION_AUTHORITY_BODY_SHA256}",
        f"MERGE_SHA={SUPERSEDED_ACTIVATION_MERGE_SHA}",
        "MERGED_TREE_EQUALS_REVIEWED_TREE=TRUE",
        "DEFECT=C2_RUNTIME_REQUIRES_EXACT_MACHINE_GRAMMAR_FOR_SUCCESSOR_MERGE_AUTHORITY",
        "C2_ACTIVATION_RECORD=NOT_CREATABLE_AS_VALID_RUNTIME_EVIDENCE",
        "LIVE_RECOVERY_WIF=C1_ONLY",
        "LIVE_RECOVERY_WIF_C2=ABSENT",
        "C2_RECOVERY_CLAIM=ABSENT",
        "C2_RECOVERY_RESULT=ABSENT",
        "SUCCESSOR_DISPATCH=NOT_PERFORMED",
        "SAFETY_DISPOSITION=FAIL_CLOSED",
        "NEXT_PHASE=SUCCESSOR_CONTROL_RECONSTRUCTION_C3",
    )
    if any(token not in superseded["body"] for token in required_superseded):
        raise RecoveryError("SUCCESSOR_SUPERSEDED_ACTIVATION_FAILURE_CONTRACT_MISMATCH")
    if superseded["created_at"] <= terminal["created_at"]:
        raise RecoveryError("SUCCESSOR_SUPERSEDED_ACTIVATION_TIMELINE_INVALID")
    if not (superseded["created_at"] < c3_architecture["created_at"] < c3_architecture_review["created_at"]):
        raise RecoveryError("SUCCESSOR_C3_ARCHITECTURE_TIMELINE_INVALID")

    failed_c3 = _successor_fixed_comment(
        comments, FAILED_C3_ACTIVATION_FAILURE_RECORD_ID,
        FAILED_C3_ACTIVATION_FAILURE_RECORD_BODY_SHA256,
        "SUCCESSOR_FAILED_C3_ACTIVATION",
    )
    for token in (
        "C3 activation fail-closed before merge",
        f"PR #{FAILED_C3_ACTIVATION_PR} authority comment {FAILED_C3_ACTIVATION_AUTHORITY_ID}",
        "GitHub stored its body with CRLF line endings",
        "PR #126 must not merge",
        "No live WIF/IAM change",
        "NEXT_PHASE=AUTHORITY_SERIALIZATION_COMPATIBILITY_CLOSURE",
    ):
        if token not in failed_c3["body"]:
            raise RecoveryError("SUCCESSOR_FAILED_C3_ACTIVATION_CONTRACT_MISMATCH")

    architecture = _successor_fixed_comment(
        comments, SUCCESSOR_ARCHITECTURE_COMMENT_ID, SUCCESSOR_ARCHITECTURE_BODY_SHA256,
        "SUCCESSOR_C4_ARCHITECTURE",
    )
    for token in (
        "STATUS=C4_ARCHITECTURE_REVISION_2_COMPLETE_PENDING_FRESH_REVIEW",
        "SUPERSEDES=5975200771",
        f"CURRENT_MAIN={FAILED_C3_CONTROL_SHA}",
        f"IMMUTABLE_C3_CONTROL={FAILED_C3_CONTROL_SHA}",
        f"FAILED_C3_ACTIVATION_PR={FAILED_C3_ACTIVATION_PR}",
        f"FAILED_C3_ACTIVATION_REVIEW={FAILED_C3_ACTIVATION_REVIEW_ID}",
        f"FAILED_C3_AUTHORITY_COMMENT={FAILED_C3_ACTIVATION_AUTHORITY_ID}",
        f"FAILED_C3_AUTHORITY_RECORD={FAILED_C3_ACTIVATION_FAILURE_RECORD_ID}",
        "REPOSITORY_CALLER=C2",
        "REPOSITORY_DESIRED_WIF=C2",
        "LIVE_RECOVERY_WIF=C1",
        "C4_IMPLEMENTATION=NOT_PERFORMED",
        "LIVE_WIF_REPIN=NOT_PERFORMED",
        "RECOVERY_DISPATCH=NOT_PERFORMED",
    ):
        if token not in architecture["body"]:
            raise RecoveryError("SUCCESSOR_C4_ARCHITECTURE_CONTRACT_MISMATCH")

    architecture_review = _successor_fixed_comment(
        comments, SUCCESSOR_ARCHITECTURE_REVIEW_COMMENT_ID,
        SUCCESSOR_ARCHITECTURE_REVIEW_BODY_SHA256, "SUCCESSOR_C4_ARCHITECTURE_REVIEW",
    )
    for token in (
        f"REVIEW_TARGET={SUCCESSOR_ARCHITECTURE_COMMENT_ID}",
        "DISPOSITION=APPROVED", "MATERIAL_BLOCKERS=NONE",
        "REPOSITORY_STATE_MODEL=PASS", "DIRECT_SUCCESSOR_REACHABILITY=PASS",
        "TRANSPORT_NORMALIZATION_BOUNDARY=PASS", "RAW_PROVENANCE=PASS",
        "FAILED_C3_PROVENANCE=PASS", "INERT_C4_CONTROL=PASS",
        "C4_ACTIVATION_AND_WIF_TRANSITIONS=PASS", "ANTI_RECURRENCE=PASS",
    ):
        if token not in architecture_review["body"]:
            raise RecoveryError("SUCCESSOR_C4_ARCHITECTURE_REVIEW_CONTRACT_MISMATCH")
    if not (c3_architecture_review["created_at"] < failed_c3["created_at"] < architecture["created_at"] < architecture_review["created_at"]):
        raise RecoveryError("SUCCESSOR_C4_ARCHITECTURE_TIMELINE_INVALID")
    return {
        "failure": failure, "s1_terminal": terminal,
        "superseded_activation": superseded,
        "c3_architecture": c3_architecture,
        "c3_architecture_review": c3_architecture_review,
        "failed_c3_activation": failed_c3,
        "architecture": architecture,
        "architecture_review": architecture_review,
    }


def _successor_review_fields(body: str) -> dict[str, str]:
    lines = canonical_comment_text(body).split("\n")
    header = "COMPLETELY_FRESH_SUBSTANTIVE_SUCCESSOR_RECOVERY_IMPLEMENTATION_SECURITY_AUTHORITY_REVIEW"
    if not lines or lines[0].strip() != header:
        raise RecoveryError("SUCCESSOR_FRESH_REVIEW_HEADER_INVALID")
    wanted = (
        "DISPOSITION", "PR", "EXACT_HEAD", "EXACT_BASE", "GOVERNING_ISSUE",
        "SUCCESSOR_ARCHITECTURE", "S1_TERMINAL", "MATERIAL_BLOCKERS",
    )
    values = {name: [] for name in wanted}
    for line in lines[1:]:
        for name in wanted:
            prefix = name + "="
            if line.startswith(prefix): values[name].append(line[len(prefix):].strip())
    if any(len(values[name]) != 1 for name in wanted):
        raise RecoveryError("SUCCESSOR_FRESH_REVIEW_FIELDS_NOT_EXACT")
    return {name: values[name][0] for name in wanted}


def _activation_merge_authority_body_for_architecture(
    architecture_comment_id: int, control_sha: str, pr_number: int,
    reviewed_head: str, review_id: int, review_body_sha256: str,
) -> str:
    if architecture_comment_id <= 0:
        raise RecoveryError("SUCCESSOR_MERGE_AUTHORITY_ARCHITECTURE_INVALID")
    if not FULL_SHA.fullmatch(control_sha) or not FULL_SHA.fullmatch(reviewed_head):
        raise RecoveryError("SUCCESSOR_MERGE_AUTHORITY_SHA_INVALID")
    if pr_number <= 0 or review_id <= 0 or not HEX64.fullmatch(review_body_sha256):
        raise RecoveryError("SUCCESSOR_MERGE_AUTHORITY_IDENTITY_INVALID")
    return "\n".join((
        "PHASE5_SLICE_C_SUCCESSOR_ACTIVATION_MERGE_AUTHORITY_V1",
        "GOVERNING_ISSUE=8ft0-ai/resilio#109",
        f"SUCCESSOR_ARCHITECTURE={architecture_comment_id}",
        f"S1_TERMINAL={S1_TERMINAL_COMMENT_ID}",
        f"SUCCESSOR_CONTROL_SHA={control_sha}",
        f"SUCCESSOR_PR={pr_number}",
        f"SUCCESSOR_REVIEWED_HEAD={reviewed_head}",
        f"SUCCESSOR_BASE={control_sha}",
        f"SUCCESSOR_FRESH_REVIEW_ID={review_id}",
        f"SUCCESSOR_FRESH_REVIEW_BODY_SHA256={review_body_sha256}",
        "AUTHORITY=MERGE_EXACT_REVIEWED_SUCCESSOR_ACTIVATION_ONLY",
    ))


def successor_activation_merge_authority_body(
    control_sha: str, pr_number: int, reviewed_head: str, review_id: int,
    review_body_sha256: str,
) -> str:
    return _activation_merge_authority_body_for_architecture(
        SUCCESSOR_ARCHITECTURE_COMMENT_ID, control_sha, pr_number,
        reviewed_head, review_id, review_body_sha256,
    )


def successor_activation_record_body(
    control_sha: str, activation_sha: str, pr_number: int, reviewed_head: str,
    review_id: int, review_body_sha256: str, authority_id: int,
    authority_body_sha256: str,
) -> str:
    if not all(FULL_SHA.fullmatch(x) for x in (control_sha, activation_sha, reviewed_head)):
        raise RecoveryError("SUCCESSOR_ACTIVATION_SHA_INVALID")
    if min(pr_number, review_id, authority_id) <= 0:
        raise RecoveryError("SUCCESSOR_ACTIVATION_ID_INVALID")
    if not all(HEX64.fullmatch(x) for x in (review_body_sha256, authority_body_sha256)):
        raise RecoveryError("SUCCESSOR_ACTIVATION_HASH_INVALID")
    return "\n".join((
        "PHASE5_SLICE_C_SUCCESSOR_ACTIVATION_V1",
        "GOVERNING_ISSUE=8ft0-ai/resilio#109",
        f"SOURCE_BOUNDARY={SOURCE_BOUNDARY_COMMENT_ID}",
        f"SUCCESSOR_ARCHITECTURE={SUCCESSOR_ARCHITECTURE_COMMENT_ID}",
        f"S1_TERMINAL={S1_TERMINAL_COMMENT_ID}",
        f"S1_TERMINAL_BODY_SHA256={S1_TERMINAL_BODY_SHA256}",
        f"SUCCESSOR_CONTROL_SHA={control_sha}",
        f"SUCCESSOR_PR={pr_number}",
        f"SUCCESSOR_REVIEWED_HEAD={reviewed_head}",
        f"SUCCESSOR_BASE={control_sha}",
        f"SUCCESSOR_MERGE={activation_sha}",
        f"SUCCESSOR_FRESH_REVIEW_ID={review_id}",
        f"SUCCESSOR_FRESH_REVIEW_BODY_SHA256={review_body_sha256}",
        f"SUCCESSOR_OWNER_MERGE_AUTHORITY_COMMENT_ID={authority_id}",
        f"SUCCESSOR_OWNER_MERGE_AUTHORITY_BODY_SHA256={authority_body_sha256}",
        "STATUS=SUCCESSOR_ACTIVATION_MERGED_EXACT",
    ))


def validate_successor_activation_record(
    comments: list[dict[str, Any]], control_sha: str, activation_sha: str
) -> dict[str, Any]:
    header = "PHASE5_SLICE_C_SUCCESSOR_ACTIVATION_V1"
    matches = [c for c in comments if _owner_issue_comment(c, GOVERNING_ISSUE)
               and canonical_comment_text(c.get("body")).startswith(header + "\n")
               and f"SUCCESSOR_CONTROL_SHA={control_sha}" in canonical_comment_text(c.get("body"))]
    if len(matches) != 1:
        raise RecoveryError("SUCCESSOR_ACTIVATION_RECORD_NOT_UNIQUE")
    comment = matches[0]
    created, body_sha = _require_unedited_owner_comment(comment, GOVERNING_ISSUE, "SUCCESSOR_ACTIVATION")
    fields = _record_fields(str(comment.get("body") or ""), header, (
        "GOVERNING_ISSUE","SOURCE_BOUNDARY","SUCCESSOR_ARCHITECTURE","S1_TERMINAL",
        "S1_TERMINAL_BODY_SHA256","SUCCESSOR_CONTROL_SHA","SUCCESSOR_PR",
        "SUCCESSOR_REVIEWED_HEAD","SUCCESSOR_BASE","SUCCESSOR_MERGE",
        "SUCCESSOR_FRESH_REVIEW_ID","SUCCESSOR_FRESH_REVIEW_BODY_SHA256",
        "SUCCESSOR_OWNER_MERGE_AUTHORITY_COMMENT_ID",
        "SUCCESSOR_OWNER_MERGE_AUTHORITY_BODY_SHA256","STATUS",
    ))
    expected_fixed = {
        "GOVERNING_ISSUE":"8ft0-ai/resilio#109",
        "SOURCE_BOUNDARY":str(SOURCE_BOUNDARY_COMMENT_ID),
        "SUCCESSOR_ARCHITECTURE":str(SUCCESSOR_ARCHITECTURE_COMMENT_ID),
        "S1_TERMINAL":str(S1_TERMINAL_COMMENT_ID),
        "S1_TERMINAL_BODY_SHA256":S1_TERMINAL_BODY_SHA256,
        "SUCCESSOR_CONTROL_SHA":control_sha,"SUCCESSOR_BASE":control_sha,
        "SUCCESSOR_MERGE":activation_sha,"STATUS":"SUCCESSOR_ACTIVATION_MERGED_EXACT",
    }
    for key,value in expected_fixed.items():
        if fields[key] != value: raise RecoveryError(f"SUCCESSOR_ACTIVATION_FIELD_MISMATCH:{key}")
    if not FULL_SHA.fullmatch(fields["SUCCESSOR_REVIEWED_HEAD"]):
        raise RecoveryError("SUCCESSOR_REVIEWED_HEAD_INVALID")
    for key in ("SUCCESSOR_FRESH_REVIEW_BODY_SHA256","SUCCESSOR_OWNER_MERGE_AUTHORITY_BODY_SHA256"):
        if not HEX64.fullmatch(fields[key]): raise RecoveryError(f"SUCCESSOR_ACTIVATION_HASH_INVALID:{key}")
    return {
        "comment_id":int(comment["id"]),"created_at":created,"body_sha256":body_sha,
        "pr_number":_positive_int(fields["SUCCESSOR_PR"],"SUCCESSOR_PR"),
        "reviewed_head":fields["SUCCESSOR_REVIEWED_HEAD"],
        "review_id":_positive_int(fields["SUCCESSOR_FRESH_REVIEW_ID"],"SUCCESSOR_FRESH_REVIEW_ID"),
        "review_body_sha256":fields["SUCCESSOR_FRESH_REVIEW_BODY_SHA256"],
        "authority_id":_positive_int(fields["SUCCESSOR_OWNER_MERGE_AUTHORITY_COMMENT_ID"],"SUCCESSOR_OWNER_MERGE_AUTHORITY_COMMENT_ID"),
        "authority_body_sha256":fields["SUCCESSOR_OWNER_MERGE_AUTHORITY_BODY_SHA256"],
    }


def validate_successor_activation_transaction(
    pr: Any, review: Any, authority_comment: Any, reviewed_commit: Any,
    merge_commit: Any, record: dict[str, Any], control_sha: str, activation_sha: str,
) -> None:
    if not isinstance(pr,dict) or pr.get("number") != record["pr_number"] or pr.get("state") != "closed" or pr.get("merged_at") is None:
        raise RecoveryError("SUCCESSOR_PR_INVALID")
    if pr.get("merge_commit_sha") != activation_sha or pr.get("head",{}).get("sha") != record["reviewed_head"]:
        raise RecoveryError("SUCCESSOR_PR_IDENTITY_MISMATCH")
    if pr.get("base",{}).get("ref") != DEFAULT_BRANCH or pr.get("base",{}).get("sha") != control_sha:
        raise RecoveryError("SUCCESSOR_PR_BASE_MISMATCH")
    hr=pr.get("head",{}).get("repo") or {}
    if hr.get("id") != REPOSITORY_ID or hr.get("full_name") != REPOSITORY:
        raise RecoveryError("SUCCESSOR_PR_REPOSITORY_MISMATCH")
    if not isinstance(reviewed_commit, dict) or reviewed_commit.get("sha") != record["reviewed_head"]:
        raise RecoveryError("SUCCESSOR_ACTIVATION_REVIEWED_COMMIT_INVALID")
    reviewed_tree = (reviewed_commit.get("commit") or {}).get("tree", {}).get("sha")
    if not FULL_SHA.fullmatch(str(reviewed_tree or "")):
        raise RecoveryError("SUCCESSOR_ACTIVATION_REVIEWED_TREE_INVALID")
    if not isinstance(merge_commit, dict) or merge_commit.get("sha") != activation_sha:
        raise RecoveryError("SUCCESSOR_ACTIVATION_MERGE_COMMIT_INVALID")
    merged_tree = (merge_commit.get("commit") or {}).get("tree", {}).get("sha")
    if merged_tree != reviewed_tree:
        raise RecoveryError("SUCCESSOR_ACTIVATION_MERGED_TREE_MISMATCH")
    if not isinstance(review,dict) or review.get("id") != record["review_id"] or review.get("state") != "COMMENTED" or review.get("commit_id") != record["reviewed_head"]:
        raise RecoveryError("SUCCESSOR_REVIEW_IDENTITY_MISMATCH")
    user=review.get("user") or {}
    if user.get("login") != OWNER_LOGIN or user.get("id") != OWNER_ID:
        raise RecoveryError("SUCCESSOR_REVIEW_AUTHOR_MISMATCH")
    fields=_successor_review_fields(str(review.get("body") or ""))
    expected={
        "DISPOSITION":"APPROVED","PR":f"8ft0-ai/resilio#{record['pr_number']}",
        "EXACT_HEAD":record["reviewed_head"],"EXACT_BASE":control_sha,
        "GOVERNING_ISSUE":"8ft0-ai/resilio#109",
        "SUCCESSOR_ARCHITECTURE":str(SUCCESSOR_ARCHITECTURE_COMMENT_ID),
        "S1_TERMINAL":str(S1_TERMINAL_COMMENT_ID),"MATERIAL_BLOCKERS":"NONE",
    }
    if fields != expected: raise RecoveryError("SUCCESSOR_REVIEW_CONTRACT_MISMATCH")
    review_sha=sha256(str(review.get("body") or "").encode())
    if review_sha != record["review_body_sha256"]: raise RecoveryError("SUCCESSOR_REVIEW_HASH_MISMATCH")
    if not isinstance(authority_comment,dict) or authority_comment.get("id") != record["authority_id"]:
        raise RecoveryError("SUCCESSOR_MERGE_AUTHORITY_INVALID")
    authority_created,authority_sha=_require_unedited_owner_comment(authority_comment,record["pr_number"],"SUCCESSOR_MERGE_AUTHORITY")
    expected_authority=successor_activation_merge_authority_body(control_sha,record["pr_number"],record["reviewed_head"],record["review_id"],record["review_body_sha256"])
    if canonical_comment_text(authority_comment.get("body")) != expected_authority or authority_sha != record["authority_body_sha256"]:
        raise RecoveryError("SUCCESSOR_MERGE_AUTHORITY_CONTRACT_MISMATCH")
    review_time=_timestamp(review.get("submitted_at"),"SUCCESSOR_REVIEW_SUBMITTED")
    merge_time=_timestamp(pr.get("merged_at"),"SUCCESSOR_MERGED")
    if not (review_time <= authority_created < merge_time <= record["created_at"]):
        raise RecoveryError("SUCCESSOR_ACTIVATION_TIMELINE_INVALID")


def validate_superseded_activation_history(
    pr: Any, review: Any, authority_comment: Any, reviewed_commit: Any,
    merge_commit: Any, failure_record: dict[str, Any]
) -> None:
    if not isinstance(pr, dict) or pr.get("number") != SUPERSEDED_ACTIVATION_PR:
        raise RecoveryError("SUPERSEDED_ACTIVATION_PR_INVALID")
    if pr.get("state") != "closed" or pr.get("merged_at") is None:
        raise RecoveryError("SUPERSEDED_ACTIVATION_PR_NOT_MERGED")
    if pr.get("merge_commit_sha") != SUPERSEDED_ACTIVATION_MERGE_SHA:
        raise RecoveryError("SUPERSEDED_ACTIVATION_MERGE_MISMATCH")
    if pr.get("head", {}).get("sha") != SUPERSEDED_ACTIVATION_REVIEWED_HEAD:
        raise RecoveryError("SUPERSEDED_ACTIVATION_HEAD_MISMATCH")
    if pr.get("base", {}).get("sha") != SUPERSEDED_CONTROL_SHA or pr.get("base", {}).get("ref") != DEFAULT_BRANCH:
        raise RecoveryError("SUPERSEDED_ACTIVATION_BASE_MISMATCH")
    if not isinstance(reviewed_commit, dict) or reviewed_commit.get("sha") != SUPERSEDED_ACTIVATION_REVIEWED_HEAD:
        raise RecoveryError("SUPERSEDED_ACTIVATION_REVIEWED_COMMIT_INVALID")
    if (reviewed_commit.get("commit") or {}).get("tree", {}).get("sha") != SUPERSEDED_ACTIVATION_REVIEWED_TREE:
        raise RecoveryError("SUPERSEDED_ACTIVATION_REVIEWED_TREE_MISMATCH")
    if not isinstance(merge_commit, dict) or merge_commit.get("sha") != SUPERSEDED_ACTIVATION_MERGE_SHA:
        raise RecoveryError("SUPERSEDED_ACTIVATION_MERGE_COMMIT_INVALID")
    if (merge_commit.get("commit") or {}).get("tree", {}).get("sha") != SUPERSEDED_ACTIVATION_REVIEWED_TREE:
        raise RecoveryError("SUPERSEDED_ACTIVATION_MERGED_TREE_MISMATCH")
    head_repo = pr.get("head", {}).get("repo") or {}
    if head_repo.get("id") != REPOSITORY_ID or head_repo.get("full_name") != REPOSITORY:
        raise RecoveryError("SUPERSEDED_ACTIVATION_REPOSITORY_MISMATCH")
    if not isinstance(review, dict) or review.get("id") != SUPERSEDED_ACTIVATION_REVIEW_ID:
        raise RecoveryError("SUPERSEDED_ACTIVATION_REVIEW_INVALID")
    review_user = review.get("user") or {}
    if review_user.get("login") != OWNER_LOGIN or review_user.get("id") != OWNER_ID:
        raise RecoveryError("SUPERSEDED_ACTIVATION_REVIEW_OWNER_MISMATCH")
    if review.get("state") != "COMMENTED" or review.get("commit_id") != SUPERSEDED_ACTIVATION_REVIEWED_HEAD:
        raise RecoveryError("SUPERSEDED_ACTIVATION_REVIEW_IDENTITY_MISMATCH")
    if sha256(str(review.get("body") or "").encode()) != SUPERSEDED_ACTIVATION_REVIEW_BODY_SHA256:
        raise RecoveryError("SUPERSEDED_ACTIVATION_REVIEW_HASH_MISMATCH")
    if not isinstance(authority_comment, dict) or authority_comment.get("id") != SUPERSEDED_ACTIVATION_AUTHORITY_ID:
        raise RecoveryError("SUPERSEDED_ACTIVATION_AUTHORITY_INVALID")
    authority_created, authority_sha = _require_unedited_owner_comment(
        authority_comment, SUPERSEDED_ACTIVATION_PR, "SUPERSEDED_ACTIVATION_AUTHORITY"
    )
    if authority_sha != SUPERSEDED_ACTIVATION_AUTHORITY_BODY_SHA256:
        raise RecoveryError("SUPERSEDED_ACTIVATION_AUTHORITY_HASH_MISMATCH")
    review_time = _timestamp(review.get("submitted_at"), "SUPERSEDED_ACTIVATION_REVIEW_SUBMITTED")
    merge_time = _timestamp(pr.get("merged_at"), "SUPERSEDED_ACTIVATION_MERGED")
    if not (review_time <= authority_created < merge_time <= failure_record["created_at"]):
        raise RecoveryError("SUPERSEDED_ACTIVATION_TIMELINE_INVALID")


def validate_failed_c3_activation_history(
    pr: Any, review: Any, authority_comment: Any, reviewed_commit: Any,
    failure_record: dict[str, Any],
) -> None:
    if not isinstance(pr, dict) or pr.get("number") != FAILED_C3_ACTIVATION_PR:
        raise RecoveryError("FAILED_C3_ACTIVATION_PR_INVALID")
    if pr.get("state") != "closed" or pr.get("merged_at") is not None:
        raise RecoveryError("FAILED_C3_ACTIVATION_PR_STATE_INVALID")
    if pr.get("head", {}).get("sha") != FAILED_C3_ACTIVATION_REVIEWED_HEAD:
        raise RecoveryError("FAILED_C3_ACTIVATION_HEAD_MISMATCH")
    if pr.get("base", {}).get("ref") != DEFAULT_BRANCH or pr.get("base", {}).get("sha") != FAILED_C3_CONTROL_SHA:
        raise RecoveryError("FAILED_C3_ACTIVATION_BASE_MISMATCH")
    head_repo = pr.get("head", {}).get("repo") or {}
    if head_repo.get("id") != REPOSITORY_ID or head_repo.get("full_name") != REPOSITORY:
        raise RecoveryError("FAILED_C3_ACTIVATION_REPOSITORY_MISMATCH")
    if not isinstance(reviewed_commit, dict) or reviewed_commit.get("sha") != FAILED_C3_ACTIVATION_REVIEWED_HEAD:
        raise RecoveryError("FAILED_C3_ACTIVATION_REVIEWED_COMMIT_INVALID")
    if (reviewed_commit.get("commit") or {}).get("tree", {}).get("sha") != FAILED_C3_ACTIVATION_REVIEWED_TREE:
        raise RecoveryError("FAILED_C3_ACTIVATION_REVIEWED_TREE_MISMATCH")
    if not isinstance(review, dict) or review.get("id") != FAILED_C3_ACTIVATION_REVIEW_ID:
        raise RecoveryError("FAILED_C3_ACTIVATION_REVIEW_INVALID")
    review_user = review.get("user") or {}
    if review_user.get("login") != OWNER_LOGIN or review_user.get("id") != OWNER_ID:
        raise RecoveryError("FAILED_C3_ACTIVATION_REVIEW_OWNER_MISMATCH")
    if review.get("state") != "COMMENTED" or review.get("commit_id") != FAILED_C3_ACTIVATION_REVIEWED_HEAD:
        raise RecoveryError("FAILED_C3_ACTIVATION_REVIEW_IDENTITY_MISMATCH")
    if sha256(str(review.get("body") or "").encode()) != FAILED_C3_ACTIVATION_REVIEW_BODY_SHA256:
        raise RecoveryError("FAILED_C3_ACTIVATION_REVIEW_HASH_MISMATCH")
    expected_review = {
        "DISPOSITION": "APPROVED",
        "PR": f"8ft0-ai/resilio#{FAILED_C3_ACTIVATION_PR}",
        "EXACT_HEAD": FAILED_C3_ACTIVATION_REVIEWED_HEAD,
        "EXACT_BASE": FAILED_C3_CONTROL_SHA,
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "SUCCESSOR_ARCHITECTURE": str(C3_ARCHITECTURE_COMMENT_ID),
        "S1_TERMINAL": str(S1_TERMINAL_COMMENT_ID),
        "MATERIAL_BLOCKERS": "NONE",
    }
    if _successor_review_fields(str(review.get("body") or "")) != expected_review:
        raise RecoveryError("FAILED_C3_ACTIVATION_REVIEW_CONTRACT_MISMATCH")
    if not isinstance(authority_comment, dict) or authority_comment.get("id") != FAILED_C3_ACTIVATION_AUTHORITY_ID:
        raise RecoveryError("FAILED_C3_ACTIVATION_AUTHORITY_INVALID")
    authority_created, authority_sha = _require_unedited_owner_comment(
        authority_comment, FAILED_C3_ACTIVATION_PR, "FAILED_C3_ACTIVATION_AUTHORITY"
    )
    if authority_sha != FAILED_C3_ACTIVATION_AUTHORITY_RAW_BODY_SHA256:
        raise RecoveryError("FAILED_C3_ACTIVATION_AUTHORITY_RAW_HASH_MISMATCH")
    raw_body = str(authority_comment.get("body") or "")
    if "\r\n" not in raw_body or "\r" in raw_body.replace("\r\n", ""):
        raise RecoveryError("FAILED_C3_ACTIVATION_AUTHORITY_TRANSPORT_NOT_CRLF")
    expected_authority = _activation_merge_authority_body_for_architecture(
        C3_ARCHITECTURE_COMMENT_ID, FAILED_C3_CONTROL_SHA, FAILED_C3_ACTIVATION_PR,
        FAILED_C3_ACTIVATION_REVIEWED_HEAD, FAILED_C3_ACTIVATION_REVIEW_ID,
        FAILED_C3_ACTIVATION_REVIEW_BODY_SHA256,
    )
    if canonical_comment_text(raw_body) != expected_authority:
        raise RecoveryError("FAILED_C3_ACTIVATION_AUTHORITY_CANONICAL_GRAMMAR_MISMATCH")
    review_time = _timestamp(review.get("submitted_at"), "FAILED_C3_ACTIVATION_REVIEW_SUBMITTED")
    if not (review_time <= authority_created < failure_record["created_at"]):
        raise RecoveryError("FAILED_C3_ACTIVATION_TIMELINE_INVALID")


def verify_successor_activation_premerge(
    control_sha: str, pr_number: int, reviewed_head: str, review_id: int,
    review_body_sha256: str, authority_id: int,
) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(control_sha) or control_sha in (PREDECESSOR_CONTROL_SHA, SUPERSEDED_CONTROL_SHA):
        raise RecoveryError("SUCCESSOR_PREMERGE_CONTROL_INVALID")
    if not FULL_SHA.fullmatch(reviewed_head) or min(pr_number, review_id, authority_id) <= 0:
        raise RecoveryError("SUCCESSOR_PREMERGE_IDENTITY_INVALID")
    if not HEX64.fullmatch(review_body_sha256):
        raise RecoveryError("SUCCESSOR_PREMERGE_REVIEW_HASH_INVALID")
    branch = github(f"/repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}")
    if not isinstance(branch, dict) or branch.get("commit", {}).get("sha") != control_sha:
        raise RecoveryError("SUCCESSOR_PREMERGE_MAIN_MISMATCH")
    pr = github(f"/repos/{REPOSITORY}/pulls/{pr_number}")
    if not isinstance(pr, dict) or pr.get("number") != pr_number or pr.get("state") != "open" or pr.get("merged_at") is not None or pr.get("draft") is True:
        raise RecoveryError("SUCCESSOR_PREMERGE_PR_INVALID")
    if pr.get("head", {}).get("sha") != reviewed_head:
        raise RecoveryError("SUCCESSOR_PREMERGE_HEAD_MISMATCH")
    if pr.get("base", {}).get("ref") != DEFAULT_BRANCH or pr.get("base", {}).get("sha") != control_sha:
        raise RecoveryError("SUCCESSOR_PREMERGE_BASE_MISMATCH")
    head_repo = pr.get("head", {}).get("repo") or {}
    if head_repo.get("id") != REPOSITORY_ID or head_repo.get("full_name") != REPOSITORY:
        raise RecoveryError("SUCCESSOR_PREMERGE_REPOSITORY_MISMATCH")
    review = github(f"/repos/{REPOSITORY}/pulls/{pr_number}/reviews/{review_id}")
    if not isinstance(review, dict) or review.get("id") != review_id or review.get("state") != "COMMENTED" or review.get("commit_id") != reviewed_head:
        raise RecoveryError("SUCCESSOR_PREMERGE_REVIEW_IDENTITY_MISMATCH")
    review_user = review.get("user") or {}
    if review_user.get("login") != OWNER_LOGIN or review_user.get("id") != OWNER_ID:
        raise RecoveryError("SUCCESSOR_PREMERGE_REVIEW_OWNER_MISMATCH")
    fields = _successor_review_fields(str(review.get("body") or ""))
    expected = {
        "DISPOSITION": "APPROVED",
        "PR": f"8ft0-ai/resilio#{pr_number}",
        "EXACT_HEAD": reviewed_head,
        "EXACT_BASE": control_sha,
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "SUCCESSOR_ARCHITECTURE": str(SUCCESSOR_ARCHITECTURE_COMMENT_ID),
        "S1_TERMINAL": str(S1_TERMINAL_COMMENT_ID),
        "MATERIAL_BLOCKERS": "NONE",
    }
    if fields != expected:
        raise RecoveryError("SUCCESSOR_PREMERGE_REVIEW_CONTRACT_MISMATCH")
    actual_review_sha = sha256(str(review.get("body") or "").encode())
    if actual_review_sha != review_body_sha256:
        raise RecoveryError("SUCCESSOR_PREMERGE_REVIEW_HASH_MISMATCH")
    authority = github(f"/repos/{REPOSITORY}/issues/comments/{authority_id}")
    authority_created, authority_sha = _require_unedited_owner_comment(
        authority, pr_number, "SUCCESSOR_PREMERGE_AUTHORITY"
    )
    expected_authority = successor_activation_merge_authority_body(
        control_sha, pr_number, reviewed_head, review_id, review_body_sha256
    )
    if canonical_comment_text(authority.get("body")) != expected_authority:
        raise RecoveryError("SUCCESSOR_PREMERGE_AUTHORITY_BODY_MISMATCH")
    review_time = _timestamp(review.get("submitted_at"), "SUCCESSOR_PREMERGE_REVIEW_SUBMITTED")
    if review_time > authority_created:
        raise RecoveryError("SUCCESSOR_PREMERGE_TIMELINE_INVALID")
    return {
        "contract": "resilio-phase5-slice-c-successor-premerge-authority/v1",
        "control_sha": control_sha,
        "pr_number": pr_number,
        "reviewed_head": reviewed_head,
        "review_id": review_id,
        "review_body_sha256": review_body_sha256,
        "authority_id": authority_id,
        "authority_body_sha256": authority_sha,
        "current_main": control_sha,
        "verified": True,
    }


def successor_wif_repin_review_body(
    control_sha: str, activation_sha: str, plan_sha: str, manifest_sha: str,
    state_lineage: str, state_serial: int,
) -> str:
    if not all(FULL_SHA.fullmatch(x) for x in (control_sha,activation_sha)) or not all(HEX64.fullmatch(x) for x in (plan_sha,manifest_sha)):
        raise RecoveryError("SUCCESSOR_WIF_REPIN_REVIEW_IDENTITY_INVALID")
    return "\n".join((
        "PHASE5_SLICE_C_SUCCESSOR_WIF_REPIN_PLAN_FRESH_REVIEW_V1",
        "GOVERNING_ISSUE=8ft0-ai/resilio#109",
        f"SUCCESSOR_CONTROL_SHA={control_sha}",f"SUCCESSOR_ACTIVATION_MAIN={activation_sha}",
        f"SAVED_PLAN_SHA256={plan_sha}",f"STRUCTURAL_MANIFEST_SHA256={manifest_sha}",
        f"BOOTSTRAP_STATE_LINEAGE={state_lineage}",f"BOOTSTRAP_STATE_SERIAL={state_serial}",
        "TERRAFORM_VERSION=1.15.8","PLAN_FORMAT_VERSION=1.2",
        "PLAN_EFFECTS=EXACT_ONE_RECOVERY_WIF_SUBJECT_REPIN_C1_TO_C4",
        "REVIEW_DISPOSITION=APPROVED","MATERIAL_BLOCKERS=NONE","APPLY_AUTHORITY=NOT_GRANTED",
    ))


def successor_wif_repin_authority_body(
    control_sha: str, activation_sha: str, plan_sha: str, manifest_sha: str,
    state_lineage: str, state_serial: int, review_id: int, review_sha: str,
) -> str:
    return "\n".join((
        "PHASE5_SLICE_C_SUCCESSOR_WIF_REPIN_APPLY_AUTHORITY_V1",
        "GOVERNING_ISSUE=8ft0-ai/resilio#109",f"SUCCESSOR_CONTROL_SHA={control_sha}",
        f"SUCCESSOR_ACTIVATION_MAIN={activation_sha}",f"SAVED_PLAN_SHA256={plan_sha}",
        f"STRUCTURAL_MANIFEST_SHA256={manifest_sha}",f"BOOTSTRAP_STATE_LINEAGE={state_lineage}",
        f"BOOTSTRAP_STATE_SERIAL={state_serial}",f"FRESH_REVIEW_COMMENT_ID={review_id}",
        f"FRESH_REVIEW_BODY_SHA256={review_sha}","AUTHORITY=APPLY_EXACT_REVIEWED_WIF_REPIN_PLAN_ONCE",
        "REPLAN=NOT_AUTHORISED","PLAN_REPLACEMENT=NOT_AUTHORISED","BLIND_RETRY=NOT_AUTHORISED",
    ))


def successor_wif_repin_terminal_body(
    control_sha: str, activation_sha: str, plan_sha: str, manifest_sha: str,
    state_lineage: str, serial_before: int, serial_after: int, review_id: int,
    review_sha: str, authority_id: int, authority_sha: str,
) -> str:
    return "\n".join((
        "PHASE5_SLICE_C_SUCCESSOR_WIF_REPIN_TERMINAL_V1",
        "GOVERNING_ISSUE=8ft0-ai/resilio#109",f"SUCCESSOR_CONTROL_SHA={control_sha}",
        f"SUCCESSOR_ACTIVATION_MAIN={activation_sha}",f"SAVED_PLAN_SHA256={plan_sha}",
        f"STRUCTURAL_MANIFEST_SHA256={manifest_sha}",f"BOOTSTRAP_STATE_LINEAGE={state_lineage}",
        f"BOOTSTRAP_STATE_SERIAL_BEFORE={serial_before}",f"BOOTSTRAP_STATE_SERIAL_AFTER={serial_after}",
        f"FRESH_REVIEW_COMMENT_ID={review_id}",f"FRESH_REVIEW_BODY_SHA256={review_sha}",
        f"OWNER_APPLY_AUTHORITY_COMMENT_ID={authority_id}",f"OWNER_APPLY_AUTHORITY_BODY_SHA256={authority_sha}",
        "WIF_REPIN=EXACT_C1_TO_C4_LIVE","OLD_C1_RECOVERY_WIF=ABSENT","SUPERSEDED_C2_RECOVERY_WIF=ABSENT","SUPERSEDED_C3_RECOVERY_WIF=ABSENT","NEW_C4_RECOVERY_WIF=EXACT_ONE",
        "GETMETADATA=UNCHANGED_LIVE","NORMAL_PHASE5_IDENTITIES=UNCHANGED",
        "BOOTSTRAP_RECONCILIATION=EXACT_NO_CHANGE","FINAL_BOOTSTRAP_LOCK=ABSENT","TERMINAL_DISPOSITION=RECONCILED",
    ))


def validate_successor_wif_repin_terminal(
    comments: list[dict[str,Any]], control_sha: str, activation_sha: str,
    activation_created_at: datetime,
) -> dict[str,Any]:
    header="PHASE5_SLICE_C_SUCCESSOR_WIF_REPIN_TERMINAL_V1"
    matches=[c for c in comments if _owner_issue_comment(c,GOVERNING_ISSUE) and canonical_comment_text(c.get("body")).startswith(header+"\n") and f"SUCCESSOR_CONTROL_SHA={control_sha}" in canonical_comment_text(c.get("body"))]
    if len(matches)!=1: raise RecoveryError("SUCCESSOR_WIF_REPIN_TERMINAL_NOT_UNIQUE")
    c=matches[0]; created,body_sha=_require_unedited_owner_comment(c,GOVERNING_ISSUE,"SUCCESSOR_WIF_REPIN_TERMINAL")
    f=_record_fields(str(c.get("body") or ""),header,(
        "GOVERNING_ISSUE","SUCCESSOR_CONTROL_SHA","SUCCESSOR_ACTIVATION_MAIN","SAVED_PLAN_SHA256","STRUCTURAL_MANIFEST_SHA256","BOOTSTRAP_STATE_LINEAGE","BOOTSTRAP_STATE_SERIAL_BEFORE","BOOTSTRAP_STATE_SERIAL_AFTER","FRESH_REVIEW_COMMENT_ID","FRESH_REVIEW_BODY_SHA256","OWNER_APPLY_AUTHORITY_COMMENT_ID","OWNER_APPLY_AUTHORITY_BODY_SHA256","WIF_REPIN","OLD_C1_RECOVERY_WIF","SUPERSEDED_C2_RECOVERY_WIF","SUPERSEDED_C3_RECOVERY_WIF","NEW_C4_RECOVERY_WIF","GETMETADATA","NORMAL_PHASE5_IDENTITIES","BOOTSTRAP_RECONCILIATION","FINAL_BOOTSTRAP_LOCK","TERMINAL_DISPOSITION"))
    expected={"GOVERNING_ISSUE":"8ft0-ai/resilio#109","SUCCESSOR_CONTROL_SHA":control_sha,"SUCCESSOR_ACTIVATION_MAIN":activation_sha,"WIF_REPIN":"EXACT_C1_TO_C4_LIVE","OLD_C1_RECOVERY_WIF":"ABSENT","SUPERSEDED_C2_RECOVERY_WIF":"ABSENT","SUPERSEDED_C3_RECOVERY_WIF":"ABSENT","NEW_C4_RECOVERY_WIF":"EXACT_ONE","GETMETADATA":"UNCHANGED_LIVE","NORMAL_PHASE5_IDENTITIES":"UNCHANGED","BOOTSTRAP_RECONCILIATION":"EXACT_NO_CHANGE","FINAL_BOOTSTRAP_LOCK":"ABSENT","TERMINAL_DISPOSITION":"RECONCILED"}
    for k,v in expected.items():
        if f[k]!=v: raise RecoveryError(f"SUCCESSOR_WIF_REPIN_FIELD_MISMATCH:{k}")
    for k in ("SAVED_PLAN_SHA256","STRUCTURAL_MANIFEST_SHA256","FRESH_REVIEW_BODY_SHA256","OWNER_APPLY_AUTHORITY_BODY_SHA256"):
        if not HEX64.fullmatch(f[k]): raise RecoveryError(f"SUCCESSOR_WIF_REPIN_HASH_INVALID:{k}")
    sb=_nonnegative_int(f["BOOTSTRAP_STATE_SERIAL_BEFORE"],"SUCCESSOR_WIF_REPIN_SERIAL_BEFORE"); sa=_nonnegative_int(f["BOOTSTRAP_STATE_SERIAL_AFTER"],"SUCCESSOR_WIF_REPIN_SERIAL_AFTER")
    if sa < sb: raise RecoveryError("SUCCESSOR_WIF_REPIN_SERIAL_REVERSED")
    review_id=_positive_int(f["FRESH_REVIEW_COMMENT_ID"],"SUCCESSOR_WIF_REPIN_REVIEW_ID"); authority_id=_positive_int(f["OWNER_APPLY_AUTHORITY_COMMENT_ID"],"SUCCESSOR_WIF_REPIN_AUTHORITY_ID")
    review_matches=[x for x in comments if x.get("id")==review_id]; authority_matches=[x for x in comments if x.get("id")==authority_id]
    if len(review_matches)!=1 or len(authority_matches)!=1: raise RecoveryError("SUCCESSOR_WIF_REPIN_PREREQUISITE_NOT_UNIQUE")
    review=review_matches[0]; review_created,review_sha=_require_unedited_owner_comment(review,GOVERNING_ISSUE,"SUCCESSOR_WIF_REPIN_REVIEW")
    expected_review=successor_wif_repin_review_body(control_sha,activation_sha,f["SAVED_PLAN_SHA256"],f["STRUCTURAL_MANIFEST_SHA256"],f["BOOTSTRAP_STATE_LINEAGE"],sb)
    if canonical_comment_text(review.get("body"))!=expected_review or review_sha!=f["FRESH_REVIEW_BODY_SHA256"]: raise RecoveryError("SUCCESSOR_WIF_REPIN_REVIEW_MISMATCH")
    authority=authority_matches[0]; authority_created,authority_sha=_require_unedited_owner_comment(authority,GOVERNING_ISSUE,"SUCCESSOR_WIF_REPIN_AUTHORITY")
    expected_authority=successor_wif_repin_authority_body(control_sha,activation_sha,f["SAVED_PLAN_SHA256"],f["STRUCTURAL_MANIFEST_SHA256"],f["BOOTSTRAP_STATE_LINEAGE"],sb,review_id,review_sha)
    if canonical_comment_text(authority.get("body"))!=expected_authority or authority_sha!=f["OWNER_APPLY_AUTHORITY_BODY_SHA256"]: raise RecoveryError("SUCCESSOR_WIF_REPIN_AUTHORITY_MISMATCH")
    if not (activation_created_at <= review_created <= authority_created <= created): raise RecoveryError("SUCCESSOR_WIF_REPIN_TIMELINE_INVALID")
    return {"comment_id":int(c["id"]),"created_at":created,"body_sha256":body_sha,"saved_plan_sha256":f["SAVED_PLAN_SHA256"],"manifest_sha256":f["STRUCTURAL_MANIFEST_SHA256"],"review_id":review_id,"review_sha256":review_sha,"authority_id":authority_id,"authority_sha256":authority_sha,"state_lineage":f["BOOTSTRAP_STATE_LINEAGE"],"serial_before":sb,"serial_after":sa}


def successor_dispatch_authority_body(
    control_sha: str, activation_sha: str, activation_record: dict[str,Any],
    repin_terminal: dict[str,Any],
) -> str:
    return "\n".join((
        "PHASE5_SLICE_C_SUCCESSOR_DISPATCH_AUTHORITY_V1","GOVERNING_ISSUE=8ft0-ai/resilio#109",
        f"SUCCESSOR_CONTROL_SHA={control_sha}",f"SUCCESSOR_ACTIVATION_MAIN={activation_sha}",
        f"SUCCESSOR_ACTIVATION_RECORD={activation_record['comment_id']}",f"SUCCESSOR_ACTIVATION_RECORD_BODY_SHA256={activation_record['body_sha256']}",
        f"SUCCESSOR_WIF_REPIN_TERMINAL={repin_terminal['comment_id']}",f"SUCCESSOR_WIF_REPIN_TERMINAL_BODY_SHA256={repin_terminal['body_sha256']}",
        f"PRODUCT_STATE_GENERATION={SUCCESSOR_EXPECTED_GENERATION}",f"PRODUCT_STATE_LINEAGE={SUCCESSOR_EXPECTED_LINEAGE}",f"PRODUCT_STATE_SERIAL={SUCCESSOR_EXPECTED_SERIAL}",f"PRODUCT_STATE_CANONICAL_SHA256={SUCCESSOR_EXPECTED_STATE_CANONICAL_SHA256}",
        f"S1_TERMINAL={S1_TERMINAL_COMMENT_ID}",f"S1_TERMINAL_BODY_SHA256={S1_TERMINAL_BODY_SHA256}",
        "AUTHORITY=DISPATCH_EXACTLY_ONE_SUCCESSOR_RECONCILIATION_ONLY_RECOVERY",
    ))


def validate_successor_dispatch_authority(
    comments: list[dict[str,Any]], control_sha: str, activation_sha: str,
    activation_record: dict[str,Any], repin_terminal: dict[str,Any],
) -> dict[str,Any]:
    expected=successor_dispatch_authority_body(control_sha,activation_sha,activation_record,repin_terminal)
    matches=[c for c in comments if _owner_issue_comment(c,GOVERNING_ISSUE) and canonical_comment_text(c.get("body"))==expected]
    if len(matches)!=1: raise RecoveryError("SUCCESSOR_DISPATCH_AUTHORITY_NOT_UNIQUE")
    c=matches[0]; created,body_sha=_require_unedited_owner_comment(c,GOVERNING_ISSUE,"SUCCESSOR_DISPATCH_AUTHORITY")
    if created < activation_record["created_at"] or created < repin_terminal["created_at"]: raise RecoveryError("SUCCESSOR_DISPATCH_AUTHORITY_PRECEDES_PREREQUISITE")
    return {"comment_id":int(c["id"]),"created_at":created,"body_sha256":body_sha}



def validate_predecessor_recovery_run(run: Any, job: Any) -> None:
    if not isinstance(run,dict) or run.get("id")!=PREDECESSOR_RECOVERY_RUN:
        raise RecoveryError("SUCCESSOR_PREDECESSOR_RUN_ID_MISMATCH")
    if run.get("run_attempt")!=1 or run.get("status")!="completed" or run.get("conclusion")!="failure" or run.get("head_branch")!=DEFAULT_BRANCH or run.get("head_sha")!=PREDECESSOR_ACTIVATION_SHA or run.get("event")!="workflow_dispatch" or str(run.get("path") or "").split("@",1)[0] != ".github/workflows/phase5-slice-c-recovery.yml":
        raise RecoveryError("SUCCESSOR_PREDECESSOR_RUN_STATE_MISMATCH")
    for key in ("repository","head_repository"):
        if (run.get(key) or {}).get("full_name")!=REPOSITORY:
            raise RecoveryError("SUCCESSOR_PREDECESSOR_RUN_REPOSITORY_MISMATCH")
    refs=run.get("referenced_workflows")
    expected=f"{REPOSITORY}/{RECOVERY_REUSABLE_PATH}@{PREDECESSOR_CONTROL_SHA}"
    matches=[x for x in refs or [] if isinstance(x,dict) and str(x.get("path") or "").split("@",1)[0]==f"{REPOSITORY}/{RECOVERY_REUSABLE_PATH}"]
    if len(matches)!=1 or matches[0].get("path")!=expected or matches[0].get("sha")!=PREDECESSOR_CONTROL_SHA:
        raise RecoveryError("SUCCESSOR_PREDECESSOR_RUN_REUSABLE_MISMATCH")
    if not isinstance(job,dict) or job.get("id")!=PREDECESSOR_RECOVERY_JOB or job.get("run_id")!=PREDECESSOR_RECOVERY_RUN or job.get("status")!="completed" or job.get("conclusion")!="failure" or job.get("name")!="recover / slice-c-recovery":
        raise RecoveryError("SUCCESSOR_PREDECESSOR_JOB_STATE_MISMATCH")


def verify_successor_github_boundary(
    activation_sha: str, control_sha: str, candidate_output: str | Path
) -> dict[str,Any]:
    branch=github(f"/repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}")
    if not isinstance(branch,dict) or branch.get("commit",{}).get("sha")!=activation_sha: raise RecoveryError("SUCCESSOR_ACTIVATION_MAIN_MISMATCH")
    issue=github(f"/repos/{REPOSITORY}/issues/{GOVERNING_ISSUE}")
    if not isinstance(issue,dict) or issue.get("state")!="open": raise RecoveryError("GOVERNING_ISSUE_NOT_OPEN")
    boundary=github(f"/repos/{REPOSITORY}/issues/comments/{SOURCE_BOUNDARY_COMMENT_ID}"); boundary_result=validate_boundary_comment(boundary)
    pr=github(f"/repos/{REPOSITORY}/pulls/{SLICE_C_PR}"); files=github(f"/repos/{REPOSITORY}/pulls/{SLICE_C_PR}/files?per_page=100"); validate_pr(pr,files)
    run=github(f"/repos/{REPOSITORY}/actions/runs/{FAILED_APPLY_RUN}"); job=github(f"/repos/{REPOSITORY}/actions/jobs/{FAILED_APPLY_JOB}"); validate_failed_apply(run,job)
    predecessor_run=github(f"/repos/{REPOSITORY}/actions/runs/{PREDECESSOR_RECOVERY_RUN}")
    predecessor_job=github(f"/repos/{REPOSITORY}/actions/jobs/{PREDECESSOR_RECOVERY_JOB}")
    validate_predecessor_recovery_run(predecessor_run,predecessor_job)
    comments=github_issue_comments(GOVERNING_ISSUE); predecessor=validate_successor_predecessor_records(comments)
    superseded_pr=github(f"/repos/{REPOSITORY}/pulls/{SUPERSEDED_ACTIVATION_PR}")
    superseded_review=github(f"/repos/{REPOSITORY}/pulls/{SUPERSEDED_ACTIVATION_PR}/reviews/{SUPERSEDED_ACTIVATION_REVIEW_ID}")
    superseded_authority=github(f"/repos/{REPOSITORY}/issues/comments/{SUPERSEDED_ACTIVATION_AUTHORITY_ID}")
    superseded_reviewed_commit=github(f"/repos/{REPOSITORY}/commits/{SUPERSEDED_ACTIVATION_REVIEWED_HEAD}")
    superseded_merge_commit=github(f"/repos/{REPOSITORY}/commits/{SUPERSEDED_ACTIVATION_MERGE_SHA}")
    validate_superseded_activation_history(
        superseded_pr, superseded_review, superseded_authority,
        superseded_reviewed_commit, superseded_merge_commit,
        predecessor["superseded_activation"],
    )
    failed_c3_pr=github(f"/repos/{REPOSITORY}/pulls/{FAILED_C3_ACTIVATION_PR}")
    failed_c3_review=github(f"/repos/{REPOSITORY}/pulls/{FAILED_C3_ACTIVATION_PR}/reviews/{FAILED_C3_ACTIVATION_REVIEW_ID}")
    failed_c3_authority=github(f"/repos/{REPOSITORY}/issues/comments/{FAILED_C3_ACTIVATION_AUTHORITY_ID}")
    failed_c3_reviewed_commit=github(f"/repos/{REPOSITORY}/commits/{FAILED_C3_ACTIVATION_REVIEWED_HEAD}")
    validate_failed_c3_activation_history(
        failed_c3_pr, failed_c3_review, failed_c3_authority,
        failed_c3_reviewed_commit, predecessor["failed_c3_activation"],
    )
    activation=validate_successor_activation_record(comments,control_sha,activation_sha)
    apr=github(f"/repos/{REPOSITORY}/pulls/{activation['pr_number']}"); areview=github(f"/repos/{REPOSITORY}/pulls/{activation['pr_number']}/reviews/{activation['review_id']}"); aauth=github(f"/repos/{REPOSITORY}/issues/comments/{activation['authority_id']}")
    activation_reviewed_commit=github(f"/repos/{REPOSITORY}/commits/{activation['reviewed_head']}")
    activation_merge_commit=github(f"/repos/{REPOSITORY}/commits/{activation_sha}")
    validate_successor_activation_transaction(
        apr, areview, aauth, activation_reviewed_commit, activation_merge_commit,
        activation, control_sha, activation_sha,
    )
    repin=validate_successor_wif_repin_terminal(comments,control_sha,activation_sha,activation["created_at"])
    dispatch=validate_successor_dispatch_authority(comments,control_sha,activation_sha,activation,repin)
    reviewed=fetch_candidate(REVIEWED_HEAD); merged=fetch_candidate(SLICE_C_MERGE); active=fetch_candidate(activation_sha)
    if reviewed!=merged or reviewed!=active: raise RecoveryError("SUCCESSOR_CANDIDATE_IDENTITY_DRIFT")
    Path(candidate_output).write_bytes(canonical(active)+b"\n")
    doc={
      "contract":"resilio-phase5-slice-c-successor-github-boundary/v1","governing_issue":GOVERNING_ISSUE,
      "source_boundary_comment_id":SOURCE_BOUNDARY_COMMENT_ID,"source_boundary_body_sha256":boundary_result["body_sha256"],
      "failed_apply_run":FAILED_APPLY_RUN,"failed_apply_job":FAILED_APPLY_JOB,
      "predecessor_control_sha":PREDECESSOR_CONTROL_SHA,"predecessor_activation_sha":PREDECESSOR_ACTIVATION_SHA,
      "predecessor_recovery_run":PREDECESSOR_RECOVERY_RUN,"predecessor_recovery_job":PREDECESSOR_RECOVERY_JOB,
      "predecessor_failure_record_id":predecessor["failure"]["comment_id"],"predecessor_failure_record_body_sha256":predecessor["failure"]["body_sha256"],
      "predecessor_claim_object":PREDECESSOR_CLAIM_OBJECT,"predecessor_claim_generation":PREDECESSOR_CLAIM_GENERATION,"predecessor_claim_body_sha256":PREDECESSOR_CLAIM_BODY_SHA256,"predecessor_claim_sha256":PREDECESSOR_CLAIM_SHA256,"predecessor_governance_chain_sha256":PREDECESSOR_GOVERNANCE_CHAIN_SHA256,"predecessor_result_object":PREDECESSOR_RESULT_OBJECT,
      "s1_terminal_comment_id":predecessor["s1_terminal"]["comment_id"],"s1_terminal_body_sha256":predecessor["s1_terminal"]["body_sha256"],
      "successor_architecture_comment_id":predecessor["architecture"]["comment_id"],"successor_architecture_body_sha256":predecessor["architecture"]["body_sha256"],"successor_architecture_review_comment_id":predecessor["architecture_review"]["comment_id"],"successor_architecture_review_body_sha256":predecessor["architecture_review"]["body_sha256"],
      "superseded_control_sha":SUPERSEDED_CONTROL_SHA,"superseded_activation_pr":SUPERSEDED_ACTIVATION_PR,"superseded_activation_reviewed_head":SUPERSEDED_ACTIVATION_REVIEWED_HEAD,"superseded_activation_reviewed_tree":SUPERSEDED_ACTIVATION_REVIEWED_TREE,"superseded_activation_review_id":SUPERSEDED_ACTIVATION_REVIEW_ID,"superseded_activation_review_body_sha256":SUPERSEDED_ACTIVATION_REVIEW_BODY_SHA256,"superseded_activation_authority_id":SUPERSEDED_ACTIVATION_AUTHORITY_ID,"superseded_activation_authority_body_sha256":SUPERSEDED_ACTIVATION_AUTHORITY_BODY_SHA256,"superseded_activation_merge_sha":SUPERSEDED_ACTIVATION_MERGE_SHA,"superseded_activation_failure_record_id":predecessor["superseded_activation"]["comment_id"],"superseded_activation_failure_record_body_sha256":predecessor["superseded_activation"]["body_sha256"],"superseded_claim_object":SUPERSEDED_CLAIM_OBJECT,"superseded_result_object":SUPERSEDED_RESULT_OBJECT,
      "failed_c3_control_sha":FAILED_C3_CONTROL_SHA,"failed_c3_activation_pr":FAILED_C3_ACTIVATION_PR,"failed_c3_activation_reviewed_head":FAILED_C3_ACTIVATION_REVIEWED_HEAD,"failed_c3_activation_reviewed_tree":FAILED_C3_ACTIVATION_REVIEWED_TREE,"failed_c3_activation_review_id":FAILED_C3_ACTIVATION_REVIEW_ID,"failed_c3_activation_review_body_sha256":FAILED_C3_ACTIVATION_REVIEW_BODY_SHA256,"failed_c3_activation_authority_id":FAILED_C3_ACTIVATION_AUTHORITY_ID,"failed_c3_activation_authority_raw_body_sha256":FAILED_C3_ACTIVATION_AUTHORITY_RAW_BODY_SHA256,"failed_c3_activation_authority_transport":"CRLF","failed_c3_activation_failure_record_id":predecessor["failed_c3_activation"]["comment_id"],"failed_c3_activation_failure_record_body_sha256":predecessor["failed_c3_activation"]["body_sha256"],"failed_c3_claim_object":FAILED_C3_CLAIM_OBJECT,"failed_c3_result_object":FAILED_C3_RESULT_OBJECT,
      "control_sha":control_sha,"activation_sha":activation_sha,"successor_pr":activation["pr_number"],"successor_reviewed_head":activation["reviewed_head"],"successor_fresh_review_id":activation["review_id"],"successor_fresh_review_body_sha256":activation["review_body_sha256"],"successor_merge_authority_comment_id":activation["authority_id"],"successor_merge_authority_body_sha256":activation["authority_body_sha256"],"successor_activation_record_comment_id":activation["comment_id"],"successor_activation_record_body_sha256":activation["body_sha256"],
      "wif_repin_saved_plan_sha256":repin["saved_plan_sha256"],"wif_repin_structural_manifest_sha256":repin["manifest_sha256"],"wif_repin_review_comment_id":repin["review_id"],"wif_repin_review_body_sha256":repin["review_sha256"],"wif_repin_apply_authority_comment_id":repin["authority_id"],"wif_repin_apply_authority_body_sha256":repin["authority_sha256"],"wif_repin_terminal_comment_id":repin["comment_id"],"wif_repin_terminal_body_sha256":repin["body_sha256"],
      "dispatch_authority_comment_id":dispatch["comment_id"],"dispatch_authority_body_sha256":dispatch["body_sha256"],
      "product_state_generation":SUCCESSOR_EXPECTED_GENERATION,"product_state_lineage":SUCCESSOR_EXPECTED_LINEAGE,"product_state_serial":SUCCESSOR_EXPECTED_SERIAL,"product_state_canonical_sha256":SUCCESSOR_EXPECTED_STATE_CANONICAL_SHA256,
    }
    doc["governance_chain_sha256"]=sha256(canonical(doc)); return doc


def verify_successor_github_boundary_document(value: Any, control_sha: str, activation_sha: str) -> dict[str,Any]:
    expected_keys={"contract","governing_issue","source_boundary_comment_id","source_boundary_body_sha256","failed_apply_run","failed_apply_job","predecessor_control_sha","predecessor_activation_sha","predecessor_recovery_run","predecessor_recovery_job","predecessor_failure_record_id","predecessor_failure_record_body_sha256","predecessor_claim_object","predecessor_claim_generation","predecessor_claim_body_sha256","predecessor_claim_sha256","predecessor_governance_chain_sha256","predecessor_result_object","s1_terminal_comment_id","s1_terminal_body_sha256","successor_architecture_comment_id","successor_architecture_body_sha256","successor_architecture_review_comment_id","successor_architecture_review_body_sha256","superseded_control_sha","superseded_activation_pr","superseded_activation_reviewed_head","superseded_activation_reviewed_tree","superseded_activation_review_id","superseded_activation_review_body_sha256","superseded_activation_authority_id","superseded_activation_authority_body_sha256","superseded_activation_merge_sha","superseded_activation_failure_record_id","superseded_activation_failure_record_body_sha256","superseded_claim_object","superseded_result_object","failed_c3_control_sha","failed_c3_activation_pr","failed_c3_activation_reviewed_head","failed_c3_activation_reviewed_tree","failed_c3_activation_review_id","failed_c3_activation_review_body_sha256","failed_c3_activation_authority_id","failed_c3_activation_authority_raw_body_sha256","failed_c3_activation_authority_transport","failed_c3_activation_failure_record_id","failed_c3_activation_failure_record_body_sha256","failed_c3_claim_object","failed_c3_result_object","control_sha","activation_sha","successor_pr","successor_reviewed_head","successor_fresh_review_id","successor_fresh_review_body_sha256","successor_merge_authority_comment_id","successor_merge_authority_body_sha256","successor_activation_record_comment_id","successor_activation_record_body_sha256","wif_repin_saved_plan_sha256","wif_repin_structural_manifest_sha256","wif_repin_review_comment_id","wif_repin_review_body_sha256","wif_repin_apply_authority_comment_id","wif_repin_apply_authority_body_sha256","wif_repin_terminal_comment_id","wif_repin_terminal_body_sha256","dispatch_authority_comment_id","dispatch_authority_body_sha256","product_state_generation","product_state_lineage","product_state_serial","product_state_canonical_sha256","governance_chain_sha256"}
    if not isinstance(value,dict) or set(value)!=expected_keys or value.get("contract")!="resilio-phase5-slice-c-successor-github-boundary/v1": raise RecoveryError("SUCCESSOR_BOUNDARY_DOCUMENT_INVALID")
    if value.get("control_sha")!=control_sha or value.get("activation_sha")!=activation_sha: raise RecoveryError("SUCCESSOR_BOUNDARY_CONTROL_INVALID")
    if value.get("product_state_generation")!=SUCCESSOR_EXPECTED_GENERATION or value.get("product_state_lineage")!=SUCCESSOR_EXPECTED_LINEAGE or value.get("product_state_serial")!=SUCCESSOR_EXPECTED_SERIAL or value.get("product_state_canonical_sha256")!=SUCCESSOR_EXPECTED_STATE_CANONICAL_SHA256: raise RecoveryError("SUCCESSOR_BOUNDARY_STATE_INVALID")
    required_hashes=("source_boundary_body_sha256","predecessor_failure_record_body_sha256","predecessor_claim_body_sha256","predecessor_claim_sha256","predecessor_governance_chain_sha256","s1_terminal_body_sha256","successor_architecture_body_sha256","successor_architecture_review_body_sha256","superseded_activation_review_body_sha256","superseded_activation_authority_body_sha256","superseded_activation_failure_record_body_sha256","failed_c3_activation_review_body_sha256","failed_c3_activation_authority_raw_body_sha256","failed_c3_activation_failure_record_body_sha256","successor_fresh_review_body_sha256","successor_merge_authority_body_sha256","successor_activation_record_body_sha256","wif_repin_saved_plan_sha256","wif_repin_structural_manifest_sha256","wif_repin_review_body_sha256","wif_repin_apply_authority_body_sha256","wif_repin_terminal_body_sha256","dispatch_authority_body_sha256","product_state_canonical_sha256","governance_chain_sha256")
    for key in required_hashes:
        if not HEX64.fullmatch(str(value.get(key) or "")): raise RecoveryError(f"SUCCESSOR_BOUNDARY_HASH_INVALID:{key}")
    chain=value["governance_chain_sha256"]; copy=dict(value); del copy["governance_chain_sha256"]
    if sha256(canonical(copy))!=chain: raise RecoveryError("SUCCESSOR_BOUNDARY_HASH_MISMATCH")
    if value.get("governing_issue")!=GOVERNING_ISSUE or value.get("source_boundary_comment_id")!=SOURCE_BOUNDARY_COMMENT_ID or value.get("failed_apply_run")!=FAILED_APPLY_RUN or value.get("failed_apply_job")!=FAILED_APPLY_JOB or value.get("predecessor_control_sha")!=PREDECESSOR_CONTROL_SHA or value.get("predecessor_activation_sha")!=PREDECESSOR_ACTIVATION_SHA or value.get("predecessor_recovery_run")!=PREDECESSOR_RECOVERY_RUN or value.get("predecessor_recovery_job")!=PREDECESSOR_RECOVERY_JOB or value.get("predecessor_failure_record_id")!=PREDECESSOR_FAILURE_RECORD_ID or value.get("predecessor_failure_record_body_sha256")!=PREDECESSOR_FAILURE_RECORD_BODY_SHA256 or value.get("predecessor_claim_object")!=PREDECESSOR_CLAIM_OBJECT or value.get("predecessor_claim_generation")!=PREDECESSOR_CLAIM_GENERATION or value.get("predecessor_claim_body_sha256")!=PREDECESSOR_CLAIM_BODY_SHA256 or value.get("predecessor_claim_sha256")!=PREDECESSOR_CLAIM_SHA256 or value.get("predecessor_governance_chain_sha256")!=PREDECESSOR_GOVERNANCE_CHAIN_SHA256 or value.get("predecessor_result_object")!=PREDECESSOR_RESULT_OBJECT or value.get("s1_terminal_comment_id")!=S1_TERMINAL_COMMENT_ID or value.get("s1_terminal_body_sha256")!=S1_TERMINAL_BODY_SHA256 or value.get("successor_architecture_comment_id")!=SUCCESSOR_ARCHITECTURE_COMMENT_ID or value.get("successor_architecture_body_sha256")!=SUCCESSOR_ARCHITECTURE_BODY_SHA256 or value.get("successor_architecture_review_comment_id")!=SUCCESSOR_ARCHITECTURE_REVIEW_COMMENT_ID or value.get("successor_architecture_review_body_sha256")!=SUCCESSOR_ARCHITECTURE_REVIEW_BODY_SHA256 or value.get("superseded_control_sha")!=SUPERSEDED_CONTROL_SHA or value.get("superseded_activation_pr")!=SUPERSEDED_ACTIVATION_PR or value.get("superseded_activation_reviewed_head")!=SUPERSEDED_ACTIVATION_REVIEWED_HEAD or value.get("superseded_activation_reviewed_tree")!=SUPERSEDED_ACTIVATION_REVIEWED_TREE or value.get("superseded_activation_review_id")!=SUPERSEDED_ACTIVATION_REVIEW_ID or value.get("superseded_activation_review_body_sha256")!=SUPERSEDED_ACTIVATION_REVIEW_BODY_SHA256 or value.get("superseded_activation_authority_id")!=SUPERSEDED_ACTIVATION_AUTHORITY_ID or value.get("superseded_activation_authority_body_sha256")!=SUPERSEDED_ACTIVATION_AUTHORITY_BODY_SHA256 or value.get("superseded_activation_merge_sha")!=SUPERSEDED_ACTIVATION_MERGE_SHA or value.get("superseded_activation_failure_record_id")!=SUPERSEDED_ACTIVATION_FAILURE_RECORD_ID or value.get("superseded_activation_failure_record_body_sha256")!=SUPERSEDED_ACTIVATION_FAILURE_RECORD_BODY_SHA256 or value.get("superseded_claim_object")!=SUPERSEDED_CLAIM_OBJECT or value.get("superseded_result_object")!=SUPERSEDED_RESULT_OBJECT or value.get("failed_c3_control_sha")!=FAILED_C3_CONTROL_SHA or value.get("failed_c3_activation_pr")!=FAILED_C3_ACTIVATION_PR or value.get("failed_c3_activation_reviewed_head")!=FAILED_C3_ACTIVATION_REVIEWED_HEAD or value.get("failed_c3_activation_reviewed_tree")!=FAILED_C3_ACTIVATION_REVIEWED_TREE or value.get("failed_c3_activation_review_id")!=FAILED_C3_ACTIVATION_REVIEW_ID or value.get("failed_c3_activation_review_body_sha256")!=FAILED_C3_ACTIVATION_REVIEW_BODY_SHA256 or value.get("failed_c3_activation_authority_id")!=FAILED_C3_ACTIVATION_AUTHORITY_ID or value.get("failed_c3_activation_authority_raw_body_sha256")!=FAILED_C3_ACTIVATION_AUTHORITY_RAW_BODY_SHA256 or value.get("failed_c3_activation_authority_transport")!="CRLF" or value.get("failed_c3_activation_failure_record_id")!=FAILED_C3_ACTIVATION_FAILURE_RECORD_ID or value.get("failed_c3_activation_failure_record_body_sha256")!=FAILED_C3_ACTIVATION_FAILURE_RECORD_BODY_SHA256 or value.get("failed_c3_claim_object")!=FAILED_C3_CLAIM_OBJECT or value.get("failed_c3_result_object")!=FAILED_C3_RESULT_OBJECT: raise RecoveryError("SUCCESSOR_BOUNDARY_PREDECESSOR_INVALID")
    if not FULL_SHA.fullmatch(str(value.get("successor_reviewed_head") or "")): raise RecoveryError("SUCCESSOR_BOUNDARY_REVIEWED_HEAD_INVALID")
    for key in ("predecessor_failure_record_id","s1_terminal_comment_id","successor_architecture_comment_id","successor_architecture_review_comment_id","superseded_activation_pr","superseded_activation_review_id","superseded_activation_authority_id","superseded_activation_failure_record_id","failed_c3_activation_pr","failed_c3_activation_review_id","failed_c3_activation_authority_id","failed_c3_activation_failure_record_id","successor_pr","successor_fresh_review_id","successor_merge_authority_comment_id","successor_activation_record_comment_id","wif_repin_review_comment_id","wif_repin_apply_authority_comment_id","wif_repin_terminal_comment_id","dispatch_authority_comment_id"):
        if not isinstance(value.get(key),int) or isinstance(value.get(key),bool) or value[key]<=0: raise RecoveryError(f"SUCCESSOR_BOUNDARY_ID_INVALID:{key}")
    return value


def successor_state_identity_from_state(state: Any, generation: str) -> dict[str,Any]:
    if not isinstance(state,dict) or generation!=SUCCESSOR_EXPECTED_GENERATION: raise RecoveryError("SUCCESSOR_STATE_GENERATION_MISMATCH")
    if state.get("lineage")!=SUCCESSOR_EXPECTED_LINEAGE or state.get("serial")!=SUCCESSOR_EXPECTED_SERIAL: raise RecoveryError("SUCCESSOR_STATE_VERSION_MISMATCH")
    observed={}
    for resource in state.get("resources") or []:
        if resource.get("mode","managed")!="managed": continue
        module=resource.get("module")
        for inst in resource.get("instances") or []:
            if inst.get("index_key") is not None: raise RecoveryError("SUCCESSOR_STATE_INDEXED_RESOURCE_FORBIDDEN")
            if inst.get("deposed") not in (None, ""):
                raise RecoveryError("SUCCESSOR_STATE_DEPOSED_INSTANCE_FORBIDDEN")
            address=f"{resource.get('type')}.{resource.get('name')}"
            if module: address=f"{module}.{address}"
            if address in observed: raise RecoveryError("SUCCESSOR_STATE_ADDRESS_DUPLICATE")
            observed[address]=str(inst.get("status") or "normal")
    if tuple(sorted(observed))!=SUCCESSOR_EXPECTED_ADDRESSES: raise RecoveryError("SUCCESSOR_STATE_ADDRESS_SET_MISMATCH")
    if observed!=SUCCESSOR_EXPECTED_STATUSES: raise RecoveryError("SUCCESSOR_STATE_STATUS_PROJECTION_MISMATCH")
    state_hash=sha256(canonical(state))
    if state_hash!=SUCCESSOR_EXPECTED_STATE_CANONICAL_SHA256: raise RecoveryError("SUCCESSOR_STATE_CANONICAL_HASH_MISMATCH")
    return {"contract":"resilio-phase5-slice-c-successor-state/v1","generation":generation,"lineage":SUCCESSOR_EXPECTED_LINEAGE,"serial":SUCCESSOR_EXPECTED_SERIAL,"managed_addresses":list(SUCCESSOR_EXPECTED_ADDRESSES),"instance_statuses":observed,"state_canonical_sha256":state_hash}


def verify_successor_state_identity(value: Any) -> dict[str,Any]:
    expected_keys={"contract","generation","lineage","serial","managed_addresses","instance_statuses","state_canonical_sha256"}
    if not isinstance(value,dict) or set(value)!=expected_keys or value.get("contract")!="resilio-phase5-slice-c-successor-state/v1": raise RecoveryError("SUCCESSOR_STATE_IDENTITY_FIELDS_INVALID")
    if value.get("generation")!=SUCCESSOR_EXPECTED_GENERATION or value.get("lineage")!=SUCCESSOR_EXPECTED_LINEAGE or value.get("serial")!=SUCCESSOR_EXPECTED_SERIAL: raise RecoveryError("SUCCESSOR_STATE_IDENTITY_VERSION_MISMATCH")
    if tuple(value.get("managed_addresses") or ())!=SUCCESSOR_EXPECTED_ADDRESSES or value.get("instance_statuses")!=SUCCESSOR_EXPECTED_STATUSES or value.get("state_canonical_sha256")!=SUCCESSOR_EXPECTED_STATE_CANONICAL_SHA256: raise RecoveryError("SUCCESSOR_STATE_IDENTITY_PROJECTION_MISMATCH")
    return value


def verify_successor_no_change_plan(plan: Any) -> dict[str,Any]:
    if not isinstance(plan,dict) or plan.get("format_version")!="1.2" or plan.get("terraform_version")!="1.15.8": raise RecoveryError("SUCCESSOR_PLAN_VERSION_INVALID")
    if plan.get("errored") is not False or plan.get("complete") is not True or plan.get("applyable") not in (False,None): raise RecoveryError("SUCCESSOR_PLAN_TERMINALITY_INVALID")
    for key in ("deferred_changes","deferred_action_invocations","action_invocations","output_changes"):
        if plan.get(key) not in (None,[],{}): raise RecoveryError(f"SUCCESSOR_PLAN_{key.upper()}_FORBIDDEN")
    rows=plan.get("resource_changes")
    if not isinstance(rows,list): raise RecoveryError("SUCCESSOR_PLAN_RESOURCE_CHANGES_INVALID")
    observed=[]
    for row in rows:
        if not isinstance(row,dict) or row.get("mode","managed")!="managed": raise RecoveryError("SUCCESSOR_PLAN_RESOURCE_ROW_INVALID")
        address=row.get("address"); change=row.get("change") or {}
        if row.get("previous_address") is not None:
            raise RecoveryError(f"SUCCESSOR_PLAN_PREVIOUS_ADDRESS_FORBIDDEN:{address}")
        if not isinstance(address,str) or change.get("actions") != ["no-op"]: raise RecoveryError(f"SUCCESSOR_PLAN_NON_NOOP_EFFECT:{address}")
        observed.append(address)
    if tuple(sorted(observed))!=SUCCESSOR_EXPECTED_ADDRESSES or _planned_addresses(plan)!=SUCCESSOR_EXPECTED_ADDRESSES: raise RecoveryError("SUCCESSOR_PLAN_ADDRESS_SET_MISMATCH")
    drift=plan.get("resource_drift") or []
    if len(drift)>1: raise RecoveryError("SUCCESSOR_PLAN_DRIFT_ROW_COUNT_INVALID")
    drift_fields=[]
    if drift:
        row=drift[0]
        if row.get("mode", "managed") != "managed" or row.get("previous_address") is not None:
            raise RecoveryError("SUCCESSOR_PLAN_DRIFT_ROW_INVALID")
        if row.get("address")!="google_firestore_database.operational": raise RecoveryError("SUCCESSOR_PLAN_DRIFT_ADDRESS_INVALID")
        change=row.get("change") or {}
        if change.get("actions") != ["update"]:
            raise RecoveryError("SUCCESSOR_PLAN_DRIFT_ACTION_INVALID")
        before=change.get("before") or {}; after=change.get("after") or {}
        fields={k for k in set(before)|set(after) if before.get(k)!=after.get(k)}
        if not fields or not fields <= SUCCESSOR_VOLATILE_FIRESTORE_FIELDS: raise RecoveryError("SUCCESSOR_PLAN_DRIFT_FIELDS_INVALID")
        drift_fields=sorted(fields)
    return {"addresses":list(SUCCESSOR_EXPECTED_ADDRESSES),"no_change":True,"residual_firestore_drift_fields":drift_fields}


def _successor_gcs_metadata(object_name: str, allow_absent: bool=False) -> dict[str,Any] | None:
    path=urllib.parse.quote(object_name,safe="")
    try: value=request_json(f"https://storage.googleapis.com/storage/v1/b/{STATE_BUCKET}/o/{path}",google_token())
    except RecoveryError as exc:
        if allow_absent and str(exc).startswith("HTTP_404"): return None
        raise
    if not isinstance(value,dict): raise RecoveryError("SUCCESSOR_GCS_METADATA_INVALID")
    return value


def _successor_gcs_json(object_name: str) -> Any:
    path=urllib.parse.quote(object_name,safe="")
    return request_json(f"https://storage.googleapis.com/storage/v1/b/{STATE_BUCKET}/o/{path}?alt=media",google_token())


def verify_successor_cloud_boundary(control_sha: str) -> dict[str,Any]:
    if not FULL_SHA.fullmatch(control_sha) or control_sha in (PREDECESSOR_CONTROL_SHA, SUPERSEDED_CONTROL_SHA, FAILED_C3_CONTROL_SHA): raise RecoveryError("SUCCESSOR_CONTROL_IDENTITY_INVALID")
    pm=_successor_gcs_metadata(PREDECESSOR_CLAIM_OBJECT)
    if str(pm.get("generation"))!=PREDECESSOR_CLAIM_GENERATION: raise RecoveryError("SUCCESSOR_PREDECESSOR_CLAIM_GENERATION_MISMATCH")
    claim=_successor_gcs_json(PREDECESSOR_CLAIM_OBJECT)
    if sha256(canonical(claim)+b"\n")!=PREDECESSOR_CLAIM_BODY_SHA256 or claim.get("claim_sha256")!=PREDECESSOR_CLAIM_SHA256 or claim.get("governance_chain_sha256")!=PREDECESSOR_GOVERNANCE_CHAIN_SHA256 or claim.get("workflow_run_id")!=str(PREDECESSOR_RECOVERY_RUN) or claim.get("control_sha")!=PREDECESSOR_CONTROL_SHA or claim.get("activation_sha")!=PREDECESSOR_ACTIVATION_SHA: raise RecoveryError("SUCCESSOR_PREDECESSOR_CLAIM_BODY_MISMATCH")
    if _successor_gcs_metadata(PREDECESSOR_RESULT_OBJECT,True) is not None: raise RecoveryError("SUCCESSOR_PREDECESSOR_RESULT_UNEXPECTED")
    if _successor_gcs_metadata(SUPERSEDED_CLAIM_OBJECT, True) is not None or _successor_gcs_metadata(SUPERSEDED_RESULT_OBJECT, True) is not None:
        raise RecoveryError("SUCCESSOR_SUPERSEDED_EVIDENCE_UNEXPECTED")
    if _successor_gcs_metadata(FAILED_C3_CLAIM_OBJECT, True) is not None or _successor_gcs_metadata(FAILED_C3_RESULT_OBJECT, True) is not None:
        raise RecoveryError("SUCCESSOR_FAILED_C3_EVIDENCE_UNEXPECTED")
    if _successor_gcs_metadata(evidence_object("claim",control_sha),True) is not None or _successor_gcs_metadata(evidence_object("result",control_sha),True) is not None: raise RecoveryError("SUCCESSOR_EVIDENCE_ALREADY_EXISTS")
    sm=_successor_gcs_metadata(STATE_OBJECT)
    if str(sm.get("generation"))!=SUCCESSOR_EXPECTED_GENERATION: raise RecoveryError("SUCCESSOR_CLOUD_STATE_GENERATION_MISMATCH")
    state=_successor_gcs_json(STATE_OBJECT); state_id=successor_state_identity_from_state(state,SUCCESSOR_EXPECTED_GENERATION)
    if _successor_gcs_metadata(LOCK_OBJECT,True) is not None: raise RecoveryError("SUCCESSOR_PRODUCT_LOCK_PRESENT")
    return {"predecessor_claim_generation":PREDECESSOR_CLAIM_GENERATION,"predecessor_claim_body_sha256":PREDECESSOR_CLAIM_BODY_SHA256,"superseded_claim_absent":True,"superseded_result_absent":True,"failed_c3_claim_absent":True,"failed_c3_result_absent":True,"state_identity":state_id,"successor_claim_absent":True,"successor_result_absent":True,"product_lock_absent":True}


def successor_claim_document(control_sha: str, activation_sha: str, run_id: str, github_boundary: Any) -> dict[str,Any]:
    boundary=verify_successor_github_boundary_document(github_boundary,control_sha,activation_sha)
    if not RUN_ID.fullmatch(run_id): raise RecoveryError("SUCCESSOR_CLAIM_RUN_ID_INVALID")
    value={"contract":"resilio-phase5-slice-c-successor-claim/v1","governing_issue":GOVERNING_ISSUE,"source_boundary_comment_id":SOURCE_BOUNDARY_COMMENT_ID,"failed_apply_run":FAILED_APPLY_RUN,"predecessor_recovery_run":PREDECESSOR_RECOVERY_RUN,"predecessor_claim_sha256":PREDECESSOR_CLAIM_SHA256,"s1_terminal_comment_id":S1_TERMINAL_COMMENT_ID,"superseded_control_sha":SUPERSEDED_CONTROL_SHA,"superseded_activation_failure_record_id":SUPERSEDED_ACTIVATION_FAILURE_RECORD_ID,"control_sha":control_sha,"activation_sha":activation_sha,"workflow_run_id":run_id,"governance_chain_sha256":boundary["governance_chain_sha256"],"github_boundary":boundary}
    value["claim_sha256"]=sha256(canonical(value)); return value


def successor_create_claim(control_sha: str, activation_sha: str, run_id: str, github_boundary: Any) -> dict[str,Any]:
    return gcs_upload_once(evidence_object("claim",control_sha),successor_claim_document(control_sha,activation_sha,run_id,github_boundary))


def successor_build_result(before: Any, after: Any, plan: Any, control_sha: str, activation_sha: str, run_id: str, github_boundary: Any) -> tuple[dict[str,Any],dict[str,Any]]:
    b=verify_successor_state_identity(before); a=verify_successor_state_identity(after)
    if b!=a: raise RecoveryError("SUCCESSOR_STATE_IDENTITY_CHANGED")
    plan_result=verify_successor_no_change_plan(plan); boundary=verify_successor_github_boundary_document(github_boundary,control_sha,activation_sha)
    claim=successor_claim_document(control_sha,activation_sha,run_id,boundary); plan_sha=sha256(canonical(plan))
    private={"contract":"resilio-phase5-slice-c-successor-result/v1","governing_issue":GOVERNING_ISSUE,"source_boundary_comment_id":SOURCE_BOUNDARY_COMMENT_ID,"failed_apply_run":FAILED_APPLY_RUN,"predecessor_recovery_run":PREDECESSOR_RECOVERY_RUN,"predecessor_claim_sha256":PREDECESSOR_CLAIM_SHA256,"s1_terminal_comment_id":S1_TERMINAL_COMMENT_ID,"superseded_control_sha":SUPERSEDED_CONTROL_SHA,"superseded_activation_failure_record_id":SUPERSEDED_ACTIVATION_FAILURE_RECORD_ID,"control_sha":control_sha,"activation_sha":activation_sha,"workflow_run_id":run_id,"governance_chain_sha256":boundary["governance_chain_sha256"],"github_boundary":boundary,"claim_sha256":claim["claim_sha256"],"claim_object":evidence_object("claim",control_sha),"result_object":evidence_object("result",control_sha),"state_before":b,"state_after":a,"plan_sha256":plan_sha,"residual_firestore_drift_fields":plan_result["residual_firestore_drift_fields"],"terraform_reconciliation":"EXACT_NO_MATERIAL_CHANGE"}
    private["result_sha256"]=sha256(canonical(private))
    public={"contract":"resilio-phase5-slice-c-successor-manifest/v1","source_boundary_comment_id":SOURCE_BOUNDARY_COMMENT_ID,"failed_apply_run":FAILED_APPLY_RUN,"predecessor_recovery_run":PREDECESSOR_RECOVERY_RUN,"superseded_control_sha":SUPERSEDED_CONTROL_SHA,"superseded_activation_failure_record_id":SUPERSEDED_ACTIVATION_FAILURE_RECORD_ID,"control_sha":control_sha,"activation_sha":activation_sha,"workflow_run_id":run_id,"governance_chain_sha256":boundary["governance_chain_sha256"],"claim_sha256":claim["claim_sha256"],"state_generation":b["generation"],"state_lineage":b["lineage"],"state_serial":b["serial"],"managed_addresses":b["managed_addresses"],"instance_statuses":b["instance_statuses"],"state_canonical_sha256":b["state_canonical_sha256"],"plan_sha256":plan_sha,"residual_firestore_drift_fields":plan_result["residual_firestore_drift_fields"],"terraform_reconciliation":"EXACT_NO_MATERIAL_CHANGE","claim_object":private["claim_object"],"result_object":private["result_object"],"result_sha256":private["result_sha256"]}
    return private,public



# C5 retained-effect recovery protocol.  This surface is intentionally inert in
# the C5 control seed: the repository caller and bootstrap WIF remain pinned to
# C4 until a separately reviewed/authorised activation and WIF-repin sequence.
C5_ARCHITECTURE_COMMENT_ID = 5976498714
C5_ARCHITECTURE_BODY_SHA256 = "b1e6e4147d1e07bf47ba8d005114ba387ad15f888a8f4cf013bf0bcb7f2d4f7f"
C5_ARCHITECTURE_REVIEW_COMMENT_ID = 5976504154
C5_ARCHITECTURE_REVIEW_BODY_SHA256 = "70c65751e7d9ee0f6e77d307786f8881b0342447152419cd5e9e1a0acd463f4e"
C5_OWNER_DISPOSITION_COMMENT_ID = 5985897003
C5_OWNER_DISPOSITION_BODY_SHA256 = "bc0a13d8e972e0f29043a864c8729b1ca15e745c2579c43aa827946bab0804f2"
C5_RETAINED_BASELINE_COMMENT_ID = 5987054333
C5_RETAINED_BASELINE_BODY_SHA256 = "8cc150919fb7fe363f0e3c6e5ac0c96456c733e73f9712496b9c865b37b311c9"
C5_BASE_MAIN = "6512a8df49c56ec797f106d02aae4d4114193779"
C5_OLD_RECOVERY_CONTROL_SHA = "03123864097df51e6edafd67acc34702f0819de3"
C5_ARCHITECTURE_CLOSURE_COMMENT_ID = 5993056257
C5_PROTOCOL_EPOCH_TEXT = "\n".join((
    "PHASE5_SLICE_C_C5_PROTOCOL_EPOCH_V1",
    "GOVERNING_ISSUE=8ft0-ai/resilio#109",
    "C5_ARCHITECTURE_COMMENT_ID=5976498714",
    "C5_ARCHITECTURE_BODY_SHA256=b1e6e4147d1e07bf47ba8d005114ba387ad15f888a8f4cf013bf0bcb7f2d4f7f",
    "C5_ARCHITECTURE_REVIEW_COMMENT_ID=5976504154",
    "C5_ARCHITECTURE_REVIEW_BODY_SHA256=70c65751e7d9ee0f6e77d307786f8881b0342447152419cd5e9e1a0acd463f4e",
    "OWNER_DISPOSITION_COMMENT_ID=5985897003",
    "OWNER_DISPOSITION_BODY_SHA256=bc0a13d8e972e0f29043a864c8729b1ca15e745c2579c43aa827946bab0804f2",
    "RETAINED_EFFECT_BASELINE_COMMENT_ID=5987054333",
    "RETAINED_EFFECT_BASELINE_BODY_SHA256=8cc150919fb7fe363f0e3c6e5ac0c96456c733e73f9712496b9c865b37b311c9",
    "BASE_MAIN=6512a8df49c56ec797f106d02aae4d4114193779",
    "OLD_RECOVERY_CONTROL_SHA=03123864097df51e6edafd67acc34702f0819de3",
))
C5_PROTOCOL_EPOCH_SHA256 = "785fd8bdb53812ebbca31e9d72da66667eb53b3b54925e6bd0a3c788180c600f"
C5_BOOTSTRAP_STATE_LINEAGE = "ae08b2f4-f18f-204c-72aa-53e17f12eea7"
C5_BOOTSTRAP_STATE_SERIAL = 71
C5_C4_SAVED_PLAN_SHA256 = "3e15f30695eacca78cbe9c38df792c7ab9844687120e51a692b2f1f718b7f38b"
C5_C4_STRUCTURAL_MANIFEST_SHA256 = "6e31aa0792c9966094fef6df56d0d55c006358e826c88ccd39a89debdc967c01"
C5_C4_INCIDENT_ID = 5976408137
C5_C4_INCIDENT_BODY_SHA256 = "4e145d27623c1fe4abcdaa70c9423d16fe958e35a0373bab8c1c5738a0d35ab2"
C5_C4_MALFORMED_AUTHORITY_ID = 5976341959
C5_C4_MALFORMED_AUTHORITY_BODY_SHA256 = "65cce5859085af8c2d4ee335fba02b81a3b9f0f1f0b9d76da0ce5155977cb5b0"
C5_C4_INVALID_TERMINAL_ID = 5976373231
C5_C4_INVALID_TERMINAL_BODY_SHA256 = "2c01be737dda00f967c2167fb00c50a6e99bbe2e9c157c30a1651a172fd2cfdf"
C5_FORBIDDEN_RECOVERY_CONTROL_SHAS = (
    PREDECESSOR_CONTROL_SHA,
    SUPERSEDED_CONTROL_SHA,
    FAILED_C3_CONTROL_SHA,
)
C5_TERMINAL_OUTCOMES = frozenset(
    ("EFFECT_SUCCEEDED", "NO_EFFECT_STABLE", "INCONSISTENT_EFFECT")
)
C5_ALL_OUTCOMES = C5_TERMINAL_OUTCOMES | frozenset(("PROCESS_OUTCOME_UNKNOWN",))


def _c5_require_sha(value: str, label: str) -> str:
    if not FULL_SHA.fullmatch(str(value or "")):
        raise RecoveryError(f"{label}_INVALID")
    return str(value)


def _c5_require_hash(value: str, label: str) -> str:
    if not HEX64.fullmatch(str(value or "")):
        raise RecoveryError(f"{label}_INVALID")
    return str(value)


def _c5_require_lineage(value: str, label: str) -> str:
    text = str(value or "")
    if not text or len(text) > 128 or "\n" in text or "\r" in text:
        raise RecoveryError(f"{label}_INVALID")
    return text


def _c5_require_enum(value: str, allowed: set[str] | frozenset[str], label: str) -> str:
    if value not in allowed:
        raise RecoveryError(f"{label}_INVALID")
    return value


def _c5_positive(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RecoveryError(f"{label}_INVALID")
    return value


def _c5_nonnegative(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RecoveryError(f"{label}_INVALID")
    return value


def validate_c5_governance_history(comments: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(comments, list):
        raise RecoveryError("C5_GOVERNANCE_COMMENTS_INVALID")

    architecture = _successor_fixed_comment(
        comments,
        C5_ARCHITECTURE_COMMENT_ID,
        C5_ARCHITECTURE_BODY_SHA256,
        "C5_ARCHITECTURE",
    )
    for token in (
        "STATUS=C5_ARCHITECTURE_REVISION_4_COMPLETE_PENDING_FRESH_REVIEW",
        f"CURRENT_MAIN={C5_BASE_MAIN}",
        "CURRENT_REPOSITORY_CALLER=C4",
        "CURRENT_REPOSITORY_DESIRED_WIF=C4",
        "CURRENT_LIVE_RECOVERY_WIF=C4_ONLY",
        f"CURRENT_BOOTSTRAP_STATE_LINEAGE={C5_BOOTSTRAP_STATE_LINEAGE}",
        f"CURRENT_BOOTSTRAP_STATE_SERIAL={C5_BOOTSTRAP_STATE_SERIAL}",
        "C4_DISPATCH=PERMANENTLY_FORBIDDEN",
        "C5_IMPLEMENTATION=NOT_AUTHORISED",
    ):
        if token not in architecture["body"]:
            raise RecoveryError("C5_ARCHITECTURE_CONTRACT_MISMATCH")

    architecture_review = _successor_fixed_comment(
        comments,
        C5_ARCHITECTURE_REVIEW_COMMENT_ID,
        C5_ARCHITECTURE_REVIEW_BODY_SHA256,
        "C5_ARCHITECTURE_REVIEW",
    )
    for token in (
        f"REVIEW_TARGET={C5_ARCHITECTURE_COMMENT_ID}",
        "DISPOSITION=APPROVED",
        "MATERIAL_BLOCKERS=NONE",
        "INCIDENT_TRUTH_AND_NON_RETROACTIVITY=PASS",
        "OWNER_DISPOSITION_AUTHORITY_CLOSURE=PASS",
        "USE_TIME_CURRENTNESS=PASS",
        "RETAINED_EFFECT_BASELINE=PASS",
        "TERMINAL_AND_DISPATCH_GATING=PASS",
        "RETAIN_POSITIVE_REACHABILITY=PASS",
        "REVERT_REACHABILITY=PASS",
    ):
        if token not in architecture_review["body"]:
            raise RecoveryError("C5_ARCHITECTURE_REVIEW_CONTRACT_MISMATCH")

    disposition_candidates = [
        comment
        for comment in comments
        if _owner_issue_comment(comment, GOVERNING_ISSUE)
        and canonical_comment_text(comment.get("body")).startswith(
            "PHASE5_SLICE_C_C4_WIF_INCIDENT_DISPOSITION_V1\n"
        )
    ]
    if len(disposition_candidates) != 1:
        raise RecoveryError("C5_OWNER_DISPOSITION_NOT_UNIQUE")
    disposition = _successor_fixed_comment(
        comments,
        C5_OWNER_DISPOSITION_COMMENT_ID,
        C5_OWNER_DISPOSITION_BODY_SHA256,
        "C5_OWNER_DISPOSITION",
    )
    disposition_fields = _record_fields(
        disposition["body"],
        "PHASE5_SLICE_C_C4_WIF_INCIDENT_DISPOSITION_V1",
        (
            "GOVERNING_ISSUE",
            "C5_ARCHITECTURE_COMMENT_ID",
            "C5_ARCHITECTURE_BODY_SHA256",
            "C5_ARCHITECTURE_REVIEW_COMMENT_ID",
            "C5_ARCHITECTURE_REVIEW_BODY_SHA256",
            "INCIDENT_ID",
            "INCIDENT_BODY_SHA256",
            "MALFORMED_AUTHORITY_ID",
            "MALFORMED_AUTHORITY_BODY_SHA256",
            "INVALID_TERMINAL_ID",
            "INVALID_TERMINAL_BODY_SHA256",
            "SAVED_PLAN_SHA256",
            "STRUCTURAL_MANIFEST_SHA256",
            "CURRENT_MAIN",
            "BOOTSTRAP_STATE_LINEAGE",
            "BOOTSTRAP_STATE_SERIAL",
            "LIVE_RECOVERY_WIF",
            "POST_APPLY_RECONCILIATION",
            "NON_RETROACTIVE_ACK",
            "DISPOSITION",
            "AUTHORITY_SCOPE",
        ),
    )
    expected_disposition = {
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "C5_ARCHITECTURE_COMMENT_ID": str(C5_ARCHITECTURE_COMMENT_ID),
        "C5_ARCHITECTURE_BODY_SHA256": C5_ARCHITECTURE_BODY_SHA256,
        "C5_ARCHITECTURE_REVIEW_COMMENT_ID": str(C5_ARCHITECTURE_REVIEW_COMMENT_ID),
        "C5_ARCHITECTURE_REVIEW_BODY_SHA256": C5_ARCHITECTURE_REVIEW_BODY_SHA256,
        "INCIDENT_ID": str(C5_C4_INCIDENT_ID),
        "INCIDENT_BODY_SHA256": C5_C4_INCIDENT_BODY_SHA256,
        "MALFORMED_AUTHORITY_ID": str(C5_C4_MALFORMED_AUTHORITY_ID),
        "MALFORMED_AUTHORITY_BODY_SHA256": C5_C4_MALFORMED_AUTHORITY_BODY_SHA256,
        "INVALID_TERMINAL_ID": str(C5_C4_INVALID_TERMINAL_ID),
        "INVALID_TERMINAL_BODY_SHA256": C5_C4_INVALID_TERMINAL_BODY_SHA256,
        "SAVED_PLAN_SHA256": C5_C4_SAVED_PLAN_SHA256,
        "STRUCTURAL_MANIFEST_SHA256": C5_C4_STRUCTURAL_MANIFEST_SHA256,
        "CURRENT_MAIN": C5_BASE_MAIN,
        "BOOTSTRAP_STATE_LINEAGE": C5_BOOTSTRAP_STATE_LINEAGE,
        "BOOTSTRAP_STATE_SERIAL": str(C5_BOOTSTRAP_STATE_SERIAL),
        "LIVE_RECOVERY_WIF": "C4_ONLY",
        "POST_APPLY_RECONCILIATION": "EXACT_NO_CHANGE",
        "NON_RETROACTIVE_ACK": "TRUE",
        "DISPOSITION": "RETAIN_EXACT_EFFECT",
        "AUTHORITY_SCOPE": "C5_INERT_CONTROL_IMPLEMENTATION_ONLY",
    }
    if disposition_fields != expected_disposition:
        raise RecoveryError("C5_OWNER_DISPOSITION_CONTRACT_MISMATCH")

    baseline_candidates = [
        comment
        for comment in comments
        if _owner_issue_comment(comment, GOVERNING_ISSUE)
        and canonical_comment_text(comment.get("body")).startswith(
            "RETAINED_C4_EFFECT_BASELINE_V1\n"
        )
    ]
    if len(baseline_candidates) != 1:
        raise RecoveryError("C5_RETAINED_BASELINE_NOT_UNIQUE")
    baseline = _successor_fixed_comment(
        comments,
        C5_RETAINED_BASELINE_COMMENT_ID,
        C5_RETAINED_BASELINE_BODY_SHA256,
        "C5_RETAINED_BASELINE",
    )
    baseline_fields = _record_fields(
        baseline["body"],
        "RETAINED_C4_EFFECT_BASELINE_V1",
        (
            "STATUS",
            "GOVERNING_ISSUE",
            "OWNER_DISPOSITION_COMMENT_ID",
            "OWNER_DISPOSITION_BODY_SHA256",
            "DISPOSITION",
            "AUTHORITY_SCOPE",
            "C5_ARCHITECTURE_COMMENT_ID",
            "C5_ARCHITECTURE_BODY_SHA256",
            "C5_ARCHITECTURE_REVIEW_COMMENT_ID",
            "C5_ARCHITECTURE_REVIEW_BODY_SHA256",
            "INCIDENT_ID",
            "MALFORMED_C4_AUTHORITY_ID",
            "INVALID_C4_TERMINAL_ID",
            "CURRENT_MAIN",
            "REPOSITORY_CALLER",
            "REPOSITORY_DESIRED_WIF",
            "LIVE_RECOVERY_WIF",
            "BOOTSTRAP_STATE_LINEAGE",
            "BOOTSTRAP_STATE_SERIAL",
            "BOOTSTRAP_STATE_RESOURCE_COUNT",
            "C2_RECOVERY_CLAIM_RESULT",
            "C3_RECOVERY_CLAIM_RESULT",
            "C4_RECOVERY_CLAIM_RESULT",
            "BOOTSTRAP_LOCK",
            "ACTIVE_GITHUB_ACTIONS_RUNS",
            "PHASE5_WIF_STATE_RESOURCES",
            "ALL_PHASE5_WIF_LIVE_MATCHES",
            "GETMETADATA_PLAN_ROLE",
            "GETMETADATA_APPLY_ROLE",
            "BOOTSTRAP_RECONCILIATION",
            "TERRAFORM_PLAN_EXIT",
            "NON_RETROACTIVE_ACK",
            "C4_DISPATCH",
            "CLOUD_MUTATION",
            "NEXT_AUTHORISED_SCOPE",
        ),
    )
    expected_baseline = {
        "STATUS": "C5_RETAINED_EFFECT_BASELINE_ESTABLISHED",
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "OWNER_DISPOSITION_COMMENT_ID": str(C5_OWNER_DISPOSITION_COMMENT_ID),
        "OWNER_DISPOSITION_BODY_SHA256": C5_OWNER_DISPOSITION_BODY_SHA256,
        "DISPOSITION": "RETAIN_EXACT_EFFECT",
        "AUTHORITY_SCOPE": "C5_INERT_CONTROL_IMPLEMENTATION_ONLY",
        "C5_ARCHITECTURE_COMMENT_ID": str(C5_ARCHITECTURE_COMMENT_ID),
        "C5_ARCHITECTURE_BODY_SHA256": C5_ARCHITECTURE_BODY_SHA256,
        "C5_ARCHITECTURE_REVIEW_COMMENT_ID": str(C5_ARCHITECTURE_REVIEW_COMMENT_ID),
        "C5_ARCHITECTURE_REVIEW_BODY_SHA256": C5_ARCHITECTURE_REVIEW_BODY_SHA256,
        "INCIDENT_ID": str(C5_C4_INCIDENT_ID),
        "MALFORMED_C4_AUTHORITY_ID": str(C5_C4_MALFORMED_AUTHORITY_ID),
        "INVALID_C4_TERMINAL_ID": str(C5_C4_INVALID_TERMINAL_ID),
        "CURRENT_MAIN": C5_BASE_MAIN,
        "REPOSITORY_CALLER": "C4",
        "REPOSITORY_DESIRED_WIF": "C4",
        "LIVE_RECOVERY_WIF": "C4_ONLY",
        "BOOTSTRAP_STATE_LINEAGE": C5_BOOTSTRAP_STATE_LINEAGE,
        "BOOTSTRAP_STATE_SERIAL": str(C5_BOOTSTRAP_STATE_SERIAL),
        "BOOTSTRAP_STATE_RESOURCE_COUNT": "138",
        "C2_RECOVERY_CLAIM_RESULT": "ABSENT",
        "C3_RECOVERY_CLAIM_RESULT": "ABSENT",
        "C4_RECOVERY_CLAIM_RESULT": "ABSENT",
        "BOOTSTRAP_LOCK": "ABSENT",
        "ACTIVE_GITHUB_ACTIONS_RUNS": "0",
        "PHASE5_WIF_STATE_RESOURCES": "8",
        "ALL_PHASE5_WIF_LIVE_MATCHES": "PASS",
        "GETMETADATA_PLAN_ROLE": "PRESENT",
        "GETMETADATA_APPLY_ROLE": "PRESENT",
        "BOOTSTRAP_RECONCILIATION": "EXACT_NO_CHANGE",
        "TERRAFORM_PLAN_EXIT": "0",
        "NON_RETROACTIVE_ACK": "TRUE",
        "C4_DISPATCH": "PERMANENTLY_FORBIDDEN",
        "CLOUD_MUTATION": "NOT_AUTHORISED",
        "NEXT_AUTHORISED_SCOPE": "C5_INERT_CONTROL_IMPLEMENTATION_ONLY",
    }
    if baseline_fields != expected_baseline:
        raise RecoveryError("C5_RETAINED_BASELINE_CONTRACT_MISMATCH")
    if not (
        architecture["created_at"]
        < architecture_review["created_at"]
        < disposition["created_at"]
        < baseline["created_at"]
    ):
        raise RecoveryError("C5_GOVERNANCE_TIMELINE_INVALID")
    return {
        "architecture": architecture,
        "architecture_review": architecture_review,
        "disposition": disposition,
        "retained_baseline": baseline,
    }


def c5_use_time_currentness_body(
    current_main: str,
    repository_caller_sha: str,
    repository_desired_wif_sha: str,
    live_recovery_wif: str,
    state_lineage: str,
    state_serial: int,
    c2_claim_result: str,
    c3_claim_result: str,
    c4_claim_result: str,
    bootstrap_reconciliation: str,
    getmetadata_plan_role: str,
    getmetadata_apply_role: str,
    normal_phase5_identities: str,
    bootstrap_lock: str,
    active_conflicting_executions: int,
) -> str:
    _c5_require_sha(current_main, "C5_CURRENT_MAIN")
    _c5_require_sha(repository_caller_sha, "C5_REPOSITORY_CALLER_SHA")
    _c5_require_sha(repository_desired_wif_sha, "C5_REPOSITORY_DESIRED_WIF_SHA")
    _c5_require_lineage(state_lineage, "C5_BOOTSTRAP_STATE_LINEAGE")
    _c5_nonnegative(state_serial, "C5_BOOTSTRAP_STATE_SERIAL")
    _c5_nonnegative(active_conflicting_executions, "C5_ACTIVE_CONFLICTING_EXECUTIONS")
    expected = (
        current_main == C5_BASE_MAIN
        and repository_caller_sha == C5_OLD_RECOVERY_CONTROL_SHA
        and repository_desired_wif_sha == C5_OLD_RECOVERY_CONTROL_SHA
        and live_recovery_wif == "C4_ONLY"
        and state_lineage == C5_BOOTSTRAP_STATE_LINEAGE
        and state_serial == C5_BOOTSTRAP_STATE_SERIAL
        and c2_claim_result == "ABSENT"
        and c3_claim_result == "ABSENT"
        and c4_claim_result == "ABSENT"
        and bootstrap_reconciliation == "EXACT_NO_CHANGE"
        and getmetadata_plan_role == "PRESENT"
        and getmetadata_apply_role == "PRESENT"
        and normal_phase5_identities == "UNCHANGED"
        and bootstrap_lock == "ABSENT"
        and active_conflicting_executions == 0
    )
    if not expected:
        raise RecoveryError("C5_USE_TIME_CURRENTNESS_MISMATCH")
    return "\n".join(
        (
            "PHASE5_SLICE_C_C5_USE_TIME_CURRENTNESS_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"C5_ARCHITECTURE_COMMENT_ID={C5_ARCHITECTURE_COMMENT_ID}",
            f"C5_ARCHITECTURE_BODY_SHA256={C5_ARCHITECTURE_BODY_SHA256}",
            f"C5_ARCHITECTURE_REVIEW_COMMENT_ID={C5_ARCHITECTURE_REVIEW_COMMENT_ID}",
            f"C5_ARCHITECTURE_REVIEW_BODY_SHA256={C5_ARCHITECTURE_REVIEW_BODY_SHA256}",
            f"OWNER_DISPOSITION_COMMENT_ID={C5_OWNER_DISPOSITION_COMMENT_ID}",
            f"OWNER_DISPOSITION_BODY_SHA256={C5_OWNER_DISPOSITION_BODY_SHA256}",
            f"RETAINED_EFFECT_BASELINE_COMMENT_ID={C5_RETAINED_BASELINE_COMMENT_ID}",
            f"RETAINED_EFFECT_BASELINE_BODY_SHA256={C5_RETAINED_BASELINE_BODY_SHA256}",
            f"CURRENT_MAIN={current_main}",
            f"REPOSITORY_CALLER_SHA={repository_caller_sha}",
            f"REPOSITORY_DESIRED_WIF_SHA={repository_desired_wif_sha}",
            f"LIVE_RECOVERY_WIF={live_recovery_wif}",
            f"BOOTSTRAP_STATE_LINEAGE={state_lineage}",
            f"BOOTSTRAP_STATE_SERIAL={state_serial}",
            f"C2_RECOVERY_CLAIM_RESULT={c2_claim_result}",
            f"C3_RECOVERY_CLAIM_RESULT={c3_claim_result}",
            f"C4_RECOVERY_CLAIM_RESULT={c4_claim_result}",
            f"BOOTSTRAP_RECONCILIATION={bootstrap_reconciliation}",
            f"GETMETADATA_PLAN_ROLE={getmetadata_plan_role}",
            f"GETMETADATA_APPLY_ROLE={getmetadata_apply_role}",
            f"NORMAL_PHASE5_IDENTITIES={normal_phase5_identities}",
            f"BOOTSTRAP_LOCK={bootstrap_lock}",
            f"ACTIVE_CONFLICTING_EXECUTIONS={active_conflicting_executions}",
            "CURRENTNESS=PASS",
        )
    )


def c5_precondition_snapshot(
    successor_control_sha: str,
    successor_activation_main: str,
    saved_plan_sha256: str,
    structural_manifest_sha256: str,
    state_lineage: str,
    state_serial: int,
    fresh_review_comment_id: int,
    fresh_review_body_sha256: str,
    owner_apply_authority_comment_id: int,
    owner_apply_authority_body_sha256: str,
    old_recovery_control_sha: str,
    new_recovery_control_sha: str,
    nonterminal_actions_count: int = 0,
    nonterminal_actions_digest_sha256: str | None = None,
) -> str:
    _c5_require_sha(successor_control_sha, "C5_SUCCESSOR_CONTROL_SHA")
    _c5_require_sha(successor_activation_main, "C5_SUCCESSOR_ACTIVATION_MAIN")
    _c5_require_hash(saved_plan_sha256, "C5_SAVED_PLAN_SHA256")
    _c5_require_hash(structural_manifest_sha256, "C5_STRUCTURAL_MANIFEST_SHA256")
    _c5_require_lineage(state_lineage, "C5_PRECONDITION_LINEAGE")
    _c5_nonnegative(state_serial, "C5_PRECONDITION_SERIAL")
    _c5_positive(fresh_review_comment_id, "C5_FRESH_REVIEW_COMMENT_ID")
    _c5_require_hash(fresh_review_body_sha256, "C5_FRESH_REVIEW_BODY_SHA256")
    _c5_positive(owner_apply_authority_comment_id, "C5_OWNER_APPLY_AUTHORITY_COMMENT_ID")
    _c5_require_hash(owner_apply_authority_body_sha256, "C5_OWNER_APPLY_AUTHORITY_BODY_SHA256")
    _c5_require_sha(old_recovery_control_sha, "C5_OLD_RECOVERY_CONTROL_SHA")
    _c5_require_sha(new_recovery_control_sha, "C5_NEW_RECOVERY_CONTROL_SHA")
    if old_recovery_control_sha != C5_OLD_RECOVERY_CONTROL_SHA:
        raise RecoveryError("C5_PRECONDITION_OLD_CONTROL_MISMATCH")
    if new_recovery_control_sha != successor_control_sha:
        raise RecoveryError("C5_PRECONDITION_NEW_CONTROL_MISMATCH")
    if new_recovery_control_sha in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS or (
        new_recovery_control_sha == old_recovery_control_sha
    ):
        raise RecoveryError("C5_PRECONDITION_NEW_CONTROL_FORBIDDEN")
    _c5_nonnegative(nonterminal_actions_count, "C5_PRECONDITION_NONTERMINAL_ACTIONS_COUNT")
    if nonterminal_actions_digest_sha256 is None:
        nonterminal_actions_digest_sha256 = sha256(canonical([]))
    _c5_require_hash(nonterminal_actions_digest_sha256, "C5_PRECONDITION_NONTERMINAL_ACTIONS_DIGEST")
    if nonterminal_actions_count != 0:
        raise RecoveryError("C5_PRECONDITION_NONTERMINAL_ACTIONS_PRESENT")
    return "\n".join(
        (
            "PHASE5_SLICE_C_WIF_REPIN_PRECONDITION_SNAPSHOT_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"SUCCESSOR_CONTROL_SHA={successor_control_sha}",
            f"SUCCESSOR_ACTIVATION_MAIN={successor_activation_main}",
            f"SAVED_PLAN_SHA256={saved_plan_sha256}",
            f"STRUCTURAL_MANIFEST_SHA256={structural_manifest_sha256}",
            f"BOOTSTRAP_STATE_LINEAGE={state_lineage}",
            f"BOOTSTRAP_STATE_SERIAL={state_serial}",
            f"FRESH_REVIEW_COMMENT_ID={fresh_review_comment_id}",
            f"FRESH_REVIEW_BODY_SHA256={fresh_review_body_sha256}",
            f"OWNER_APPLY_AUTHORITY_COMMENT_ID={owner_apply_authority_comment_id}",
            f"OWNER_APPLY_AUTHORITY_BODY_SHA256={owner_apply_authority_body_sha256}",
            f"OLD_RECOVERY_CONTROL_SHA={old_recovery_control_sha}",
            f"NEW_RECOVERY_CONTROL_SHA={new_recovery_control_sha}",
            f"FORBIDDEN_RECOVERY_CONTROL_SHA_1={PREDECESSOR_CONTROL_SHA}",
            f"FORBIDDEN_RECOVERY_CONTROL_SHA_2={SUPERSEDED_CONTROL_SHA}",
            f"FORBIDDEN_RECOVERY_CONTROL_SHA_3={FAILED_C3_CONTROL_SHA}",
            "LIVE_RECOVERY_WIF=OLD_ONLY",
            "OLD_CONTROL_RECOVERY_CLAIM_RESULT=ABSENT",
            "NEW_CONTROL_RECOVERY_CLAIM_RESULT=ABSENT",
            "SUPERSEDED_C2_RECOVERY_CLAIM_RESULT=ABSENT",
            "SUPERSEDED_C3_RECOVERY_CLAIM_RESULT=ABSENT",
            "BOOTSTRAP_LOCK=ABSENT",
            "ACTIVE_CONFLICTING_EXECUTIONS=0",
            f"NONTERMINAL_ACTIONS_COUNT={nonterminal_actions_count}",
            f"NONTERMINAL_ACTIONS_DIGEST_SHA256={nonterminal_actions_digest_sha256}",
            "BOOTSTRAP_STATE_LOCKING=MANDATORY_NO_BYPASS",
            "TERRAFORM_VERSION=1.15.8",
            "PLAN_FORMAT_VERSION=1.2",
            "PLAN_APPLYABLE=true",
            "PLAN_COMPLETE=true",
            "PLAN_ERRORED=false",
            "PLAN_EFFECTS=EXACT_ONE_RECOVERY_WIF_SUBJECT_REPIN_OLD_TO_NEW",
            "OUTPUT_CHANGES=0",
        )
    )


def c5_precondition_digest_sha256(*args: Any, **kwargs: Any) -> str:
    snapshot = c5_precondition_snapshot(*args, **kwargs)
    return sha256(snapshot.encode("utf-8"))


def c5_attempt_series_body(
    successor_control_sha: str,
    successor_activation_main: str,
    old_recovery_control_sha: str,
    new_recovery_control_sha: str,
) -> str:
    _c5_require_sha(successor_control_sha, "C5_ATTEMPT_SUCCESSOR_CONTROL_SHA")
    _c5_require_sha(successor_activation_main, "C5_ATTEMPT_SUCCESSOR_ACTIVATION_MAIN")
    _c5_require_sha(old_recovery_control_sha, "C5_ATTEMPT_OLD_CONTROL_SHA")
    _c5_require_sha(new_recovery_control_sha, "C5_ATTEMPT_NEW_CONTROL_SHA")
    if old_recovery_control_sha != C5_OLD_RECOVERY_CONTROL_SHA:
        raise RecoveryError("C5_ATTEMPT_OLD_CONTROL_MISMATCH")
    if new_recovery_control_sha != successor_control_sha:
        raise RecoveryError("C5_ATTEMPT_NEW_CONTROL_MISMATCH")
    if new_recovery_control_sha in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS or (
        new_recovery_control_sha == old_recovery_control_sha
    ):
        raise RecoveryError("C5_ATTEMPT_NEW_CONTROL_FORBIDDEN")
    return "\n".join(
        (
            "PHASE5_SLICE_C_WIF_REPIN_ATTEMPT_SERIES_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"SUCCESSOR_CONTROL_SHA={successor_control_sha}",
            f"SUCCESSOR_ACTIVATION_MAIN={successor_activation_main}",
            f"OLD_RECOVERY_CONTROL_SHA={old_recovery_control_sha}",
            f"NEW_RECOVERY_CONTROL_SHA={new_recovery_control_sha}",
        )
    )


def c5_attempt_series_id_sha256(*args: Any, **kwargs: Any) -> str:
    return sha256(c5_attempt_series_body(*args, **kwargs).encode("utf-8"))


C5_ATTEMPT_CLAIM_FIELDS = (
    "GOVERNING_ISSUE",
    "C5_PROTOCOL_EPOCH_SHA256",
    "ATTEMPT_SERIES_ID_SHA256",
    "ATTEMPT_GENERATION",
    "SUCCESSOR_CONTROL_SHA",
    "SUCCESSOR_ACTIVATION_MAIN",
    "OLD_RECOVERY_CONTROL_SHA",
    "NEW_RECOVERY_CONTROL_SHA",
    "SAVED_PLAN_SHA256",
    "STRUCTURAL_MANIFEST_SHA256",
    "PRECONDITION_DIGEST_SHA256",
    "BOOTSTRAP_STATE_LINEAGE_BEFORE",
    "BOOTSTRAP_STATE_SERIAL_BEFORE",
    "NONTERMINAL_ACTIONS_DIGEST_SHA256",
    "FRESH_REVIEW_COMMENT_ID",
    "FRESH_REVIEW_BODY_SHA256",
    "OWNER_APPLY_AUTHORITY_COMMENT_ID",
    "OWNER_APPLY_AUTHORITY_BODY_SHA256",
    "EFFECT_EXECUTOR",
    "BOOTSTRAP_STATE_LOCKING",
    "AUTHORITY_CONSUMPTION",
)


def c5_attempt_claim_body(
    successor_control_sha: str,
    successor_activation_main: str,
    old_recovery_control_sha: str,
    new_recovery_control_sha: str,
    generation: int,
    saved_plan_sha256: str,
    structural_manifest_sha256: str,
    precondition_digest_sha256: str,
    fresh_review_comment_id: int,
    fresh_review_body_sha256: str,
    owner_apply_authority_comment_id: int,
    owner_apply_authority_body_sha256: str,
) -> str:
    series_id = c5_attempt_series_id_sha256(
        successor_control_sha,
        successor_activation_main,
        old_recovery_control_sha,
        new_recovery_control_sha,
    )
    _c5_positive(generation, "C5_ATTEMPT_GENERATION")
    _c5_require_hash(saved_plan_sha256, "C5_ATTEMPT_SAVED_PLAN_SHA256")
    _c5_require_hash(structural_manifest_sha256, "C5_ATTEMPT_STRUCTURAL_MANIFEST_SHA256")
    _c5_require_hash(precondition_digest_sha256, "C5_ATTEMPT_PRECONDITION_DIGEST_SHA256")
    _c5_positive(fresh_review_comment_id, "C5_ATTEMPT_FRESH_REVIEW_COMMENT_ID")
    _c5_require_hash(fresh_review_body_sha256, "C5_ATTEMPT_FRESH_REVIEW_BODY_SHA256")
    _c5_positive(
        owner_apply_authority_comment_id,
        "C5_ATTEMPT_OWNER_APPLY_AUTHORITY_COMMENT_ID",
    )
    _c5_require_hash(
        owner_apply_authority_body_sha256,
        "C5_ATTEMPT_OWNER_APPLY_AUTHORITY_BODY_SHA256",
    )
    return "\n".join(
        (
            "WIF_REPIN_ATTEMPT_CLAIM_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"ATTEMPT_SERIES_ID_SHA256={series_id}",
            f"ATTEMPT_GENERATION={generation}",
            f"SUCCESSOR_CONTROL_SHA={successor_control_sha}",
            f"SUCCESSOR_ACTIVATION_MAIN={successor_activation_main}",
            f"OLD_RECOVERY_CONTROL_SHA={old_recovery_control_sha}",
            f"NEW_RECOVERY_CONTROL_SHA={new_recovery_control_sha}",
            f"SAVED_PLAN_SHA256={saved_plan_sha256}",
            f"STRUCTURAL_MANIFEST_SHA256={structural_manifest_sha256}",
            f"PRECONDITION_DIGEST_SHA256={precondition_digest_sha256}",
            f"BOOTSTRAP_STATE_LINEAGE_BEFORE={C5_BOOTSTRAP_STATE_LINEAGE}",
            f"BOOTSTRAP_STATE_SERIAL_BEFORE={C5_BOOTSTRAP_STATE_SERIAL}",
            f"NONTERMINAL_ACTIONS_DIGEST_SHA256={sha256(canonical([]))}",
            f"FRESH_REVIEW_COMMENT_ID={fresh_review_comment_id}",
            f"FRESH_REVIEW_BODY_SHA256={fresh_review_body_sha256}",
            f"OWNER_APPLY_AUTHORITY_COMMENT_ID={owner_apply_authority_comment_id}",
            f"OWNER_APPLY_AUTHORITY_BODY_SHA256={owner_apply_authority_body_sha256}",
            "EFFECT_EXECUTOR=apply-c5-wif-repin-effect",
            "BOOTSTRAP_STATE_LOCKING=CANONICAL_TERRAFORM_LOCK_TRUE_REQUIRED",
            "AUTHORITY_CONSUMPTION=CONSUMED_ON_POST",
        )
    )


def _c5_parse_attempt_claim(comment: dict[str, Any]) -> dict[str, Any]:
    created, body_sha = _require_unedited_owner_comment(
        comment, GOVERNING_ISSUE, "C5_ATTEMPT_CLAIM"
    )
    fields = _record_fields(
        str(comment.get("body") or ""),
        "WIF_REPIN_ATTEMPT_CLAIM_V1",
        C5_ATTEMPT_CLAIM_FIELDS,
    )
    if fields["GOVERNING_ISSUE"] != "8ft0-ai/resilio#109":
        raise RecoveryError("C5_ATTEMPT_CLAIM_ISSUE_MISMATCH")
    if fields["C5_PROTOCOL_EPOCH_SHA256"] != C5_PROTOCOL_EPOCH_SHA256:
        raise RecoveryError("C5_ATTEMPT_CLAIM_PROTOCOL_EPOCH_MISMATCH")
    for name in (
        "ATTEMPT_SERIES_ID_SHA256",
        "SAVED_PLAN_SHA256",
        "STRUCTURAL_MANIFEST_SHA256",
        "PRECONDITION_DIGEST_SHA256",
        "FRESH_REVIEW_BODY_SHA256",
        "OWNER_APPLY_AUTHORITY_BODY_SHA256",
        "NONTERMINAL_ACTIONS_DIGEST_SHA256",
    ):
        _c5_require_hash(fields[name], f"C5_ATTEMPT_CLAIM_{name}")
    for name in (
        "SUCCESSOR_CONTROL_SHA",
        "SUCCESSOR_ACTIVATION_MAIN",
        "OLD_RECOVERY_CONTROL_SHA",
        "NEW_RECOVERY_CONTROL_SHA",
    ):
        _c5_require_sha(fields[name], f"C5_ATTEMPT_CLAIM_{name}")
    generation = _positive_int(fields["ATTEMPT_GENERATION"], "C5_ATTEMPT_GENERATION")
    _positive_int(fields["FRESH_REVIEW_COMMENT_ID"], "C5_ATTEMPT_FRESH_REVIEW_COMMENT_ID")
    _positive_int(
        fields["OWNER_APPLY_AUTHORITY_COMMENT_ID"],
        "C5_ATTEMPT_OWNER_APPLY_AUTHORITY_COMMENT_ID",
    )
    if fields["BOOTSTRAP_STATE_LINEAGE_BEFORE"] != C5_BOOTSTRAP_STATE_LINEAGE:
        raise RecoveryError("C5_ATTEMPT_CLAIM_LINEAGE_MISMATCH")
    if _positive_int(fields["BOOTSTRAP_STATE_SERIAL_BEFORE"], "C5_ATTEMPT_CLAIM_SERIAL") != C5_BOOTSTRAP_STATE_SERIAL:
        raise RecoveryError("C5_ATTEMPT_CLAIM_SERIAL_MISMATCH")
    if fields["NONTERMINAL_ACTIONS_DIGEST_SHA256"] != sha256(canonical([])):
        raise RecoveryError("C5_ATTEMPT_CLAIM_ACTIONS_DIGEST_MISMATCH")
    if fields["EFFECT_EXECUTOR"] != "apply-c5-wif-repin-effect":
        raise RecoveryError("C5_ATTEMPT_EFFECT_EXECUTOR_INVALID")
    if (
        fields["BOOTSTRAP_STATE_LOCKING"]
        != "CANONICAL_TERRAFORM_LOCK_TRUE_REQUIRED"
    ):
        raise RecoveryError("C5_ATTEMPT_BOOTSTRAP_LOCKING_INVALID")
    if fields["AUTHORITY_CONSUMPTION"] != "CONSUMED_ON_POST":
        raise RecoveryError("C5_ATTEMPT_AUTHORITY_CONSUMPTION_INVALID")
    expected_series = c5_attempt_series_id_sha256(
        fields["SUCCESSOR_CONTROL_SHA"],
        fields["SUCCESSOR_ACTIVATION_MAIN"],
        fields["OLD_RECOVERY_CONTROL_SHA"],
        fields["NEW_RECOVERY_CONTROL_SHA"],
    )
    if fields["ATTEMPT_SERIES_ID_SHA256"] != expected_series:
        raise RecoveryError("C5_ATTEMPT_SERIES_ID_MISMATCH")
    return {
        "comment_id": int(comment["id"]),
        "created_at": created,
        "body_sha256": body_sha,
        "generation": generation,
        "fields": fields,
    }


def validate_c5_attempt_history(
    comments: list[dict[str, Any]],
    successor_control_sha: str,
    successor_activation_main: str,
    old_recovery_control_sha: str,
    new_recovery_control_sha: str,
) -> dict[str, Any]:
    expected_series = c5_attempt_series_id_sha256(
        successor_control_sha,
        successor_activation_main,
        old_recovery_control_sha,
        new_recovery_control_sha,
    )
    claims: list[dict[str, Any]] = []
    for comment in comments:
        if not _owner_issue_comment(comment, GOVERNING_ISSUE):
            continue
        body = canonical_comment_text(comment.get("body"))
        if not body.startswith("WIF_REPIN_ATTEMPT_CLAIM_V1\n"):
            continue
        parsed = _c5_parse_attempt_claim(comment)
        fields = parsed["fields"]
        same_tuple = (
            fields["SUCCESSOR_CONTROL_SHA"] == successor_control_sha
            and fields["SUCCESSOR_ACTIVATION_MAIN"] == successor_activation_main
            and fields["OLD_RECOVERY_CONTROL_SHA"] == old_recovery_control_sha
            and fields["NEW_RECOVERY_CONTROL_SHA"] == new_recovery_control_sha
        )
        if same_tuple and fields["ATTEMPT_SERIES_ID_SHA256"] != expected_series:
            raise RecoveryError("C5_ATTEMPT_SERIES_CONFLICT")
        if fields["ATTEMPT_SERIES_ID_SHA256"] == expected_series:
            if not same_tuple:
                raise RecoveryError("C5_ATTEMPT_SERIES_ID_COLLISION")
            claims.append(parsed)
    generations = [item["generation"] for item in claims]
    if len(generations) != len(set(generations)):
        raise RecoveryError("C5_ATTEMPT_GENERATION_DUPLICATE")
    ordered = sorted(generations)
    if ordered and ordered != list(range(1, max(ordered) + 1)):
        raise RecoveryError("C5_ATTEMPT_GENERATION_GAP")
    return {
        "attempt_series_id_sha256": expected_series,
        "claims": sorted(claims, key=lambda item: item["generation"]),
        "next_generation": 1 if not ordered else max(ordered) + 1,
    }


def validate_c5_posted_attempt_claim(
    comment: dict[str, Any],
    authority_created_at: datetime,
    expected_body: str,
) -> dict[str, Any]:
    parsed = _c5_parse_attempt_claim(comment)
    if canonical_comment_text(comment.get("body")) != expected_body:
        raise RecoveryError("C5_ATTEMPT_CLAIM_BODY_MISMATCH")
    if parsed["body_sha256"] != sha256(str(comment.get("body") or "").encode("utf-8")):
        raise RecoveryError("C5_ATTEMPT_CLAIM_RAW_HASH_MISMATCH")
    if parsed["created_at"] <= authority_created_at:
        raise RecoveryError("C5_ATTEMPT_CLAIM_PRECEDES_AUTHORITY")
    return parsed


def c5_wif_repin_review_body(
    successor_control_sha: str,
    successor_activation_main: str,
    saved_plan_sha256: str,
    structural_manifest_sha256: str,
    state_lineage: str,
    state_serial: int,
) -> str:
    _c5_require_sha(successor_control_sha, "C5_REVIEW_SUCCESSOR_CONTROL_SHA")
    _c5_require_sha(successor_activation_main, "C5_REVIEW_SUCCESSOR_ACTIVATION_MAIN")
    if successor_control_sha in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS or (
        successor_control_sha == C5_OLD_RECOVERY_CONTROL_SHA
    ):
        raise RecoveryError("C5_REVIEW_SUCCESSOR_CONTROL_FORBIDDEN")
    _c5_require_hash(saved_plan_sha256, "C5_REVIEW_SAVED_PLAN_SHA256")
    _c5_require_hash(structural_manifest_sha256, "C5_REVIEW_STRUCTURAL_MANIFEST_SHA256")
    _c5_require_lineage(state_lineage, "C5_REVIEW_STATE_LINEAGE")
    _c5_nonnegative(state_serial, "C5_REVIEW_STATE_SERIAL")
    return "\n".join(
        (
            "PHASE5_SLICE_C_C5_WIF_REPIN_PLAN_FRESH_REVIEW_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"C5_ARCHITECTURE_COMMENT_ID={C5_ARCHITECTURE_COMMENT_ID}",
            f"RETAINED_EFFECT_BASELINE_COMMENT_ID={C5_RETAINED_BASELINE_COMMENT_ID}",
            f"SUCCESSOR_CONTROL_SHA={successor_control_sha}",
            f"SUCCESSOR_ACTIVATION_MAIN={successor_activation_main}",
            f"OLD_RECOVERY_CONTROL_SHA={C5_OLD_RECOVERY_CONTROL_SHA}",
            f"NEW_RECOVERY_CONTROL_SHA={successor_control_sha}",
            f"SAVED_PLAN_SHA256={saved_plan_sha256}",
            f"STRUCTURAL_MANIFEST_SHA256={structural_manifest_sha256}",
            f"BOOTSTRAP_STATE_LINEAGE={state_lineage}",
            f"BOOTSTRAP_STATE_SERIAL={state_serial}",
            "TERRAFORM_VERSION=1.15.8",
            "PLAN_FORMAT_VERSION=1.2",
            "PLAN_APPLYABLE=true",
            "PLAN_COMPLETE=true",
            "PLAN_ERRORED=false",
            "PLAN_EFFECTS=EXACT_ONE_RECOVERY_WIF_SUBJECT_REPIN_OLD_TO_NEW",
            "OUTPUT_CHANGES=0",
            "REVIEW_DISPOSITION=APPROVED",
            "MATERIAL_BLOCKERS=NONE",
            "APPLY_AUTHORITY=NOT_GRANTED",
        )
    )


def c5_wif_repin_authority_body(
    successor_control_sha: str,
    successor_activation_main: str,
    saved_plan_sha256: str,
    structural_manifest_sha256: str,
    state_lineage: str,
    state_serial: int,
    fresh_review_comment_id: int,
    fresh_review_body_sha256: str,
) -> str:
    c5_wif_repin_review_body(
        successor_control_sha,
        successor_activation_main,
        saved_plan_sha256,
        structural_manifest_sha256,
        state_lineage,
        state_serial,
    )
    _c5_positive(fresh_review_comment_id, "C5_AUTHORITY_FRESH_REVIEW_COMMENT_ID")
    _c5_require_hash(
        fresh_review_body_sha256, "C5_AUTHORITY_FRESH_REVIEW_BODY_SHA256"
    )
    return "\n".join(
        (
            "PHASE5_SLICE_C_C5_WIF_REPIN_APPLY_AUTHORITY_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"C5_ARCHITECTURE_COMMENT_ID={C5_ARCHITECTURE_COMMENT_ID}",
            f"RETAINED_EFFECT_BASELINE_COMMENT_ID={C5_RETAINED_BASELINE_COMMENT_ID}",
            f"SUCCESSOR_CONTROL_SHA={successor_control_sha}",
            f"SUCCESSOR_ACTIVATION_MAIN={successor_activation_main}",
            f"OLD_RECOVERY_CONTROL_SHA={C5_OLD_RECOVERY_CONTROL_SHA}",
            f"NEW_RECOVERY_CONTROL_SHA={successor_control_sha}",
            f"SAVED_PLAN_SHA256={saved_plan_sha256}",
            f"STRUCTURAL_MANIFEST_SHA256={structural_manifest_sha256}",
            f"BOOTSTRAP_STATE_LINEAGE={state_lineage}",
            f"BOOTSTRAP_STATE_SERIAL={state_serial}",
            f"FRESH_REVIEW_COMMENT_ID={fresh_review_comment_id}",
            f"FRESH_REVIEW_BODY_SHA256={fresh_review_body_sha256}",
            "AUTHORITY=APPLY_EXACT_REVIEWED_WIF_REPIN_PLAN_ONCE",
            "EFFECT_EXECUTOR=apply-c5-wif-repin-effect",
            "BOOTSTRAP_STATE_LOCKING=CANONICAL_TERRAFORM_LOCK_TRUE_REQUIRED",
            "REPLAN=NOT_AUTHORISED",
            "PLAN_REPLACEMENT=NOT_AUTHORISED",
            "SAME_GENERATION_RETRY=NOT_AUTHORISED",
            "C4_DISPATCH=PERMANENTLY_FORBIDDEN",
        )
    )


def c5_classify_wif_repin_outcome(
    *,
    observation_complete: bool,
    old_wif_count: int,
    new_wif_count: int,
    forbidden_wif_counts: tuple[int, int, int],
    lineage_before: str,
    lineage_after: str,
    serial_before: int,
    serial_after: int,
    claim_result_states: tuple[str, str, str, str],
    bootstrap_lock_absent: bool,
    exact_no_change: bool,
    exact_pending_effect: bool,
    getmetadata_unchanged: bool,
    normal_identities_unchanged: bool,
    observation_1_sha256: str | None = None,
    observation_2_sha256: str | None = None,
    observation_separation_seconds: int = 0,
) -> str:
    if not isinstance(observation_complete, bool):
        raise RecoveryError("C5_OUTCOME_OBSERVATION_COMPLETE_INVALID")
    for value, label in (
        (old_wif_count, "C5_OUTCOME_OLD_WIF_COUNT"),
        (new_wif_count, "C5_OUTCOME_NEW_WIF_COUNT"),
        (serial_before, "C5_OUTCOME_SERIAL_BEFORE"),
        (serial_after, "C5_OUTCOME_SERIAL_AFTER"),
        (observation_separation_seconds, "C5_OUTCOME_OBSERVATION_SEPARATION"),
    ):
        _c5_nonnegative(value, label)
    if len(forbidden_wif_counts) != 3:
        raise RecoveryError("C5_OUTCOME_FORBIDDEN_WIF_COUNTS_INVALID")
    for value in forbidden_wif_counts:
        _c5_nonnegative(value, "C5_OUTCOME_FORBIDDEN_WIF_COUNT")
    _c5_require_lineage(lineage_before, "C5_OUTCOME_LINEAGE_BEFORE")
    _c5_require_lineage(lineage_after, "C5_OUTCOME_LINEAGE_AFTER")
    if len(claim_result_states) != 4:
        raise RecoveryError("C5_OUTCOME_CLAIM_RESULT_STATES_INVALID")
    allowed_states = {"ABSENT", "PRESENT", "UNKNOWN"}
    for value in claim_result_states:
        _c5_require_enum(value, allowed_states, "C5_OUTCOME_CLAIM_RESULT_STATE")
    if not observation_complete or "UNKNOWN" in claim_result_states:
        return "PROCESS_OUTCOME_UNKNOWN"

    clean_claim_results = all(value == "ABSENT" for value in claim_result_states)
    common = (
        all(value == 0 for value in forbidden_wif_counts)
        and lineage_before == lineage_after
        and clean_claim_results
        and bootstrap_lock_absent
        and getmetadata_unchanged
        and normal_identities_unchanged
    )
    effect_succeeded = (
        common
        and old_wif_count == 0
        and new_wif_count == 1
        and serial_after >= serial_before
        and exact_no_change
    )
    if effect_succeeded:
        return "EFFECT_SUCCEEDED"

    observation_hashes_valid = (
        observation_1_sha256 is not None
        and observation_2_sha256 is not None
        and HEX64.fullmatch(observation_1_sha256) is not None
        and HEX64.fullmatch(observation_2_sha256) is not None
    )
    no_effect_stable = (
        common
        and old_wif_count == 1
        and new_wif_count == 0
        and serial_after == serial_before
        and exact_pending_effect
        and observation_hashes_valid
        and observation_separation_seconds >= 60
    )
    if no_effect_stable:
        return "NO_EFFECT_STABLE"
    return "INCONSISTENT_EFFECT"


def c5_wif_repin_terminal_body(
    *,
    successor_control_sha: str,
    successor_activation_main: str,
    saved_plan_sha256: str,
    structural_manifest_sha256: str,
    fresh_review_comment_id: int,
    fresh_review_body_sha256: str,
    owner_apply_authority_comment_id: int,
    owner_apply_authority_body_sha256: str,
    attempt_claim_comment_id: int,
    attempt_claim_body_sha256: str,
    attempt_series_id_sha256: str,
    attempt_generation: int,
    precondition_digest_sha256: str,
    lineage_before: str,
    lineage_after: str,
    serial_before: int,
    serial_after: int,
    old_wif_count: int,
    new_wif_count: int,
    forbidden_wif_counts: tuple[int, int, int],
    claim_result_states: tuple[str, str, str, str],
    bootstrap_lock_absent: bool,
    exact_no_change: bool,
    exact_pending_effect: bool,
    getmetadata_unchanged: bool,
    normal_identities_unchanged: bool,
    observation_complete: bool,
    observation_1_sha256: str | None = None,
    observation_2_sha256: str | None = None,
    observation_separation_seconds: int = 0,
) -> str:
    _c5_require_sha(successor_control_sha, "C5_TERMINAL_SUCCESSOR_CONTROL_SHA")
    _c5_require_sha(successor_activation_main, "C5_TERMINAL_SUCCESSOR_ACTIVATION_MAIN")
    if successor_control_sha in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS or (
        successor_control_sha == C5_OLD_RECOVERY_CONTROL_SHA
    ):
        raise RecoveryError("C5_TERMINAL_SUCCESSOR_CONTROL_FORBIDDEN")
    for value, label in (
        (saved_plan_sha256, "C5_TERMINAL_SAVED_PLAN_SHA256"),
        (structural_manifest_sha256, "C5_TERMINAL_STRUCTURAL_MANIFEST_SHA256"),
        (fresh_review_body_sha256, "C5_TERMINAL_FRESH_REVIEW_BODY_SHA256"),
        (owner_apply_authority_body_sha256, "C5_TERMINAL_OWNER_AUTHORITY_BODY_SHA256"),
        (attempt_claim_body_sha256, "C5_TERMINAL_ATTEMPT_CLAIM_BODY_SHA256"),
        (attempt_series_id_sha256, "C5_TERMINAL_ATTEMPT_SERIES_ID_SHA256"),
        (precondition_digest_sha256, "C5_TERMINAL_PRECONDITION_DIGEST_SHA256"),
    ):
        _c5_require_hash(value, label)
    for value, label in (
        (fresh_review_comment_id, "C5_TERMINAL_FRESH_REVIEW_COMMENT_ID"),
        (owner_apply_authority_comment_id, "C5_TERMINAL_OWNER_AUTHORITY_COMMENT_ID"),
        (attempt_claim_comment_id, "C5_TERMINAL_ATTEMPT_CLAIM_COMMENT_ID"),
        (attempt_generation, "C5_TERMINAL_ATTEMPT_GENERATION"),
    ):
        _c5_positive(value, label)
    expected_series = c5_attempt_series_id_sha256(
        successor_control_sha,
        successor_activation_main,
        C5_OLD_RECOVERY_CONTROL_SHA,
        successor_control_sha,
    )
    if attempt_series_id_sha256 != expected_series:
        raise RecoveryError("C5_TERMINAL_ATTEMPT_SERIES_MISMATCH")
    outcome = c5_classify_wif_repin_outcome(
        observation_complete=observation_complete,
        old_wif_count=old_wif_count,
        new_wif_count=new_wif_count,
        forbidden_wif_counts=forbidden_wif_counts,
        lineage_before=lineage_before,
        lineage_after=lineage_after,
        serial_before=serial_before,
        serial_after=serial_after,
        claim_result_states=claim_result_states,
        bootstrap_lock_absent=bootstrap_lock_absent,
        exact_no_change=exact_no_change,
        exact_pending_effect=exact_pending_effect,
        getmetadata_unchanged=getmetadata_unchanged,
        normal_identities_unchanged=normal_identities_unchanged,
        observation_1_sha256=observation_1_sha256,
        observation_2_sha256=observation_2_sha256,
        observation_separation_seconds=observation_separation_seconds,
    )
    if outcome == "PROCESS_OUTCOME_UNKNOWN":
        raise RecoveryError("C5_PROCESS_OUTCOME_UNKNOWN_NOT_TERMINAL")
    _c5_require_enum(outcome, C5_TERMINAL_OUTCOMES, "C5_TERMINAL_OUTCOME")
    return "\n".join(
        (
            "PHASE5_SLICE_C_C5_WIF_REPIN_TERMINAL_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"C5_ARCHITECTURE_COMMENT_ID={C5_ARCHITECTURE_COMMENT_ID}",
            f"RETAINED_EFFECT_BASELINE_COMMENT_ID={C5_RETAINED_BASELINE_COMMENT_ID}",
            f"SUCCESSOR_CONTROL_SHA={successor_control_sha}",
            f"SUCCESSOR_ACTIVATION_MAIN={successor_activation_main}",
            f"OLD_RECOVERY_CONTROL_SHA={C5_OLD_RECOVERY_CONTROL_SHA}",
            f"NEW_RECOVERY_CONTROL_SHA={successor_control_sha}",
            f"SAVED_PLAN_SHA256={saved_plan_sha256}",
            f"STRUCTURAL_MANIFEST_SHA256={structural_manifest_sha256}",
            f"FRESH_REVIEW_COMMENT_ID={fresh_review_comment_id}",
            f"FRESH_REVIEW_BODY_SHA256={fresh_review_body_sha256}",
            f"OWNER_APPLY_AUTHORITY_COMMENT_ID={owner_apply_authority_comment_id}",
            f"OWNER_APPLY_AUTHORITY_BODY_SHA256={owner_apply_authority_body_sha256}",
            f"ATTEMPT_CLAIM_COMMENT_ID={attempt_claim_comment_id}",
            f"ATTEMPT_CLAIM_BODY_SHA256={attempt_claim_body_sha256}",
            f"ATTEMPT_SERIES_ID_SHA256={attempt_series_id_sha256}",
            f"ATTEMPT_GENERATION={attempt_generation}",
            f"PRECONDITION_DIGEST_SHA256={precondition_digest_sha256}",
            f"BOOTSTRAP_STATE_LINEAGE_BEFORE={lineage_before}",
            f"BOOTSTRAP_STATE_LINEAGE_AFTER={lineage_after}",
            f"BOOTSTRAP_STATE_SERIAL_BEFORE={serial_before}",
            f"BOOTSTRAP_STATE_SERIAL_AFTER={serial_after}",
            f"OLD_RECOVERY_WIF_COUNT={old_wif_count}",
            f"NEW_RECOVERY_WIF_COUNT={new_wif_count}",
            f"FORBIDDEN_C1_RECOVERY_WIF_COUNT={forbidden_wif_counts[0]}",
            f"SUPERSEDED_C2_RECOVERY_WIF_COUNT={forbidden_wif_counts[1]}",
            f"SUPERSEDED_C3_RECOVERY_WIF_COUNT={forbidden_wif_counts[2]}",
            f"C2_RECOVERY_CLAIM_RESULT={claim_result_states[0]}",
            f"C3_RECOVERY_CLAIM_RESULT={claim_result_states[1]}",
            f"OLD_CONTROL_RECOVERY_CLAIM_RESULT={claim_result_states[2]}",
            f"NEW_CONTROL_RECOVERY_CLAIM_RESULT={claim_result_states[3]}",
            f"BOOTSTRAP_LOCK={'ABSENT' if bootstrap_lock_absent else 'PRESENT'}",
            f"BOOTSTRAP_RECONCILIATION={'EXACT_NO_CHANGE' if exact_no_change else 'NOT_EXACT_NO_CHANGE'}",
            f"PENDING_REVIEWED_EFFECT={'EXACT' if exact_pending_effect else 'NOT_EXACT'}",
            f"GETMETADATA={'UNCHANGED' if getmetadata_unchanged else 'CHANGED'}",
            f"NORMAL_PHASE5_IDENTITIES={'UNCHANGED' if normal_identities_unchanged else 'CHANGED'}",
            f"OBSERVATION_1_SHA256={observation_1_sha256 or 'NONE'}",
            f"OBSERVATION_2_SHA256={observation_2_sha256 or 'NONE'}",
            f"OBSERVATION_SEPARATION_SECONDS={observation_separation_seconds}",
            f"OUTCOME={outcome}",
        )
    )


def c5_terminal_record_summary(
    comment_id: int, raw_body: str, outcome: str
) -> dict[str, Any]:
    _c5_positive(comment_id, "C5_TERMINAL_COMMENT_ID")
    _c5_require_enum(outcome, C5_TERMINAL_OUTCOMES, "C5_TERMINAL_OUTCOME")
    body_hash = sha256(str(raw_body).encode("utf-8"))
    _c5_require_hash(body_hash, "C5_TERMINAL_BODY_SHA256")
    return {
        "comment_id": comment_id,
        "body_sha256": body_hash,
        "outcome": outcome,
    }


def c5_dispatch_authority_body(
    successor_control_sha: str,
    successor_activation_main: str,
    terminal_record: dict[str, Any],
) -> str:
    _c5_require_sha(successor_control_sha, "C5_DISPATCH_SUCCESSOR_CONTROL_SHA")
    _c5_require_sha(successor_activation_main, "C5_DISPATCH_SUCCESSOR_ACTIVATION_MAIN")
    if successor_control_sha == C5_OLD_RECOVERY_CONTROL_SHA:
        raise RecoveryError("C4_DISPATCH_PERMANENTLY_FORBIDDEN")
    if successor_control_sha in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS:
        raise RecoveryError("C5_DISPATCH_CONTROL_FORBIDDEN")
    if not isinstance(terminal_record, dict):
        raise RecoveryError("C5_DISPATCH_TERMINAL_INVALID")
    terminal_id = terminal_record.get("comment_id")
    terminal_hash = terminal_record.get("body_sha256")
    terminal_outcome = terminal_record.get("outcome")
    _c5_positive(terminal_id, "C5_DISPATCH_TERMINAL_COMMENT_ID")
    _c5_require_hash(terminal_hash, "C5_DISPATCH_TERMINAL_BODY_SHA256")
    if terminal_outcome != "EFFECT_SUCCEEDED":
        raise RecoveryError("C5_DISPATCH_REQUIRES_EFFECT_SUCCEEDED")
    return "\n".join(
        (
            "PHASE5_SLICE_C_C5_DISPATCH_AUTHORITY_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"C5_ARCHITECTURE_COMMENT_ID={C5_ARCHITECTURE_COMMENT_ID}",
            f"RETAINED_EFFECT_BASELINE_COMMENT_ID={C5_RETAINED_BASELINE_COMMENT_ID}",
            f"SUCCESSOR_CONTROL_SHA={successor_control_sha}",
            f"SUCCESSOR_ACTIVATION_MAIN={successor_activation_main}",
            f"C5_WIF_REPIN_TERMINAL_COMMENT_ID={terminal_id}",
            f"C5_WIF_REPIN_TERMINAL_BODY_SHA256={terminal_hash}",
            "C5_WIF_REPIN_TERMINAL_OUTCOME=EFFECT_SUCCEEDED",
            "C4_DISPATCH=PERMANENTLY_FORBIDDEN",
            "AUTHORITY=DISPATCH_EXACTLY_ONE_C5_RECONCILIATION_ONLY_RECOVERY",
        )
    )


C5_BOOTSTRAP_STATE_OBJECT = "bootstrap/default.tfstate"
C5_BOOTSTRAP_LOCK_OBJECT = "bootstrap/default.tflock"
C5_PRODUCT_PLANNER_SA = (
    "github-p5-product-planner@resilio-control-e882d4.iam.gserviceaccount.com"
)
C5_REFERENCE_PROJECT = "resilio-reference-e882d4"
C5_GETMETADATA_ROLES = (
    "resilio_p5_product_reference_plan",
    "resilio_p5_product_reference_apply",
)
C5_EXPECTED_BOOTSTRAP_RESOURCE_COUNT = 138
C5_BASELINE_NORMAL_CONTROL_SHA = "47b3b17d32ffebf3ce8e9b7d15bc3d3539dc7239"
C5_EXPECTED_PHASE5_WIF_ROWS = {
    "github_phase5_acceptance": (
        "github-p5-acceptance@resilio-reference-e882d4.iam.gserviceaccount.com",
        "phase5-acceptance-reusable.yml",
        C5_BASELINE_NORMAL_CONTROL_SHA,
    ),
    "github_phase5_build": (
        "github-p5-build@resilio-control-e882d4.iam.gserviceaccount.com",
        "phase5-build-reusable.yml",
        C5_BASELINE_NORMAL_CONTROL_SHA,
    ),
    "github_phase5_deployer": (
        "github-p5-deployer@resilio-reference-e882d4.iam.gserviceaccount.com",
        "phase5-deploy-reusable.yml",
        C5_BASELINE_NORMAL_CONTROL_SHA,
    ),
    "github_phase5_evidence": (
        "github-p5-evidence@resilio-control-e882d4.iam.gserviceaccount.com",
        "phase5-evidence-reusable.yml",
        C5_BASELINE_NORMAL_CONTROL_SHA,
    ),
    "github_phase5_product_applier": (
        "github-p5-product-" + "applier@resilio-control-e882d4.iam.gserviceaccount.com",
        "phase5-terraform-apply-reusable.yml",
        C5_BASELINE_NORMAL_CONTROL_SHA,
    ),
    "github_phase5_product_planner": (
        "github-p5-product-planner@resilio-control-e882d4.iam.gserviceaccount.com",
        "phase5-terraform-plan-reusable.yml",
        C5_BASELINE_NORMAL_CONTROL_SHA,
    ),
    "github_phase5_slice_c_recovery": (
        C5_PRODUCT_PLANNER_SA,
        "phase5-slice-c-recovery-reusable.yml",
        C5_OLD_RECOVERY_CONTROL_SHA,
    ),
    "github_phase5_verifier": (
        "github-p5-acceptance@resilio-reference-e882d4.iam.gserviceaccount.com",
        "phase5-verify-reusable.yml",
        C5_BASELINE_NORMAL_CONTROL_SHA,
    ),
}
C5_EXPECTED_ROLE_PERMISSIONS = {
    "resilio_p5_product_reference_plan": frozenset(
        (
            "datastore.databases.get",
            "datastore.databases.getMetadata",
            "datastore.databases.list",
            "pubsub.subscriptions.get",
            "pubsub.subscriptions.list",
            "pubsub.topics.get",
            "pubsub.topics.list",
            "resourcemanager.projects.get",
            "serviceusage.services.get",
            "serviceusage.services.list",
        )
    ),
    "resilio_p5_product_reference_apply": frozenset(
        (
            "datastore.databases.create",
            "datastore.databases.get",
            "datastore.databases.getMetadata",
            "datastore.databases.list",
            "datastore.databases.update",
            "pubsub.subscriptions.create",
            "pubsub.subscriptions.get",
            "pubsub.subscriptions.list",
            "pubsub.subscriptions.update",
            "pubsub.topics.attachSubscription",
            "pubsub.topics.create",
            "pubsub.topics.get",
            "pubsub.topics.list",
            "pubsub.topics.update",
            "resourcemanager.projects.get",
            "serviceusage.services.enable",
            "serviceusage.services.get",
            "serviceusage.services.list",
        )
    ),
}


def _c5_fetch_repo_text(path: str, ref: str) -> str:
    _c5_require_sha(ref, "C5_REPOSITORY_REF")
    encoded = urllib.parse.quote(path, safe="/")
    value = github(f"/repos/{REPOSITORY}/contents/{encoded}?ref={ref}")
    if (
        not isinstance(value, dict)
        or value.get("type") != "file"
        or value.get("path") != path
        or value.get("encoding") != "base64"
    ):
        raise RecoveryError(f"C5_REPOSITORY_FILE_INVALID:{path}")
    try:
        raw = decode_github_base64(value.get("content"))
        return raw.decode("utf-8")
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise RecoveryError(f"C5_REPOSITORY_FILE_DECODE_INVALID:{path}") from exc


def _c5_iam_policy(service_account_email: str) -> dict[str, Any]:
    if (
        not service_account_email
        or "/" in service_account_email
        or "@" not in service_account_email
    ):
        raise RecoveryError("C5_SERVICE_ACCOUNT_EMAIL_INVALID")
    resource = "projects/-/serviceAccounts/" + urllib.parse.quote(
        service_account_email, safe="@.-"
    )
    value = request_json(
        f"https://iam.googleapis.com/v1/{resource}:getIamPolicy",
        google_token(),
        method="POST",
        data=b"{}",
        content_type="application/json",
    )
    if not isinstance(value, dict):
        raise RecoveryError("C5_IAM_POLICY_INVALID")
    return value


def _c5_role(role_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.]+", role_id):
        raise RecoveryError("C5_ROLE_ID_INVALID")
    value = request_json(
        f"https://iam.googleapis.com/v1/projects/{C5_REFERENCE_PROJECT}/roles/{role_id}",
        google_token(),
    )
    if not isinstance(value, dict):
        raise RecoveryError("C5_ROLE_INVALID")
    return value


def _c5_policy_members(policy: dict[str, Any], role: str) -> list[str]:
    values: list[str] = []
    bindings = policy.get("bindings")
    if bindings is None:
        return values
    if not isinstance(bindings, list):
        raise RecoveryError("C5_IAM_BINDINGS_INVALID")
    for binding in bindings:
        if not isinstance(binding, dict):
            raise RecoveryError("C5_IAM_BINDING_INVALID")
        if binding.get("role") == role:
            members = binding.get("members") or []
            if not isinstance(members, list) or not all(
                isinstance(item, str) for item in members
            ):
                raise RecoveryError("C5_IAM_MEMBERS_INVALID")
            values.extend(members)
    return values


def _c5_bootstrap_wif_rows(state: Any) -> list[dict[str, str]]:
    if not isinstance(state, dict):
        raise RecoveryError("C5_BOOTSTRAP_STATE_INVALID")
    rows: list[dict[str, str]] = []
    resources = state.get("resources")
    if not isinstance(resources, list):
        raise RecoveryError("C5_BOOTSTRAP_RESOURCES_INVALID")
    if len(resources) != C5_EXPECTED_BOOTSTRAP_RESOURCE_COUNT:
        raise RecoveryError("C5_BOOTSTRAP_RESOURCE_COUNT_INVALID")
    for resource in resources:
        if (
            not isinstance(resource, dict)
            or resource.get("type") != "google_service_account_iam_member"
            or not str(resource.get("name") or "").startswith("github_phase5")
        ):
            continue
        instances = resource.get("instances")
        if not isinstance(instances, list) or len(instances) != 1:
            raise RecoveryError("C5_PHASE5_WIF_INSTANCE_CARDINALITY_INVALID")
        attributes = instances[0].get("attributes") if isinstance(instances[0], dict) else None
        if not isinstance(attributes, dict):
            raise RecoveryError("C5_PHASE5_WIF_ATTRIBUTES_INVALID")
        service_account_id = str(attributes.get("service_account_id") or "")
        marker = "/serviceAccounts/"
        if marker not in service_account_id:
            raise RecoveryError("C5_PHASE5_WIF_SERVICE_ACCOUNT_INVALID")
        rows.append(
            {
                "name": str(resource.get("name") or ""),
                "service_account": service_account_id.split(marker, 1)[1],
                "role": str(attributes.get("role") or ""),
                "member": str(attributes.get("member") or ""),
            }
        )
    if len(rows) != len(C5_EXPECTED_PHASE5_WIF_ROWS):
        raise RecoveryError("C5_PHASE5_WIF_RESOURCE_COUNT_INVALID")
    observed_names = {row["name"] for row in rows}
    if observed_names != set(C5_EXPECTED_PHASE5_WIF_ROWS):
        raise RecoveryError("C5_PHASE5_WIF_NAME_SET_INVALID")
    prefix = (
        "principalSet://iam.googleapis.com/projects/400271474382/locations/global/"
        "workloadIdentityPools/github/attribute.job_workflow_ref/8ft0-ai/resilio/"
        ".github/workflows/"
    )
    for row in rows:
        expected_sa, expected_workflow, expected_sha = C5_EXPECTED_PHASE5_WIF_ROWS[
            row["name"]
        ]
        if row["service_account"] != expected_sa:
            raise RecoveryError(f"C5_PHASE5_WIF_STATE_SA_MISMATCH:{row['name']}")
        if row["role"] != "roles/iam.workloadIdentityUser":
            raise RecoveryError(f"C5_PHASE5_WIF_STATE_ROLE_MISMATCH:{row['name']}")
        if row["member"] != prefix + expected_workflow + "@" + expected_sha:
            raise RecoveryError(f"C5_PHASE5_WIF_STATE_MEMBER_MISMATCH:{row['name']}")
    return rows


def verify_c5_bootstrap_state_and_live_iam(
    state: Any, new_recovery_control_sha: str
) -> dict[str, Any]:
    _c5_require_sha(new_recovery_control_sha, "C5_LIVE_NEW_CONTROL_SHA")
    lineage = _c5_require_lineage(
        str(state.get("lineage") or ""), "C5_LIVE_BOOTSTRAP_LINEAGE"
    )
    serial = state.get("serial")
    _c5_nonnegative(serial, "C5_LIVE_BOOTSTRAP_SERIAL")
    if lineage != C5_BOOTSTRAP_STATE_LINEAGE or serial != C5_BOOTSTRAP_STATE_SERIAL:
        raise RecoveryError("C5_LIVE_BOOTSTRAP_STATE_IDENTITY_MISMATCH")
    rows = _c5_bootstrap_wif_rows(state)
    cache: dict[str, dict[str, Any]] = {}
    expected_by_binding: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        key = (row["service_account"], row["role"])
        expected_by_binding.setdefault(key, set()).add(row["member"])
    for (service_account, role), expected_members in expected_by_binding.items():
        if service_account not in cache:
            cache[service_account] = _c5_iam_policy(service_account)
        members = _c5_policy_members(cache[service_account], role)
        if len(members) != len(expected_members) or set(members) != expected_members:
            raise RecoveryError(f"C5_PHASE5_WIF_LIVE_SET_MISMATCH:{service_account}")

    recovery_rows = [
        row for row in rows if row["name"] == "github_phase5_slice_c_recovery"
    ]
    if len(recovery_rows) != 1:
        raise RecoveryError("C5_RECOVERY_WIF_STATE_NOT_UNIQUE")
    recovery = recovery_rows[0]
    expected_old_suffix = (
        "/.github/workflows/phase5-slice-c-recovery-reusable.yml@"
        + C5_OLD_RECOVERY_CONTROL_SHA
    )
    if not recovery["member"].endswith(expected_old_suffix):
        raise RecoveryError("C5_RECOVERY_WIF_STATE_NOT_C4")
    recovery_policy = cache[recovery["service_account"]]
    recovery_members = [
        member
        for member in _c5_policy_members(recovery_policy, recovery["role"])
        if "/.github/workflows/phase5-slice-c-recovery-reusable.yml@" in member
    ]
    if recovery_members != [recovery["member"]]:
        raise RecoveryError("C5_LIVE_RECOVERY_WIF_NOT_OLD_ONLY")
    forbidden_suffixes = tuple(
        "/.github/workflows/phase5-slice-c-recovery-reusable.yml@" + sha
        for sha in (*C5_FORBIDDEN_RECOVERY_CONTROL_SHAS, new_recovery_control_sha)
    )
    if any(
        member.endswith(suffix)
        for member in recovery_members
        for suffix in forbidden_suffixes
    ):
        raise RecoveryError("C5_LIVE_RECOVERY_WIF_FORBIDDEN_PRESENT")

    for role_id in C5_GETMETADATA_ROLES:
        role = _c5_role(role_id)
        permissions = role.get("includedPermissions")
        if not isinstance(permissions, list):
            raise RecoveryError(f"C5_ROLE_PERMISSIONS_INVALID:{role_id}")
        if frozenset(permissions) != C5_EXPECTED_ROLE_PERMISSIONS[role_id] or (
            len(permissions) != len(C5_EXPECTED_ROLE_PERMISSIONS[role_id])
        ):
            raise RecoveryError(f"C5_ROLE_PERMISSIONS_CHANGED:{role_id}")

    return {
        "state_lineage": lineage,
        "state_serial": serial,
        "phase5_wif_state_resources": len(rows),
        "all_phase5_wif_live_matches": True,
        "live_recovery_wif": "OLD_ONLY",
        "getmetadata_unchanged": True,
        "normal_phase5_identities_unchanged": True,
    }


def verify_c5_repository_activation(
    activation_main: str, successor_control_sha: str
) -> dict[str, Any]:
    _c5_require_sha(activation_main, "C5_ACTIVATION_MAIN")
    _c5_require_sha(successor_control_sha, "C5_ACTIVATION_CONTROL_SHA")
    if successor_control_sha in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS or (
        successor_control_sha == C5_OLD_RECOVERY_CONTROL_SHA
    ):
        raise RecoveryError("C5_ACTIVATION_CONTROL_FORBIDDEN")
    caller = _c5_fetch_repo_text(
        ".github/workflows/phase5-slice-c-recovery.yml", activation_main
    )
    authority = _c5_fetch_repo_text(
        "infra/bootstrap/phase5_authority.tf", activation_main
    )
    caller_ref = (
        "uses: 8ft0-ai/resilio/.github/workflows/"
        f"phase5-slice-c-recovery-reusable.yml@{successor_control_sha}"
    )
    desired_ref = (
        'phase5_slice_c_recovery_workflow_ref = '
        '"8ft0-ai/resilio/.github/workflows/'
        f'phase5-slice-c-recovery-reusable.yml@{successor_control_sha}"'
    )
    if caller.count(caller_ref) != 1:
        raise RecoveryError("C5_ACTIVATION_CALLER_NOT_EXACT")
    if authority.count(desired_ref) != 1:
        raise RecoveryError("C5_ACTIVATION_DESIRED_WIF_NOT_EXACT")
    return {
        "activation_main": activation_main,
        "successor_control_sha": successor_control_sha,
        "repository_caller": "NEW_CONTROL",
        "repository_desired_wif": "NEW_CONTROL",
    }


def c5_verify_wif_repin_plan(
    plan: Any, old_recovery_control_sha: str, new_recovery_control_sha: str
) -> dict[str, Any]:
    _c5_require_sha(old_recovery_control_sha, "C5_PLAN_OLD_CONTROL_SHA")
    _c5_require_sha(new_recovery_control_sha, "C5_PLAN_NEW_CONTROL_SHA")
    if old_recovery_control_sha != C5_OLD_RECOVERY_CONTROL_SHA:
        raise RecoveryError("C5_PLAN_OLD_CONTROL_MISMATCH")
    if new_recovery_control_sha in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS or (
        new_recovery_control_sha == old_recovery_control_sha
    ):
        raise RecoveryError("C5_PLAN_NEW_CONTROL_FORBIDDEN")
    if not isinstance(plan, dict):
        raise RecoveryError("C5_PLAN_INVALID")
    expected_scalars = {
        "format_version": "1.2",
        "terraform_version": "1.15.8",
        "applyable": True,
        "complete": True,
        "errored": False,
    }
    for key, value in expected_scalars.items():
        if plan.get(key) != value:
            raise RecoveryError(f"C5_PLAN_FIELD_MISMATCH:{key}")
    if plan.get("output_changes") not in ({}, None):
        raise RecoveryError("C5_PLAN_OUTPUT_CHANGES_PRESENT")
    for key in (
        "resource_drift",
        "deferred_changes",
        "deferred_action_invocations",
        "action_invocations",
    ):
        if plan.get(key) not in (None, []):
            raise RecoveryError(f"C5_PLAN_UNEXPECTED:{key}")
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise RecoveryError("C5_PLAN_RESOURCE_CHANGES_INVALID")
    effect_rows: list[dict[str, Any]] = []
    for row in changes:
        if not isinstance(row, dict):
            raise RecoveryError("C5_PLAN_RESOURCE_CHANGE_INVALID")
        actions = ((row.get("change") or {}).get("actions")) if isinstance(row.get("change"), dict) else None
        if actions == ["no-op"]:
            continue
        effect_rows.append(row)
    if len(effect_rows) != 1:
        raise RecoveryError("C5_PLAN_EFFECT_CARDINALITY_INVALID")
    effect = effect_rows[0]
    if effect.get("address") != (
        "google_service_account_iam_member.github_phase5_slice_c_recovery"
    ):
        raise RecoveryError("C5_PLAN_EFFECT_ADDRESS_INVALID")
    change = effect.get("change")
    if not isinstance(change, dict) or change.get("actions") not in (
        ["delete", "create"],
        ["create", "delete"],
    ):
        raise RecoveryError("C5_PLAN_EFFECT_ACTIONS_INVALID")
    before = change.get("before")
    after = change.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise RecoveryError("C5_PLAN_EFFECT_VALUES_INVALID")
    old_member = str(before.get("member") or "")
    new_member = str(after.get("member") or "")
    old_suffix = (
        "/.github/workflows/phase5-slice-c-recovery-reusable.yml@"
        + old_recovery_control_sha
    )
    new_suffix = (
        "/.github/workflows/phase5-slice-c-recovery-reusable.yml@"
        + new_recovery_control_sha
    )
    if not old_member.endswith(old_suffix) or not new_member.endswith(new_suffix):
        raise RecoveryError("C5_PLAN_EFFECT_MEMBER_TRANSITION_INVALID")
    before_copy = dict(before)
    after_copy = dict(after)
    before_copy["member"] = "<RECOVERY_MEMBER>"
    after_copy["member"] = "<RECOVERY_MEMBER>"
    for volatile in ("id",):
        before_copy.pop(volatile, None)
        after_copy.pop(volatile, None)
    if before_copy != after_copy:
        raise RecoveryError("C5_PLAN_EFFECT_UNRELATED_ATTRIBUTE_CHANGE")
    return {
        "effect_address": effect["address"],
        "old_recovery_control_sha": old_recovery_control_sha,
        "new_recovery_control_sha": new_recovery_control_sha,
        "plan_effects": "EXACT_ONE_RECOVERY_WIF_SUBJECT_REPIN_OLD_TO_NEW",
        "output_changes": 0,
    }


def _c5_saved_plan_json(
    saved_plan_path: str | Path, terraform_workdir: str | Path
) -> dict[str, Any]:
    plan_path = Path(saved_plan_path).resolve()
    workdir = Path(terraform_workdir).resolve()
    if not plan_path.is_file():
        raise RecoveryError("C5_SAVED_PLAN_MISSING")
    if not workdir.is_dir():
        raise RecoveryError("C5_TERRAFORM_WORKDIR_MISSING")
    result = subprocess.run(
        [
            "terraform",
            f"-chdir={workdir}",
            "show",
            "-json",
            str(plan_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RecoveryError("C5_SAVED_PLAN_SHOW_FAILED")
    value = strict_json(result.stdout)
    if not isinstance(value, dict):
        raise RecoveryError("C5_SAVED_PLAN_JSON_INVALID")
    return value


def c5_verify_structural_manifest(
    manifest: Any, old_recovery_control_sha: str, new_recovery_control_sha: str
) -> dict[str, Any]:
    _c5_require_sha(old_recovery_control_sha, "C5_MANIFEST_OLD_CONTROL_SHA")
    _c5_require_sha(new_recovery_control_sha, "C5_MANIFEST_NEW_CONTROL_SHA")
    if not isinstance(manifest, dict):
        raise RecoveryError("C5_STRUCTURAL_MANIFEST_INVALID")
    expected_keys = {
        "applyable",
        "complete",
        "errored",
        "output_change_count",
        "plan_format_version",
        "resource_change_count",
        "resource_effects",
        "schema",
        "terraform_version",
    }
    if set(manifest) != expected_keys:
        raise RecoveryError("C5_STRUCTURAL_MANIFEST_KEYS_INVALID")
    expected_fixed = {
        "schema": "resilio-bootstrap-wif-repin-structural-manifest/v1",
        "terraform_version": "1.15.8",
        "plan_format_version": "1.2",
        "applyable": True,
        "complete": True,
        "errored": False,
        "output_change_count": 0,
        "resource_change_count": 1,
    }
    for key, value in expected_fixed.items():
        if manifest.get(key) != value:
            raise RecoveryError(f"C5_STRUCTURAL_MANIFEST_FIELD_MISMATCH:{key}")
    effects = manifest.get("resource_effects")
    if not isinstance(effects, list) or len(effects) != 1:
        raise RecoveryError("C5_STRUCTURAL_MANIFEST_EFFECT_CARDINALITY_INVALID")
    effect = effects[0]
    if not isinstance(effect, dict):
        raise RecoveryError("C5_STRUCTURAL_MANIFEST_EFFECT_INVALID")
    prefix = (
        "principalSet://iam.googleapis.com/projects/400271474382/locations/global/"
        "workloadIdentityPools/github/attribute.job_workflow_ref/8ft0-ai/resilio/"
        ".github/workflows/phase5-slice-c-recovery-reusable.yml@"
    )
    expected_effect = {
        "action_reason": "replace_because_cannot_update",
        "actions": ["delete", "create"],
        "address": "google_service_account_iam_member.github_phase5_slice_c_recovery",
        "after_member": prefix + new_recovery_control_sha,
        "after_role": "roles/iam.workloadIdentityUser",
        "after_service_account_id": (
            "projects/resilio-control-e882d4/serviceAccounts/"
            "github-p5-product-planner@resilio-control-e882d4.iam.gserviceaccount.com"
        ),
        "before_member": prefix + old_recovery_control_sha,
        "before_role": "roles/iam.workloadIdentityUser",
        "before_service_account_id": (
            "projects/resilio-control-e882d4/serviceAccounts/"
            "github-p5-product-planner@resilio-control-e882d4.iam.gserviceaccount.com"
        ),
        "mode": "managed",
        "name": "github_phase5_slice_c_recovery",
        "type": "google_service_account_iam_member",
    }
    if effect != expected_effect:
        raise RecoveryError("C5_STRUCTURAL_MANIFEST_EFFECT_MISMATCH")
    return {
        "schema": expected_fixed["schema"],
        "resource_change_count": 1,
        "output_change_count": 0,
        "effect_address": expected_effect["address"],
    }


def _c5_comment_by_id(
    comments: list[dict[str, Any]], comment_id: int, label: str
) -> dict[str, Any]:
    matches = [row for row in comments if row.get("id") == comment_id]
    if len(matches) != 1:
        raise RecoveryError(f"{label}_NOT_UNIQUE")
    return matches[0]


C5_ACTIONS_TERMINAL_STATUSES = frozenset(("completed",))


def c5_nonterminal_actions_snapshot() -> dict[str, Any]:
    """Enumerate every Actions page and bind the complete nonterminal set."""
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = github(f"/repos/{REPOSITORY}/actions/runs?per_page=100&page={page}")
        if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
            raise RecoveryError("C5_ACTIONS_RUN_SET_INVALID")
        batch = payload["workflow_runs"]
        for run in batch:
            if not isinstance(run, dict):
                raise RecoveryError("C5_ACTIONS_RUN_INVALID")
            status = str(run.get("status") or "")
            if status not in C5_ACTIONS_TERMINAL_STATUSES:
                run_id = run.get("id")
                if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
                    raise RecoveryError("C5_ACTIONS_NONTERMINAL_RUN_ID_INVALID")
                rows.append({"id": run_id, "status": status,
                    "event": str(run.get("event") or ""), "head_sha": str(run.get("head_sha") or ""),
                    "path": str(run.get("path") or "")})
        if len(batch) < 100:
            break
        page += 1
        if page > 1000:
            raise RecoveryError("C5_ACTIONS_PAGINATION_UNBOUNDED")
    rows.sort(key=lambda row: (row["id"], row["status"], row["event"], row["head_sha"], row["path"]))
    return {"count": len(rows), "digest_sha256": sha256(canonical(rows)), "runs": rows, "pages_scanned": page}


def _c5_validate_plan_review_and_authority(
    comments: list[dict[str, Any]],
    successor_control_sha: str,
    activation_main: str,
    plan_sha256: str,
    manifest_sha256: str,
    state_lineage: str,
    state_serial: int,
    fresh_review_comment_id: int,
    owner_apply_authority_comment_id: int,
) -> dict[str, Any]:
    review_comment = _c5_comment_by_id(
        comments, fresh_review_comment_id, "C5_WIF_REPIN_REVIEW"
    )
    review_created, review_hash = _require_unedited_owner_comment(
        review_comment, GOVERNING_ISSUE, "C5_WIF_REPIN_REVIEW"
    )
    expected_review = c5_wif_repin_review_body(
        successor_control_sha,
        activation_main,
        plan_sha256,
        manifest_sha256,
        state_lineage,
        state_serial,
    )
    if canonical_comment_text(review_comment.get("body")) != expected_review:
        raise RecoveryError("C5_WIF_REPIN_REVIEW_BODY_MISMATCH")

    authority_comment = _c5_comment_by_id(
        comments,
        owner_apply_authority_comment_id,
        "C5_WIF_REPIN_AUTHORITY",
    )
    authority_created, authority_hash = _require_unedited_owner_comment(
        authority_comment, GOVERNING_ISSUE, "C5_WIF_REPIN_AUTHORITY"
    )
    expected_authority = c5_wif_repin_authority_body(
        successor_control_sha,
        activation_main,
        plan_sha256,
        manifest_sha256,
        state_lineage,
        state_serial,
        fresh_review_comment_id,
        review_hash,
    )
    if canonical_comment_text(authority_comment.get("body")) != expected_authority:
        raise RecoveryError("C5_WIF_REPIN_AUTHORITY_BODY_MISMATCH")
    if review_created > authority_created:
        raise RecoveryError("C5_WIF_REPIN_REVIEW_AUTHORITY_TIMELINE_INVALID")
    return {
        "review_comment_id": fresh_review_comment_id,
        "review_body_sha256": review_hash,
        "review_created_at": review_created,
        "authority_comment_id": owner_apply_authority_comment_id,
        "authority_body_sha256": authority_hash,
        "authority_created_at": authority_created,
    }


def verify_c5_wif_repin_pre_effect(
    *,
    successor_control_sha: str,
    activation_main: str,
    saved_plan_path: str | Path,
    terraform_workdir: str | Path,
    structural_manifest_path: str | Path,
    fresh_review_comment_id: int,
    owner_apply_authority_comment_id: int,
    posted_claim_comment_id: int | None = None,
) -> dict[str, Any]:
    _c5_require_sha(successor_control_sha, "C5_PRE_EFFECT_SUCCESSOR_CONTROL_SHA")
    _c5_require_sha(activation_main, "C5_PRE_EFFECT_ACTIVATION_MAIN")
    _c5_positive(fresh_review_comment_id, "C5_PRE_EFFECT_REVIEW_ID")
    _c5_positive(owner_apply_authority_comment_id, "C5_PRE_EFFECT_AUTHORITY_ID")
    if posted_claim_comment_id is not None:
        _c5_positive(posted_claim_comment_id, "C5_PRE_EFFECT_CLAIM_ID")

    branch = github(f"/repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}")
    if (
        not isinstance(branch, dict)
        or branch.get("commit", {}).get("sha") != activation_main
    ):
        raise RecoveryError("C5_PRE_EFFECT_MAIN_MISMATCH")
    verify_c5_repository_activation(activation_main, successor_control_sha)

    comments = github_issue_comments(GOVERNING_ISSUE)
    governance = validate_c5_governance_history(comments)
    activation_record = validate_c5_activation_record(
        comments, successor_control_sha, activation_main
    )

    plan_bytes = Path(saved_plan_path).read_bytes()
    manifest_bytes = Path(structural_manifest_path).read_bytes()
    plan_sha = sha256(plan_bytes)
    manifest_sha = sha256(manifest_bytes)
    plan = _c5_saved_plan_json(saved_plan_path, terraform_workdir)
    plan_result = c5_verify_wif_repin_plan(
        plan, C5_OLD_RECOVERY_CONTROL_SHA, successor_control_sha
    )
    manifest = strict_json(manifest_bytes)
    c5_verify_structural_manifest(
        manifest, C5_OLD_RECOVERY_CONTROL_SHA, successor_control_sha
    )

    state = _successor_gcs_json(C5_BOOTSTRAP_STATE_OBJECT)
    live = verify_c5_bootstrap_state_and_live_iam(state, successor_control_sha)
    if _successor_gcs_metadata(C5_BOOTSTRAP_LOCK_OBJECT, True) is not None:
        raise RecoveryError("C5_PRE_EFFECT_BOOTSTRAP_LOCK_PRESENT")

    review_authority = _c5_validate_plan_review_and_authority(
        comments,
        successor_control_sha,
        activation_main,
        plan_sha,
        manifest_sha,
        live["state_lineage"],
        live["state_serial"],
        fresh_review_comment_id,
        owner_apply_authority_comment_id,
    )

    if not (
        activation_record["created_at"] < review_authority["review_created_at"]
        < review_authority["authority_created_at"]
    ):
        raise RecoveryError("C5_ACTIVATION_REVIEW_AUTHORITY_ORDER_INVALID")

    controls = (
        SUPERSEDED_CONTROL_SHA,
        FAILED_C3_CONTROL_SHA,
        C5_OLD_RECOVERY_CONTROL_SHA,
        successor_control_sha,
    )
    for control in controls:
        for kind in ("claim", "result"):
            if _successor_gcs_metadata(evidence_object(kind, control), True) is not None:
                raise RecoveryError(
                    f"C5_PRE_EFFECT_RECOVERY_{kind.upper()}_UNEXPECTED:{control}"
                )

    conflicts = c5_nonterminal_actions_snapshot()
    if conflicts["count"] != 0:
        raise RecoveryError("C5_PRE_EFFECT_ACTIVE_CONFLICTING_EXECUTIONS")

    snapshot = c5_precondition_snapshot(
        successor_control_sha,
        activation_main,
        plan_sha,
        manifest_sha,
        live["state_lineage"],
        live["state_serial"],
        fresh_review_comment_id,
        review_authority["review_body_sha256"],
        owner_apply_authority_comment_id,
        review_authority["authority_body_sha256"],
        C5_OLD_RECOVERY_CONTROL_SHA,
        successor_control_sha,
        conflicts["count"],
        conflicts["digest_sha256"],
    )
    precondition_digest = sha256(snapshot.encode("utf-8"))
    history = validate_c5_attempt_history(
        comments,
        successor_control_sha,
        activation_main,
        C5_OLD_RECOVERY_CONTROL_SHA,
        successor_control_sha,
    )

    if posted_claim_comment_id is None:
        generation = history["next_generation"]
        claim_body = c5_attempt_claim_body(
            successor_control_sha,
            activation_main,
            C5_OLD_RECOVERY_CONTROL_SHA,
            successor_control_sha,
            generation,
            plan_sha,
            manifest_sha,
            precondition_digest,
            fresh_review_comment_id,
            review_authority["review_body_sha256"],
            owner_apply_authority_comment_id,
            review_authority["authority_body_sha256"],
        )
        claim = None
        phase = "CLAIM_READY"
    else:
        claim = _c5_comment_by_id(
            comments, posted_claim_comment_id, "C5_POSTED_ATTEMPT_CLAIM"
        )
        parsed = _c5_parse_attempt_claim(claim)
        generations = [item["generation"] for item in history["claims"]]
        if not generations or parsed["generation"] != max(generations):
            raise RecoveryError("C5_POSTED_ATTEMPT_CLAIM_NOT_CURRENT_GENERATION")
        generation = parsed["generation"]
        claim_body = c5_attempt_claim_body(
            successor_control_sha,
            activation_main,
            C5_OLD_RECOVERY_CONTROL_SHA,
            successor_control_sha,
            generation,
            plan_sha,
            manifest_sha,
            precondition_digest,
            fresh_review_comment_id,
            review_authority["review_body_sha256"],
            owner_apply_authority_comment_id,
            review_authority["authority_body_sha256"],
        )
        validate_c5_posted_attempt_claim(
            claim,
            review_authority["authority_created_at"],
            claim_body,
        )
        phase = "EFFECT_READY"

    return {
        "contract": "resilio-phase5-slice-c-c5-wif-repin-pre-effect/v1",
        "phase": phase,
        "governing_issue": GOVERNING_ISSUE,
        "c5_architecture_comment_id": governance["architecture"]["comment_id"],
        "c5_architecture_review_comment_id": governance["architecture_review"][
            "comment_id"
        ],
        "owner_disposition_comment_id": governance["disposition"]["comment_id"],
        "retained_effect_baseline_comment_id": governance["retained_baseline"][
            "comment_id"
        ],
        "c5_control_record_comment_id": activation_record[
            "control_record_comment_id"
        ],
        "c5_control_record_body_sha256": activation_record[
            "control_record_body_sha256"
        ],
        "c5_activation_record_comment_id": activation_record["comment_id"],
        "c5_activation_record_body_sha256": activation_record["body_sha256"],
        "successor_control_sha": successor_control_sha,
        "activation_main": activation_main,
        "saved_plan_sha256": plan_sha,
        "structural_manifest_sha256": manifest_sha,
        "bootstrap_state_lineage": live["state_lineage"],
        "bootstrap_state_serial": live["state_serial"],
        "phase5_wif_state_resources": live["phase5_wif_state_resources"],
        "all_phase5_wif_live_matches": live["all_phase5_wif_live_matches"],
        "getmetadata_unchanged": live["getmetadata_unchanged"],
        "normal_phase5_identities_unchanged": live[
            "normal_phase5_identities_unchanged"
        ],
        "bootstrap_lock": "ABSENT",
        "active_conflicting_executions": 0,
        "plan_effects": plan_result["plan_effects"],
        "output_changes": plan_result["output_changes"],
        "fresh_review_comment_id": fresh_review_comment_id,
        "fresh_review_body_sha256": review_authority["review_body_sha256"],
        "owner_apply_authority_comment_id": owner_apply_authority_comment_id,
        "owner_apply_authority_body_sha256": review_authority[
            "authority_body_sha256"
        ],
        "precondition_snapshot": snapshot,
        "precondition_digest_sha256": precondition_digest,
        "attempt_series_id_sha256": history["attempt_series_id_sha256"],
        "attempt_generation": generation,
        "attempt_claim_body": claim_body,
        "posted_claim_comment_id": posted_claim_comment_id,
        "ready_for_effect": posted_claim_comment_id is not None,
    }


def execute_c5_wif_repin_effect(
    *,
    successor_control_sha: str,
    activation_main: str,
    saved_plan_path: str | Path,
    terraform_workdir: str | Path,
    structural_manifest_path: str | Path,
    fresh_review_comment_id: int,
    owner_apply_authority_comment_id: int,
    posted_claim_comment_id: int,
) -> dict[str, Any]:
    """Consume one posted claim through the only authorised locked apply path."""
    verification = verify_c5_wif_repin_pre_effect(
        successor_control_sha=successor_control_sha,
        activation_main=activation_main,
        saved_plan_path=saved_plan_path,
        terraform_workdir=terraform_workdir,
        structural_manifest_path=structural_manifest_path,
        fresh_review_comment_id=fresh_review_comment_id,
        owner_apply_authority_comment_id=owner_apply_authority_comment_id,
        posted_claim_comment_id=posted_claim_comment_id,
    )
    if (
        verification.get("phase") != "EFFECT_READY"
        or verification.get("ready_for_effect") is not True
        or verification.get("posted_claim_comment_id") != posted_claim_comment_id
    ):
        raise RecoveryError("C5_EFFECT_REVERIFY_NOT_EFFECT_READY")

    plan_path = Path(saved_plan_path).resolve()
    workdir = Path(terraform_workdir).resolve()
    if not plan_path.is_file():
        raise RecoveryError("C5_EFFECT_SAVED_PLAN_MISSING")
    if not workdir.is_dir():
        raise RecoveryError("C5_EFFECT_TERRAFORM_WORKDIR_MISSING")

    command = [
        "terraform",
        f"-chdir={workdir}",
        "apply",
        "-input=false",
        "-lock=true",
        str(plan_path),
    ]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RecoveryError("C5_EFFECT_APPLY_FAILED__OUTCOME_REQUIRES_OBSERVATION")

    return {
        "contract": "resilio-phase5-slice-c-c5-locked-effect/v1",
        "phase": "EFFECT_ATTEMPTED",
        "successor_control_sha": successor_control_sha,
        "activation_main": activation_main,
        "saved_plan_sha256": verification["saved_plan_sha256"],
        "attempt_series_id_sha256": verification["attempt_series_id_sha256"],
        "attempt_generation": verification["attempt_generation"],
        "posted_claim_comment_id": posted_claim_comment_id,
        "bootstrap_state_locking": "CANONICAL_TERRAFORM_LOCK_TRUE",
        "observation_required": True,
    }


C5_CONTROL_ALLOWED_FILES = (
    "scripts/phase5_slice_c_recovery.py",
    "scripts/validate_phase5_slice_c_recovery.py",
    "tests/test_phase5_slice_c_recovery.py",
)
C5_ACTIVATION_ALLOWED_FILES = (
    ".github/workflows/phase5-slice-c-recovery.yml",
    "infra/bootstrap/phase5_authority.tf",
)


def _c5_review_field_map(
    body: str, header: str, names: tuple[str, ...], label: str
) -> dict[str, str]:
    lines = canonical_comment_text(body).split("\n")
    if not lines or lines[0] != header:
        raise RecoveryError(f"{label}_HEADER_INVALID")
    values: dict[str, list[str]] = {name: [] for name in names}
    for line in lines[1:]:
        for name in names:
            prefix = name + "="
            if line.startswith(prefix):
                values[name].append(line[len(prefix) :].strip())
    if any(len(values[name]) != 1 for name in names):
        raise RecoveryError(f"{label}_FIELDS_NOT_EXACT")
    return {name: values[name][0] for name in names}


def verify_c5_control_use_time_currentness(successor_control_sha: str, expected_main: str) -> dict[str, Any]:
    _c5_require_sha(successor_control_sha, "C5_CONTROL_CURRENTNESS_SUCCESSOR")
    _c5_require_sha(expected_main, "C5_CONTROL_CURRENTNESS_MAIN")
    branch = github(f"/repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}")
    if not isinstance(branch, dict) or branch.get("commit", {}).get("sha") != expected_main:
        raise RecoveryError("C5_CONTROL_CURRENTNESS_MAIN_MISMATCH")
    caller = _c5_fetch_repo_text(
        ".github/workflows/phase5-slice-c-recovery.yml", expected_main
    )
    authority = _c5_fetch_repo_text(
        "infra/bootstrap/phase5_authority.tf", expected_main
    )
    expected_caller = (
        "uses: 8ft0-ai/resilio/.github/workflows/"
        f"phase5-slice-c-recovery-reusable.yml@{C5_OLD_RECOVERY_CONTROL_SHA}"
    )
    expected_desired = (
        'phase5_slice_c_recovery_workflow_ref = "8ft0-ai/resilio/.github/workflows/'
        f'phase5-slice-c-recovery-reusable.yml@{C5_OLD_RECOVERY_CONTROL_SHA}"'
    )
    if caller.count(expected_caller) != 1:
        raise RecoveryError("C5_CONTROL_CURRENTNESS_CALLER_NOT_C4")
    if authority.count(expected_desired) != 1:
        raise RecoveryError("C5_CONTROL_CURRENTNESS_DESIRED_WIF_NOT_C4")
    state = _successor_gcs_json(C5_BOOTSTRAP_STATE_OBJECT)
    live = verify_c5_bootstrap_state_and_live_iam(state, successor_control_sha)
    if _successor_gcs_metadata(C5_BOOTSTRAP_LOCK_OBJECT, True) is not None:
        raise RecoveryError("C5_CONTROL_CURRENTNESS_BOOTSTRAP_LOCK_PRESENT")
    for control in (SUPERSEDED_CONTROL_SHA, FAILED_C3_CONTROL_SHA, C5_OLD_RECOVERY_CONTROL_SHA, successor_control_sha):
        for kind in ("claim", "result"):
            if _successor_gcs_metadata(evidence_object(kind, control), True) is not None:
                raise RecoveryError(f"C5_CONTROL_CURRENTNESS_{kind.upper()}_UNEXPECTED:{control}")
    conflicts = c5_nonterminal_actions_snapshot()
    if conflicts["count"] != 0:
        raise RecoveryError("C5_CONTROL_CURRENTNESS_NONTERMINAL_ACTIONS")
    snapshot = {"contract": "resilio-phase5-slice-c-c5-control-currentness/v1",
        "c5_protocol_epoch_sha256": C5_PROTOCOL_EPOCH_SHA256, "current_main": expected_main,
        "repository_caller_sha": C5_OLD_RECOVERY_CONTROL_SHA,
        "repository_desired_wif_sha": C5_OLD_RECOVERY_CONTROL_SHA,
        "live_recovery_wif": live["live_recovery_wif"], "state_lineage": live["state_lineage"],
        "state_serial": live["state_serial"], "phase5_wif_state_resources": live["phase5_wif_state_resources"],
        "getmetadata_unchanged": live["getmetadata_unchanged"],
        "normal_phase5_identities_unchanged": live["normal_phase5_identities_unchanged"],
        "claim_result_namespaces": "ABSENT", "bootstrap_lock": "ABSENT",
        "nonterminal_actions_count": conflicts["count"],
        "nonterminal_actions_digest_sha256": conflicts["digest_sha256"]}
    snapshot["currentness_digest_sha256"] = sha256(canonical(snapshot))
    return snapshot


def c5_control_implementation_review_body(
    pr_number: int, reviewed_head: str
) -> str:
    _c5_positive(pr_number, "C5_CONTROL_REVIEW_PR")
    _c5_require_sha(reviewed_head, "C5_CONTROL_REVIEW_HEAD")
    return "\n".join(
        (
            "COMPLETELY_FRESH_SUBSTANTIVE_C5_IMPLEMENTATION_SECURITY_AUTHORITY_REVIEW",
            "DISPOSITION=APPROVED",
            f"PR=8ft0-ai/resilio#{pr_number}",
            f"EXACT_HEAD={reviewed_head}",
            f"EXACT_BASE={C5_BASE_MAIN}",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"C5_ARCHITECTURE={C5_ARCHITECTURE_COMMENT_ID}",
            f"OWNER_DISPOSITION={C5_OWNER_DISPOSITION_COMMENT_ID}",
            f"RETAINED_EFFECT_BASELINE={C5_RETAINED_BASELINE_COMMENT_ID}",
            "C5_CONTROL_SCOPE=RECOVERY_HELPER_VALIDATOR_TESTS_ONLY",
            "CALLER_REMAINS=C4",
            "DESIRED_WIF_REMAINS=C4",
            "LIVE_WIF_REMAINS=C4",
            "CLOUD_EFFECT=NONE",
            "MATERIAL_BLOCKERS=NONE",
        )
    )


def c5_control_merge_authority_body(
    pr_number: int,
    reviewed_head: str,
    review_id: int,
    review_body_sha256: str,
) -> str:
    c5_control_implementation_review_body(pr_number, reviewed_head)
    _c5_positive(review_id, "C5_CONTROL_REVIEW_ID")
    _c5_require_hash(review_body_sha256, "C5_CONTROL_REVIEW_BODY_SHA256")
    return "\n".join(
        (
            "PHASE5_SLICE_C_C5_CONTROL_MERGE_AUTHORITY_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"C5_ARCHITECTURE={C5_ARCHITECTURE_COMMENT_ID}",
            f"OWNER_DISPOSITION={C5_OWNER_DISPOSITION_COMMENT_ID}",
            f"RETAINED_EFFECT_BASELINE={C5_RETAINED_BASELINE_COMMENT_ID}",
            f"C5_CONTROL_PR={pr_number}",
            f"C5_CONTROL_REVIEWED_HEAD={reviewed_head}",
            f"C5_CONTROL_BASE={C5_BASE_MAIN}",
            f"C5_FRESH_REVIEW_ID={review_id}",
            f"C5_FRESH_REVIEW_BODY_SHA256={review_body_sha256}",
            "AUTHORITY=MERGE_EXACT_REVIEWED_C5_INERT_CONTROL_ONLY",
            "CALLER_PIN_CHANGE=FORBIDDEN",
            "DESIRED_WIF_CHANGE=FORBIDDEN",
            "CLOUD_EFFECT=FORBIDDEN",
        )
    )


def _c5_validate_pr_files(
    files: Any, expected: tuple[str, ...], label: str
) -> None:
    if not isinstance(files, list):
        raise RecoveryError(f"{label}_FILES_INVALID")
    observed = tuple(sorted(str(row.get("filename") or "") for row in files))
    if observed != tuple(sorted(expected)):
        raise RecoveryError(f"{label}_FILE_SET_MISMATCH")


def verify_c5_control_premerge(
    pr_number: int,
    reviewed_head: str,
    review_id: int,
    review_body_sha256: str,
    authority_id: int,
) -> dict[str, Any]:
    _c5_positive(pr_number, "C5_CONTROL_PREMERGE_PR")
    _c5_require_sha(reviewed_head, "C5_CONTROL_PREMERGE_HEAD")
    _c5_positive(review_id, "C5_CONTROL_PREMERGE_REVIEW_ID")
    _c5_require_hash(
        review_body_sha256, "C5_CONTROL_PREMERGE_REVIEW_BODY_SHA256"
    )
    _c5_positive(authority_id, "C5_CONTROL_PREMERGE_AUTHORITY_ID")

    branch = github(f"/repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}")
    if (
        not isinstance(branch, dict)
        or branch.get("commit", {}).get("sha") != C5_BASE_MAIN
    ):
        raise RecoveryError("C5_CONTROL_PREMERGE_MAIN_MISMATCH")
    pr = github(f"/repos/{REPOSITORY}/pulls/{pr_number}")
    if (
        not isinstance(pr, dict)
        or pr.get("number") != pr_number
        or pr.get("state") != "open"
        or pr.get("merged_at") is not None
        or pr.get("draft") is True
    ):
        raise RecoveryError("C5_CONTROL_PREMERGE_PR_INVALID")
    if pr.get("head", {}).get("sha") != reviewed_head:
        raise RecoveryError("C5_CONTROL_PREMERGE_HEAD_MISMATCH")
    if (
        pr.get("base", {}).get("ref") != DEFAULT_BRANCH
        or pr.get("base", {}).get("sha") != C5_BASE_MAIN
    ):
        raise RecoveryError("C5_CONTROL_PREMERGE_BASE_MISMATCH")
    head_repo = pr.get("head", {}).get("repo") or {}
    if (
        head_repo.get("id") != REPOSITORY_ID
        or head_repo.get("full_name") != REPOSITORY
    ):
        raise RecoveryError("C5_CONTROL_PREMERGE_REPOSITORY_MISMATCH")
    files = github(f"/repos/{REPOSITORY}/pulls/{pr_number}/files?per_page=100")
    _c5_validate_pr_files(files, C5_CONTROL_ALLOWED_FILES, "C5_CONTROL_PREMERGE")
    currentness = verify_c5_control_use_time_currentness(reviewed_head, C5_BASE_MAIN)

    review = github(f"/repos/{REPOSITORY}/pulls/{pr_number}/reviews/{review_id}")
    if (
        not isinstance(review, dict)
        or review.get("id") != review_id
        or review.get("state") != "COMMENTED"
        or review.get("commit_id") != reviewed_head
    ):
        raise RecoveryError("C5_CONTROL_PREMERGE_REVIEW_IDENTITY_MISMATCH")
    review_user = review.get("user") or {}
    if (
        review_user.get("login") != OWNER_LOGIN
        or review_user.get("id") != OWNER_ID
    ):
        raise RecoveryError("C5_CONTROL_PREMERGE_REVIEW_OWNER_MISMATCH")
    expected_review = c5_control_implementation_review_body(
        pr_number, reviewed_head
    )
    if canonical_comment_text(review.get("body")) != expected_review:
        raise RecoveryError("C5_CONTROL_PREMERGE_REVIEW_BODY_MISMATCH")
    actual_review_sha = sha256(str(review.get("body") or "").encode("utf-8"))
    if actual_review_sha != review_body_sha256:
        raise RecoveryError("C5_CONTROL_PREMERGE_REVIEW_HASH_MISMATCH")

    authority = github(f"/repos/{REPOSITORY}/issues/comments/{authority_id}")
    authority_created, authority_sha = _require_unedited_owner_comment(
        authority, pr_number, "C5_CONTROL_PREMERGE_AUTHORITY"
    )
    expected_authority = c5_control_merge_authority_body(
        pr_number, reviewed_head, review_id, review_body_sha256
    )
    if canonical_comment_text(authority.get("body")) != expected_authority:
        raise RecoveryError("C5_CONTROL_PREMERGE_AUTHORITY_BODY_MISMATCH")
    review_time = _timestamp(
        review.get("submitted_at"), "C5_CONTROL_PREMERGE_REVIEW_SUBMITTED"
    )
    if review_time > authority_created:
        raise RecoveryError("C5_CONTROL_PREMERGE_TIMELINE_INVALID")
    return {
        "contract": "resilio-phase5-slice-c-c5-control-premerge/v1",
        "pr_number": pr_number,
        "reviewed_head": reviewed_head,
        "base": C5_BASE_MAIN,
        "review_id": review_id,
        "review_body_sha256": actual_review_sha,
        "authority_id": authority_id,
        "authority_body_sha256": authority_sha,
        "authority_created_at": authority_created,
        "c5_protocol_epoch_sha256": C5_PROTOCOL_EPOCH_SHA256,
        "currentness_digest_sha256": currentness["currentness_digest_sha256"],
        "verified": True,
    }


def c5_control_merge_record_body(
    control_sha: str,
    pr_number: int,
    reviewed_head: str,
    reviewed_tree: str,
    review_id: int,
    review_body_sha256: str,
    authority_id: int,
    authority_body_sha256: str,
    currentness_digest_sha256: str,
) -> str:
    _c5_require_sha(control_sha, "C5_CONTROL_SHA")
    _c5_positive(pr_number, "C5_CONTROL_RECORD_PR")
    _c5_require_sha(reviewed_head, "C5_CONTROL_RECORD_REVIEWED_HEAD")
    _c5_require_sha(reviewed_tree, "C5_CONTROL_RECORD_REVIEWED_TREE")
    _c5_positive(review_id, "C5_CONTROL_RECORD_REVIEW_ID")
    _c5_require_hash(
        review_body_sha256, "C5_CONTROL_RECORD_REVIEW_BODY_SHA256"
    )
    _c5_positive(authority_id, "C5_CONTROL_RECORD_AUTHORITY_ID")
    _c5_require_hash(
        authority_body_sha256, "C5_CONTROL_RECORD_AUTHORITY_BODY_SHA256"
    )
    _c5_require_hash(
        currentness_digest_sha256, "C5_CONTROL_RECORD_CURRENTNESS_DIGEST_SHA256"
    )
    return "\n".join(
        (
            "PHASE5_SLICE_C_C5_CONTROL_MERGE_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"C5_ARCHITECTURE={C5_ARCHITECTURE_COMMENT_ID}",
            f"OWNER_DISPOSITION={C5_OWNER_DISPOSITION_COMMENT_ID}",
            f"RETAINED_EFFECT_BASELINE={C5_RETAINED_BASELINE_COMMENT_ID}",
            f"C5_CONTROL_PR={pr_number}",
            f"C5_CONTROL_REVIEWED_HEAD={reviewed_head}",
            f"C5_CONTROL_REVIEWED_TREE={reviewed_tree}",
            f"C5_CONTROL_BASE={C5_BASE_MAIN}",
            f"C5_CONTROL_MERGE={control_sha}",
            f"C5_FRESH_REVIEW_ID={review_id}",
            f"C5_FRESH_REVIEW_BODY_SHA256={review_body_sha256}",
            f"C5_OWNER_MERGE_AUTHORITY_COMMENT_ID={authority_id}",
            f"C5_OWNER_MERGE_AUTHORITY_BODY_SHA256={authority_body_sha256}",
            f"C5_CONTROL_CURRENTNESS_DIGEST_SHA256={currentness_digest_sha256}",
            f"C5_CONTROL_CURRENTNESS_EXPECTED_MAIN={control_sha}",
            "C5_CONTROL_CURRENTNESS_CAPTURE=FRESH_POST_MERGE",
            "MERGED_TREE_EQUALS_REVIEWED_TREE=TRUE",
            "CALLER_REMAINS=C4",
            "DESIRED_WIF_REMAINS=C4",
            "LIVE_WIF_REMAINS=C4",
            "CLOUD_EFFECT=NONE",
            "STATUS=C5_INERT_CONTROL_MERGED_EXACT",
        )
    )


C5_CONTROL_RECORD_FIELDS = (
    "GOVERNING_ISSUE",
    "C5_PROTOCOL_EPOCH_SHA256",
    "C5_ARCHITECTURE",
    "OWNER_DISPOSITION",
    "RETAINED_EFFECT_BASELINE",
    "C5_CONTROL_PR",
    "C5_CONTROL_REVIEWED_HEAD",
    "C5_CONTROL_REVIEWED_TREE",
    "C5_CONTROL_BASE",
    "C5_CONTROL_MERGE",
    "C5_FRESH_REVIEW_ID",
    "C5_FRESH_REVIEW_BODY_SHA256",
    "C5_OWNER_MERGE_AUTHORITY_COMMENT_ID",
    "C5_OWNER_MERGE_AUTHORITY_BODY_SHA256",
    "C5_CONTROL_CURRENTNESS_DIGEST_SHA256",
    "C5_CONTROL_CURRENTNESS_EXPECTED_MAIN",
    "C5_CONTROL_CURRENTNESS_CAPTURE",
    "MERGED_TREE_EQUALS_REVIEWED_TREE",
    "CALLER_REMAINS",
    "DESIRED_WIF_REMAINS",
    "LIVE_WIF_REMAINS",
    "CLOUD_EFFECT",
    "STATUS",
)


def validate_c5_control_merge_record(
    comments: list[dict[str, Any]], control_sha: str
) -> dict[str, Any]:
    _c5_require_sha(control_sha, "C5_CONTROL_RECORD_CONTROL_SHA")
    candidates = [
        comment
        for comment in comments
        if _owner_issue_comment(comment, GOVERNING_ISSUE)
        and canonical_comment_text(comment.get("body")).startswith(
            "PHASE5_SLICE_C_C5_CONTROL_MERGE_V1\n"
        )
        and f"C5_CONTROL_MERGE={control_sha}" in canonical_comment_text(
            comment.get("body")
        )
    ]
    if len(candidates) != 1:
        raise RecoveryError("C5_CONTROL_RECORD_NOT_UNIQUE")
    comment = candidates[0]
    created, body_sha = _require_unedited_owner_comment(
        comment, GOVERNING_ISSUE, "C5_CONTROL_RECORD"
    )
    fields = _record_fields(
        str(comment.get("body") or ""),
        "PHASE5_SLICE_C_C5_CONTROL_MERGE_V1",
        C5_CONTROL_RECORD_FIELDS,
    )
    expected = {
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "C5_PROTOCOL_EPOCH_SHA256": C5_PROTOCOL_EPOCH_SHA256,
        "C5_ARCHITECTURE": str(C5_ARCHITECTURE_COMMENT_ID),
        "OWNER_DISPOSITION": str(C5_OWNER_DISPOSITION_COMMENT_ID),
        "RETAINED_EFFECT_BASELINE": str(C5_RETAINED_BASELINE_COMMENT_ID),
        "C5_CONTROL_BASE": C5_BASE_MAIN,
        "C5_CONTROL_MERGE": control_sha,
        "C5_CONTROL_CURRENTNESS_EXPECTED_MAIN": control_sha,
        "C5_CONTROL_CURRENTNESS_CAPTURE": "FRESH_POST_MERGE",
        "MERGED_TREE_EQUALS_REVIEWED_TREE": "TRUE",
        "CALLER_REMAINS": "C4",
        "DESIRED_WIF_REMAINS": "C4",
        "LIVE_WIF_REMAINS": "C4",
        "CLOUD_EFFECT": "NONE",
        "STATUS": "C5_INERT_CONTROL_MERGED_EXACT",
    }
    for key, value in expected.items():
        if fields[key] != value:
            raise RecoveryError(f"C5_CONTROL_RECORD_FIELD_MISMATCH:{key}")
    pr_number = _positive_int(fields["C5_CONTROL_PR"], "C5_CONTROL_RECORD_PR")
    review_id = _positive_int(
        fields["C5_FRESH_REVIEW_ID"], "C5_CONTROL_RECORD_REVIEW_ID"
    )
    authority_id = _positive_int(
        fields["C5_OWNER_MERGE_AUTHORITY_COMMENT_ID"],
        "C5_CONTROL_RECORD_AUTHORITY_ID",
    )
    reviewed_head = _c5_require_sha(
        fields["C5_CONTROL_REVIEWED_HEAD"], "C5_CONTROL_RECORD_REVIEWED_HEAD"
    )
    reviewed_tree = _c5_require_sha(
        fields["C5_CONTROL_REVIEWED_TREE"], "C5_CONTROL_RECORD_REVIEWED_TREE"
    )
    review_hash = _c5_require_hash(
        fields["C5_FRESH_REVIEW_BODY_SHA256"],
        "C5_CONTROL_RECORD_REVIEW_BODY_SHA256",
    )
    authority_hash = _c5_require_hash(
        fields["C5_OWNER_MERGE_AUTHORITY_BODY_SHA256"],
        "C5_CONTROL_RECORD_AUTHORITY_BODY_SHA256",
    )
    currentness_hash = _c5_require_hash(
        fields["C5_CONTROL_CURRENTNESS_DIGEST_SHA256"],
        "C5_CONTROL_RECORD_CURRENTNESS_DIGEST_SHA256",
    )

    pr = github(f"/repos/{REPOSITORY}/pulls/{pr_number}")
    if (
        not isinstance(pr, dict)
        or pr.get("state") != "closed"
        or pr.get("merged_at") is None
        or pr.get("merge_commit_sha") != control_sha
        or pr.get("head", {}).get("sha") != reviewed_head
        or pr.get("base", {}).get("sha") != C5_BASE_MAIN
        or pr.get("base", {}).get("ref") != DEFAULT_BRANCH
    ):
        raise RecoveryError("C5_CONTROL_RECORD_PR_MISMATCH")
    files = github(f"/repos/{REPOSITORY}/pulls/{pr_number}/files?per_page=100")
    _c5_validate_pr_files(files, C5_CONTROL_ALLOWED_FILES, "C5_CONTROL_RECORD")
    reviewed_commit = github(f"/repos/{REPOSITORY}/commits/{reviewed_head}")
    merge_commit = github(f"/repos/{REPOSITORY}/commits/{control_sha}")
    if (
        (reviewed_commit.get("commit") or {}).get("tree", {}).get("sha")
        != reviewed_tree
        or (merge_commit.get("commit") or {}).get("tree", {}).get("sha")
        != reviewed_tree
    ):
        raise RecoveryError("C5_CONTROL_RECORD_TREE_MISMATCH")
    review = github(f"/repos/{REPOSITORY}/pulls/{pr_number}/reviews/{review_id}")
    expected_review = c5_control_implementation_review_body(
        pr_number, reviewed_head
    )
    if (
        not isinstance(review, dict)
        or review.get("id") != review_id
        or review.get("state") != "COMMENTED"
        or review.get("commit_id") != reviewed_head
        or canonical_comment_text(review.get("body")) != expected_review
        or sha256(str(review.get("body") or "").encode("utf-8")) != review_hash
    ):
        raise RecoveryError("C5_CONTROL_RECORD_REVIEW_MISMATCH")
    review_user = review.get("user") or {}
    if (
        review_user.get("login") != OWNER_LOGIN
        or review_user.get("id") != OWNER_ID
    ):
        raise RecoveryError("C5_CONTROL_RECORD_REVIEW_OWNER_MISMATCH")
    authority = github(f"/repos/{REPOSITORY}/issues/comments/{authority_id}")
    authority_created, observed_authority_hash = _require_unedited_owner_comment(
        authority, pr_number, "C5_CONTROL_RECORD_AUTHORITY"
    )
    if observed_authority_hash != authority_hash:
        raise RecoveryError("C5_CONTROL_RECORD_AUTHORITY_HASH_MISMATCH")
    if canonical_comment_text(authority.get("body")) != c5_control_merge_authority_body(
        pr_number, reviewed_head, review_id, review_hash
    ):
        raise RecoveryError("C5_CONTROL_RECORD_AUTHORITY_BODY_MISMATCH")
    review_time = _timestamp(
        review.get("submitted_at"), "C5_CONTROL_RECORD_REVIEW_SUBMITTED"
    )
    merge_time = _timestamp(pr.get("merged_at"), "C5_CONTROL_RECORD_MERGED")
    if not (review_time <= authority_created < merge_time <= created):
        raise RecoveryError("C5_CONTROL_RECORD_TIMELINE_INVALID")
    return {
        "comment_id": int(comment["id"]),
        "created_at": created,
        "body_sha256": body_sha,
        "control_sha": control_sha,
        "pr_number": pr_number,
        "reviewed_head": reviewed_head,
        "reviewed_tree": reviewed_tree,
        "review_id": review_id,
        "review_body_sha256": review_hash,
        "authority_id": authority_id,
        "authority_body_sha256": authority_hash,
        "currentness_digest_sha256": currentness_hash,
    }


def c5_activation_review_body(
    control_sha: str, pr_number: int, reviewed_head: str
) -> str:
    _c5_require_sha(control_sha, "C5_ACTIVATION_REVIEW_CONTROL_SHA")
    if control_sha in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS or (
        control_sha == C5_OLD_RECOVERY_CONTROL_SHA
    ):
        raise RecoveryError("C5_ACTIVATION_REVIEW_CONTROL_FORBIDDEN")
    _c5_positive(pr_number, "C5_ACTIVATION_REVIEW_PR")
    _c5_require_sha(reviewed_head, "C5_ACTIVATION_REVIEW_HEAD")
    return "\n".join(
        (
            "COMPLETELY_FRESH_SUBSTANTIVE_C5_ACTIVATION_SECURITY_AUTHORITY_REVIEW",
            "DISPOSITION=APPROVED",
            f"PR=8ft0-ai/resilio#{pr_number}",
            f"EXACT_HEAD={reviewed_head}",
            f"EXACT_BASE={control_sha}",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"C5_ARCHITECTURE={C5_ARCHITECTURE_COMMENT_ID}",
            f"C5_CONTROL_SHA={control_sha}",
            "ACTIVATION_EFFECT=REPOSITORY_CALLER_AND_DESIRED_WIF_C4_TO_C5_ONLY",
            "LIVE_WIF_EFFECT=NONE",
            "CLOUD_EFFECT=NONE",
            "MATERIAL_BLOCKERS=NONE",
        )
    )


def c5_activation_merge_authority_body(
    control_sha: str,
    pr_number: int,
    reviewed_head: str,
    review_id: int,
    review_body_sha256: str,
) -> str:
    c5_activation_review_body(control_sha, pr_number, reviewed_head)
    _c5_positive(review_id, "C5_ACTIVATION_REVIEW_ID")
    _c5_require_hash(review_body_sha256, "C5_ACTIVATION_REVIEW_BODY_SHA256")
    return "\n".join(
        (
            "PHASE5_SLICE_C_C5_ACTIVATION_MERGE_AUTHORITY_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"C5_ARCHITECTURE={C5_ARCHITECTURE_COMMENT_ID}",
            f"C5_CONTROL_SHA={control_sha}",
            f"C5_ACTIVATION_PR={pr_number}",
            f"C5_ACTIVATION_REVIEWED_HEAD={reviewed_head}",
            f"C5_ACTIVATION_BASE={control_sha}",
            f"C5_FRESH_REVIEW_ID={review_id}",
            f"C5_FRESH_REVIEW_BODY_SHA256={review_body_sha256}",
            "AUTHORITY=MERGE_EXACT_REVIEWED_C5_REPOSITORY_ACTIVATION_ONLY",
            "LIVE_WIF_EFFECT=FORBIDDEN",
            "CLOUD_EFFECT=FORBIDDEN",
        )
    )


def _c5_verify_activation_file_transform(
    control_sha: str, reviewed_head: str
) -> None:
    for path in C5_ACTIVATION_ALLOWED_FILES:
        before = _c5_fetch_repo_text(path, control_sha)
        after = _c5_fetch_repo_text(path, reviewed_head)
        count = before.count(C5_OLD_RECOVERY_CONTROL_SHA)
        if count != 1:
            raise RecoveryError(f"C5_ACTIVATION_BASE_PIN_COUNT_INVALID:{path}")
        expected = before.replace(
            C5_OLD_RECOVERY_CONTROL_SHA, control_sha, 1
        )
        if after != expected:
            raise RecoveryError(f"C5_ACTIVATION_FILE_TRANSFORM_INVALID:{path}")


def verify_c5_activation_premerge(
    control_sha: str,
    pr_number: int,
    reviewed_head: str,
    review_id: int,
    review_body_sha256: str,
    authority_id: int,
) -> dict[str, Any]:
    _c5_require_sha(control_sha, "C5_ACTIVATION_PREMERGE_CONTROL_SHA")
    _c5_positive(pr_number, "C5_ACTIVATION_PREMERGE_PR")
    _c5_require_sha(reviewed_head, "C5_ACTIVATION_PREMERGE_HEAD")
    _c5_positive(review_id, "C5_ACTIVATION_PREMERGE_REVIEW_ID")
    _c5_require_hash(
        review_body_sha256, "C5_ACTIVATION_PREMERGE_REVIEW_BODY_SHA256"
    )
    _c5_positive(authority_id, "C5_ACTIVATION_PREMERGE_AUTHORITY_ID")
    if control_sha in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS or (
        control_sha == C5_OLD_RECOVERY_CONTROL_SHA
    ):
        raise RecoveryError("C5_ACTIVATION_PREMERGE_CONTROL_FORBIDDEN")

    comments = github_issue_comments(GOVERNING_ISSUE)
    validate_c5_control_merge_record(comments, control_sha)
    branch = github(f"/repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}")
    if (
        not isinstance(branch, dict)
        or branch.get("commit", {}).get("sha") != control_sha
    ):
        raise RecoveryError("C5_ACTIVATION_PREMERGE_MAIN_MISMATCH")
    pr = github(f"/repos/{REPOSITORY}/pulls/{pr_number}")
    if (
        not isinstance(pr, dict)
        or pr.get("number") != pr_number
        or pr.get("state") != "open"
        or pr.get("merged_at") is not None
        or pr.get("draft") is True
        or pr.get("head", {}).get("sha") != reviewed_head
        or pr.get("base", {}).get("sha") != control_sha
        or pr.get("base", {}).get("ref") != DEFAULT_BRANCH
    ):
        raise RecoveryError("C5_ACTIVATION_PREMERGE_PR_INVALID")
    files = github(f"/repos/{REPOSITORY}/pulls/{pr_number}/files?per_page=100")
    _c5_validate_pr_files(files, C5_ACTIVATION_ALLOWED_FILES, "C5_ACTIVATION")
    _c5_verify_activation_file_transform(control_sha, reviewed_head)

    review = github(f"/repos/{REPOSITORY}/pulls/{pr_number}/reviews/{review_id}")
    expected_review = c5_activation_review_body(
        control_sha, pr_number, reviewed_head
    )
    if (
        not isinstance(review, dict)
        or review.get("id") != review_id
        or review.get("state") != "COMMENTED"
        or review.get("commit_id") != reviewed_head
        or canonical_comment_text(review.get("body")) != expected_review
    ):
        raise RecoveryError("C5_ACTIVATION_PREMERGE_REVIEW_MISMATCH")
    review_user = review.get("user") or {}
    if (
        review_user.get("login") != OWNER_LOGIN
        or review_user.get("id") != OWNER_ID
    ):
        raise RecoveryError("C5_ACTIVATION_PREMERGE_REVIEW_OWNER_MISMATCH")
    actual_review_sha = sha256(str(review.get("body") or "").encode("utf-8"))
    if actual_review_sha != review_body_sha256:
        raise RecoveryError("C5_ACTIVATION_PREMERGE_REVIEW_HASH_MISMATCH")
    authority = github(f"/repos/{REPOSITORY}/issues/comments/{authority_id}")
    authority_created, authority_hash = _require_unedited_owner_comment(
        authority, pr_number, "C5_ACTIVATION_PREMERGE_AUTHORITY"
    )
    if canonical_comment_text(authority.get("body")) != c5_activation_merge_authority_body(
        control_sha, pr_number, reviewed_head, review_id, review_body_sha256
    ):
        raise RecoveryError("C5_ACTIVATION_PREMERGE_AUTHORITY_BODY_MISMATCH")
    review_time = _timestamp(
        review.get("submitted_at"), "C5_ACTIVATION_PREMERGE_REVIEW_SUBMITTED"
    )
    if review_time > authority_created:
        raise RecoveryError("C5_ACTIVATION_PREMERGE_TIMELINE_INVALID")
    return {
        "contract": "resilio-phase5-slice-c-c5-activation-premerge/v1",
        "control_sha": control_sha,
        "pr_number": pr_number,
        "reviewed_head": reviewed_head,
        "review_id": review_id,
        "review_body_sha256": actual_review_sha,
        "authority_id": authority_id,
        "authority_body_sha256": authority_hash,
        "verified": True,
    }


def c5_activation_record_body(
    control_sha: str,
    activation_main: str,
    pr_number: int,
    reviewed_head: str,
    reviewed_tree: str,
    review_id: int,
    review_body_sha256: str,
    authority_id: int,
    authority_body_sha256: str,
) -> str:
    _c5_require_sha(control_sha, "C5_ACTIVATION_RECORD_CONTROL_SHA")
    _c5_require_sha(activation_main, "C5_ACTIVATION_RECORD_MAIN")
    _c5_positive(pr_number, "C5_ACTIVATION_RECORD_PR")
    _c5_require_sha(reviewed_head, "C5_ACTIVATION_RECORD_HEAD")
    _c5_require_sha(reviewed_tree, "C5_ACTIVATION_RECORD_TREE")
    _c5_positive(review_id, "C5_ACTIVATION_RECORD_REVIEW_ID")
    _c5_require_hash(
        review_body_sha256, "C5_ACTIVATION_RECORD_REVIEW_BODY_SHA256"
    )
    _c5_positive(authority_id, "C5_ACTIVATION_RECORD_AUTHORITY_ID")
    _c5_require_hash(
        authority_body_sha256, "C5_ACTIVATION_RECORD_AUTHORITY_BODY_SHA256"
    )
    return "\n".join(
        (
            "PHASE5_SLICE_C_C5_ACTIVATION_V1",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"C5_ARCHITECTURE={C5_ARCHITECTURE_COMMENT_ID}",
            f"C5_CONTROL_SHA={control_sha}",
            f"C5_ACTIVATION_PR={pr_number}",
            f"C5_ACTIVATION_REVIEWED_HEAD={reviewed_head}",
            f"C5_ACTIVATION_REVIEWED_TREE={reviewed_tree}",
            f"C5_ACTIVATION_BASE={control_sha}",
            f"C5_ACTIVATION_MAIN={activation_main}",
            f"C5_FRESH_REVIEW_ID={review_id}",
            f"C5_FRESH_REVIEW_BODY_SHA256={review_body_sha256}",
            f"C5_OWNER_MERGE_AUTHORITY_COMMENT_ID={authority_id}",
            f"C5_OWNER_MERGE_AUTHORITY_BODY_SHA256={authority_body_sha256}",
            "MERGED_TREE_EQUALS_REVIEWED_TREE=TRUE",
            "REPOSITORY_CALLER=C5",
            "REPOSITORY_DESIRED_WIF=C5",
            "LIVE_WIF=C4_ONLY",
            "CLOUD_EFFECT=NONE",
            "STATUS=C5_REPOSITORY_ACTIVATION_MERGED_EXACT",
        )
    )


C5_ACTIVATION_RECORD_FIELDS = (
    "GOVERNING_ISSUE",
    "C5_PROTOCOL_EPOCH_SHA256",
    "C5_ARCHITECTURE",
    "C5_CONTROL_SHA",
    "C5_ACTIVATION_PR",
    "C5_ACTIVATION_REVIEWED_HEAD",
    "C5_ACTIVATION_REVIEWED_TREE",
    "C5_ACTIVATION_BASE",
    "C5_ACTIVATION_MAIN",
    "C5_FRESH_REVIEW_ID",
    "C5_FRESH_REVIEW_BODY_SHA256",
    "C5_OWNER_MERGE_AUTHORITY_COMMENT_ID",
    "C5_OWNER_MERGE_AUTHORITY_BODY_SHA256",
    "MERGED_TREE_EQUALS_REVIEWED_TREE",
    "REPOSITORY_CALLER",
    "REPOSITORY_DESIRED_WIF",
    "LIVE_WIF",
    "CLOUD_EFFECT",
    "STATUS",
)


def validate_c5_activation_record(
    comments: list[dict[str, Any]],
    control_sha: str,
    activation_main: str,
) -> dict[str, Any]:
    control_record = validate_c5_control_merge_record(comments, control_sha)
    candidates = [
        comment
        for comment in comments
        if _owner_issue_comment(comment, GOVERNING_ISSUE)
        and canonical_comment_text(comment.get("body")).startswith(
            "PHASE5_SLICE_C_C5_ACTIVATION_V1\n"
        )
        and f"C5_CONTROL_SHA={control_sha}" in canonical_comment_text(
            comment.get("body")
        )
        and f"C5_ACTIVATION_MAIN={activation_main}" in canonical_comment_text(
            comment.get("body")
        )
    ]
    if len(candidates) != 1:
        raise RecoveryError("C5_ACTIVATION_RECORD_NOT_UNIQUE")
    comment = candidates[0]
    created, body_sha = _require_unedited_owner_comment(
        comment, GOVERNING_ISSUE, "C5_ACTIVATION_RECORD"
    )
    fields = _record_fields(
        str(comment.get("body") or ""),
        "PHASE5_SLICE_C_C5_ACTIVATION_V1",
        C5_ACTIVATION_RECORD_FIELDS,
    )
    expected = {
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "C5_PROTOCOL_EPOCH_SHA256": C5_PROTOCOL_EPOCH_SHA256,
        "C5_ARCHITECTURE": str(C5_ARCHITECTURE_COMMENT_ID),
        "C5_CONTROL_SHA": control_sha,
        "C5_ACTIVATION_BASE": control_sha,
        "C5_ACTIVATION_MAIN": activation_main,
        "MERGED_TREE_EQUALS_REVIEWED_TREE": "TRUE",
        "REPOSITORY_CALLER": "C5",
        "REPOSITORY_DESIRED_WIF": "C5",
        "LIVE_WIF": "C4_ONLY",
        "CLOUD_EFFECT": "NONE",
        "STATUS": "C5_REPOSITORY_ACTIVATION_MERGED_EXACT",
    }
    for key, value in expected.items():
        if fields[key] != value:
            raise RecoveryError(f"C5_ACTIVATION_RECORD_FIELD_MISMATCH:{key}")
    pr_number = _positive_int(
        fields["C5_ACTIVATION_PR"], "C5_ACTIVATION_RECORD_PR"
    )
    reviewed_head = _c5_require_sha(
        fields["C5_ACTIVATION_REVIEWED_HEAD"],
        "C5_ACTIVATION_RECORD_REVIEWED_HEAD",
    )
    reviewed_tree = _c5_require_sha(
        fields["C5_ACTIVATION_REVIEWED_TREE"],
        "C5_ACTIVATION_RECORD_REVIEWED_TREE",
    )
    review_id = _positive_int(
        fields["C5_FRESH_REVIEW_ID"], "C5_ACTIVATION_RECORD_REVIEW_ID"
    )
    review_hash = _c5_require_hash(
        fields["C5_FRESH_REVIEW_BODY_SHA256"],
        "C5_ACTIVATION_RECORD_REVIEW_BODY_SHA256",
    )
    authority_id = _positive_int(
        fields["C5_OWNER_MERGE_AUTHORITY_COMMENT_ID"],
        "C5_ACTIVATION_RECORD_AUTHORITY_ID",
    )
    authority_hash = _c5_require_hash(
        fields["C5_OWNER_MERGE_AUTHORITY_BODY_SHA256"],
        "C5_ACTIVATION_RECORD_AUTHORITY_BODY_SHA256",
    )
    pr = github(f"/repos/{REPOSITORY}/pulls/{pr_number}")
    if (
        not isinstance(pr, dict)
        or pr.get("state") != "closed"
        or pr.get("merged_at") is None
        or pr.get("merge_commit_sha") != activation_main
        or pr.get("head", {}).get("sha") != reviewed_head
        or pr.get("base", {}).get("sha") != control_sha
        or pr.get("base", {}).get("ref") != DEFAULT_BRANCH
    ):
        raise RecoveryError("C5_ACTIVATION_RECORD_PR_MISMATCH")
    files = github(f"/repos/{REPOSITORY}/pulls/{pr_number}/files?per_page=100")
    _c5_validate_pr_files(files, C5_ACTIVATION_ALLOWED_FILES, "C5_ACTIVATION_RECORD")
    _c5_verify_activation_file_transform(control_sha, reviewed_head)
    reviewed_commit = github(f"/repos/{REPOSITORY}/commits/{reviewed_head}")
    merge_commit = github(f"/repos/{REPOSITORY}/commits/{activation_main}")
    if (
        (reviewed_commit.get("commit") or {}).get("tree", {}).get("sha")
        != reviewed_tree
        or (merge_commit.get("commit") or {}).get("tree", {}).get("sha")
        != reviewed_tree
    ):
        raise RecoveryError("C5_ACTIVATION_RECORD_TREE_MISMATCH")
    review = github(f"/repos/{REPOSITORY}/pulls/{pr_number}/reviews/{review_id}")
    expected_review = c5_activation_review_body(
        control_sha, pr_number, reviewed_head
    )
    if (
        not isinstance(review, dict)
        or review.get("id") != review_id
        or review.get("state") != "COMMENTED"
        or review.get("commit_id") != reviewed_head
        or canonical_comment_text(review.get("body")) != expected_review
        or sha256(str(review.get("body") or "").encode("utf-8")) != review_hash
    ):
        raise RecoveryError("C5_ACTIVATION_RECORD_REVIEW_MISMATCH")
    review_user = review.get("user") or {}
    if (
        review_user.get("login") != OWNER_LOGIN
        or review_user.get("id") != OWNER_ID
    ):
        raise RecoveryError("C5_ACTIVATION_RECORD_REVIEW_OWNER_MISMATCH")
    authority = github(f"/repos/{REPOSITORY}/issues/comments/{authority_id}")
    authority_created, observed_authority_hash = _require_unedited_owner_comment(
        authority, pr_number, "C5_ACTIVATION_RECORD_AUTHORITY"
    )
    if observed_authority_hash != authority_hash:
        raise RecoveryError("C5_ACTIVATION_RECORD_AUTHORITY_HASH_MISMATCH")
    if canonical_comment_text(authority.get("body")) != c5_activation_merge_authority_body(
        control_sha, pr_number, reviewed_head, review_id, review_hash
    ):
        raise RecoveryError("C5_ACTIVATION_RECORD_AUTHORITY_BODY_MISMATCH")
    review_time = _timestamp(
        review.get("submitted_at"), "C5_ACTIVATION_RECORD_REVIEW_SUBMITTED"
    )
    merge_time = _timestamp(pr.get("merged_at"), "C5_ACTIVATION_RECORD_MERGED")
    if not (
        control_record["created_at"] <= review_time
        <= authority_created
        < merge_time
        <= created
    ):
        raise RecoveryError("C5_ACTIVATION_RECORD_TIMELINE_INVALID")
    return {
        "comment_id": int(comment["id"]),
        "created_at": created,
        "body_sha256": body_sha,
        "control_record_comment_id": control_record["comment_id"],
        "control_record_body_sha256": control_record["body_sha256"],
        "control_sha": control_sha,
        "activation_main": activation_main,
        "pr_number": pr_number,
        "reviewed_head": reviewed_head,
        "reviewed_tree": reviewed_tree,
        "review_id": review_id,
        "review_body_sha256": review_hash,
        "authority_id": authority_id,
        "authority_body_sha256": authority_hash,
    }


# C5 closure R1: total observation -> terminal -> authority provenance.
# Historical predecessor validators remain below this line only as evidence
# interpreters; the public successor runtime entrypoint is rebound to C5.
_legacy_verify_successor_github_boundary = verify_successor_github_boundary

C5_OBSERVATION_FIELDS = (
    "GOVERNING_ISSUE",
    "C5_PROTOCOL_EPOCH_SHA256",
    "SUCCESSOR_CONTROL_SHA",
    "SUCCESSOR_ACTIVATION_MAIN",
    "ATTEMPT_CLAIM_COMMENT_ID",
    "ATTEMPT_CLAIM_BODY_SHA256",
    "ATTEMPT_SERIES_ID_SHA256",
    "ATTEMPT_GENERATION",
    "PRECONDITION_DIGEST_SHA256",
    "OBSERVED_AT",
    "BOOTSTRAP_STATE_LINEAGE",
    "BOOTSTRAP_STATE_SERIAL",
    "BOOTSTRAP_STATE_CANONICAL_SHA256",
    "OLD_RECOVERY_WIF_COUNT",
    "NEW_RECOVERY_WIF_COUNT",
    "FORBIDDEN_C1_RECOVERY_WIF_COUNT",
    "SUPERSEDED_C2_RECOVERY_WIF_COUNT",
    "SUPERSEDED_C3_RECOVERY_WIF_COUNT",
    "UNEXPECTED_RECOVERY_WIF_COUNT",
    "RECOVERY_WIF_MEMBER_SET_SHA256",
    "C2_RECOVERY_CLAIM_RESULT",
    "C3_RECOVERY_CLAIM_RESULT",
    "OLD_CONTROL_RECOVERY_CLAIM_RESULT",
    "NEW_CONTROL_RECOVERY_CLAIM_RESULT",
    "BOOTSTRAP_LOCK",
    "RECONCILIATION",
    "RECONCILIATION_PLAN_SHA256",
    "GETMETADATA_ROLE_SET_SHA256",
    "NORMAL_PHASE5_IDENTITY_SET_SHA256",
    "OBSERVATION_COMPLETE",
    "FACT_DIGEST_SHA256",
)


def _c5_observation_fact_lines(fields: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        f"{name}={fields[name]}"
        for name in C5_OBSERVATION_FIELDS
        if name not in ("OBSERVED_AT", "FACT_DIGEST_SHA256")
    )


def c5_wif_repin_observation_body(
    *,
    successor_control_sha: str,
    successor_activation_main: str,
    attempt_claim_comment_id: int,
    attempt_claim_body_sha256: str,
    attempt_series_id_sha256: str,
    attempt_generation: int,
    precondition_digest_sha256: str,
    observed_at: str,
    state_lineage: str,
    state_serial: int,
    state_canonical_sha256: str,
    old_wif_count: int,
    new_wif_count: int,
    forbidden_wif_counts: tuple[int, int, int],
    unexpected_wif_count: int,
    recovery_wif_member_set_sha256: str,
    claim_result_states: tuple[str, str, str, str],
    bootstrap_lock_absent: bool,
    reconciliation: str,
    reconciliation_plan_sha256: str,
    getmetadata_role_set_sha256: str,
    normal_phase5_identity_set_sha256: str,
) -> str:
    _c5_require_sha(successor_control_sha, "C5_OBSERVATION_CONTROL")
    _c5_require_sha(successor_activation_main, "C5_OBSERVATION_ACTIVATION")
    if (
        successor_control_sha == C5_OLD_RECOVERY_CONTROL_SHA
        or successor_control_sha in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS
    ):
        raise RecoveryError("C5_OBSERVATION_CONTROL_FORBIDDEN")
    _c5_positive(attempt_claim_comment_id, "C5_OBSERVATION_CLAIM_ID")
    _c5_positive(attempt_generation, "C5_OBSERVATION_GENERATION")
    for value, label in (
        (attempt_claim_body_sha256, "CLAIM"),
        (attempt_series_id_sha256, "SERIES"),
        (precondition_digest_sha256, "PRECONDITION"),
        (state_canonical_sha256, "STATE"),
        (recovery_wif_member_set_sha256, "WIF_SET"),
        (getmetadata_role_set_sha256, "GETMETADATA"),
        (normal_phase5_identity_set_sha256, "NORMAL_IDENTITIES"),
        (reconciliation_plan_sha256, "RECONCILIATION_PLAN"),
    ):
        _c5_require_hash(value, f"C5_OBSERVATION_{label}_HASH")
    _timestamp(observed_at, "C5_OBSERVATION_OBSERVED_AT")
    _c5_require_lineage(state_lineage, "C5_OBSERVATION_LINEAGE")
    _c5_nonnegative(state_serial, "C5_OBSERVATION_SERIAL")
    _c5_nonnegative(old_wif_count, "C5_OBSERVATION_OLD_WIF_COUNT")
    _c5_nonnegative(new_wif_count, "C5_OBSERVATION_NEW_WIF_COUNT")
    if len(forbidden_wif_counts) != 3 or len(claim_result_states) != 4:
        raise RecoveryError("C5_OBSERVATION_VECTOR_INVALID")
    for value in forbidden_wif_counts:
        _c5_nonnegative(value, "C5_OBSERVATION_FORBIDDEN_WIF_COUNT")
    _c5_nonnegative(unexpected_wif_count, "C5_OBSERVATION_UNEXPECTED_WIF_COUNT")
    for value in claim_result_states:
        _c5_require_enum(
            value, {"ABSENT", "PRESENT"}, "C5_OBSERVATION_CLAIM_RESULT"
        )
    _c5_require_enum(
        reconciliation,
        {"EXACT_NO_CHANGE", "EXACT_PENDING_REVIEWED_EFFECT", "INCONSISTENT"},
        "C5_OBSERVATION_RECONCILIATION",
    )
    fields = {
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "C5_PROTOCOL_EPOCH_SHA256": C5_PROTOCOL_EPOCH_SHA256,
        "SUCCESSOR_CONTROL_SHA": successor_control_sha,
        "SUCCESSOR_ACTIVATION_MAIN": successor_activation_main,
        "ATTEMPT_CLAIM_COMMENT_ID": str(attempt_claim_comment_id),
        "ATTEMPT_CLAIM_BODY_SHA256": attempt_claim_body_sha256,
        "ATTEMPT_SERIES_ID_SHA256": attempt_series_id_sha256,
        "ATTEMPT_GENERATION": str(attempt_generation),
        "PRECONDITION_DIGEST_SHA256": precondition_digest_sha256,
        "OBSERVED_AT": observed_at,
        "BOOTSTRAP_STATE_LINEAGE": state_lineage,
        "BOOTSTRAP_STATE_SERIAL": str(state_serial),
        "BOOTSTRAP_STATE_CANONICAL_SHA256": state_canonical_sha256,
        "OLD_RECOVERY_WIF_COUNT": str(old_wif_count),
        "NEW_RECOVERY_WIF_COUNT": str(new_wif_count),
        "FORBIDDEN_C1_RECOVERY_WIF_COUNT": str(forbidden_wif_counts[0]),
        "SUPERSEDED_C2_RECOVERY_WIF_COUNT": str(forbidden_wif_counts[1]),
        "SUPERSEDED_C3_RECOVERY_WIF_COUNT": str(forbidden_wif_counts[2]),
        "UNEXPECTED_RECOVERY_WIF_COUNT": str(unexpected_wif_count),
        "RECOVERY_WIF_MEMBER_SET_SHA256": recovery_wif_member_set_sha256,
        "C2_RECOVERY_CLAIM_RESULT": claim_result_states[0],
        "C3_RECOVERY_CLAIM_RESULT": claim_result_states[1],
        "OLD_CONTROL_RECOVERY_CLAIM_RESULT": claim_result_states[2],
        "NEW_CONTROL_RECOVERY_CLAIM_RESULT": claim_result_states[3],
        "BOOTSTRAP_LOCK": "ABSENT" if bootstrap_lock_absent else "PRESENT",
        "RECONCILIATION": reconciliation,
        "RECONCILIATION_PLAN_SHA256": reconciliation_plan_sha256,
        "GETMETADATA_ROLE_SET_SHA256": getmetadata_role_set_sha256,
        "NORMAL_PHASE5_IDENTITY_SET_SHA256": normal_phase5_identity_set_sha256,
        "OBSERVATION_COMPLETE": "TRUE",
    }
    fields["FACT_DIGEST_SHA256"] = sha256(
        "\n".join(_c5_observation_fact_lines(fields)).encode("utf-8")
    )
    return "\n".join(
        ("PHASE5_SLICE_C_C5_WIF_REPIN_OBSERVATION_V1",)
        + tuple(f"{name}={fields[name]}" for name in C5_OBSERVATION_FIELDS)
    )


def validate_c5_wif_repin_observation(
    comment: dict[str, Any],
    successor_control_sha: str,
    activation_main: str,
    expected_claim: dict[str, Any],
) -> dict[str, Any]:
    created, raw_hash = _require_unedited_owner_comment(
        comment, GOVERNING_ISSUE, "C5_OBSERVATION"
    )
    fields = _record_fields(
        str(comment.get("body") or ""),
        "PHASE5_SLICE_C_C5_WIF_REPIN_OBSERVATION_V1",
        C5_OBSERVATION_FIELDS,
    )
    if (
        fields["GOVERNING_ISSUE"] != "8ft0-ai/resilio#109"
        or fields["C5_PROTOCOL_EPOCH_SHA256"] != C5_PROTOCOL_EPOCH_SHA256
    ):
        raise RecoveryError("C5_OBSERVATION_PROTOCOL_ROOT_MISMATCH")
    if (
        fields["SUCCESSOR_CONTROL_SHA"] != successor_control_sha
        or fields["SUCCESSOR_ACTIVATION_MAIN"] != activation_main
    ):
        raise RecoveryError("C5_OBSERVATION_TARGET_MISMATCH")
    if fields["OBSERVATION_COMPLETE"] != "TRUE":
        raise RecoveryError("C5_OBSERVATION_INCOMPLETE")
    digest = sha256(
        "\n".join(_c5_observation_fact_lines(fields)).encode("utf-8")
    )
    if fields["FACT_DIGEST_SHA256"] != digest:
        raise RecoveryError("C5_OBSERVATION_FACT_DIGEST_MISMATCH")
    observed_at = _timestamp(fields["OBSERVED_AT"], "C5_OBSERVATION_OBSERVED_AT")
    claim_id = _positive_int(
        fields["ATTEMPT_CLAIM_COMMENT_ID"], "C5_OBSERVATION_CLAIM_ID"
    )
    generation = _positive_int(
        fields["ATTEMPT_GENERATION"], "C5_OBSERVATION_GENERATION"
    )
    for name in (
        "ATTEMPT_CLAIM_BODY_SHA256",
        "ATTEMPT_SERIES_ID_SHA256",
        "PRECONDITION_DIGEST_SHA256",
        "BOOTSTRAP_STATE_CANONICAL_SHA256",
        "RECOVERY_WIF_MEMBER_SET_SHA256",
        "GETMETADATA_ROLE_SET_SHA256",
        "NORMAL_PHASE5_IDENTITY_SET_SHA256",
        "RECONCILIATION_PLAN_SHA256",
        "FACT_DIGEST_SHA256",
    ):
        _c5_require_hash(fields[name], f"C5_OBSERVATION_{name}")
    _c5_nonnegative(int(fields["UNEXPECTED_RECOVERY_WIF_COUNT"]), "C5_OBSERVATION_UNEXPECTED_WIF_COUNT")
    if fields["BOOTSTRAP_STATE_LINEAGE"] != expected_claim["fields"]["BOOTSTRAP_STATE_LINEAGE_BEFORE"]:
        raise RecoveryError("C5_OBSERVATION_LINEAGE_MISMATCH")
    if (
        claim_id != expected_claim["comment_id"]
        or fields["ATTEMPT_CLAIM_BODY_SHA256"] != expected_claim["body_sha256"]
        or fields["ATTEMPT_SERIES_ID_SHA256"]
        != expected_claim["fields"]["ATTEMPT_SERIES_ID_SHA256"]
        or generation != expected_claim["generation"]
        or fields["PRECONDITION_DIGEST_SHA256"]
        != expected_claim["fields"]["PRECONDITION_DIGEST_SHA256"]
    ):
        raise RecoveryError("C5_OBSERVATION_CLAIM_BINDING_MISMATCH")
    if created <= expected_claim["created_at"]:
        raise RecoveryError("C5_OBSERVATION_PRECEDES_ATTEMPT")
    return {
        "comment_id": int(comment["id"]),
        "created_at": created,
        "observed_at": observed_at,
        "body_sha256": raw_hash,
        "fact_digest_sha256": digest,
        "fields": fields,
    }


C5_TERMINAL_V2_FIELDS = (
    "GOVERNING_ISSUE",
    "C5_PROTOCOL_EPOCH_SHA256",
    "SUCCESSOR_CONTROL_SHA",
    "SUCCESSOR_ACTIVATION_MAIN",
    "ATTEMPT_CLAIM_COMMENT_ID",
    "ATTEMPT_CLAIM_BODY_SHA256",
    "ATTEMPT_SERIES_ID_SHA256",
    "ATTEMPT_GENERATION",
    "PRECONDITION_DIGEST_SHA256",
    "OBSERVATION_1_COMMENT_ID",
    "OBSERVATION_1_BODY_SHA256",
    "OBSERVATION_2_COMMENT_ID",
    "OBSERVATION_2_BODY_SHA256",
    "OUTCOME",
)



def c5_expected_normal_identity_set_sha256() -> str:
    rows = [
        {"name": name, "service_account": service_account,
         "workflow": workflow, "control_sha": control_sha}
        for name, (service_account, workflow, control_sha)
        in sorted(C5_EXPECTED_PHASE5_WIF_ROWS.items())
        if name != "github_phase5_slice_c_recovery"
    ]
    return sha256(canonical(rows))


def c5_expected_getmetadata_role_set_sha256() -> str:
    return sha256(canonical({
        role_id: sorted(C5_EXPECTED_ROLE_PERMISSIONS[role_id])
        for role_id in sorted(C5_GETMETADATA_ROLES)
    }))


def _c5_post_effect_live_facts(
    state: Any, new_recovery_control_sha: str
) -> dict[str, Any]:
    _c5_require_sha(new_recovery_control_sha, "C5_POST_EFFECT_NEW_CONTROL")
    if not isinstance(state, dict):
        raise RecoveryError("C5_POST_EFFECT_STATE_INVALID")
    lineage = _c5_require_lineage(
        str(state.get("lineage") or ""), "C5_POST_EFFECT_LINEAGE"
    )
    serial = state.get("serial")
    _c5_nonnegative(serial, "C5_POST_EFFECT_SERIAL")
    if lineage != C5_BOOTSTRAP_STATE_LINEAGE or serial < C5_BOOTSTRAP_STATE_SERIAL:
        raise RecoveryError("C5_POST_EFFECT_STATE_IDENTITY_INVALID")
    resources = state.get("resources")
    if not isinstance(resources, list) or len(resources) != C5_EXPECTED_BOOTSTRAP_RESOURCE_COUNT:
        raise RecoveryError("C5_POST_EFFECT_RESOURCE_COUNT_INVALID")

    prefix = (
        "principalSet://iam.googleapis.com/projects/400271474382/locations/global/"
        "workloadIdentityPools/github/attribute.job_workflow_ref/8ft0-ai/resilio/"
        ".github/workflows/"
    )
    rows: list[dict[str, str]] = []
    for resource in resources:
        if (
            not isinstance(resource, dict)
            or resource.get("type") != "google_service_account_iam_member"
            or not str(resource.get("name") or "").startswith("github_phase5")
        ):
            continue
        instances = resource.get("instances")
        if not isinstance(instances, list) or len(instances) != 1:
            raise RecoveryError("C5_POST_EFFECT_WIF_INSTANCE_INVALID")
        attrs = instances[0].get("attributes") if isinstance(instances[0], dict) else None
        if not isinstance(attrs, dict):
            raise RecoveryError("C5_POST_EFFECT_WIF_ATTRIBUTES_INVALID")
        service_account_id = str(attrs.get("service_account_id") or "")
        marker = "/serviceAccounts/"
        if marker not in service_account_id:
            raise RecoveryError("C5_POST_EFFECT_WIF_SERVICE_ACCOUNT_INVALID")
        rows.append({
            "name": str(resource.get("name") or ""),
            "service_account": service_account_id.split(marker, 1)[1],
            "role": str(attrs.get("role") or ""),
            "member": str(attrs.get("member") or ""),
        })
    if len(rows) != len(C5_EXPECTED_PHASE5_WIF_ROWS):
        raise RecoveryError("C5_POST_EFFECT_WIF_RESOURCE_COUNT_INVALID")
    by_name = {row["name"]: row for row in rows}
    if set(by_name) != set(C5_EXPECTED_PHASE5_WIF_ROWS):
        raise RecoveryError("C5_POST_EFFECT_WIF_NAME_SET_INVALID")

    normal_ok = True
    cache: dict[str, dict[str, Any]] = {}
    for name, (expected_sa, expected_workflow, expected_sha) in C5_EXPECTED_PHASE5_WIF_ROWS.items():
        row = by_name[name]
        if row["service_account"] != expected_sa or row["role"] != "roles/iam.workloadIdentityUser":
            normal_ok = False
        if name != "github_phase5_slice_c_recovery":
            if row["member"] != prefix + expected_workflow + "@" + expected_sha:
                normal_ok = False
            policy = cache.setdefault(row["service_account"], _c5_iam_policy(row["service_account"]))
            if row["member"] not in _c5_policy_members(policy, row["role"]):
                normal_ok = False

    recovery = by_name["github_phase5_slice_c_recovery"]
    recovery_policy = cache.setdefault(
        recovery["service_account"], _c5_iam_policy(recovery["service_account"])
    )
    recovery_members = sorted(
        member for member in _c5_policy_members(recovery_policy, recovery["role"])
        if "/.github/workflows/phase5-slice-c-recovery-reusable.yml@" in member
    )
    old_suffix = "/.github/workflows/phase5-slice-c-recovery-reusable.yml@" + C5_OLD_RECOVERY_CONTROL_SHA
    new_suffix = "/.github/workflows/phase5-slice-c-recovery-reusable.yml@" + new_recovery_control_sha
    forbidden_suffixes = tuple(
        "/.github/workflows/phase5-slice-c-recovery-reusable.yml@" + control
        for control in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS
    )
    old_count = sum(member.endswith(old_suffix) for member in recovery_members)
    new_count = sum(member.endswith(new_suffix) for member in recovery_members)
    forbidden_counts = tuple(
        sum(member.endswith(suffix) for member in recovery_members)
        for suffix in forbidden_suffixes
    )
    known_count = old_count + new_count + sum(forbidden_counts)
    unexpected_count = max(0, len(recovery_members) - known_count)

    roles: dict[str, list[str]] = {}
    roles_ok = True
    for role_id in C5_GETMETADATA_ROLES:
        role = _c5_role(role_id)
        permissions = role.get("includedPermissions")
        if not isinstance(permissions, list):
            raise RecoveryError(f"C5_POST_EFFECT_ROLE_INVALID:{role_id}")
        roles[role_id] = sorted(str(value) for value in permissions)
        if (
            frozenset(permissions) != C5_EXPECTED_ROLE_PERMISSIONS[role_id]
            or len(permissions) != len(C5_EXPECTED_ROLE_PERMISSIONS[role_id])
        ):
            roles_ok = False

    return {
        "state_lineage": lineage,
        "state_serial": serial,
        "state_canonical_sha256": sha256(canonical(state)),
        "old_wif_count": old_count,
        "new_wif_count": new_count,
        "forbidden_wif_counts": forbidden_counts,
        "unexpected_wif_count": unexpected_count,
        "recovery_wif_member_set_sha256": sha256(canonical(recovery_members)),
        "normal_phase5_identity_set_sha256": (
            c5_expected_normal_identity_set_sha256()
            if normal_ok
            else sha256(canonical({"mismatch": "normal_phase5", "rows": rows}))
        ),
        "getmetadata_role_set_sha256": sha256(canonical(roles)),
        "normal_identities_ok": normal_ok,
        "getmetadata_ok": roles_ok,
    }


def _c5_reconciliation_plan_fact_sha256(plan: dict[str, Any]) -> str:
    """Hash semantic plan JSON while excluding Terraform's run timestamp."""
    if not isinstance(plan, dict):
        raise RecoveryError("C5_RECONCILIATION_PLAN_INVALID")
    stable = dict(plan)
    stable.pop("timestamp", None)
    return sha256(canonical(stable))


def _c5_fresh_reconciliation(
    terraform_workdir: str | Path,
    old_recovery_control_sha: str,
    new_recovery_control_sha: str,
) -> dict[str, Any]:
    workdir = Path(terraform_workdir).resolve()
    if not workdir.is_dir():
        raise RecoveryError("C5_OBSERVATION_TERRAFORM_WORKDIR_MISSING")
    with tempfile.TemporaryDirectory(prefix="resilio-c5-observation-") as temp:
        plan_path = Path(temp) / "reconciliation.tfplan"
        result = subprocess.run(
            [
                "terraform",
                f"-chdir={workdir}",
                "plan",
                "-input=false",
                "-no-color",
                "-lock=true",
                "-detailed-exitcode",
                f"-out={plan_path}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode not in (0, 2):
            raise RecoveryError("C5_OBSERVATION_FRESH_PLAN_FAILED")
        plan = _c5_saved_plan_json(plan_path, workdir)
        if result.returncode == 2:
            c5_verify_wif_repin_plan(
                plan, old_recovery_control_sha, new_recovery_control_sha
            )
            mode = "EXACT_PENDING_REVIEWED_EFFECT"
        else:
            if (
                plan.get("format_version") != "1.2"
                or plan.get("terraform_version") != "1.15.8"
                or plan.get("errored") is not False
                or plan.get("output_changes") not in ({}, None)
            ):
                raise RecoveryError("C5_OBSERVATION_NO_CHANGE_PLAN_INVALID")
            for key in (
                "resource_drift", "deferred_changes",
                "deferred_action_invocations", "action_invocations",
            ):
                if plan.get(key) not in (None, []):
                    raise RecoveryError(f"C5_OBSERVATION_NO_CHANGE_PLAN_UNEXPECTED:{key}")
            rows = plan.get("resource_changes")
            if not isinstance(rows, list):
                raise RecoveryError("C5_OBSERVATION_NO_CHANGE_ROWS_INVALID")
            for row in rows:
                if not isinstance(row, dict):
                    raise RecoveryError("C5_OBSERVATION_NO_CHANGE_ROW_INVALID")
                if ((row.get("change") or {}).get("actions")) not in (["no-op"], []):
                    raise RecoveryError("C5_OBSERVATION_NO_CHANGE_EFFECT_PRESENT")
            mode = "EXACT_NO_CHANGE"
        return {
            "reconciliation": mode,
            "plan_sha256": _c5_reconciliation_plan_fact_sha256(plan),
        }


def verify_c5_wif_repin_observation(
    *,
    successor_control_sha: str,
    activation_main: str,
    attempt_claim_comment_id: int,
    terraform_workdir: str | Path,
) -> dict[str, Any]:
    _c5_require_sha(successor_control_sha, "C5_OBSERVE_CONTROL")
    _c5_require_sha(activation_main, "C5_OBSERVE_ACTIVATION")
    _c5_positive(attempt_claim_comment_id, "C5_OBSERVE_CLAIM_ID")
    observed_at = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    branch = github(f"/repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}")
    if (
        not isinstance(branch, dict)
        or branch.get("commit", {}).get("sha") != activation_main
    ):
        raise RecoveryError("C5_OBSERVE_MAIN_MISMATCH")
    verify_c5_repository_activation(activation_main, successor_control_sha)
    comments = github_issue_comments(GOVERNING_ISSUE)
    validate_c5_governance_history(comments)
    validate_c5_activation_record(comments, successor_control_sha, activation_main)
    claim = _c5_parse_attempt_claim(
        _c5_comment_by_id(
            comments, attempt_claim_comment_id, "C5_OBSERVE_ATTEMPT_CLAIM"
        )
    )
    if (
        claim["fields"]["C5_PROTOCOL_EPOCH_SHA256"] != C5_PROTOCOL_EPOCH_SHA256
        or claim["fields"]["SUCCESSOR_CONTROL_SHA"] != successor_control_sha
        or claim["fields"]["SUCCESSOR_ACTIVATION_MAIN"] != activation_main
    ):
        raise RecoveryError("C5_OBSERVE_CLAIM_TARGET_MISMATCH")

    state = _successor_gcs_json(C5_BOOTSTRAP_STATE_OBJECT)
    live = _c5_post_effect_live_facts(state, successor_control_sha)
    lock_absent = _successor_gcs_metadata(C5_BOOTSTRAP_LOCK_OBJECT, True) is None
    states: list[str] = []
    for control in (
        SUPERSEDED_CONTROL_SHA, FAILED_C3_CONTROL_SHA,
        C5_OLD_RECOVERY_CONTROL_SHA, successor_control_sha,
    ):
        present = any(
            _successor_gcs_metadata(evidence_object(kind, control), True) is not None
            for kind in ("claim", "result")
        )
        states.append("PRESENT" if present else "ABSENT")
    reconciliation = _c5_fresh_reconciliation(
        terraform_workdir, C5_OLD_RECOVERY_CONTROL_SHA, successor_control_sha
    )
    body = c5_wif_repin_observation_body(
        successor_control_sha=successor_control_sha,
        successor_activation_main=activation_main,
        attempt_claim_comment_id=attempt_claim_comment_id,
        attempt_claim_body_sha256=claim["body_sha256"],
        attempt_series_id_sha256=claim["fields"]["ATTEMPT_SERIES_ID_SHA256"],
        attempt_generation=claim["generation"],
        precondition_digest_sha256=claim["fields"]["PRECONDITION_DIGEST_SHA256"],
        observed_at=observed_at,
        state_lineage=live["state_lineage"],
        state_serial=live["state_serial"],
        state_canonical_sha256=live["state_canonical_sha256"],
        old_wif_count=live["old_wif_count"],
        new_wif_count=live["new_wif_count"],
        forbidden_wif_counts=live["forbidden_wif_counts"],
        unexpected_wif_count=live["unexpected_wif_count"],
        recovery_wif_member_set_sha256=live["recovery_wif_member_set_sha256"],
        claim_result_states=tuple(states),
        bootstrap_lock_absent=lock_absent,
        reconciliation=reconciliation["reconciliation"],
        reconciliation_plan_sha256=reconciliation["plan_sha256"],
        getmetadata_role_set_sha256=live["getmetadata_role_set_sha256"],
        normal_phase5_identity_set_sha256=live["normal_phase5_identity_set_sha256"],
    )
    return {
        "contract": "resilio-phase5-slice-c-c5-wif-observation-verifier/v1",
        "body": body,
        "c5_protocol_epoch_sha256": C5_PROTOCOL_EPOCH_SHA256,
        "attempt_claim_comment_id": attempt_claim_comment_id,
        "reconciliation": reconciliation["reconciliation"],
        "verified_live": True,
    }


def c5_terminal_body_from_observation_comments(
    successor_control_sha: str,
    activation_main: str,
    observation_1_comment_id: int,
    observation_2_comment_id: int | None = None,
) -> str:
    comments = github_issue_comments(GOVERNING_ISSUE)
    obs1_comment = _c5_comment_by_id(
        comments, observation_1_comment_id, "C5_TERMINAL_BUILD_OBS1"
    )
    fields = _record_fields(
        str(obs1_comment.get("body") or ""),
        "PHASE5_SLICE_C_C5_WIF_REPIN_OBSERVATION_V1",
        C5_OBSERVATION_FIELDS,
    )
    claim = _c5_parse_attempt_claim(
        _c5_comment_by_id(
            comments,
            _positive_int(fields["ATTEMPT_CLAIM_COMMENT_ID"], "C5_TERMINAL_BUILD_CLAIM_ID"),
            "C5_TERMINAL_BUILD_CLAIM",
        )
    )
    obs1 = validate_c5_wif_repin_observation(
        obs1_comment, successor_control_sha, activation_main, claim
    )
    obs2 = None
    if observation_2_comment_id is not None:
        obs2 = validate_c5_wif_repin_observation(
            _c5_comment_by_id(
                comments, observation_2_comment_id, "C5_TERMINAL_BUILD_OBS2"
            ),
            successor_control_sha, activation_main, claim,
        )
    return c5_wif_repin_terminal_v2_body(
        successor_control_sha, activation_main, claim, obs1, obs2
    )


def _c5_observation_outcome(
    first: dict[str, Any], second: dict[str, Any] | None,
    claim: dict[str, Any] | None = None,
) -> str:
    f = first["fields"]
    forbidden = tuple(
        int(f[name])
        for name in (
            "FORBIDDEN_C1_RECOVERY_WIF_COUNT",
            "SUPERSEDED_C2_RECOVERY_WIF_COUNT",
            "SUPERSEDED_C3_RECOVERY_WIF_COUNT",
        )
    )
    claims = tuple(
        f[name]
        for name in (
            "C2_RECOVERY_CLAIM_RESULT",
            "C3_RECOVERY_CLAIM_RESULT",
            "OLD_CONTROL_RECOVERY_CLAIM_RESULT",
            "NEW_CONTROL_RECOVERY_CLAIM_RESULT",
        )
    )
    baseline_lineage = C5_BOOTSTRAP_STATE_LINEAGE if claim is None else claim["fields"]["BOOTSTRAP_STATE_LINEAGE_BEFORE"]
    baseline_serial = C5_BOOTSTRAP_STATE_SERIAL if claim is None else _positive_int(claim["fields"]["BOOTSTRAP_STATE_SERIAL_BEFORE"], "C5_OUTCOME_BASELINE_SERIAL")
    clean = (
        all(value == 0 for value in forbidden)
        and int(f["UNEXPECTED_RECOVERY_WIF_COUNT"]) == 0
        and f["BOOTSTRAP_STATE_LINEAGE"] == baseline_lineage
        and f["GETMETADATA_ROLE_SET_SHA256"] == c5_expected_getmetadata_role_set_sha256()
        and f["NORMAL_PHASE5_IDENTITY_SET_SHA256"] == c5_expected_normal_identity_set_sha256()
        and all(value == "ABSENT" for value in claims)
        and f["BOOTSTRAP_LOCK"] == "ABSENT"
    )
    if (
        clean
        and f["OLD_RECOVERY_WIF_COUNT"] == "0"
        and f["NEW_RECOVERY_WIF_COUNT"] == "1"
        and int(f["BOOTSTRAP_STATE_SERIAL"]) >= baseline_serial
        and f["RECONCILIATION"] == "EXACT_NO_CHANGE"
    ):
        if second is not None:
            raise RecoveryError("C5_EFFECT_SUCCEEDED_SECOND_OBSERVATION_FORBIDDEN")
        return "EFFECT_SUCCEEDED"
    if second is not None:
        second_fields = second["fields"]
        # The late-effect fence requires both the verifier-owned observation
        # clock and durable GitHub comment creation times to span >=60 seconds.
        # Neither caller-provided text nor posting delay alone can satisfy it.
        durable_separation = (
            second["created_at"] - first["created_at"]
        ).total_seconds()
        verifier_separation = (
            second["observed_at"] - first["observed_at"]
        ).total_seconds()
        if (
            first["fact_digest_sha256"] == second["fact_digest_sha256"]
            and durable_separation >= 60
            and verifier_separation >= 60
            and clean
            and f["OLD_RECOVERY_WIF_COUNT"] == "1"
            and f["NEW_RECOVERY_WIF_COUNT"] == "0"
            and int(f["BOOTSTRAP_STATE_SERIAL"]) == baseline_serial
            and int(second_fields["BOOTSTRAP_STATE_SERIAL"]) == baseline_serial
            and f["RECONCILIATION"] == "EXACT_PENDING_REVIEWED_EFFECT"
            and second_fields["OLD_RECOVERY_WIF_COUNT"] == "1"
            and second_fields["NEW_RECOVERY_WIF_COUNT"] == "0"
        ):
            return "NO_EFFECT_STABLE"
    return "INCONSISTENT_EFFECT"


def c5_wif_repin_terminal_v2_body(
    successor_control_sha: str,
    activation_main: str,
    claim: dict[str, Any],
    observation_1: dict[str, Any],
    observation_2: dict[str, Any] | None = None,
) -> str:
    outcome = _c5_observation_outcome(observation_1, observation_2, claim)
    fields = {
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "C5_PROTOCOL_EPOCH_SHA256": C5_PROTOCOL_EPOCH_SHA256,
        "SUCCESSOR_CONTROL_SHA": successor_control_sha,
        "SUCCESSOR_ACTIVATION_MAIN": activation_main,
        "ATTEMPT_CLAIM_COMMENT_ID": str(claim["comment_id"]),
        "ATTEMPT_CLAIM_BODY_SHA256": claim["body_sha256"],
        "ATTEMPT_SERIES_ID_SHA256": claim["fields"]["ATTEMPT_SERIES_ID_SHA256"],
        "ATTEMPT_GENERATION": str(claim["generation"]),
        "PRECONDITION_DIGEST_SHA256": claim["fields"][
            "PRECONDITION_DIGEST_SHA256"
        ],
        "OBSERVATION_1_COMMENT_ID": str(observation_1["comment_id"]),
        "OBSERVATION_1_BODY_SHA256": observation_1["body_sha256"],
        "OBSERVATION_2_COMMENT_ID": (
            str(observation_2["comment_id"]) if observation_2 else "NONE"
        ),
        "OBSERVATION_2_BODY_SHA256": (
            observation_2["body_sha256"] if observation_2 else "NONE"
        ),
        "OUTCOME": outcome,
    }
    return "\n".join(
        ("PHASE5_SLICE_C_C5_WIF_REPIN_TERMINAL_V2",)
        + tuple(f"{name}={fields[name]}" for name in C5_TERMINAL_V2_FIELDS)
    )


def validate_c5_wif_repin_terminal(
    comments: list[dict[str, Any]],
    successor_control_sha: str,
    activation_main: str,
    terminal_comment_id: int,
) -> dict[str, Any]:
    terminal = _c5_comment_by_id(comments, terminal_comment_id, "C5_TERMINAL")
    created, body_hash = _require_unedited_owner_comment(
        terminal, GOVERNING_ISSUE, "C5_TERMINAL"
    )
    fields = _record_fields(
        str(terminal.get("body") or ""),
        "PHASE5_SLICE_C_C5_WIF_REPIN_TERMINAL_V2",
        C5_TERMINAL_V2_FIELDS,
    )
    if (
        fields["GOVERNING_ISSUE"] != "8ft0-ai/resilio#109"
        or fields["C5_PROTOCOL_EPOCH_SHA256"] != C5_PROTOCOL_EPOCH_SHA256
    ):
        raise RecoveryError("C5_TERMINAL_PROTOCOL_ROOT_MISMATCH")
    if (
        fields["SUCCESSOR_CONTROL_SHA"] != successor_control_sha
        or fields["SUCCESSOR_ACTIVATION_MAIN"] != activation_main
    ):
        raise RecoveryError("C5_TERMINAL_TARGET_MISMATCH")
    claim = _c5_parse_attempt_claim(
        _c5_comment_by_id(
            comments,
            _positive_int(
                fields["ATTEMPT_CLAIM_COMMENT_ID"], "C5_TERMINAL_CLAIM_ID"
            ),
            "C5_TERMINAL_CLAIM",
        )
    )
    if (
        claim["body_sha256"] != fields["ATTEMPT_CLAIM_BODY_SHA256"]
        or claim["fields"]["C5_PROTOCOL_EPOCH_SHA256"]
        != C5_PROTOCOL_EPOCH_SHA256
        or claim["fields"]["SUCCESSOR_CONTROL_SHA"] != successor_control_sha
        or claim["fields"]["SUCCESSOR_ACTIVATION_MAIN"] != activation_main
        or claim["fields"]["ATTEMPT_SERIES_ID_SHA256"]
        != fields["ATTEMPT_SERIES_ID_SHA256"]
        or str(claim["generation"]) != fields["ATTEMPT_GENERATION"]
        or claim["fields"]["PRECONDITION_DIGEST_SHA256"]
        != fields["PRECONDITION_DIGEST_SHA256"]
    ):
        raise RecoveryError("C5_TERMINAL_CLAIM_CHAIN_MISMATCH")
    obs1 = validate_c5_wif_repin_observation(
        _c5_comment_by_id(
            comments,
            _positive_int(
                fields["OBSERVATION_1_COMMENT_ID"], "C5_TERMINAL_OBS1_ID"
            ),
            "C5_TERMINAL_OBS1",
        ),
        successor_control_sha,
        activation_main,
        claim,
    )
    if obs1["body_sha256"] != fields["OBSERVATION_1_BODY_SHA256"]:
        raise RecoveryError("C5_TERMINAL_OBS1_HASH_MISMATCH")
    obs2 = None
    if (
        fields["OBSERVATION_2_COMMENT_ID"] != "NONE"
        or fields["OBSERVATION_2_BODY_SHA256"] != "NONE"
    ):
        if (
            fields["OBSERVATION_2_COMMENT_ID"] == "NONE"
            or fields["OBSERVATION_2_BODY_SHA256"] == "NONE"
        ):
            raise RecoveryError("C5_TERMINAL_OBS2_PARTIAL")
        obs2 = validate_c5_wif_repin_observation(
            _c5_comment_by_id(
                comments,
                _positive_int(
                    fields["OBSERVATION_2_COMMENT_ID"], "C5_TERMINAL_OBS2_ID"
                ),
                "C5_TERMINAL_OBS2",
            ),
            successor_control_sha,
            activation_main,
            claim,
        )
        if obs2["body_sha256"] != fields["OBSERVATION_2_BODY_SHA256"]:
            raise RecoveryError("C5_TERMINAL_OBS2_HASH_MISMATCH")
    derived = _c5_observation_outcome(obs1, obs2, claim)
    if fields["OUTCOME"] != derived:
        raise RecoveryError("C5_TERMINAL_OUTCOME_MISMATCH")
    if created <= (obs2 or obs1)["created_at"]:
        raise RecoveryError("C5_TERMINAL_PRECEDES_OBSERVATION")
    activation = validate_c5_activation_record(
        comments, successor_control_sha, activation_main
    )
    review = _c5_comment_by_id(
        comments,
        _positive_int(
            claim["fields"]["FRESH_REVIEW_COMMENT_ID"], "C5_TERMINAL_REVIEW_ID"
        ),
        "C5_TERMINAL_REVIEW",
    )
    authority = _c5_comment_by_id(
        comments,
        _positive_int(
            claim["fields"]["OWNER_APPLY_AUTHORITY_COMMENT_ID"],
            "C5_TERMINAL_AUTHORITY_ID",
        ),
        "C5_TERMINAL_AUTHORITY",
    )
    review_created, review_hash = _require_unedited_owner_comment(
        review, GOVERNING_ISSUE, "C5_TERMINAL_REVIEW"
    )
    authority_created, authority_hash = _require_unedited_owner_comment(
        authority, GOVERNING_ISSUE, "C5_TERMINAL_AUTHORITY"
    )
    if (
        review_hash != claim["fields"]["FRESH_REVIEW_BODY_SHA256"]
        or authority_hash != claim["fields"]["OWNER_APPLY_AUTHORITY_BODY_SHA256"]
        or not (
            activation["created_at"]
            < review_created
            < authority_created
            < claim["created_at"]
        )
    ):
        raise RecoveryError("C5_TERMINAL_AUTHORITY_CHAIN_INVALID")
    return {
        "comment_id": terminal_comment_id,
        "created_at": created,
        "body_sha256": body_hash,
        "outcome": derived,
        "observation_1": obs1,
        "observation_2": obs2,
        "claim": claim,
        "protocol_epoch_sha256": C5_PROTOCOL_EPOCH_SHA256,
    }


C5_DISPATCH_AUTHORITY_V2_FIELDS = (
    "GOVERNING_ISSUE",
    "C5_PROTOCOL_EPOCH_SHA256",
    "SUCCESSOR_CONTROL_SHA",
    "SUCCESSOR_ACTIVATION_MAIN",
    "C5_WIF_REPIN_TERMINAL_COMMENT_ID",
    "C5_WIF_REPIN_TERMINAL_BODY_SHA256",
    "C5_WIF_REPIN_TERMINAL_OUTCOME",
    "C4_DISPATCH",
    "AUTHORITY",
)


def c5_dispatch_authority_body(
    successor_control_sha: str,
    successor_activation_main: str,
    terminal_comment_id: int,
) -> str:
    comments = github_issue_comments(GOVERNING_ISSUE)
    terminal = validate_c5_wif_repin_terminal(
        comments,
        successor_control_sha,
        successor_activation_main,
        terminal_comment_id,
    )
    if terminal["outcome"] != "EFFECT_SUCCEEDED":
        raise RecoveryError("C5_DISPATCH_REQUIRES_EFFECT_SUCCEEDED")
    return "\n".join(
        (
            "PHASE5_SLICE_C_C5_DISPATCH_AUTHORITY_V2",
            "GOVERNING_ISSUE=8ft0-ai/resilio#109",
            f"C5_PROTOCOL_EPOCH_SHA256={C5_PROTOCOL_EPOCH_SHA256}",
            f"SUCCESSOR_CONTROL_SHA={successor_control_sha}",
            f"SUCCESSOR_ACTIVATION_MAIN={successor_activation_main}",
            f"C5_WIF_REPIN_TERMINAL_COMMENT_ID={terminal_comment_id}",
            f"C5_WIF_REPIN_TERMINAL_BODY_SHA256={terminal['body_sha256']}",
            "C5_WIF_REPIN_TERMINAL_OUTCOME=EFFECT_SUCCEEDED",
            "C4_DISPATCH=PERMANENTLY_FORBIDDEN",
            "AUTHORITY=DISPATCH_EXACTLY_ONE_C5_RECONCILIATION_ONLY_RECOVERY",
        )
    )


def validate_c5_dispatch_authority(
    comments: list[dict[str, Any]],
    successor_control_sha: str,
    activation_main: str,
) -> dict[str, Any]:
    candidates = [
        row
        for row in comments
        if _owner_issue_comment(row, GOVERNING_ISSUE)
        and canonical_comment_text(row.get("body")).startswith(
            "PHASE5_SLICE_C_C5_DISPATCH_AUTHORITY_V2\n"
        )
        and f"SUCCESSOR_CONTROL_SHA={successor_control_sha}"
        in canonical_comment_text(row.get("body"))
        and f"SUCCESSOR_ACTIVATION_MAIN={activation_main}"
        in canonical_comment_text(row.get("body"))
    ]
    if len(candidates) != 1:
        raise RecoveryError("C5_DISPATCH_AUTHORITY_NOT_UNIQUE")
    row = candidates[0]
    created, raw_hash = _require_unedited_owner_comment(
        row, GOVERNING_ISSUE, "C5_DISPATCH_AUTHORITY"
    )
    fields = _record_fields(
        str(row.get("body") or ""),
        "PHASE5_SLICE_C_C5_DISPATCH_AUTHORITY_V2",
        C5_DISPATCH_AUTHORITY_V2_FIELDS,
    )
    expected = {
        "GOVERNING_ISSUE": "8ft0-ai/resilio#109",
        "C5_PROTOCOL_EPOCH_SHA256": C5_PROTOCOL_EPOCH_SHA256,
        "SUCCESSOR_CONTROL_SHA": successor_control_sha,
        "SUCCESSOR_ACTIVATION_MAIN": activation_main,
        "C5_WIF_REPIN_TERMINAL_OUTCOME": "EFFECT_SUCCEEDED",
        "C4_DISPATCH": "PERMANENTLY_FORBIDDEN",
        "AUTHORITY": "DISPATCH_EXACTLY_ONE_C5_RECONCILIATION_ONLY_RECOVERY",
    }
    for key, value in expected.items():
        if fields[key] != value:
            raise RecoveryError(f"C5_DISPATCH_AUTHORITY_FIELD_MISMATCH:{key}")
    terminal_id = _positive_int(
        fields["C5_WIF_REPIN_TERMINAL_COMMENT_ID"], "C5_DISPATCH_TERMINAL_ID"
    )
    terminal = validate_c5_wif_repin_terminal(
        comments, successor_control_sha, activation_main, terminal_id
    )
    if (
        terminal["body_sha256"] != fields["C5_WIF_REPIN_TERMINAL_BODY_SHA256"]
        or terminal["outcome"] != "EFFECT_SUCCEEDED"
    ):
        raise RecoveryError("C5_DISPATCH_TERMINAL_INVALID")
    if created <= terminal["created_at"]:
        raise RecoveryError("C5_DISPATCH_AUTHORITY_PRECEDES_TERMINAL")
    return {
        "comment_id": int(row["id"]),
        "created_at": created,
        "body_sha256": raw_hash,
        "terminal": terminal,
    }


def verify_c5_github_boundary(
    activation_sha: str, control_sha: str, candidate_output: str | Path
) -> dict[str, Any]:
    _c5_require_sha(activation_sha, "C5_RUNTIME_ACTIVATION")
    _c5_require_sha(control_sha, "C5_RUNTIME_CONTROL")
    if (
        control_sha == C5_OLD_RECOVERY_CONTROL_SHA
        or control_sha in C5_FORBIDDEN_RECOVERY_CONTROL_SHAS
    ):
        raise RecoveryError("C4_DISPATCH_PERMANENTLY_FORBIDDEN")
    branch = github(f"/repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}")
    if (
        not isinstance(branch, dict)
        or branch.get("commit", {}).get("sha") != activation_sha
    ):
        raise RecoveryError("C5_RUNTIME_MAIN_MISMATCH")
    issue = github(f"/repos/{REPOSITORY}/issues/{GOVERNING_ISSUE}")
    if not isinstance(issue, dict) or issue.get("state") != "open":
        raise RecoveryError("C5_RUNTIME_GOVERNING_ISSUE_NOT_OPEN")
    comments = github_issue_comments(GOVERNING_ISSUE)
    validate_c5_governance_history(comments)
    activation = validate_c5_activation_record(
        comments, control_sha, activation_sha
    )
    dispatch = validate_c5_dispatch_authority(
        comments, control_sha, activation_sha
    )
    active = fetch_candidate(activation_sha)
    reviewed = fetch_candidate(REVIEWED_HEAD)
    if active != reviewed:
        raise RecoveryError("C5_RUNTIME_PRODUCT_CANDIDATE_DRIFT")
    Path(candidate_output).write_bytes(canonical(active) + b"\n")
    terminal = dispatch["terminal"]
    document = {
        "contract": "resilio-phase5-slice-c-c5-github-boundary/v1",
        "governing_issue": GOVERNING_ISSUE,
        "c5_protocol_epoch_sha256": C5_PROTOCOL_EPOCH_SHA256,
        "c5_architecture_closure_comment_id": C5_ARCHITECTURE_CLOSURE_COMMENT_ID,
        "control_sha": control_sha,
        "activation_sha": activation_sha,
        "activation_record_comment_id": activation["comment_id"],
        "activation_record_body_sha256": activation["body_sha256"],
        "attempt_claim_comment_id": terminal["claim"]["comment_id"],
        "attempt_claim_body_sha256": terminal["claim"]["body_sha256"],
        "terminal_comment_id": terminal["comment_id"],
        "terminal_body_sha256": terminal["body_sha256"],
        "terminal_outcome": terminal["outcome"],
        "dispatch_authority_comment_id": dispatch["comment_id"],
        "dispatch_authority_body_sha256": dispatch["body_sha256"],
        "c4_dispatch": "PERMANENTLY_FORBIDDEN",
    }
    document["governance_chain_sha256"] = sha256(canonical(document))
    return document


def verify_successor_github_boundary(
    activation_sha: str, control_sha: str, candidate_output: str | Path
) -> dict[str, Any]:
    """The existing immutable workflow command enters the C5 protocol only."""
    return verify_c5_github_boundary(activation_sha, control_sha, candidate_output)



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

    p = commands.add_parser("emit-successor-activation-merge-authority")
    p.add_argument("--control-sha", required=True)
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--reviewed-head", required=True)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--review-body-sha256", required=True)

    p = commands.add_parser("verify-successor-activation-premerge")
    p.add_argument("--control-sha", required=True)
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--reviewed-head", required=True)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--review-body-sha256", required=True)
    p.add_argument("--authority-id", required=True, type=int)

    p = commands.add_parser("emit-successor-activation-record")
    p.add_argument("--control-sha", required=True)
    p.add_argument("--activation-sha", required=True)
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--reviewed-head", required=True)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--review-body-sha256", required=True)
    p.add_argument("--authority-id", required=True, type=int)
    p.add_argument("--authority-body-sha256", required=True)

    p = commands.add_parser("verify-successor-github-boundary")
    p.add_argument("--activation-sha", required=True)
    p.add_argument("--control-sha", required=True)
    p.add_argument("--candidate-output", required=True)

    p = commands.add_parser("verify-successor-cloud-boundary")
    p.add_argument("--control-sha", required=True)

    p = commands.add_parser("successor-state-identity")
    p.add_argument("--state-json", required=True)
    p.add_argument("--generation", required=True)
    p.add_argument("--output", required=True)

    p = commands.add_parser("successor-claim")
    p.add_argument("--activation-sha", required=True)
    p.add_argument("--control-sha", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--github-boundary", required=True)

    p = commands.add_parser("verify-successor-state")
    p.add_argument("--file", required=True)

    p = commands.add_parser("verify-successor-plan")
    p.add_argument("--file", required=True)

    p = commands.add_parser("build-successor-result")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--plan-json", required=True)
    p.add_argument("--activation-sha", required=True)
    p.add_argument("--control-sha", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--github-boundary", required=True)
    p.add_argument("--private-output", required=True)
    p.add_argument("--public-output", required=True)

    p = commands.add_parser("upload-successor-result")
    p.add_argument("--control-sha", required=True)
    p.add_argument("--file", required=True)

    p = commands.add_parser("emit-c5-control-review")
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--reviewed-head", required=True)

    p = commands.add_parser("emit-c5-control-merge-authority")
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--reviewed-head", required=True)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--review-body-sha256", required=True)

    p = commands.add_parser("verify-c5-control-premerge")
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--reviewed-head", required=True)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--review-body-sha256", required=True)
    p.add_argument("--authority-id", required=True, type=int)

    p = commands.add_parser("emit-c5-control-merge-record")
    p.add_argument("--control-sha", required=True)
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--reviewed-head", required=True)
    p.add_argument("--reviewed-tree", required=True)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--review-body-sha256", required=True)
    p.add_argument("--authority-id", required=True, type=int)
    p.add_argument("--authority-body-sha256", required=True)

    p = commands.add_parser("emit-c5-activation-review")
    p.add_argument("--control-sha", required=True)
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--reviewed-head", required=True)

    p = commands.add_parser("emit-c5-activation-merge-authority")
    p.add_argument("--control-sha", required=True)
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--reviewed-head", required=True)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--review-body-sha256", required=True)

    p = commands.add_parser("verify-c5-activation-premerge")
    p.add_argument("--control-sha", required=True)
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--reviewed-head", required=True)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--review-body-sha256", required=True)
    p.add_argument("--authority-id", required=True, type=int)

    p = commands.add_parser("emit-c5-activation-record")
    p.add_argument("--control-sha", required=True)
    p.add_argument("--activation-main", required=True)
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--reviewed-head", required=True)
    p.add_argument("--reviewed-tree", required=True)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--review-body-sha256", required=True)
    p.add_argument("--authority-id", required=True, type=int)
    p.add_argument("--authority-body-sha256", required=True)

    p = commands.add_parser("emit-c5-wif-repin-review")
    p.add_argument("--successor-control-sha", required=True)
    p.add_argument("--activation-main", required=True)
    p.add_argument("--saved-plan-sha256", required=True)
    p.add_argument("--structural-manifest-sha256", required=True)
    p.add_argument("--state-lineage", required=True)
    p.add_argument("--state-serial", required=True, type=int)

    p = commands.add_parser("emit-c5-wif-repin-authority")
    p.add_argument("--successor-control-sha", required=True)
    p.add_argument("--activation-main", required=True)
    p.add_argument("--saved-plan-sha256", required=True)
    p.add_argument("--structural-manifest-sha256", required=True)
    p.add_argument("--state-lineage", required=True)
    p.add_argument("--state-serial", required=True, type=int)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--review-body-sha256", required=True)

    p = commands.add_parser("verify-c5-wif-repin-pre-effect")
    p.add_argument("--successor-control-sha", required=True)
    p.add_argument("--activation-main", required=True)
    p.add_argument("--saved-plan", required=True)
    p.add_argument("--terraform-workdir", required=True)
    p.add_argument("--structural-manifest", required=True)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--authority-id", required=True, type=int)
    p.add_argument("--posted-claim-id", type=int)
    p.add_argument("--claim-output")

    p = commands.add_parser("apply-c5-wif-repin-effect")
    p.add_argument("--successor-control-sha", required=True)
    p.add_argument("--activation-main", required=True)
    p.add_argument("--saved-plan", required=True)
    p.add_argument("--terraform-workdir", required=True)
    p.add_argument("--structural-manifest", required=True)
    p.add_argument("--review-id", required=True, type=int)
    p.add_argument("--authority-id", required=True, type=int)
    p.add_argument("--posted-claim-id", required=True, type=int)

    p = commands.add_parser("emit-c5-wif-observation")
    p.add_argument("--successor-control-sha", required=True)
    p.add_argument("--activation-main", required=True)
    p.add_argument("--attempt-claim-comment-id", required=True, type=int)
    p.add_argument("--terraform-workdir", required=True)

    p = commands.add_parser("emit-c5-wif-terminal-v2")
    p.add_argument("--successor-control-sha", required=True)
    p.add_argument("--activation-main", required=True)
    p.add_argument("--observation-1-comment-id", required=True, type=int)
    p.add_argument("--observation-2-comment-id", type=int)

    p = commands.add_parser("emit-c5-dispatch-authority-v2")
    p.add_argument("--successor-control-sha", required=True)
    p.add_argument("--activation-main", required=True)
    p.add_argument("--terminal-comment-id", required=True, type=int)

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
        elif args.command == "emit-successor-activation-merge-authority":
            print(successor_activation_merge_authority_body(
                args.control_sha, args.pr_number, args.reviewed_head,
                args.review_id, args.review_body_sha256,
            ))
        elif args.command == "verify-successor-activation-premerge":
            result = verify_successor_activation_premerge(
                args.control_sha, args.pr_number, args.reviewed_head,
                args.review_id, args.review_body_sha256, args.authority_id,
            )
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        elif args.command == "emit-successor-activation-record":
            print(successor_activation_record_body(
                args.control_sha, args.activation_sha, args.pr_number,
                args.reviewed_head, args.review_id, args.review_body_sha256,
                args.authority_id, args.authority_body_sha256,
            ))
        elif args.command == "verify-successor-github-boundary":
            result = verify_successor_github_boundary(args.activation_sha, args.control_sha, args.candidate_output)
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        elif args.command == "verify-successor-cloud-boundary":
            result = verify_successor_cloud_boundary(args.control_sha)
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        elif args.command == "successor-state-identity":
            state = strict_json(Path(args.state_json).read_bytes())
            result = successor_state_identity_from_state(state, args.generation)
            Path(args.output).write_bytes(canonical(result) + b"\n")
        elif args.command == "successor-claim":
            boundary = strict_json(Path(args.github_boundary).read_bytes())
            result = successor_create_claim(args.control_sha, args.activation_sha, args.run_id, boundary)
            print(json.dumps({key: result.get(key) for key in ("bucket", "name", "generation", "metageneration")}, sort_keys=True, separators=(",", ":")))
        elif args.command == "verify-successor-state":
            value = strict_json(Path(args.file).read_bytes())
            verify_successor_state_identity(value)
        elif args.command == "verify-successor-plan":
            value = strict_json(Path(args.file).read_bytes())
            verify_successor_no_change_plan(value)
        elif args.command == "build-successor-result":
            before = strict_json(Path(args.before).read_bytes())
            after = strict_json(Path(args.after).read_bytes())
            plan = strict_json(Path(args.plan_json).read_bytes())
            boundary = strict_json(Path(args.github_boundary).read_bytes())
            private, public = successor_build_result(before, after, plan, args.control_sha, args.activation_sha, args.run_id, boundary)
            Path(args.private_output).write_bytes(canonical(private) + b"\n")
            Path(args.public_output).write_bytes(canonical(public) + b"\n")
        elif args.command == "upload-successor-result":
            value = strict_json(Path(args.file).read_bytes())
            if value.get("contract") != "resilio-phase5-slice-c-successor-result/v1": raise RecoveryError("SUCCESSOR_RESULT_CONTRACT_INVALID")
            if value.get("control_sha") != args.control_sha: raise RecoveryError("SUCCESSOR_RESULT_CONTROL_MISMATCH")
            result = gcs_upload_once(evidence_object("result", args.control_sha), value)
            print(json.dumps({key: result.get(key) for key in ("bucket", "name", "generation", "metageneration")}, sort_keys=True, separators=(",", ":")))
        elif args.command == "emit-c5-control-review":
            print(c5_control_implementation_review_body(
                args.pr_number, args.reviewed_head
            ))
        elif args.command == "emit-c5-control-merge-authority":
            print(c5_control_merge_authority_body(
                args.pr_number, args.reviewed_head, args.review_id,
                args.review_body_sha256,
            ))
        elif args.command == "verify-c5-control-premerge":
            result = verify_c5_control_premerge(
                args.pr_number, args.reviewed_head, args.review_id,
                args.review_body_sha256, args.authority_id,
            )
            result.pop("authority_created_at", None)
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        elif args.command == "emit-c5-control-merge-record":
            currentness = verify_c5_control_use_time_currentness(
                args.control_sha, args.control_sha
            )
            print(c5_control_merge_record_body(
                args.control_sha, args.pr_number, args.reviewed_head,
                args.reviewed_tree, args.review_id, args.review_body_sha256,
                args.authority_id, args.authority_body_sha256,
                currentness["currentness_digest_sha256"],
            ))
        elif args.command == "emit-c5-activation-review":
            print(c5_activation_review_body(
                args.control_sha, args.pr_number, args.reviewed_head
            ))
        elif args.command == "emit-c5-activation-merge-authority":
            print(c5_activation_merge_authority_body(
                args.control_sha, args.pr_number, args.reviewed_head,
                args.review_id, args.review_body_sha256,
            ))
        elif args.command == "verify-c5-activation-premerge":
            result = verify_c5_activation_premerge(
                args.control_sha, args.pr_number, args.reviewed_head,
                args.review_id, args.review_body_sha256, args.authority_id,
            )
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        elif args.command == "emit-c5-activation-record":
            print(c5_activation_record_body(
                args.control_sha, args.activation_main, args.pr_number,
                args.reviewed_head, args.reviewed_tree, args.review_id,
                args.review_body_sha256, args.authority_id,
                args.authority_body_sha256,
            ))
        elif args.command == "emit-c5-wif-repin-review":
            print(c5_wif_repin_review_body(
                args.successor_control_sha, args.activation_main,
                args.saved_plan_sha256, args.structural_manifest_sha256,
                args.state_lineage, args.state_serial,
            ))
        elif args.command == "emit-c5-wif-repin-authority":
            print(c5_wif_repin_authority_body(
                args.successor_control_sha, args.activation_main,
                args.saved_plan_sha256, args.structural_manifest_sha256,
                args.state_lineage, args.state_serial, args.review_id,
                args.review_body_sha256,
            ))
        elif args.command == "verify-c5-wif-repin-pre-effect":
            result = verify_c5_wif_repin_pre_effect(
                successor_control_sha=args.successor_control_sha,
                activation_main=args.activation_main,
                saved_plan_path=args.saved_plan,
                terraform_workdir=args.terraform_workdir,
                structural_manifest_path=args.structural_manifest,
                fresh_review_comment_id=args.review_id,
                owner_apply_authority_comment_id=args.authority_id,
                posted_claim_comment_id=args.posted_claim_id,
            )
            claim_body = result.pop("attempt_claim_body")
            snapshot = result.pop("precondition_snapshot")
            if args.claim_output:
                Path(args.claim_output).write_text(claim_body, encoding="utf-8")
                result["attempt_claim_output"] = args.claim_output
            result["attempt_claim_body_sha256"] = sha256(claim_body.encode("utf-8"))
            result["precondition_snapshot_sha256"] = sha256(snapshot.encode("utf-8"))
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        elif args.command == "apply-c5-wif-repin-effect":
            result = execute_c5_wif_repin_effect(
                successor_control_sha=args.successor_control_sha,
                activation_main=args.activation_main,
                saved_plan_path=args.saved_plan,
                terraform_workdir=args.terraform_workdir,
                structural_manifest_path=args.structural_manifest,
                fresh_review_comment_id=args.review_id,
                owner_apply_authority_comment_id=args.authority_id,
                posted_claim_comment_id=args.posted_claim_id,
            )
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        elif args.command == "emit-c5-wif-observation":
            result = verify_c5_wif_repin_observation(
                successor_control_sha=args.successor_control_sha,
                activation_main=args.activation_main,
                attempt_claim_comment_id=args.attempt_claim_comment_id,
                terraform_workdir=args.terraform_workdir,
            )
            print(result["body"])
        elif args.command == "emit-c5-wif-terminal-v2":
            print(c5_terminal_body_from_observation_comments(
                args.successor_control_sha,
                args.activation_main,
                args.observation_1_comment_id,
                args.observation_2_comment_id,
            ))
        elif args.command == "emit-c5-dispatch-authority-v2":
            print(c5_dispatch_authority_body(
                args.successor_control_sha,
                args.activation_main,
                args.terminal_comment_id,
            ))
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
