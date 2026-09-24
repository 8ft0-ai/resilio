"""Phase 5 deployment-observed v1: dependency-free, deterministic product contract.

All domain identity and canonicalisation are pure. No provider client is imported.
The accepted v1 schema contains only strings, arrays, objects and the integer 1;
the serializer is RFC 8785 JCS for that deliberately bounded type subset.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

MAX_EVENT_BYTES = 32768
MAX_EVIDENCE = 8
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class PermanentFailure(ValueError):
    """A deterministic negative result; never acknowledge before recording it."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, entry in pairs:
        if key in value:
            raise PermanentFailure("DUPLICATE_JSON_KEY")
        value[key] = entry
    return value


def _reject_number(_: str) -> None:
    raise PermanentFailure("UNSUPPORTED_NUMBER")


def strict_json(raw: bytes) -> Any:
    if len(raw) > MAX_EVENT_BYTES:
        raise PermanentFailure("PAYLOAD_TOO_LARGE")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys,
                          parse_float=_reject_number, parse_constant=_reject_number)
    except UnicodeDecodeError as exc:
        raise PermanentFailure("INVALID_UTF8") from exc
    except json.JSONDecodeError as exc:
        raise PermanentFailure("INVALID_JSON") from exc


def _fields(value: Any, required: set[str], optional: set[str] | None = None) -> None:
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - (optional or set()):
        raise PermanentFailure("SCHEMA_FIELDS_INVALID")


def _text(value: Any, limit: int, pattern: re.Pattern[str] | None = None) -> str:
    if (type(value) is not str or not value or len(value.encode("utf-8", errors="surrogatepass")) > limit
            or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
            or (pattern is not None and not pattern.fullmatch(value))):
        raise PermanentFailure("SCHEMA_VALUE_INVALID")
    return value


def validate(observed: Any) -> dict[str, Any]:
    _fields(observed, {"schema_version", "event_type", "service", "environment",
                       "change", "deployment", "evidence"})
    if type(observed["schema_version"]) is not int or observed["schema_version"] != 1:
        raise PermanentFailure("SCHEMA_VERSION_UNSUPPORTED")
    if observed["event_type"] != "deployment.observed":
        raise PermanentFailure("EVENT_TYPE_UNSUPPORTED")
    _fields(observed["service"], {"id"})
    _fields(observed["environment"], {"id"})
    _text(observed["service"]["id"], 128, IDENTIFIER)
    _text(observed["environment"]["id"], 128, IDENTIFIER)
    _fields(observed["change"], {"repository", "source_sha"})
    _text(observed["change"]["repository"], 256, REPOSITORY)
    _text(observed["change"]["source_sha"], 40, HEX40)
    deployment = observed["deployment"]
    _fields(deployment, {"id", "release_id", "artifact_digest", "runtime"})
    _text(deployment["id"], 128, IDENTIFIER)
    _text(deployment["release_id"], 128, IDENTIFIER)
    _text(deployment["artifact_digest"], 71, DIGEST)
    runtime = deployment["runtime"]
    _fields(runtime, {"provider", "kind", "resource_id"})
    _text(runtime["provider"], 64, IDENTIFIER)
    _text(runtime["kind"], 64, IDENTIFIER)
    _text(runtime["resource_id"], 512)
    evidence = observed["evidence"]
    if type(evidence) is not list or not 1 <= len(evidence) <= MAX_EVIDENCE:
        raise PermanentFailure("EVIDENCE_COUNT_INVALID")
    seen: set[tuple[str, str, str]] = set()
    for item in evidence:
        _fields(item, {"kind", "ref"}, {"sha256"})
        kind = _text(item["kind"], 64, IDENTIFIER)
        ref = _text(item["ref"], 1024)
        digest = _text(item["sha256"], 64, HEX64) if "sha256" in item else ""
        identity = (kind, ref, digest)
        if identity in seen:
            raise PermanentFailure("DUPLICATE_EVIDENCE")
        seen.add(identity)
    # Sorting is intentionally part of the canonical payload contract, not identity.
    return {**observed, "evidence": sorted(evidence,
                                            key=lambda x: (x["kind"], x["ref"], x.get("sha256", "")))}


def jcs(value: Any) -> bytes:
    """RFC 8785 for v1's bounded JSON type set (no arbitrary JSON numbers)."""
    if type(value) is dict:
        keys = sorted(value, key=lambda key: key.encode("utf-16-be"))
        return b"{" + b",".join(jcs(key) + b":" + jcs(value[key]) for key in keys) + b"}"
    if type(value) is list:
        return b"[" + b",".join(jcs(item) for item in value) + b"]"
    if type(value) is str:
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise PermanentFailure("INVALID_UNICODE_SCALAR")
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if type(value) is int and value == 1:
        return b"1"
    raise PermanentFailure("UNSUPPORTED_CANONICAL_VALUE")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class Event:
    observed: dict[str, Any]
    canonical_bytes: bytes
    event_id: str
    payload_sha256: str


def event_from_bytes(raw: bytes, *, require_canonical: bool = False) -> Event:
    observed = validate(strict_json(raw))
    canonical = jcs(observed)
    if len(canonical) > MAX_EVENT_BYTES:
        raise PermanentFailure("CANONICAL_PAYLOAD_TOO_LARGE")
    if require_canonical and raw != canonical:
        raise PermanentFailure("NON_CANONICAL_PAYLOAD")
    projection = {
        "event_type": "deployment.observed",
        "service_id": observed["service"]["id"],
        "environment_id": observed["environment"]["id"],
        "deployment_id": observed["deployment"]["id"],
    }
    event_id = sha256(b"resilio:event-id:v1\n" + jcs(projection))
    return Event(observed, canonical, event_id, sha256(canonical))
