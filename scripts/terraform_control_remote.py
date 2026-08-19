"""GitHub/GCS transport helpers for the trusted Terraform control path."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from terraform_control_core import *


def _request_json(url: str, *, token: str | None = None, method: str = "GET", data: bytes | None = None,
                  content_type: str | None = None) -> tuple[Any, Any]:
    headers = {"Accept": "application/json", "User-Agent": "resilio-terraform-control/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=30)
    except urllib.error.HTTPError as exc:
        body = exc.read(1024).decode("utf-8", "replace")
        raise ControlError(f"HTTP_{exc.code}:{body[:256]}") from exc
    except urllib.error.URLError as exc:
        raise ControlError("NETWORK_ERROR") from exc
    raw = response.read()
    if not raw:
        return None, response
    try:
        return json.loads(raw), response
    except json.JSONDecodeError as exc:
        raise ControlError("INVALID_HTTP_JSON") from exc


def _github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise ControlError("GITHUB_TOKEN_REQUIRED")
    return token


def _github_api(path: str) -> Any:
    return _request_json(f"https://api.github.com{path}", token=_github_token())[0]


def fetch_candidate(repository: str, sha: str, output: Path) -> dict[str, Any]:
    if repository != REPOSITORY or not FULL_SHA.fullmatch(sha):
        raise ControlError("CANDIDATE_IDENTITY_INVALID")
    encoded = urllib.parse.quote(CANDIDATE_PATH, safe="/")
    payload = _github_api(f"/repos/{repository}/contents/{encoded}?ref={sha}")
    if not isinstance(payload, dict) or payload.get("type") != "file" or payload.get("path") != CANDIDATE_PATH:
        raise ControlError("CANDIDATE_PATH_MISMATCH")
    if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
        raise ControlError("CANDIDATE_CONTENT_ENCODING_INVALID")
    try:
        raw = base64.b64decode(payload["content"])
    except ValueError as exc:
        raise ControlError("CANDIDATE_BASE64_INVALID") from exc
    canonical = canonical_json_bytes(validate_candidate_document(load_json_strict_bytes(raw))) + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical)
    return {"repository": repository, "sha": sha, "path": CANDIDATE_PATH,
            "blob_sha": payload.get("sha"), "canonical_sha256": sha256_bytes(canonical)}


def verify_pr(*, repository: str, pr_number: int, head_sha: str, base_sha: str, require_open: bool,
              require_merged: bool, allowed_files: Iterable[str], expected_merge_sha: str | None = None) -> dict[str, Any]:
    if repository != REPOSITORY or pr_number <= 0 or not FULL_SHA.fullmatch(head_sha) or not FULL_SHA.fullmatch(base_sha):
        raise ControlError("PR_IDENTITY_INVALID")
    if expected_merge_sha is not None and not FULL_SHA.fullmatch(expected_merge_sha):
        raise ControlError("INVALID_MERGE_SHA")
    pr = _github_api(f"/repos/{repository}/pulls/{pr_number}")
    if not isinstance(pr, dict):
        raise ControlError("PR_RESPONSE_INVALID")
    if pr.get("base", {}).get("ref") != DEFAULT_BRANCH or pr.get("base", {}).get("sha") != base_sha:
        raise ControlError("PR_BASE_MISMATCH")
    if pr.get("head", {}).get("sha") != head_sha:
        raise ControlError("PR_HEAD_SHA_MISMATCH")
    head_repo = pr.get("head", {}).get("repo", {})
    if head_repo.get("id") != REPOSITORY_ID or head_repo.get("full_name") != REPOSITORY:
        raise ControlError("PR_HEAD_REPOSITORY_MISMATCH")
    if require_open and pr.get("state") != "open":
        raise ControlError("PR_NOT_OPEN")
    if require_merged and pr.get("merged_at") is None:
        raise ControlError("PR_NOT_MERGED")
    if expected_merge_sha is not None and pr.get("merge_commit_sha") != expected_merge_sha:
        raise ControlError("PR_MERGE_SHA_MISMATCH")
    files: list[str] = []
    for page in range(1, 21):
        rows = _github_api(f"/repos/{repository}/pulls/{pr_number}/files?per_page=100&page={page}")
        if not isinstance(rows, list):
            raise ControlError("PR_FILES_RESPONSE_INVALID")
        files.extend(str(row.get("filename")) for row in rows if isinstance(row, dict))
        if len(rows) < 100:
            break
    else:
        raise ControlError("PR_FILE_PAGINATION_EXCEEDED")
    if sorted(files) != sorted(set(allowed_files)):
        raise ControlError("PR_FILE_SET_MISMATCH:" + ",".join(sorted(files)))
    return {"number": pr_number, "head_sha": head_sha, "base_sha": base_sha, "files": sorted(files)}


def verify_main(repository: str, expected_sha: str) -> str:
    if repository != REPOSITORY or not FULL_SHA.fullmatch(expected_sha):
        raise ControlError("MAIN_IDENTITY_INVALID")
    branch = _github_api(f"/repos/{repository}/branches/{DEFAULT_BRANCH}")
    if not isinstance(branch, dict) or branch.get("commit", {}).get("sha") != expected_sha:
        raise ControlError("MAIN_SHA_MISMATCH")
    return expected_sha


def _gcs_token() -> str:
    token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN", "")
    if not token:
        raise ControlError("GOOGLE_OAUTH_ACCESS_TOKEN_REQUIRED")
    return token


def _gcs_url(bucket: str, object_name: str, *, download: bool = False) -> str:
    encoded = urllib.parse.quote(object_name, safe="")
    prefix = "https://storage.googleapis.com/download/storage/v1" if download else "https://storage.googleapis.com/storage/v1"
    suffix = "?alt=media" if download else ""
    return f"{prefix}/b/{bucket}/o/{encoded}{suffix}"


def gcs_metadata(bucket: str, object_name: str, allow_absent: bool = False) -> dict[str, Any] | None:
    try:
        return _request_json(_gcs_url(bucket, object_name), token=_gcs_token())[0]
    except ControlError as exc:
        if allow_absent and str(exc).startswith("HTTP_404"):
            return None
        raise


def gcs_upload_json_once(bucket: str, object_name: str, value: dict[str, Any]) -> dict[str, Any]:
    if not SAFE_EVIDENCE_OBJECT.fullmatch(object_name):
        raise ControlError("EVIDENCE_OBJECT_INVALID")
    query = urllib.parse.urlencode({"uploadType": "media", "name": object_name, "ifGenerationMatch": "0"})
    url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o?{query}"
    payload = canonical_json_bytes(value) + b"\n"
    metadata = _request_json(url, token=_gcs_token(), method="POST", data=payload, content_type="application/json")[0]
    if not isinstance(metadata, dict) or metadata.get("name") != object_name:
        raise ControlError("GCS_UPLOAD_IDENTITY_MISMATCH")
    return metadata


def gcs_download_json(bucket: str, object_name: str) -> dict[str, Any]:
    if not SAFE_EVIDENCE_OBJECT.fullmatch(object_name):
        raise ControlError("EVIDENCE_OBJECT_INVALID")
    request = urllib.request.Request(_gcs_url(bucket, object_name, download=True),
                                     headers={"Authorization": f"Bearer {_gcs_token()}", "User-Agent": "resilio-terraform-control/1"})
    try:
        raw = urllib.request.urlopen(request, timeout=30).read()
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise ControlError("GCS_DOWNLOAD_FAILED") from exc
    value = load_json_strict_bytes(raw)
    if not isinstance(value, dict):
        raise ControlError("PRIVATE_EVIDENCE_INVALID")
    return value
