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

from services.resilio_app.core import event_from_bytes, jcs, sha256
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
        captured = (publisher.messages[-1] if component == "processor"
                    and publisher.messages and body == publisher.envelope() else None)
        request_event_id = (document.get("event_id") if component == "ingest"
                            else path.removeprefix(EVENT_PATH + "/") if method == "GET"
                            and path.startswith(EVENT_PATH + "/") else
                            captured["attributes"]["event_id"] if captured else None)
        request_digest = (document.get("payload_sha256") if component == "ingest"
                          else captured["attributes"]["payload_sha256"] if captured else None)
        request_message_id = (document.get("message_id") if component == "ingest"
                              else captured["messageId"] if captured else None)
        rows.append({
            "phase": name, "http_status": status, "response": document,
            "request": {"component": component, "method": method, "path": path,
                        "body_sha256": sha256(body), "event_id": request_event_id,
                        "payload_sha256": request_digest, "message_id": request_message_id},
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



# #136: deterministic, credential-free acceptance witnesses. No provider calls.
import hashlib
from services.resilio_app.provider import ProviderFailure as _ProviderFailure

ACCEPTANCE_SOURCE = "fcbaa777d05982ebae4311e2cc30763405d6e6d2"
ACCEPTANCE_CASES = (
    "R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10", "R11", "R12"
)


def _safe(value):
    """Bound witness JSON to the existing JCS scalar domain."""
    if value is None:
        return "<absent>"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if type(value) is tuple:
        return [_safe(v) for v in value]
    if type(value) is list:
        return [_safe(v) for v in value]
    if type(value) is dict:
        return {str(k): _safe(v) for k, v in value.items()}
    if type(value) is str:
        return value
    raise TypeError(type(value))


class _WitnessClock:
    def __init__(self):
        self.trace = []

    def add(self, kind, identity="", outcome="ok", code=""):
        self.trace.append({
            "seq": str(len(self.trace) + 1), "kind": kind,
            "identity": identity, "outcome": outcome, "code": code,
        })


class _WitnessPublisher(FakePublisher):
    def __init__(self, clock):
        super().__init__()
        self.clock = clock
        self.fail = False

    def publish(self, raw, event_id, digest):
        self.clock.add("PUBLISH_ATTEMPT", event_id)
        if self.fail:
            self.clock.add("INJECT_FAILURE", event_id, "fail", "PUBLISH_UNAVAILABLE")
            raise _ProviderFailure("PUBLISH_UNAVAILABLE")
        mid = super().publish(raw, event_id, digest)
        self.clock.add("PUBLISH_COMMITTED", mid)
        return mid


class _WitnessStore(FakeStore):
    def __init__(self, clock):
        super().__init__()
        self.clock = clock
        self.fail_create = False
        self.fail_read = False

    def create_event(self, event_id, canonical, digest, message_id):
        self.clock.add("CREATE_ATTEMPT", event_id)
        if self.fail_create:
            self.clock.add("INJECT_FAILURE", event_id, "fail", "CREATE_FAILED")
            raise _ProviderFailure("CREATE_FAILED")
        before = copy.deepcopy(self.events)
        result = super().create_event(event_id, canonical, digest, message_id)
        if self.events != before:
            self.clock.add("CREATE_COMMITTED", event_id)
        return result

    def record_rejection(self, rejection_id, code, mid, event_id, digest, raw_sha):
        self.clock.add("REJECTION_ATTEMPT", rejection_id)
        if self.reject_writes:
            self.clock.add("INJECT_FAILURE", rejection_id, "fail", "REJECTION_WRITE_FAILED")
            raise _ProviderFailure("REJECTION_WRITE_FAILED")
        before = copy.deepcopy(self.rejections)
        super().record_rejection(rejection_id, code, mid, event_id, digest, raw_sha)
        if self.rejections != before:
            self.clock.add("REJECTION_COMMITTED", rejection_id)

    def read_event(self, event_id):
        self.clock.add("READ_ATTEMPT", event_id)
        if self.fail_read:
            self.clock.add("INJECT_FAILURE", event_id, "fail", "READ_UNAVAILABLE")
            raise _ProviderFailure("READ_UNAVAILABLE")
        result = super().read_event(event_id)
        self.clock.add("READ_RESULT", event_id)
        return result


def _snapshot(store, publisher):
    state = {
        "events": [{"key": key, "record": _safe(store.events[key])}
                   for key in sorted(store.events)],
        "rejections": [{"key": key, "record": _safe(store.rejections[key])}
                       for key in sorted(store.rejections)],
        "published": _safe(publisher.messages),
    }
    state["state_sha256"] = sha256(jcs(state))
    return state


def _push_bytes(event, mid, attributes=None, data=None):
    return jcs({"message": {
        "messageId": mid,
        "data": base64.b64encode(event.canonical_bytes if data is None else data).decode("ascii"),
        "attributes": (
            {"event_id": event.event_id, "payload_sha256": event.payload_sha256}
            if attributes is None else attributes
        ),
    }})


def _make_witness(case, variant=""):
    event = verified_event()
    clock = _WitnessClock()
    publisher = _WitnessPublisher(clock)
    store = _WitnessStore(clock)
    path = EVENT_PATH + "/" + event.event_id
    # Seed through the real processor when the case needs a previously accepted state.
    if case in {"R04", "R05", "R10", "R11", "R12"}:
        seed = _push_bytes(event, "first-message")
        status, _ = dispatch("processor", "POST", PUSH_PATH, seed, publisher, store)
        if status != 200 or event.event_id not in store.events:
            raise RuntimeError("SEED_FAILURE")
        clock.trace.clear()
    component, method, target, body = "processor", "POST", PUSH_PATH, b""
    if case == "R01":
        body = _push_bytes(event, "mismatch-id", {"event_id": "wrong", "payload_sha256": event.payload_sha256})
    elif case == "R02":
        body = _push_bytes(event, "mismatch-sha", {"event_id": event.event_id, "payload_sha256": "0" * 64})
    elif case == "R03":
        packet = json.loads(_push_bytes(event, "temporary"))
        if variant == "invalid":
            packet["message"]["messageId"] = "bad id"
        else:
            del packet["message"]["messageId"]
        body = jcs(packet)
    elif case == "R04":
        body = _push_bytes(event, "replayed-message")
    elif case == "R05":
        observed = copy.deepcopy(event.observed)
        observed["deployment"]["artifact_digest"] = "sha256:" + "a" * 64
        other = event_from_bytes(jcs(observed))
        body = _push_bytes(other, "conflict-message")
    elif case == "R06":
        if variant == "noncanonical":
            body = _push_bytes(event, "notcanonical", data=json.dumps(event.observed, indent=2).encode())
        else:
            body = b"bad-envelope"
    elif case == "R07":
        body = b"bad-envelope"
        store.reject_writes = True
    elif case == "R08":
        body = _push_bytes(event, "create-failed")
        store.fail_create = True
    elif case == "R09":
        component, method, target, body = "ingest", "POST", EVENT_PATH, event.canonical_bytes
        publisher.fail = True
    elif case == "R10":
        component, method, target, body = "api", "GET", path, b""
        rec = store.events[event.event_id]
        if variant == "event_id":
            rec["event_id"] = "0" * 64
        elif variant == "observed_json":
            rec["observed_json"] = "not-json"
        elif variant == "payload_sha256":
            rec["payload_sha256"] = "0" * 64
        elif variant == "first_pubsub_message_id":
            rec["first_pubsub_message_id"] = ""
        elif variant == "missing_mid":
            del rec["first_pubsub_message_id"]
        elif variant == "mid_type":
            rec["first_pubsub_message_id"] = 123
        elif variant == "mid_oversize":
            rec["first_pubsub_message_id"] = "x" * 129
        elif variant == "noncanonical":
            rec["observed_json"] = json.dumps(event.observed, indent=2)
        elif variant == "missing_observed":
            del rec["observed_json"]
        elif variant == "other_identity":
            other = copy.deepcopy(event.observed)
            other["deployment"]["id"] = "different"
            rec["observed_json"] = event_from_bytes(jcs(other)).canonical_bytes.decode()
        else:
            raise RuntimeError("UNKNOWN_CORRUPTION")
    elif case == "R11":
        component, method, target, body = "api", "GET", path, b""
    elif case == "R12":
        component, method, target, body = "api", "POST", EVENT_PATH, event.canonical_bytes
    else:
        raise RuntimeError("UNKNOWN_CASE")
    before = _snapshot(store, publisher)
    response_status, response_bytes = dispatch(component, method, target, body, publisher, store)
    clock.add("HTTP_RESPONSE", str(response_status))
    after = _snapshot(store, publisher)
    response = json.loads(response_bytes.decode("utf-8"))
    return {
        "id": case, "variant": variant,
        "input": {"component": component, "method": method, "path": target,
                  "body_b64": base64.b64encode(body).decode("ascii")},
        "observed": {"status": str(response_status), "response": _safe(response)},
        "state_before": before, "state_after": after, "trace": clock.trace,
    }


def resilience_acceptance():
    variants = {
        "R03": ("missing", "invalid"),
        "R06": ("malformed", "noncanonical"),
        "R10": ("event_id", "observed_json", "payload_sha256",
                "first_pubsub_message_id", "missing_mid", "mid_type",
                "mid_oversize", "noncanonical", "missing_observed", "other_identity"),
    }
    cases = [_make_witness(case, variant)
             for case in ACCEPTANCE_CASES
             for variant in variants.get(case, ("",))]
    report = {
        "contract": "resilio-phase5-local-acceptance/v1",
        "scope": "LOCAL_FAKE_PROVIDER_ONLY",
        "source_commit": ACCEPTANCE_SOURCE,
        "fixture_version": "phase5-verified-event/v1",
        "scenarios": cases,
    }
    report["acceptance_sha256"] = sha256(jcs(report))
    return report


def resilience_acceptance_bytes():
    return jcs(resilience_acceptance()) + b"\n"

if __name__ == "__main__":
    sys.stdout.buffer.write(resilience_acceptance_bytes())
