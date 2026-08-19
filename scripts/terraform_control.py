#!/usr/bin/env python3
"""Trusted helpers for Resilio's bounded Phase 3 Terraform control path."""

from __future__ import annotations

import argparse, copy, hashlib, json, os, re, sys, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from typing import Any

REPO = "8ft0-ai/resilio"
CANDIDATE_PATH = "infra/foundation/resources.tf.json"
STATE_BUCKET = "resilio-control-e882d4-tfstate"
STATE_OBJECT = "foundation/default.tfstate"
EVIDENCE_PREFIX = "plan-evidence/foundation/"
SENTINEL_TYPE = "google_service_account"
SENTINEL_NAME = "phase3_terraform_sentinel"
SENTINEL_BODY = {
    "account_id": "phase3-terraform-sentinel",
    "display_name": "Phase 3 Terraform sentinel",
    "description": "Non-privileged Phase 3 Terraform control-path sentinel.",
    "project": "resilio-reference-e882d4",
    "lifecycle": {"prevent_destroy": True},
}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ContractError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict_bytes(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc


def empty_candidate_payload() -> dict[str, Any]:
    return {}


def sentinel_candidate_payload() -> dict[str, Any]:
    return {"resource": {SENTINEL_TYPE: {SENTINEL_NAME: copy.deepcopy(SENTINEL_BODY)}}}


def validate_candidate_payload(payload: Any, allow_empty: bool = True) -> str:
    if payload == {}:
        if allow_empty:
            return "empty"
        raise ContractError("empty candidate is not allowed")
    if not isinstance(payload, dict) or set(payload) != {"resource"}:
        raise ContractError("candidate must be empty or contain only top-level resource")
    if payload != sentinel_candidate_payload():
        raise ContractError("candidate is outside the exact Phase 3 sentinel grammar")
    return "sentinel"


def validate_candidate_file(path: Path, allow_empty: bool = True) -> tuple[str, dict[str, Any]]:
    payload = load_json_strict_bytes(path.read_bytes())
    return validate_candidate_payload(payload, allow_empty), payload


def plan_effect(plan: dict[str, Any]) -> dict[str, Any]:
    fmt = str(plan.get("format_version", ""))
    if not fmt.startswith("1."):
        raise ContractError(f"unsupported Terraform JSON plan format: {fmt!r}")
    changes = []
    for item in plan.get("resource_changes", []):
        changes.append({
            "address": item.get("address"),
            "mode": item.get("mode"),
            "type": item.get("type"),
            "name": item.get("name"),
            "provider_name": item.get("provider_name"),
            "change": item.get("change"),
        })
    changes.sort(key=lambda x: str(x["address"]))
    outputs = plan.get("output_changes") or {}
    return {"resource_changes": changes, "output_changes": outputs}


def state_identity(state: dict[str, Any], generation: str) -> dict[str, Any]:
    lineage = state.get("lineage")
    serial = state.get("serial")
    if not isinstance(lineage, str) or not isinstance(serial, int) or not str(generation).isdigit():
        raise ContractError("state identity is incomplete")
    return {
        "lineage_digest": sha256_bytes(lineage.encode()),
        "serial": serial,
        "generation": str(generation),
    }


def public_manifest(plan: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    effect = plan_effect(plan)
    actions = []
    for item in effect["resource_changes"]:
        actions.append({"address": item["address"], "actions": item["change"].get("actions", [])})
    output_actions = {
        name: change.get("actions", [])
        for name, change in sorted(effect["output_changes"].items())
    }
    manifest = {k: meta[k] for k in (
        "pr", "base_sha", "head_sha", "root", "terraform_version",
        "provider_lock_digest", "configuration_tree_digest",
        "state_lineage_digest", "state_serial", "state_generation",
        "workflow_run_id", "workflow_run_attempt", "policy_result", "cost_result",
    ) if k in meta}
    manifest.update({
        "resource_actions": actions,
        "output_actions": output_actions,
        "material_effect_sha256": sha256_bytes(canonical_bytes(effect)),
    })
    manifest["manifest_sha256"] = sha256_bytes(canonical_bytes(manifest))
    return manifest


def private_evidence(plan: dict[str, Any], state: dict[str, Any], generation: str, meta: dict[str, Any]) -> dict[str, Any]:
    effect = plan_effect(plan)
    ident = state_identity(state, generation)
    public_meta = dict(meta)
    public_meta.update({
        "state_lineage_digest": ident["lineage_digest"],
        "state_serial": ident["serial"],
        "state_generation": ident["generation"],
    })
    return {
        "schema": "resilio/terraform-plan-evidence/v1",
        "review": {"head_sha": meta["head_sha"], "base_sha": meta.get("base_sha", ""), "pr": meta.get("pr", 0)},
        "state": ident,
        "effect": effect,
        "effect_sha256": sha256_bytes(canonical_bytes(effect)),
        "public_manifest": public_manifest(plan, public_meta),
    }


def verify_reviewed(reviewed: dict[str, Any], plan: dict[str, Any], state: dict[str, Any], generation: str, head_sha: str) -> None:
    if reviewed.get("schema") != "resilio/terraform-plan-evidence/v1":
        raise ContractError("unsupported reviewed evidence schema")
    if reviewed.get("review", {}).get("head_sha") != head_sha:
        raise ContractError("reviewed head does not match current authorised head")
    current_state = state_identity(state, generation)
    if reviewed.get("state") != current_state:
        raise ContractError("Terraform state identity changed after review")
    effect = plan_effect(plan)
    if reviewed.get("effect") != effect or reviewed.get("effect_sha256") != sha256_bytes(canonical_bytes(effect)):
        raise ContractError("fresh main plan materially differs from reviewed effect")


def _github_json(url: str, token: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.load(res)


def fetch_candidate(ref: str, token: str, expected_blob_sha: str | None = None) -> bytes:
    if not HEX40.fullmatch(ref):
        raise ContractError("candidate ref must be an exact 40-hex commit SHA")
    url = f"https://api.github.com/repos/{REPO}/contents/{urllib.parse.quote(CANDIDATE_PATH)}?ref={ref}"
    obj = _github_json(url, token)
    if expected_blob_sha and obj.get("sha") != expected_blob_sha:
        raise ContractError("candidate blob SHA does not match expected identity")
    download = obj.get("download_url")
    if not download:
        raise ContractError("candidate download URL unavailable")
    req = urllib.request.Request(download, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as res:
        return res.read()


def _gcs_request(method: str, object_name: str, token: str, data: bytes | None = None, generation: str | None = None, create_only: bool = False) -> Any:
    quoted = urllib.parse.quote(object_name, safe="")
    media = method == "MEDIA"
    if method == "GET":
        url = f"https://storage.googleapis.com/storage/v1/b/{STATE_BUCKET}/o/{quoted}"
        if generation:
            url += "?generation=" + urllib.parse.quote(generation)
    elif method == "MEDIA":
        url = f"https://storage.googleapis.com/download/storage/v1/b/{STATE_BUCKET}/o/{quoted}?alt=media"
        if generation:
            url += "&generation=" + urllib.parse.quote(generation)
        method = "GET"
    elif method == "POST":
        q = urllib.parse.urlencode({"uploadType": "media", "name": object_name, **({"ifGenerationMatch": "0"} if create_only else {})})
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{STATE_BUCKET}/o?{q}"
    else:
        raise ContractError("unsupported GCS operation")
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raw = res.read()
            if media:
                return raw
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise ContractError(f"GCS request failed with HTTP {exc.code}") from exc


def gcs_metadata(object_name: str, token: str) -> dict[str, Any] | None:
    result = _gcs_request("GET", object_name, token)
    return result if isinstance(result, dict) else None


def gcs_upload_new(object_name: str, token: str, payload: bytes) -> dict[str, Any]:
    if not object_name.startswith(EVIDENCE_PREFIX):
        raise ContractError("private evidence object is outside approved prefix")
    result = _gcs_request("POST", object_name, token, payload, create_only=True)
    if not isinstance(result, dict):
        raise ContractError("GCS create did not return metadata")
    return result


def gcs_download(object_name: str, token: str, generation: str) -> bytes:
    if not object_name.startswith(EVIDENCE_PREFIX) or not generation.isdigit():
        raise ContractError("invalid private evidence identity")
    result = _gcs_request("MEDIA", object_name, token, generation=generation)
    if not isinstance(result, (bytes, bytearray)):
        raise ContractError("private evidence download failed")
    return bytes(result)


def _load(path: str) -> dict[str, Any]:
    value = load_json_strict_bytes(Path(path).read_bytes())
    if not isinstance(value, dict):
        raise ContractError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    v = sp.add_parser("validate-candidate"); v.add_argument("--path", required=True); v.add_argument("--require-sentinel", action="store_true")
    f = sp.add_parser("fetch-candidate"); f.add_argument("--ref", required=True); f.add_argument("--output", required=True); f.add_argument("--expected-blob-sha")
    c = sp.add_parser("canonical-effect"); c.add_argument("--plan-json", required=True); c.add_argument("--output", required=True)
    b = sp.add_parser("build-evidence")
    for x in ("plan-json", "state-json", "state-generation", "metadata-json", "private-output", "public-output"): b.add_argument("--"+x, required=True)
    q = sp.add_parser("verify-reviewed")
    for x in ("reviewed-evidence", "plan-json", "state-json", "state-generation", "reviewed-head-sha"): q.add_argument("--"+x, required=True)
    m = sp.add_parser("gcs-metadata"); m.add_argument("--object", default=STATE_OBJECT)
    a = sp.add_parser("gcs-assert-absent"); a.add_argument("--object", default=STATE_OBJECT)
    u = sp.add_parser("upload-evidence"); u.add_argument("--object", required=True); u.add_argument("--path", required=True)
    d = sp.add_parser("download-evidence"); d.add_argument("--object", required=True); d.add_argument("--generation", required=True); d.add_argument("--output", required=True)
    args = ap.parse_args()
    token = os.getenv("GCS_ACCESS_TOKEN", "")
    if args.cmd == "validate-candidate":
        kind, _ = validate_candidate_file(Path(args.path), allow_empty=not args.require_sentinel); print(f"candidate_kind={kind}")
    elif args.cmd == "fetch-candidate":
        data = fetch_candidate(args.ref, os.environ["GITHUB_TOKEN"], args.expected_blob_sha); Path(args.output).write_bytes(data); validate_candidate_file(Path(args.output))
    elif args.cmd == "canonical-effect":
        Path(args.output).write_bytes(canonical_bytes(plan_effect(_load(args.plan_json))))
    elif args.cmd == "build-evidence":
        ev = private_evidence(_load(args.plan_json), _load(args.state_json), args.state_generation, _load(args.metadata_json)); Path(args.private_output).write_bytes(canonical_bytes(ev)); Path(args.public_output).write_bytes(canonical_bytes(ev["public_manifest"]))
    elif args.cmd == "verify-reviewed":
        verify_reviewed(_load(args.reviewed_evidence), _load(args.plan_json), _load(args.state_json), args.state_generation, args.reviewed_head_sha); print("reviewed_effect_match=true")
    elif args.cmd == "gcs-metadata":
        if not token: raise ContractError("GCS_ACCESS_TOKEN is required")
        obj = gcs_metadata(args.object, token)
        if obj is None: raise ContractError("GCS object does not exist")
        print(json.dumps({"name": obj.get("name"), "generation": obj.get("generation")}, sort_keys=True))
    elif args.cmd == "gcs-assert-absent":
        if not token: raise ContractError("GCS_ACCESS_TOKEN is required")
        if gcs_metadata(args.object, token) is not None: raise ContractError("GCS object already exists")
        print("object_absent=true")
    elif args.cmd == "upload-evidence":
        if not token: raise ContractError("GCS_ACCESS_TOKEN is required")
        obj = gcs_upload_new(args.object, token, Path(args.path).read_bytes()); print(json.dumps({"name": obj.get("name"), "generation": obj.get("generation")}, sort_keys=True))
    elif args.cmd == "download-evidence":
        if not token: raise ContractError("GCS_ACCESS_TOKEN is required")
        Path(args.output).write_bytes(gcs_download(args.object, token, args.generation))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractError, KeyError, OSError, urllib.error.URLError) as exc:
        print(f"terraform-control: {exc}", file=sys.stderr)
        raise SystemExit(1)
