"""Verify the exact committed Phase 4-derived acceptance fixture, then emit JCS.

Credential-free. This is not a caller, dispatch mechanism or cloud authority.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from services.resilio_app.core import event_from_bytes

ROOT = Path(__file__).resolve().parents[1]
RELEASE_ID = "a24dd47861df1e07f89116493071c70a3119d100611a59e0bb1a67d3fcba11f3"
RELEASE = ROOT / "deployments" / "phase4" / "revisions" / (RELEASE_ID + ".json")
FIXTURE = ROOT / "tests" / "fixtures" / "phase5-phase4-observed-v1.json"
REVISION = "phase4-proof-00002-jq5"
OPERATION = "baf9da9b-339f-4c30-a41b-845a7311b002"


def verified_event():
    release = json.loads(RELEASE.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected = {
        "schema_version": 1,
        "event_type": "deployment.observed",
        "service": {"id": "phase4-proof"},
        "environment": {"id": "resilio-reference-e882d4"},
        "change": {"repository": "8ft0-ai/resilio", "source_sha": release["artifact"]["source_sha"]},
        "deployment": {
            "id": REVISION, "release_id": RELEASE_ID,
            "artifact_digest": release["artifact"]["image"].split("@", 1)[1],
            "runtime": {
                "provider": "gcp", "kind": "cloud_run_revision",
                "resource_id": "projects/resilio-reference-e882d4/locations/us-central1/"
                               "services/phase4-proof/revisions/" + REVISION,
            },
        },
        "evidence": [
            {"kind": "phase4_release", "ref": "deployments/phase4/revisions/" + RELEASE_ID + ".json"},
            {"kind": "provider_operation", "ref": OPERATION},
            {"kind": "sbom", "ref": release["evidence"]["sbom"]["object"],
             "sha256": release["evidence"]["sbom"]["sha256"]},
            {"kind": "transition", "ref": release["evidence"]["transition"]["object"],
             "sha256": release["evidence"]["transition"]["sha256"]},
        ],
    }
    if fixture != expected:
        raise RuntimeError("PHASE4_ACCEPTANCE_FIXTURE_DRIFT")
    event = event_from_bytes(FIXTURE.read_bytes())
    if event.event_id != "1e3f7b39b9ae97578982e42e557744345eb7af1ad82257c076a03eac36ca4494":
        raise RuntimeError("FIXTURE_EVENT_ID_MISMATCH")
    return event


if __name__ == "__main__":
    sys.stdout.buffer.write(verified_event().canonical_bytes)
