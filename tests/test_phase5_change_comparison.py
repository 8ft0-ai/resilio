"""Contract and hostile-input tests for #138 comparison V1."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from services.resilio_app.core import PermanentFailure, event_from_bytes, jcs, sha256
from services.resilio_app.change_comparison import compare_deployments


def observation():
    return {
        "schema_version": 1,
        "event_type": "deployment.observed",
        "service": {"id": "svc"},
        "environment": {"id": "prod"},
        "change": {"repository": "acme/repo", "source_sha": "a" * 40},
        "deployment": {
            "id": "deploy-1",
            "release_id": "release-1",
            "artifact_digest": "sha256:" + "b" * 64,
            "runtime": {"provider": "local", "kind": "job", "resource_id": "resource-1"},
        },
        "evidence": [{"kind": "build", "ref": "local:1"}],
    }


def encoded(value):
    return jcs(value)


def report(baseline, candidate):
    return json.loads(compare_deployments(encoded(baseline), encoded(candidate)))


def test_identical_and_independent_identities():
    item = observation()
    raw = encoded(item)
    result_bytes = compare_deployments(raw, raw)
    result = json.loads(result_bytes)
    event = event_from_bytes(raw, require_canonical=True)
    assert result_bytes == jcs(result)
    assert result["classification"] == "UNCHANGED"
    assert result["differences"] == result["evidence_added"] == result["evidence_removed"] == []
    assert len(result["unchanged_fields"]) == 8
    for role in ("baseline", "candidate"):
        assert result[role] == {"event_id": event.event_id, "payload_sha256": sha256(raw)}
    assert result["context"] == {"service_id": "svc", "environment_id": "prod"}
    assert result["contract"] == "resilio-deployment-change-comparison/v1"
    assert result["scope"] == "LOCAL_COMPARISON_ONLY"
    assert result["explanation"] == (
        "The baseline and candidate observations have identical canonical payloads. Differing fields: none."
        " Supplied evidence references added: 0; removed: 0. These references are not independently verified."
    )


def test_changed_all_fields_and_order():
    old = observation()
    new = copy.deepcopy(old)
    new["change"] = {"repository": "other/repo", "source_sha": "c" * 40}
    new["deployment"] = {
        "id": "deploy-2", "release_id": "release-2",
        "artifact_digest": "sha256:" + "d" * 64,
        "runtime": {"provider": "changed", "kind": "task", "resource_id": "resource-2"},
    }
    result = report(old, new)
    names = [
        "change.repository", "change.source_sha", "deployment.id", "deployment.release_id",
        "deployment.artifact_digest", "deployment.runtime.provider",
        "deployment.runtime.kind", "deployment.runtime.resource_id",
    ]
    assert result["classification"] == "CHANGED"
    assert [x["field"] for x in result["differences"]] == names
    assert result["unchanged_fields"] == []
    assert result["differences"][0] == {
        "field": "change.repository", "before": "acme/repo", "after": "other/repo"
    }
    assert result["baseline"]["event_id"] != result["candidate"]["event_id"]
    assert result["explanation"] == (
        "The observations have different logical deployment identities within the same service and environment."
        " Differing fields: " + ", ".join(names)
        + ". Supplied evidence references added: 0; removed: 0."
        " These references are not independently verified."
    )


def test_conflict_and_evidence_only_presence():
    old = observation()
    new = copy.deepcopy(old)
    new["evidence"] = [{"kind": "build", "ref": "local:1", "sha256": "f" * 64}]
    result = report(old, new)
    assert result["classification"] == "IDENTITY_CONFLICT"
    assert result["baseline"]["event_id"] == result["candidate"]["event_id"]
    assert result["baseline"]["payload_sha256"] != result["candidate"]["payload_sha256"]
    assert result["differences"] == []
    assert result["evidence_added"] == new["evidence"]
    assert result["evidence_removed"] == old["evidence"]
    assert result["explanation"] == (
        "The observations share a logical deployment identity but have different canonical payloads;"
        " this is not evidence of a successful transition. Differing fields: none."
        " Supplied evidence references added: 1; removed: 1. These references are not independently verified."
    )


def test_evidence_ordering_with_two_membership_deltas():
    old = observation()
    new = copy.deepcopy(old)
    new["evidence"] = [
        {"kind": "a", "ref": "a"}, {"kind": "build", "ref": "local:1"}, {"kind": "z", "ref": "z"}
    ]
    result = report(old, new)
    assert result["evidence_added"] == [{"kind": "a", "ref": "a"}, {"kind": "z", "ref": "z"}]
    assert result["evidence_removed"] == []
    assert "added: 2; removed: 0." in result["explanation"]


def test_maximal_valid_fields():
    item = observation()
    item["deployment"]["runtime"]["resource_id"] = "ü" * 256
    item["evidence"][0]["ref"] = "r" * 1024
    item["service"]["id"] = "s" * 128
    item["deployment"]["release_id"] = "r" * 128
    raw = encoded(item)
    assert len(raw) <= 32768
    assert json.loads(compare_deployments(raw, raw))["classification"] == "UNCHANGED"


def error_pair(baseline, candidate):
    with pytest.raises(PermanentFailure) as raised:
        compare_deployments(baseline, candidate)
    err = raised.value
    assert str(err) == err.code
    return err.role, err.code


@pytest.mark.parametrize("invalid", [None, True, "bytes", bytearray(b"{}"), memoryview(b"{}"), 4, object()])
def test_baseline_wrong_type_precedes_other_errors(invalid):
    assert error_pair(invalid, b"not JSON") == ("baseline", "COMPARISON_INPUT_TYPE_INVALID")


def test_candidate_wrong_type():
    raw = encoded(observation())
    assert error_pair(raw, bytearray(raw)) == ("candidate", "COMPARISON_INPUT_TYPE_INVALID")


@pytest.mark.parametrize("bad,code", [
    (b"{", "INVALID_JSON"),
    (b"\xff", "INVALID_UTF8"),
    (b'{"a":1,"a":2}', "DUPLICATE_JSON_KEY"),
    (b'{"schema_version":2}', "SCHEMA_FIELDS_INVALID"),
    (b"x" * 32769, "PAYLOAD_TOO_LARGE"),
])
def test_core_error_preserved(bad, code):
    assert error_pair(bad, b"{") == ("baseline", code)
    assert error_pair(encoded(observation()), bad) == ("candidate", code)


def test_noncanonical_and_unsupported_schema_and_evidence_order():
    good = observation()
    assert error_pair(json.dumps(good).encode(), encoded(good)) == ("baseline", "NON_CANONICAL_PAYLOAD")
    bad = copy.deepcopy(good)
    bad["schema_version"] = 2
    assert error_pair(encoded(bad), encoded(good)) == ("baseline", "SCHEMA_VERSION_UNSUPPORTED")
    bad = copy.deepcopy(good)
    bad["evidence"] = [{"kind": "z", "ref": "z"}, {"kind": "a", "ref": "a"}]
    assert error_pair(encoded(bad), encoded(good)) == ("baseline", "NON_CANONICAL_PAYLOAD")
    bad = copy.deepcopy(good)
    del bad["deployment"]["id"]
    assert error_pair(encoded(good), encoded(bad)) == ("candidate", "SCHEMA_FIELDS_INVALID")


def test_precedence_over_context_mismatch():
    good = observation()
    other = copy.deepcopy(good)
    other["environment"]["id"] = "staging"
    assert error_pair(b"{", encoded(other)) == ("baseline", "INVALID_JSON")
    assert error_pair(encoded(other), b"{") == ("candidate", "INVALID_JSON")
    assert error_pair(encoded(good), encoded(other)) == ("comparison", "COMPARISON_CONTEXT_MISMATCH")
    assert error_pair(encoded(other), encoded(good)) == ("comparison", "COMPARISON_CONTEXT_MISMATCH")


def test_repeat_and_optimised_subprocess():
    raw = encoded(observation())
    expected = compare_deployments(raw, raw)
    assert all(compare_deployments(raw, raw) == expected for _ in range(5))
    script = (
        "import sys;"
        "from services.resilio_app.change_comparison import compare_deployments;"
        "x=bytes.fromhex(sys.argv[1]);"
        "sys.stdout.buffer.write(compare_deployments(x,x))"
    )
    for flag in ([], ["-O"]):
        proc = subprocess.run([sys.executable, *flag, "-c", script, raw.hex()],
                              capture_output=True, check=True, env=os.environ.copy())
        assert proc.stdout == expected
        assert proc.stderr == b""


def test_negative_authority_source_surface():
    source = (Path(__file__).parents[1] / "services/resilio_app/change_comparison.py").read_text()
    forbidden = (
        "import requests", "import socket", "import subprocess",
        "import urllib", "import http", "import provider",
        "open(", "write_text(", "write_bytes(", "getenv(",
        "environ", "credentials", "google.cloud", "terraform", "listen("
    )
    assert all(term not in source for term in forbidden)
