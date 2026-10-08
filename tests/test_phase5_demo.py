"""Regression tests for the credential-free connected Phase 5 demonstration."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.phase5_demo import demonstrate
from services.resilio_app.core import sha256
from services.resilio_app.server import EVENT_PATH, PUSH_PATH


class Phase5DemoTests(unittest.TestCase):
    def test_connected_product_demonstration(self):
        transcript = demonstrate()
        self.assertEqual(transcript["result"], "PASS")
        self.assertEqual(transcript["scope"], "LOCAL_FAKE_PROVIDER_ONLY")
        self.assertIs(transcript["live_provider_acceptance"], False)
        self.assertEqual(transcript["final_stored_count"], 1)
        self.assertEqual(transcript["final_rejection_count"], 2)
        self.assertNotEqual(transcript["first_message_id"],
                            transcript["replay_message_id"])
        steps = {row["phase"]: row for row in transcript["steps"]}
        self.assertEqual(steps["before"]["http_status"], 404)
        self.assertEqual(steps["ingest"]["http_status"], 202)
        self.assertEqual(steps["process"]["response"]["status"], "acknowledged")
        self.assertEqual(steps["read"]["response"]["first_pubsub_message_id"],
                         transcript["first_message_id"])
        self.assertEqual(steps["replay_process"]["response"]["status"], "acknowledged")
        self.assertEqual(steps["replay_read"]["response"]["first_pubsub_message_id"],
                         transcript["first_message_id"])
        self.assertEqual(steps["conflict_process"]["response"]["status"], "rejected")
        self.assertEqual(steps["invalid_ingest"]["http_status"], 400)
        self.assertEqual(steps["invalid_push"]["response"]["status"], "rejected")
        self.assertEqual(steps["rejection_store_failure"]["http_status"], 503)
        self.assertEqual(steps["api_write_forbidden"]["http_status"], 404)
        self.assertEqual(steps["ingest"]["request"]["component"], "ingest")
        self.assertEqual(steps["ingest"]["request"]["method"], "POST")
        self.assertEqual(steps["ingest"]["request"]["path"], EVENT_PATH)
        self.assertEqual(steps["ingest"]["request"]["event_id"], transcript["event_id"])
        self.assertEqual(steps["ingest"]["request"]["payload_sha256"],
                         transcript["payload_sha256"])
        self.assertEqual(steps["ingest"]["request"]["message_id"],
                         transcript["first_message_id"])
        self.assertEqual(steps["process"]["request"]["path"], PUSH_PATH)
        self.assertEqual(steps["process"]["request"]["message_id"],
                         transcript["first_message_id"])
        self.assertEqual(steps["replay_process"]["request"]["message_id"],
                         transcript["replay_message_id"])
        self.assertEqual(steps["conflict_process"]["request"]["message_id"],
                         steps["conflict_ingest"]["response"]["message_id"])
        self.assertEqual(steps["conflict_process"]["request"]["event_id"],
                         transcript["event_id"])
        self.assertEqual(steps["conflict_process"]["request"]["payload_sha256"],
                         steps["conflict_ingest"]["response"]["payload_sha256"])
        self.assertNotEqual(steps["conflict_process"]["request"]["payload_sha256"],
                            transcript["payload_sha256"])
        self.assertEqual(steps["invalid_ingest"]["request"]["body_sha256"],
                         sha256(b"{}"))
        self.assertIsNone(steps["invalid_ingest"]["request"]["message_id"])
        self.assertEqual(steps["invalid_push"]["request"]["body_sha256"],
                         sha256(b"invalid-push-envelope"))
        self.assertIsNone(steps["invalid_push"]["request"]["message_id"])
        self.assertEqual(steps["rejection_store_failure"]["request"]["body_sha256"],
                         sha256(b"another-invalid-envelope"))
        self.assertTrue(all(len(row["request"]["body_sha256"]) == 64
                            and row["request"]["component"]
                            and row["request"]["method"]
                            and row["request"]["path"]
                            for row in transcript["steps"]))
        self.assertTrue(all(row["assertion"] == "PASS" for row in transcript["steps"]))

    def test_deterministic_transcript(self):
        first = demonstrate()
        second = demonstrate()
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))


if __name__ == "__main__":
    unittest.main()

# #136: independent, closed acceptance-witness checks.
import base64
import copy
import hashlib

from scripts.phase5_demo import (
    ACCEPTANCE_SOURCE, resilience_acceptance, resilience_acceptance_bytes,
)
from scripts.phase5_acceptance_fixture import verified_event
from services.resilio_app.core import event_from_bytes, jcs
from services.resilio_app.server import _rejection_id


_EXPECTED_CASES = [
    ("R01", ""), ("R02", ""), ("R03", "missing"), ("R03", "invalid"),
    ("R04", ""), ("R05", ""), ("R06", "malformed"), ("R06", "noncanonical"),
    ("R07", ""), ("R08", ""), ("R09", ""),
    *[("R10", v) for v in (
        "event_id", "observed_json", "payload_sha256", "first_pubsub_message_id",
        "missing_mid", "mid_type", "mid_oversize", "noncanonical",
        "missing_observed", "other_identity",
    )],
    ("R11", ""), ("R12", ""),
]


def _require(truth, name):
    if not truth:
        raise ValueError("WITNESS_INVALID:" + name)


def _parse_strict(raw):
    def hook(pairs):
        out = {}
        for key, value in pairs:
            _require(key not in out, "DUPLICATE_KEY")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=hook)


def _event_map(snapshot):
    return {row["key"]: row["record"] for row in snapshot["events"]}


def _rejection_map(snapshot):
    return {row["key"]: row["record"] for row in snapshot["rejections"]}


def verify_resilience_report(report):
    """Read-only verifier: reconstructs fixture identities and fake-state transitions.

    No trust in producer PASS labels, counts, state digests, or HTTP status alone.
    """
    _require(type(report) is dict and set(report) == {
        "contract", "scope", "source_commit", "fixture_version",
        "scenarios", "acceptance_sha256",
    }, "REPORT_FIELDS")
    _require(report["contract"] == "resilio-phase5-local-acceptance/v1", "CONTRACT")
    _require(report["scope"] == "LOCAL_FAKE_PROVIDER_ONLY", "SCOPE")
    _require(report["source_commit"] == ACCEPTANCE_SOURCE, "SOURCE")
    _require(report["fixture_version"] == "phase5-verified-event/v1", "FIXTURE")
    doc = dict(report)
    digest = doc.pop("acceptance_sha256")
    _require(digest == sha256(jcs(doc)), "REPORT_SHA")
    rows = report["scenarios"]
    _require(type(rows) is list and len(rows) == len(_EXPECTED_CASES), "ROWS")
    fixture = verified_event()
    for row, (case, variant) in zip(rows, _EXPECTED_CASES):
        _require(type(row) is dict and set(row) == {
            "id", "variant", "input", "observed", "state_before",
            "state_after", "trace",
        }, "CASE_FIELDS")
        _require((row["id"], row["variant"]) == (case, variant), "CASE_ID")
        inp, obs = row["input"], row["observed"]
        _require(type(inp) is dict and set(inp) == {
            "component", "method", "path", "body_b64",
        }, "INPUT_FIELDS")
        _require(type(obs) is dict and set(obs) == {"status", "response"}, "RESPONSE_FIELDS")
        try:
            raw = base64.b64decode(inp["body_b64"], validate=True)
        except (ValueError, base64.binascii.Error) as error:
            raise ValueError("WITNESS_INVALID:BASE64") from error
        _require(base64.b64encode(raw).decode() == inp["body_b64"], "BASE64_CANON")
        before, after = row["state_before"], row["state_after"]
        for state in (before, after):
            _require(type(state) is dict and set(state) == {
                "events", "rejections", "published", "state_sha256",
            }, "STATE_FIELDS")
            state_preimage = dict(state)
            state_digest = state_preimage.pop("state_sha256")
            _require(state_digest == sha256(jcs(state_preimage)), "STATE_DIGEST")
            for key in ("events", "rejections"):
                records = state[key]
                _require(type(records) is list, "STATE_LIST")
                identities = [record["key"] for record in records]
                _require(identities == sorted(set(identities)), "STATE_SORT")
            _require(type(state["published"]) is list, "PUBLISH_LIST")
        before_events, after_events = _event_map(before), _event_map(after)
        before_reject, after_reject = _rejection_map(before), _rejection_map(after)
        trace = row["trace"]
        _require(type(trace) is list and bool(trace), "TRACE")
        kinds = []
        for ix, item in enumerate(trace, 1):
            _require(type(item) is dict and set(item) == {
                "seq", "kind", "identity", "outcome", "code",
            }, "TRACE_FIELDS")
            _require(item["seq"] == str(ix), "TRACE_SEQUENCE")
            _require(item["kind"] in {
                "INJECT_FAILURE", "PUBLISH_ATTEMPT", "PUBLISH_COMMITTED",
                "CREATE_ATTEMPT", "CREATE_COMMITTED", "REJECTION_ATTEMPT",
                "REJECTION_COMMITTED", "READ_ATTEMPT", "READ_RESULT", "HTTP_RESPONSE",
            }, "TRACE_KIND")
            kinds.append(item["kind"])
        expected_trace = {
            "R01": ["REJECTION_ATTEMPT", "REJECTION_COMMITTED", "HTTP_RESPONSE"],
            "R02": ["REJECTION_ATTEMPT", "REJECTION_COMMITTED", "HTTP_RESPONSE"],
            "R03": ["REJECTION_ATTEMPT", "REJECTION_COMMITTED", "HTTP_RESPONSE"],
            "R04": ["CREATE_ATTEMPT", "HTTP_RESPONSE"],
            "R05": ["CREATE_ATTEMPT", "REJECTION_ATTEMPT",
                    "REJECTION_COMMITTED", "HTTP_RESPONSE"],
            "R06": ["REJECTION_ATTEMPT", "REJECTION_COMMITTED", "HTTP_RESPONSE"],
            "R07": ["REJECTION_ATTEMPT", "INJECT_FAILURE", "HTTP_RESPONSE"],
            "R08": ["CREATE_ATTEMPT", "INJECT_FAILURE", "HTTP_RESPONSE"],
            "R09": ["PUBLISH_ATTEMPT", "INJECT_FAILURE", "HTTP_RESPONSE"],
            "R10": ["READ_ATTEMPT", "READ_RESULT", "HTTP_RESPONSE"],
            "R11": ["READ_ATTEMPT", "READ_RESULT", "HTTP_RESPONSE"],
            "R12": ["HTTP_RESPONSE"],
        }
        _require(kinds == expected_trace[case], "EXACT_TRANSITION_GRAMMAR")
        # Independently bind every operation identity and failure to its input
        # and the exact fake state. A self-rehashed but forged trace must fail.
        expected_identity = fixture.event_id
        if case in {"R01", "R02", "R03", "R05", "R06", "R07"}:
            message_id = {
                "R01": "mismatch-id", "R02": "mismatch-sha",
                "R03": "", "R05": "conflict-message",
                "R06": "notcanonical" if variant == "noncanonical" else "",
                "R07": "",
            }[case]
            expected_rejection = _rejection_id(message_id, raw)
        else:
            expected_rejection = ""
        expected_identities = {
            "R01": [expected_rejection, expected_rejection, "200"],
            "R02": [expected_rejection, expected_rejection, "200"],
            "R03": [expected_rejection, expected_rejection, "200"],
            "R04": [expected_identity, "200"],
            "R05": [expected_identity, expected_rejection, expected_rejection, "200"],
            "R06": [expected_rejection, expected_rejection, "200"],
            "R07": [expected_rejection, expected_rejection, "503"],
            "R08": [expected_identity, expected_identity, "503"],
            "R09": [expected_identity, expected_identity, "503"],
            "R10": [expected_identity, expected_identity, "503"],
            "R11": [expected_identity, expected_identity, "200"],
            "R12": ["404"],
        }
        expected_failures = {
            "R07": "REJECTION_WRITE_FAILED",
            "R08": "CREATE_FAILED",
            "R09": "PUBLISH_UNAVAILABLE",
        }
        _require(
            [(item["kind"], item["identity"], item["outcome"], item["code"])
             for item in trace] == [
                (kind, identity,
                 "fail" if kind == "INJECT_FAILURE" else "ok",
                 expected_failures[case] if kind == "INJECT_FAILURE" else "")
                for kind, identity in zip(expected_trace[case], expected_identities[case])
            ], "TRACE_IDENTITY_CAUSAL_BINDING")
        # B02: the complete new rejection record is derived from the request
        # and real handler's deterministic context, not trusted from the fake.
        if case in {"R01", "R02", "R03", "R05", "R06"}:
            expected_codes = {
                "R01": "PERMANENT_IDENTITY_MISMATCH",
                "R02": "PERMANENT_IDENTITY_MISMATCH",
                "R03": "PUSH_MESSAGE_ID_INVALID",
                "R05": "PERMANENT_IMMUTABLE_DEPLOYMENT_CONFLICT",
                "R06": ("NON_CANONICAL_PAYLOAD" if variant == "noncanonical"
                        else "PUSH_ENVELOPE_INVALID"),
            }
            event_ident = (fixture.event_id if case in {"R01", "R02", "R05"} else "")
            event_digest = ""
            if case in {"R01", "R02"}:
                event_digest = fixture.payload_sha256
            if case == "R05":
                other = copy.deepcopy(fixture.observed)
                other["deployment"]["artifact_digest"] = "sha256:" + "a" * 64
                event_digest = event_from_bytes(jcs(other)).payload_sha256
            _require(after_reject.get(expected_rejection) == [
                expected_codes[case],
                {"R01":"mismatch-id","R02":"mismatch-sha","R03":"",
                 "R05":"conflict-message",
                 "R06":"notcanonical" if variant=="noncanonical" else ""}[case],
                event_ident, event_digest, sha256(raw),
            ], "EXACT_REJECTION_RECORD")
            _require(set(after_reject) - set(before_reject) ==
                     {expected_rejection}, "EXACT_REJECTION_DELTA")
        for item in trace:
            if item["kind"] == "INJECT_FAILURE":
                _require(item["outcome"] == "fail", "INJECTION_OUTCOME")
            else:
                _require(item["outcome"] == "ok" and item["code"] == "",
                         "TRACE_SUCCESS_OUTCOME")
        _require(kinds[-1] == "HTTP_RESPONSE" and kinds.count("HTTP_RESPONSE") == 1,
                 "RESPONSE_ORDER")
        _require(trace[-1]["identity"] == obs["status"], "RESPONSE_STATUS_BINDING")
        _require(type(obs["response"]) is dict, "RESPONSE_TYPE")
        expected_status = "503" if case in {"R07", "R08", "R09", "R10"} else (
            "404" if case == "R12" else "200"
        )
        _require(obs["status"] == expected_status, "EXPECTED_STATUS")
        _require(all(key in inp for key in ("component", "method", "path")), "INPUT")
        # Input and state witnesses must bind to exact case semantics, not a
        # producer-controlled status and an arbitrary self-consistent digest.
        if case in {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08"}:
            if case in {"R06", "R07"} and variant != "noncanonical":
                _require(raw == b"bad-envelope", "NEGATIVE_RAW_VECTOR")
            else:
                message = _parse_strict(raw)["message"]
                _require(type(message) is dict, "MESSAGE")
                if case == "R03":
                    if variant == "missing":
                        _require("messageId" not in message, "MISSING_MID_VECTOR")
                    else:
                        _require(message["messageId"] == "bad id", "INVALID_MID_VECTOR")
                elif case == "R01":
                    _require(message["messageId"] == "mismatch-id" and
                             message["attributes"] == {
                                 "event_id": "wrong",
                                 "payload_sha256": fixture.payload_sha256,
                             }, "MISMATCH_ID_VECTOR")
                elif case == "R02":
                    _require(message["messageId"] == "mismatch-sha" and
                             message["attributes"] == {
                                 "event_id": fixture.event_id,
                                 "payload_sha256": "0" * 64,
                             }, "MISMATCH_SHA_VECTOR")
                elif case == "R04":
                    _require(message["messageId"] == "replayed-message", "REPLAY_VECTOR")
                elif case == "R05":
                    _require(message["messageId"] == "conflict-message", "CONFLICT_VECTOR")
                elif case == "R06":
                    _require(message["messageId"] == "notcanonical", "NONCANON_VECTOR")
                elif case == "R08":
                    _require(message["messageId"] == "create-failed", "CREATE_VECTOR")
                if case not in {"R03"}:
                    decoded = base64.b64decode(message["data"], validate=True)
                    if case == "R05":
                        changed = event_from_bytes(decoded, require_canonical=True)
                        _require(changed.event_id == fixture.event_id and
                                 changed.payload_sha256 != fixture.payload_sha256,
                                 "CONFLICT_PAYLOAD_IDENTITY")
                    elif case == "R06":
                        _require(decoded != fixture.canonical_bytes, "NONCANON_RAW")
                        _require(event_from_bytes(decoded).event_id == fixture.event_id,
                                 "NONCANON_EVENT")
                    else:
                        _require(decoded == fixture.canonical_bytes, "FIXTURE_PAYLOAD")
        if case == "R10":
            record = before_events.get(fixture.event_id, {})
            _require(set(before_events) == {fixture.event_id}, "CORRUPT_SEED_KEY")
            valid = {
                "event_id": fixture.event_id,
                "payload_sha256": fixture.payload_sha256,
                "observed_json": fixture.canonical_bytes.decode(),
                "first_pubsub_message_id": "first-message",
                "first_observed_at": "deterministic-local-fixture",
            }
            expected = dict(valid)
            if variant == "event_id":
                expected["event_id"] = "0" * 64
            elif variant == "observed_json":
                expected["observed_json"] = "not-json"
            elif variant == "payload_sha256":
                expected["payload_sha256"] = "0" * 64
            elif variant == "first_pubsub_message_id":
                expected["first_pubsub_message_id"] = ""
            elif variant == "missing_mid":
                del expected["first_pubsub_message_id"]
            elif variant == "mid_type":
                expected["first_pubsub_message_id"] = {"$type": "integer", "decimal": "123"}
            elif variant == "mid_oversize":
                expected["first_pubsub_message_id"] = "x" * 129
            elif variant == "noncanonical":
                expected["observed_json"] = json.dumps(fixture.observed, indent=2)
            elif variant == "missing_observed":
                del expected["observed_json"]
            elif variant == "other_identity":
                changed = copy.deepcopy(fixture.observed)
                changed["deployment"]["id"] = "different"
                expected["observed_json"] = event_from_bytes(
                    jcs(changed)).canonical_bytes.decode()
            _require(record == expected, "EXACT_CORRUPTION_VECTOR")
        if case in {"R04", "R05", "R11", "R12"}:
            record = before_events.get(fixture.event_id, {})
            _require(record == {
                "event_id": fixture.event_id,
                "payload_sha256": fixture.payload_sha256,
                "observed_json": fixture.canonical_bytes.decode(),
                "first_pubsub_message_id": "first-message",
                "first_observed_at": "deterministic-local-fixture",
            }, "EXACT_SEEDED_STATE")
        if case == "R09":
            _require((inp["component"], inp["method"], inp["path"]) ==
                     ("ingest", "POST", EVENT_PATH), "INGEST_ROUTE")
            _require(event_from_bytes(raw).event_id == fixture.event_id, "INGEST_EVENT")
            _require(obs["response"] == {"error": "PUBLISH_UNAVAILABLE"}, "PUBLISH_ERROR")
            _require("PUBLISH_ATTEMPT" in kinds and "PUBLISH_COMMITTED" not in kinds,
                     "NO_FALSE_PUBLISH")
            _require(after == before, "PUBLISH_NO_MUTATION")
            continue
        if case in {"R10", "R11", "R12"}:
            _require(inp["component"] == "api", "API_COMPONENT")
            _require(inp["path"] == (EVENT_PATH if case == "R12" else
                     EVENT_PATH + "/" + fixture.event_id), "API_PATH")
            _require(after == before, "READ_ONLY")
            if case == "R10":
                _require(obs["response"] == {"error": "STATE_INTEGRITY_FAILURE"}, "API_INTEGRITY")
            elif case == "R11":
                _require(obs["response"]["event_id"] == fixture.event_id, "API_EVENT_ID")
                _require(obs["response"]["payload_sha256"] == fixture.payload_sha256,
                         "API_PAYLOAD_DIGEST")
            else:
                _require(obs["response"] == {"error": "ROUTE_NOT_FOUND"}, "API_FORBIDDEN")
            _require(set(before_events) == {fixture.event_id}, "SEEDED_STATE")
            continue
        _require((inp["component"], inp["method"], inp["path"]) ==
                 ("processor", "POST", PUSH_PATH), "PROCESSOR_ROUTE")
        mid = ""
        try:
            parsed = _parse_strict(raw)
            message = parsed.get("message", {})
            mid = message.get("messageId", message.get("message_id", ""))
            if not isinstance(mid, str) or any(ord(c) < 33 or ord(c) > 127 for c in mid):
                mid = ""
        except (ValueError, UnicodeDecodeError, AttributeError):
            mid = ""
        if case in {"R01", "R02", "R03", "R05", "R06"}:
            _require(obs["response"].get("status") == "rejected", "REJECTED")
            _require("REJECTION_ATTEMPT" in kinds and
                     "REJECTION_COMMITTED" in kinds, "REJECTION_COMMIT")
            _require(kinds.index("REJECTION_ATTEMPT") <
                     kinds.index("REJECTION_COMMITTED") < kinds.index("HTTP_RESPONSE"),
                     "REJECT_BEFORE_ACK")
            rejection_id = _rejection_id(mid, raw)
            _require(obs["response"]["rejection_id"] == rejection_id, "REJECTION_ID")
            _require(rejection_id in after_reject and rejection_id not in before_reject,
                     "REJECTION_RECORD")
            _require(after_events == before_events, "IMMUTABLE_ON_REJECT")
            _require(after_reject[rejection_id][1] == mid, "REJECTION_MID")
            _require(after_reject[rejection_id][-1] == sha256(raw), "REJECTION_BODY_SHA")
            if case in {"R01", "R02"}:
                _require(after_reject[rejection_id][0] == "PERMANENT_IDENTITY_MISMATCH",
                         "IDENTITY_MISMATCH")
            elif case == "R03":
                _require(after_reject[rejection_id][0] == "PUSH_MESSAGE_ID_INVALID",
                         "MISSING_INVALID_MESSAGE_ID")
            elif case == "R06":
                required_code = ("NON_CANONICAL_PAYLOAD" if variant == "noncanonical"
                                 else "PUSH_ENVELOPE_INVALID")
                _require(after_reject[rejection_id][0] == required_code,
                         "MALFORMED_NONCANONICAL_REJECTION")
            elif case == "R05":
                _require(after_reject[rejection_id][0] ==
                         "PERMANENT_IMMUTABLE_DEPLOYMENT_CONFLICT", "IMMUTABLE_CONFLICT")
        elif case == "R04":
            _require(obs["response"] == {"status": "acknowledged"}, "REPLAY_ACK")
            _require(before == after, "REPLAY_PRESERVES_FIRST")
            _require("CREATE_ATTEMPT" in kinds and "CREATE_COMMITTED" not in kinds,
                     "REPLAY_NO_WRITE")
        elif case == "R07":
            _require(obs["response"] == {"error": "REJECTION_WRITE_FAILED"}, "REJECT_503")
            _require("REJECTION_ATTEMPT" in kinds and
                     "REJECTION_COMMITTED" not in kinds, "REJECT_NO_COMMIT")
            _require(after == before, "REJECT_FAILURE_NO_MUTATION")
        elif case == "R08":
            _require(obs["response"] == {"error": "PROVIDER_RETRYABLE"}, "CREATE_503")
            _require("CREATE_ATTEMPT" in kinds and "CREATE_COMMITTED" not in kinds,
                     "CREATE_NO_COMMIT")
            _require(after == before, "CREATE_FAILURE_NO_MUTATION")
        else:
            raise ValueError("WITNESS_INVALID:UNKNOWN_CASE")
        if case in {"R04", "R05"}:
            _require(set(before_events) == {fixture.event_id}, "SEEDED_STATE")
            record = before_events[fixture.event_id]
            _require(record["payload_sha256"] == fixture.payload_sha256 and
                     record["first_pubsub_message_id"] == "first-message",
                     "ORIGINAL_IDENTITY")
    return True


class ResilienceWitnessTests(unittest.TestCase):
    def test_closed_witness_and_determinism(self):
        report = resilience_acceptance()
        self.assertTrue(verify_resilience_report(report))
        self.assertEqual(resilience_acceptance_bytes(), resilience_acceptance_bytes())

    def test_adversarial_mutations_fail_closed(self):
        original = resilience_acceptance()
        candidates = []
        def altered(change, recompute=False):
            r = copy.deepcopy(original)
            change(r)
            if recompute:
                d = dict(r)
                d.pop("acceptance_sha256")
                r["acceptance_sha256"] = sha256(jcs(d))
            candidates.append(r)
        altered(lambda r: r["scenarios"][0]["input"].update(body_b64="YWJj"), True)
        altered(lambda r: r["scenarios"][4]["state_after"]["events"][0]["record"].update(
            first_pubsub_message_id="forged"), True)
        altered(lambda r: r["scenarios"][0]["trace"].reverse(), True)
        altered(lambda r: r["scenarios"][0]["state_after"]["rejections"][0].update(
            key="0" * 64), True)
        altered(lambda r: r.update(acceptance_sha256="0" * 64))
        # Rehashed forgery attacks must be rejected by the verifier, not by
        # the outer report digest alone.
        altered(lambda r: r["scenarios"][0]["trace"][0].update(
            identity="0" * 64), True)
        altered(lambda r: r["scenarios"][0]["trace"][1].update(
            identity="0" * 64), True)
        altered(lambda r: r["scenarios"][8]["trace"][1].update(
            code="FABRICATED_FAILURE"), True)
        altered(lambda r: r["scenarios"][0]["state_after"]["rejections"][0][
            "record"].__setitem__(0, "FORGED_REJECTION"), True)
        def typed_corruption_to_valid_string(r):
            record = r["scenarios"][16]["state_before"]["events"][0]["record"]
            record["first_pubsub_message_id"] = "123"
            r["scenarios"][16]["state_after"]["events"][0][
                "record"]["first_pubsub_message_id"] = "123"
            for state in ("state_before", "state_after"):
                entry = r["scenarios"][16][state]
                preimage = dict(entry)
                preimage.pop("state_sha256")
                entry["state_sha256"] = sha256(jcs(preimage))
        altered(typed_corruption_to_valid_string, True)
        for mutated in candidates:
            with self.assertRaises((ValueError, TypeError, KeyError, IndexError)):
                verify_resilience_report(mutated)

    def test_separate_processes_and_optimised_interpreter(self):
        command = [sys.executable, str(ROOT / "scripts" / "phase5_demo.py")]
        a = subprocess.run(command, cwd=ROOT, check=True, capture_output=True).stdout
        b = subprocess.run(command, cwd=ROOT, check=True, capture_output=True).stdout
        self.assertEqual(a, b)
        self.assertEqual(a, jcs(_parse_strict(a)) + b"\n")
        self.assertTrue(verify_resilience_report(_parse_strict(a)))
        optimised = subprocess.run([sys.executable, "-O", command[1]], cwd=ROOT,
                                   check=True, capture_output=True).stdout
        self.assertEqual(a, optimised)
        altered = _parse_strict(optimised)
        altered["acceptance_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            verify_resilience_report(altered)
