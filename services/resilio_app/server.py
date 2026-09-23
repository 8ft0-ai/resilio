"""Private HTTP entrypoint for ingest, processor and read-only API.

Cloud Run IAM provides the authentication boundary. Per-service principals,
not RESILIO_COMPONENT, enforce independent publish/write/read capabilities.
"""
from __future__ import annotations

import base64
import binascii
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from typing import Any

from resilio_app.core import (
    MAX_EVENT_BYTES, PermanentFailure, _reject_duplicate_keys,
    _reject_number, event_from_bytes, jcs, sha256,
)
from resilio_app.provider import PROJECT, ProviderFailure, Publisher, Store


COMPONENTS = {"ingest", "processor", "api"}
EVENT_PATH = "/v1/deployments"
PUSH_PATH = "/internal/pubsub/deployment-events"
EVENT_READ = re.compile(r"/v1/deployments/([0-9a-f]{64})\Z")
MAX_PUSH_BYTES = 65536


def configured_component() -> str:
    component = os.environ.get("RESILIO_COMPONENT", "")
    if component not in COMPONENTS:
        raise RuntimeError("RESILIO_COMPONENT_UNKNOWN")
    if os.environ.get("GOOGLE_CLOUD_PROJECT") != PROJECT:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT_MISMATCH")
    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        raise RuntimeError("SERVICE_ACCOUNT_KEY_PATH_FORBIDDEN")
    return component


def _json_response(code: int, document: dict[str, Any]) -> tuple[int, bytes]:
    return code, jcs(document)


def _rejection_id(message_id: str, request: bytes) -> str:
    if message_id:
        return sha256(b"resilio:pubsub-rejection:v1\n" + message_id.encode("utf-8"))
    return sha256(b"resilio:raw-rejection:v1\n" + bytes.fromhex(sha256(request)))


def _message(raw: bytes) -> tuple[bytes, str, dict[str, str]]:
    if len(raw) > MAX_PUSH_BYTES:
        raise PermanentFailure("PUSH_PAYLOAD_TOO_LARGE")
    try:
        outer = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys,
                           parse_float=_reject_number, parse_constant=_reject_number)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PermanentFailure("PUSH_ENVELOPE_INVALID") from exc
    if type(outer) is not dict or set(outer) - {"message", "subscription"} or "message" not in outer:
        raise PermanentFailure("PUSH_ENVELOPE_INVALID")
    msg = outer["message"]
    if type(msg) is not dict or "data" not in msg or set(msg) - {
        "data", "messageId", "message_id", "publishTime", "attributes", "orderingKey",
    }:
        raise PermanentFailure("PUSH_MESSAGE_INVALID")
    mid = msg.get("messageId", msg.get("message_id", ""))
    if type(mid) is not str or len(mid) > 128 or any(ord(c) > 127 or ord(c) < 33 for c in mid):
        raise PermanentFailure("PUSH_MESSAGE_ID_INVALID")
    attributes = msg.get("attributes", {})
    if type(attributes) is not dict or set(attributes) - {"event_id", "payload_sha256"}:
        raise PermanentFailure("PUSH_ATTRIBUTES_INVALID")
    if any(type(value) is not str for value in attributes.values()):
        raise PermanentFailure("PUSH_ATTRIBUTES_INVALID")
    encoded = msg["data"]
    if type(encoded) is not str:
        raise PermanentFailure("PUSH_DATA_INVALID")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PermanentFailure("PUSH_DATA_INVALID") from exc
    if len(payload) > MAX_EVENT_BYTES:
        raise PermanentFailure("PUSH_DATA_TOO_LARGE")
    return payload, mid, attributes


def dispatch(component: str, method: str, path: str, body: bytes,
             publisher: Publisher | None = None, store: Store | None = None) -> tuple[int, bytes]:
    if method == "GET" and path == "/health":
        return _json_response(200, {"status": "ok"})
    if component == "ingest" and method == "POST" and path == EVENT_PATH:
        try:
            event = event_from_bytes(body)
        except PermanentFailure as exc:
            return _json_response(400, {"error": exc.code})
        assert publisher is not None
        try:
            message_id = publisher.publish(event.canonical_bytes, event.event_id, event.payload_sha256)
        except ProviderFailure:
            return _json_response(503, {"error": "PUBLISH_UNAVAILABLE"})
        return _json_response(202, {"event_id": event.event_id, "message_id": message_id,
                                    "payload_sha256": event.payload_sha256})
    if component == "processor" and method == "POST" and path == PUSH_PATH:
        assert store is not None
        mid = ""
        event_id = ""
        payload_sha256 = ""
        try:
            canonical, mid, attributes = _message(body)
            event = event_from_bytes(canonical, require_canonical=True)
            event_id, payload_sha256 = event.event_id, event.payload_sha256
            if ((attributes.get("event_id") is not None and attributes["event_id"] != event.event_id)
                    or (attributes.get("payload_sha256") is not None
                        and attributes["payload_sha256"] != event.payload_sha256)):
                raise PermanentFailure("PERMANENT_IDENTITY_MISMATCH")
            result = store.create_event(event.event_id, event.canonical_bytes, event.payload_sha256)
            if result == "PERMANENT_IMMUTABLE_DEPLOYMENT_CONFLICT":
                raise PermanentFailure(result)
            if result != "SUCCESS_NEW_OR_DUPLICATE":
                raise ProviderFailure("UNKNOWN_STORE_RESULT")
            return _json_response(200, {"status": "acknowledged"})
        except PermanentFailure as exc:
            rejection_id = _rejection_id(mid, body)
            try:
                store.record_rejection(rejection_id, exc.code, mid, event_id,
                                       payload_sha256, sha256(body))
            except ProviderFailure:
                return _json_response(503, {"error": "REJECTION_WRITE_FAILED"})
            return _json_response(200, {"status": "rejected", "rejection_id": rejection_id})
        except ProviderFailure:
            return _json_response(503, {"error": "PROVIDER_RETRYABLE"})
    if component == "api" and method == "GET":
        match = EVENT_READ.fullmatch(path)
        if match:
            assert store is not None
            try:
                record = store.read_event(match.group(1))
            except ProviderFailure:
                return _json_response(503, {"error": "READ_UNAVAILABLE"})
            if record is None:
                return _json_response(404, {"error": "NOT_FOUND"})
            if record.get("event_id") != match.group(1) or not isinstance(record.get("observed_json"), str):
                return _json_response(503, {"error": "STATE_INTEGRITY_FAILURE"})
            try:
                event = event_from_bytes(record["observed_json"].encode(), require_canonical=True)
            except PermanentFailure:
                return _json_response(503, {"error": "STATE_INTEGRITY_FAILURE"})
            if event.event_id != match.group(1) or record.get("payload_sha256") != event.payload_sha256:
                return _json_response(503, {"error": "STATE_INTEGRITY_FAILURE"})
            return _json_response(200, {"event_id": event.event_id,
                                        "payload_sha256": event.payload_sha256,
                                        "observed": event.observed,
                                        "first_observed_at": record.get("first_observed_at", "")})
    return _json_response(404, {"error": "ROUTE_NOT_FOUND"})


def main() -> None:
    component = configured_component()
    port = int(os.environ["PORT"])
    if not 1 <= port <= 65535:
        raise RuntimeError("PORT_INVALID")
    publisher = Publisher() if component == "ingest" else None
    store = Store() if component in {"processor", "api"} else None

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            length = self.headers.get("Content-Length", "0")
            if not length.isdecimal() or int(length) > MAX_PUSH_BYTES:
                self.send_error(413)
                return
            data = self.rfile.read(int(length))
            try:
                code, response = dispatch(component, self.command, self.path, data, publisher, store)
            except Exception:  # Unknown failures stay retryable; never log source payloads.
                code, response = _json_response(503, {"error": "INTERNAL_RETRYABLE"})
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def do_GET(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def log_message(self, fmt: str, *args: object) -> None:
            return

    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
