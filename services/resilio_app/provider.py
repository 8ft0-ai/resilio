"""Narrow Cloud Run adapters; no credentials or network activity at import time.

Service identities, endpoint names and resource permissions are enforced by the
future bootstrap/IAM activation; these adapters never grant authority.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PROJECT = "resilio-reference-e882d4"
TOPIC = f"projects/{PROJECT}/topics/resilio-deployment-events"
DATABASE = "(default)"
METADATA_TOKEN = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"


class ProviderFailure(RuntimeError):
    pass


class AlreadyExists(ProviderFailure):
    pass


class NotFound(ProviderFailure):
    pass


def _token() -> str:
    req = Request(METADATA_TOKEN, headers={"Metadata-Flavor": "Google"})
    try:
        with urlopen(req, timeout=5) as response:
            value = json.load(response).get("access_token")
    except (OSError, ValueError) as exc:
        raise ProviderFailure("METADATA_TOKEN_UNAVAILABLE") from exc
    if not isinstance(value, str) or not value:
        raise ProviderFailure("METADATA_TOKEN_INVALID")
    return value


def _call(method: str, url: str, data: dict | None = None) -> dict:
    payload = json.dumps(data, separators=(",", ":")).encode() if data is not None else None
    req = Request(url, data=payload, method=method, headers={
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    })
    try:
        with urlopen(req, timeout=15) as response:
            result = json.load(response)
    except HTTPError as exc:
        if exc.code == 409:
            raise AlreadyExists("DOCUMENT_ALREADY_EXISTS") from exc
        if exc.code == 404:
            raise NotFound("DOCUMENT_NOT_FOUND") from exc
        raise ProviderFailure(f"GOOGLE_API_STATUS_{exc.code}") from exc
    except (OSError, ValueError, URLError) as exc:
        raise ProviderFailure("GOOGLE_API_UNAVAILABLE") from exc
    if not isinstance(result, dict):
        raise ProviderFailure("GOOGLE_API_RESPONSE_INVALID")
    return result


class Publisher:
    def publish(self, canonical: bytes, event_id: str, payload_sha256: str) -> str:
        result = _call("POST", f"https://pubsub.googleapis.com/v1/{TOPIC}:publish", {
            "messages": [{
                "data": base64.b64encode(canonical).decode("ascii"),
                "attributes": {"event_id": event_id, "payload_sha256": payload_sha256},
            }],
        })
        values = result.get("messageIds")
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str) or not values[0]:
            raise ProviderFailure("PUBSUB_MESSAGE_ID_INVALID")
        return values[0]


class Store:
    """Firestore REST create-if-absent: the first canonical observed event wins."""

    ROOT = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/{DATABASE}/documents"

    @classmethod
    def _get(cls, collection: str, doc_id: str) -> dict | None:
        try:
            value = _call("GET", f"{cls.ROOT}/{collection}/{quote(doc_id, safe='')}")
        except NotFound:
            return None
        fields = value.get("fields")
        if not isinstance(fields, dict):
            raise ProviderFailure("FIRESTORE_READ_SHAPE_INVALID")
        result: dict[str, str] = {}
        for key, item in fields.items():
            if not isinstance(item, dict) or not isinstance(item.get("stringValue"), str):
                raise ProviderFailure("FIRESTORE_FIELD_INVALID")
            result[key] = item["stringValue"]
        return result

    @classmethod
    def _create_or_reconcile(cls, collection: str, doc_id: str, fields: dict[str, str],
                             compare: tuple[str, ...]) -> bool:
        url = f"{cls.ROOT}/{collection}?documentId={quote(doc_id, safe='')}"
        document = {"fields": {name: {"stringValue": value} for name, value in fields.items()}}
        try:
            _call("POST", url, document)
            return True
        except AlreadyExists:
            existing = cls._get(collection, doc_id)
            if existing is None:
                raise ProviderFailure("FIRESTORE_CREATE_READ_RACE")
            if any(existing.get(key) != fields[key] for key in compare):
                return False
            return True

    def read_event(self, event_id: str) -> dict | None:
        return self._get("deployment_events", event_id)

    def create_event(self, event_id: str, canonical: bytes, digest: str,
                     message_id: str) -> str:
        if (not isinstance(message_id, str) or not message_id or len(message_id) > 128
                or any(ord(c) > 127 or ord(c) < 33 for c in message_id)):
            raise ProviderFailure("PUBSUB_MESSAGE_ID_INVALID")
        fields = {
            "event_id": event_id,
            "payload_sha256": digest,
            "observed_json": canonical.decode("utf-8"),
            "first_pubsub_message_id": message_id,
            "first_observed_at": datetime.now(timezone.utc).isoformat(),
        }
        if self._create_or_reconcile("deployment_events", event_id, fields,
                                     ("event_id", "payload_sha256", "observed_json")):
            return "SUCCESS_NEW_OR_DUPLICATE"
        return "PERMANENT_IMMUTABLE_DEPLOYMENT_CONFLICT"

    def record_rejection(self, rejection_id: str, code: str, message_id: str,
                         event_id: str, payload_sha256: str, raw_request_sha256: str) -> None:
        fields = {
            "rejection_code": code, "pubsub_message_id": message_id,
            "event_id": event_id, "payload_sha256": payload_sha256,
            "raw_request_sha256": raw_request_sha256,
            "first_observed_at": datetime.now(timezone.utc).isoformat(),
        }
        if not self._create_or_reconcile(
            "deployment_event_rejections", rejection_id, fields,
            ("rejection_code", "pubsub_message_id", "event_id",
             "payload_sha256", "raw_request_sha256"),
        ):
            raise ProviderFailure("REJECTION_ID_CONFLICT")
