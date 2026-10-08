"""Credential-free Phase 5 demonstration using the real product dispatch handlers.

No network, provider adapters, IAM or cloud state. All output is deterministic.
"""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.resilio_app.core import event_from_bytes, jcs
from services.resilio_app.provider import ProviderFailure
from services.resilio_app.server import EVENT_PATH, PUSH_PATH, dispatch
from scripts.phase5_acceptance_fixture import verified_event


class FakePublisher:
    def __init__(self):
        self.messages = []

    def publish(self, raw, event_id, digest):
        message_id = f"demo-message-{len(self.messages) + 1}"
        self.messages.append({
            "messageId": message_id,
            "data": base64.b64encode(raw).decode("ascii"),
            "attributes": {"event_id": event_id, "payload_sha256": digest},
        })
        return message_id

    def envelope(self, position=-1):
        return jcs({"message": self.messages[position]})


class FakeStore:
    def __init__(self):
        self.events = {}
        self.rejections = {}
        self.reject_writes = False

    def create_event(self, event_id, canonical, digest, message_id):
        existing = self.events.get(event_id)
        if existing is not None:
            if (existing["payload_sha256"] == digest
                    and existing["observed_json"] == canonical.decode("utf-8")):
                return "SUCCESS_NEW_OR_DUPLICATE"
            return "PERMANENT_IMMUTABLE_DEPLOYMENT_CONFLICT"
        self.events[event_id] = {
            "event_id": event_id,
            "payload_sha256": digest,
            "observed_json": canonical.decode("utf-8"),
            "first_pubsub_message_id": message_id,
            "first_observed_at": "deterministic-local-fixture",
        }
        return "SUCCESS_NEW_OR_DUPLICATE"

    def read_event(self, event_id):
        return self.events.get(event_id)

    def record_rejection(self, rejection_id, code, message_id, event_id, digest, raw_sha):
        if self.reject_writes:
            raise ProviderFailure("FAKE_REJECTION_STORE_UNAVAILABLE")
        fields = (code, message_id, event_id, digest, raw_sha)
        previous = self.rejections.setdefault(rejection_id, fields)
        if previous != fields:
            raise ProviderFailure("REJECTION_ID_CONFLICT")


def demonstrate():
    event = verified_event()
    publisher, store = FakePublisher(), FakeStore()
    rows = []

    def step(name, component, method, path, body, expected_status, expected_key=None):
        status, raw = dispatch(component, method, path, body, publisher, store)
        document = json.loads(raw)
        assert status == expected_status, (name, status, document)
        if expected_key is not None:
            key, expected = expected_key
            assert document.get(key) == expected, (name, document)
        rows.append({
            "phase": name, "http_status": status, "response": document,
            "published_count": len(publisher.messages),
            "stored_count": len(store.events),
            "rejection_count": len(store.rejections),
            "assertion": "PASS",
        })
        return document

    path = EVENT_PATH + "/" + event.event_id
    step("before", "api", "GET", path, b"", 404, ("error", "NOT_FOUND"))
    assert store.events == {}

    first = step("ingest", "ingest", "POST", EVENT_PATH, event.canonical_bytes,
                 202, ("event_id", event.event_id))
    assert first["payload_sha256"] == event.payload_sha256
    assert first["message_id"] == publisher.messages[0]["messageId"]
    assert base64.b64decode(publisher.messages[0]["data"], validate=True) == event.canonical_bytes
    step("process", "processor", "POST", PUSH_PATH, publisher.envelope(), 200,
         ("status", "acknowledged"))
    result = step("read", "api", "GET", path, b"", 200, ("event_id", event.event_id))
    assert result["observed"] == event.observed
    assert result["payload_sha256"] == event.payload_sha256
    assert result["first_pubsub_message_id"] == first["message_id"]
    pristine = copy.deepcopy(store.events)
    step("read_only", "api", "GET", path, b"", 200)
    assert pristine == store.events

    replay = step("replay_ingest", "ingest", "POST", EVENT_PATH, event.canonical_bytes,
                  202, ("event_id", event.event_id))
    assert replay["message_id"] != first["message_id"]
    step("replay_process", "processor", "POST", PUSH_PATH, publisher.envelope(), 200,
         ("status", "acknowledged"))
    assert pristine == store.events and len(store.events) == 1
    step("replay_read", "api", "GET", path, b"", 200,
         ("first_pubsub_message_id", first["message_id"]))

    conflicting = copy.deepcopy(event.observed)
    conflicting["deployment"]["artifact_digest"] = "sha256:" + "a" * 64
    conflict_event = event_from_bytes(jcs(conflicting))
    assert conflict_event.event_id == event.event_id
    assert conflict_event.payload_sha256 != event.payload_sha256
    step("conflict_ingest", "ingest", "POST", EVENT_PATH, conflict_event.canonical_bytes, 202)
    conflict = step("conflict_process", "processor", "POST", PUSH_PATH,
                    publisher.envelope(), 200, ("status", "rejected"))
    assert conflict["rejection_id"] in store.rejections
    assert store.rejections[conflict["rejection_id"]][0] == "PERMANENT_IMMUTABLE_DEPLOYMENT_CONFLICT"
    assert pristine == store.events

    published_before = len(publisher.messages)
    step("invalid_ingest", "ingest", "POST", EVENT_PATH, b"{}", 400)
    assert published_before == len(publisher.messages)
    invalid = step("invalid_push", "processor", "POST", PUSH_PATH,
                   b"invalid-push-envelope", 200, ("status", "rejected"))
    assert invalid["rejection_id"] in store.rejections
    assert len(store.rejections) == 2 and pristine == store.events

    store.reject_writes = True
    step("rejection_store_failure", "processor", "POST", PUSH_PATH,
         b"another-invalid-envelope", 503, ("error", "REJECTION_WRITE_FAILED"))
    assert len(store.rejections) == 2
    step("api_write_forbidden", "api", "POST", EVENT_PATH, event.canonical_bytes,
         404, ("error", "ROUTE_NOT_FOUND"))
    assert pristine == store.events

    return {
        "scope": "LOCAL_FAKE_PROVIDER_ONLY",
        "live_provider_acceptance": False,
        "event_id": event.event_id,
        "payload_sha256": event.payload_sha256,
        "first_message_id": first["message_id"],
        "replay_message_id": replay["message_id"],
        "steps": rows,
        "final_stored_count": len(store.events),
        "final_rejection_count": len(store.rejections),
        "result": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(demonstrate(), sort_keys=True, separators=(",", ":")))
