"""Phase 5 credential-free contract and HTTP handler tests."""
import base64
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.resilio_app.core import PermanentFailure, event_from_bytes, jcs, sha256
from services.resilio_app.provider import ProviderFailure
from services.resilio_app.server import (
    EVENT_PATH, PUSH_PATH, _rejection_id, configured_component, dispatch,
)
from scripts.phase5_acceptance_fixture import verified_event


class MemoryStore:
    def __init__(self):
        self.events = {}
        self.rejections = {}
        self.fail = False

    def create_event(self, event_id, canonical, digest, message_id):
        if self.fail:
            raise ProviderFailure("STORE_DOWN")
        existing = self.events.get(event_id)
        if existing:
            if existing["payload_sha256"] == digest and existing["observed_json"] == canonical.decode():
                return "SUCCESS_NEW_OR_DUPLICATE"
            return "PERMANENT_IMMUTABLE_DEPLOYMENT_CONFLICT"
        self.events[event_id] = {
            "event_id": event_id, "payload_sha256": digest,
            "observed_json": canonical.decode(), "first_pubsub_message_id": message_id,
            "first_observed_at": "original"
        }
        return "SUCCESS_NEW_OR_DUPLICATE"

    def read_event(self, event_id):
        if self.fail:
            raise ProviderFailure("STORE_DOWN")
        return self.events.get(event_id)

    def record_rejection(self, rejection_id, code, mid, event_id, digest, raw_sha):
        if self.fail:
            raise ProviderFailure("STORE_DOWN")
        value = (code, mid, event_id, digest, raw_sha)
        old = self.rejections.setdefault(rejection_id, value)
        if old != value:
            raise ProviderFailure("REJECTION_ID_CONFLICT")


class Publisher:
    def __init__(self):
        self.calls = []
        self.fail = False

    def publish(self, raw, event_id, digest):
        if self.fail:
            raise ProviderFailure("PUBSUB_DOWN")
        self.calls.append((raw, event_id, digest))
        return "msg-1"


def push(event, mid="1234", attrs=True, data=None):
    msg = {"messageId": mid, "data": base64.b64encode(
        event.canonical_bytes if data is None else data).decode()}
    if attrs:
        msg["attributes"] = {"event_id": event.event_id, "payload_sha256": event.payload_sha256}
    return jcs({"message": msg})


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.event = verified_event()
        self.store = MemoryStore()
        self.publisher = Publisher()

    def test_exact_phase4_identity_vector(self):
        self.assertEqual(self.event.event_id, "1e3f7b39b9ae97578982e42e557744345eb7af1ad82257c076a03eac36ca4494")
        self.assertEqual(self.event.payload_sha256, sha256(self.event.canonical_bytes))
        self.assertEqual(self.event_from(self.event.observed).canonical_bytes, self.event.canonical_bytes)

    @staticmethod
    def event_from(observed):
        return event_from_bytes(jcs(observed))

    def test_evidence_order_is_not_identity(self):
        a = copy.deepcopy(self.event.observed)
        a["evidence"].reverse()
        self.assertEqual(self.event_from(a), self.event)

    def test_payload_fact_change_never_bypasses_deployment_key(self):
        a = copy.deepcopy(self.event.observed)
        a["deployment"]["artifact_digest"] = "sha256:" + "a" * 64
        changed = self.event_from(a)
        self.assertEqual(changed.event_id, self.event.event_id)
        self.assertNotEqual(changed.payload_sha256, self.event.payload_sha256)

    def test_closed_schema_duplicate_keys_bad_digest_unsupported_version(self):
        invalids = [
            b'{"schema_version":1,"schema_version":1}',
            b'{"schema_version":1,"schema_version":1.0}',
        ]
        for raw in invalids:
            with self.assertRaises(PermanentFailure):
                event_from_bytes(raw)
        for field, value in [("schema_version", 2), ("event_type", "other")]:
            a = copy.deepcopy(self.event.observed)
            a[field] = value
            with self.assertRaises(PermanentFailure):
                self.event_from(a)
        a = copy.deepcopy(self.event.observed)
        a["new_field"] = "not accepted"
        with self.assertRaises(PermanentFailure):
            self.event_from(a)
        a = copy.deepcopy(self.event.observed)
        a["change"]["source_sha"] = "bad"
        with self.assertRaises(PermanentFailure):
            self.event_from(a)
        a = copy.deepcopy(self.event.observed)
        a["deployment"]["artifact_digest"] = "sha256:bad"
        with self.assertRaises(PermanentFailure):
            self.event_from(a)
        a = copy.deepcopy(self.event.observed)
        a["evidence"].append(a["evidence"][0])
        with self.assertRaises(PermanentFailure):
            self.event_from(a)

    def test_reject_noncanonical_processor_payload(self):
        raw = json.dumps(self.event.observed, indent=2).encode()
        with self.assertRaises(PermanentFailure) as cm:
            event_from_bytes(raw, require_canonical=True)
        self.assertEqual(cm.exception.code, "NON_CANONICAL_PAYLOAD")

    def test_ingest_exact_bytes_only_no_state(self):
        code, out = dispatch("ingest", "POST", EVENT_PATH, self.event.canonical_bytes,
                             self.publisher, self.store)
        self.assertEqual(code, 202)
        self.assertEqual(len(self.publisher.calls), 1)
        self.assertEqual(self.publisher.calls[0][0], self.event.canonical_bytes)
        self.assertEqual(self.store.events, {})
        self.assertEqual(json.loads(out)["event_id"], self.event.event_id)
        code, _ = dispatch("ingest", "POST", EVENT_PATH, b"{}", self.publisher, self.store)
        self.assertEqual(code, 400)
        self.assertEqual(len(self.publisher.calls), 1)

    def test_replay_identical_and_api_read_only(self):
        for packet in (push(self.event, "first-message"), push(self.event, "replay-message")):
            code, _ = dispatch("processor", "POST", PUSH_PATH, packet, self.publisher, self.store)
            self.assertEqual(code, 200)
        self.assertEqual(len(self.store.events), 1)
        first = self.store.events[self.event.event_id].copy()
        self.assertEqual(first["first_observed_at"], "original")
        self.assertEqual(first["first_pubsub_message_id"], "first-message")
        code, raw = dispatch("api", "GET", EVENT_PATH + "/" + self.event.event_id,
                             b"", self.publisher, self.store)
        self.assertEqual(code, 200)
        response = json.loads(raw)
        self.assertEqual(response["payload_sha256"], self.event.payload_sha256)
        self.assertEqual(response["first_pubsub_message_id"], "first-message")
        self.assertEqual(first, self.store.events[self.event.event_id])
        self.assertEqual(dispatch("api", "POST", EVENT_PATH, push(self.event),
                                  self.publisher, self.store)[0], 404)

    def test_conflict_is_durable_then_acknowledged(self):
        self.assertEqual(dispatch("processor", "POST", PUSH_PATH, push(self.event, "one"),
                                  self.publisher, self.store)[0], 200)
        prior = copy.deepcopy(self.store.events)
        a = copy.deepcopy(self.event.observed)
        a["deployment"]["artifact_digest"] = "sha256:" + "a" * 64
        changed = self.event_from(a)
        packet = push(changed, "two")
        self.assertEqual(dispatch("processor", "POST", PUSH_PATH, packet,
                                  self.publisher, self.store)[0], 200)
        self.assertEqual(prior, self.store.events)
        self.assertEqual(len(self.store.rejections), 1)
        self.assertEqual(next(iter(self.store.rejections.values()))[0],
                         "PERMANENT_IMMUTABLE_DEPLOYMENT_CONFLICT")

    def test_rejection_write_failure_must_retry(self):
        self.store.fail = True
        code, _ = dispatch("processor", "POST", PUSH_PATH, push(self.event, data=b"invalid"),
                           self.publisher, self.store)
        self.assertEqual(code, 503)
        self.assertEqual(len(self.store.rejections), 0)

    def test_provider_failure_must_retry(self):
        self.store.fail = True
        self.assertEqual(dispatch("processor", "POST", PUSH_PATH, push(self.event),
                                  self.publisher, self.store)[0], 503)
        self.publisher.fail = True
        self.assertEqual(dispatch("ingest", "POST", EVENT_PATH, self.event.canonical_bytes,
                                  self.publisher, self.store)[0], 503)

    def test_negative_attribute_and_invalid_body(self):
        packet = json.loads(push(self.event))
        packet["message"]["attributes"]["event_id"] = "bad"
        code, _ = dispatch("processor", "POST", PUSH_PATH, jcs(packet), self.publisher, self.store)
        self.assertEqual(code, 200)
        self.assertEqual(len(self.store.rejections), 1)
        self.assertEqual(len(self.store.events), 0)
        code, _ = dispatch("processor", "POST", PUSH_PATH, b"invalid", self.publisher, self.store)
        self.assertEqual(code, 200)
        self.assertEqual(len(self.store.rejections), 2)
        missing_id = json.loads(push(self.event))
        del missing_id["message"]["messageId"]
        code, _ = dispatch("processor", "POST", PUSH_PATH, jcs(missing_id),
                           self.publisher, self.store)
        self.assertEqual(code, 200)
        self.assertEqual(len(self.store.events), 0)

    def test_fail_closed_component_and_ambient_keys(self):
        for value in ("", "writer", "ingest,api"):
            with patch.dict(os.environ, {"RESILIO_COMPONENT": value,
                                         "GOOGLE_CLOUD_PROJECT": "resilio-reference-e882d4"}, clear=True):
                with self.assertRaises(RuntimeError):
                    configured_component()
        with patch.dict(os.environ, {"RESILIO_COMPONENT": "api",
                                     "GOOGLE_CLOUD_PROJECT": "resilio-reference-e882d4",
                                     "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/a/key"}, clear=True):
            with self.assertRaises(RuntimeError):
                configured_component()

    def test_rejection_id_is_stable(self):
        self.assertEqual(_rejection_id("123", b"a"), _rejection_id("123", b"b"))
        self.assertNotEqual(_rejection_id("", b"a"), _rejection_id("", b"b"))


if __name__ == "__main__":
    unittest.main()
