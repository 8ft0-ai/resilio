"""Credential-free Phase 5 control-envelope and Terraform-boundary tests."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.phase5_control_seed import (
    ControlError, EVIDENCE_BUCKET, EXACT_RESOURCES, FIXED_CONFIG, IMAGE_REPOSITORY,
    SERVICES, validate_inert_operation, validate_release, require_absence,
)
from scripts.phase5_terraform_seed import (
    BASE_ADDRESSES, CandidateError, LOCK_PATH, ROUTING_ADDRESS, STATE_BUCKET,
    STATE_PATH, validate_candidate,
)


def sample_release() -> dict:
    image = IMAGE_REPOSITORY + "@sha256:" + "a" * 64
    service_configuration = {}
    for name, (component, runtime) in SERVICES.items():
        service_configuration[name] = {
            "resource": next(path for path in EXACT_RESOURCES if path.endswith("/" + name)),
            "component": component,
            "runtime_service_account": runtime,
            "image": image,
            **FIXED_CONFIG,
        }
    return {
        "contract": "resilio-phase5-product-release/v1",
        "source_sha": "1" * 40,
        "control_sha": "2" * 40,
        "image": image,
        "build_id": "unused-test-build-identity",
        "evidence": {
            "tests_sha256": "3" * 64,
            "sbom": {"ref": EVIDENCE_BUCKET + "/sbom.json", "sha256": "4" * 64},
            "vulnerability": {"ref": EVIDENCE_BUCKET + "/scan.json", "sha256": "5" * 64},
            "provenance": {"ref": EVIDENCE_BUCKET + "/provenance.json", "sha256": "6" * 64},
        },
        "services": service_configuration,
    }


def candidate(addresses) -> bytes:
    return json.dumps({
        "contract": "resilio-product-terraform-candidate/v1",
        "state_bucket": STATE_BUCKET,
        "state_path": STATE_PATH,
        "lock_path": LOCK_PATH,
        "addresses": addresses,
    }).encode("utf-8")


class ProductControlTests(unittest.TestCase):
    def test_exact_one_image_three_services(self):
        release = sample_release()
        digest = validate_release(release)
        self.assertEqual(digest, validate_release(release))
        self.assertEqual(len(digest), 64)

    def test_service_authority_is_not_shared(self):
        for invalid in ("resilio-ingest", "resilio-processor", "resilio-api"):
            release = sample_release()
            release["services"][invalid]["runtime_service_account"] = (
                release["services"]["resilio-ingest"]["runtime_service_account"]
                if invalid != "resilio-ingest" else
                release["services"]["resilio-api"]["runtime_service_account"]
            )
            if invalid == "resilio-ingest":
                self.assertNotEqual(
                    release["services"][invalid]["runtime_service_account"],
                    SERVICES[invalid][1],
                )
            else:
                self.assertNotEqual(
                    release["services"][invalid]["runtime_service_account"],
                    SERVICES[invalid][1],
                )
            with self.assertRaises(ControlError):
                validate_release(release)

    def test_reject_unapproved_service_or_digest(self):
        release = sample_release()
        release["services"]["unauthorised-fourth-service"] = {}
        with self.assertRaises(ControlError):
            validate_release(release)
        release = sample_release()
        release["services"]["resilio-api"]["image"] = IMAGE_REPOSITORY + "@sha256:" + "b" * 64
        with self.assertRaises(ControlError):
            validate_release(release)

    def test_reject_broad_or_public_configuration(self):
        for key, value in (
            ("min_instances", 1), ("max_instances", 2), ("public", True),
            ("timeout_seconds", 30), ("concurrency", 80),
        ):
            release = sample_release()
            release["services"]["resilio-processor"][key] = value
            with self.assertRaises(ControlError):
                validate_release(release)

    def test_create_if_absent_excludes_unknown_existing_and_partial(self):
        empty = {name: {"status": "ABSENT"} for name in EXACT_RESOURCES}
        require_absence(empty)
        for key in EXACT_RESOURCES:
            existing = {name: value.copy() for name, value in empty.items()}
            existing[key] = {"status": "EXISTS"}
            with self.assertRaises(ControlError):
                require_absence(existing)
        with self.assertRaises(ControlError):
            require_absence({})
        with self.assertRaises(ControlError):
            require_absence({**empty, "unexpected": {"status": "ABSENT"}})

    def test_inert_workflows_have_no_valid_execution_kind(self):
        for kind in ("build", "evidence", "deploy", "verify", "acceptance",
                     "terraform-plan", "terraform-apply", "unknown"):
            with self.assertRaises(ControlError):
                validate_inert_operation(kind)

    def test_terraform_address_only_not_live_grammar(self):
        self.assertEqual(validate_candidate(candidate(sorted(BASE_ADDRESSES))),
                         tuple(sorted(BASE_ADDRESSES)))
        self.assertEqual(validate_candidate(candidate([ROUTING_ADDRESS])),
                         (ROUTING_ADDRESS,))
        for bad in (
            ["google_project_iam_member.administrator"],
            ["google_service_account.runtime"],
            ["google_cloud_run_v2_service.product"],
            [ROUTING_ADDRESS, next(iter(BASE_ADDRESSES))],
            [next(iter(BASE_ADDRESSES))] * 2,
            [],
        ):
            with self.assertRaises(CandidateError):
                validate_candidate(candidate(bad))

    def test_terraform_rejects_wrong_state_or_duplicate_json_keys(self):
        with self.assertRaises(CandidateError):
            validate_candidate(candidate([next(iter(BASE_ADDRESSES))]).replace(
                b"product/default.tfstate", b"foundation/default.tfstate"
            ))
        with self.assertRaises(CandidateError):
            validate_candidate(b'{"contract":1,"contract":2}')


if __name__ == "__main__":
    unittest.main()
