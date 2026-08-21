from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase4_supply_chain as p4  # noqa: E402
import terraform_control_core as tfc  # noqa: E402


class BuildContractTests(unittest.TestCase):
    def test_build_request_is_fixed_and_digest_pinned(self) -> None:
        source, workflow = "a" * 40, "b" * 40
        request = p4.build_request(source, workflow)
        self.assertEqual(request["source"]["gitSource"], {"url": p4.SOURCE_URL, "revision": source})
        self.assertEqual(request["serviceAccount"], f"projects/{p4.CONTROL_PROJECT}/serviceAccounts/{p4.BUILDER}")
        self.assertEqual(request["options"]["requestedVerifyOption"], "VERIFIED")
        self.assertEqual(request["options"]["machineType"], "E2_STANDARD_2")
        self.assertEqual(request["options"]["substitutionOption"], "MUST_MATCH")
        self.assertEqual(request["queueTtl"], "600s")
        self.assertEqual(request["images"], [p4.image_tag(source)])
        for step in request["steps"]:
            self.assertRegex(step["name"], r"@sha256:[0-9a-f]{64}$")
        self.assertIn("--network=none", request["steps"][1]["args"])
        self.assertNotIn("substitutions", request)

    def _build(self, source: str = "a" * 40, workflow: str = "b" * 40) -> dict:
        request = p4.build_request(source, workflow)
        build = copy.deepcopy(request)
        build.update({
            "id": "12345678-abcd",
            "status": "SUCCESS",
            "sourceProvenance": {"resolvedGitSource": {"url": p4.SOURCE_URL, "revision": source}},
            "results": {"images": [{"name": p4.image_tag(source), "digest": "sha256:" + "c" * 64}]},
        })
        return build

    def test_build_validation_binds_requested_and_resolved_source(self) -> None:
        result = p4.validate_build(self._build(), "a" * 40, "b" * 40)
        self.assertEqual(result["image"], f"{p4.IMAGE_PREFIX}@sha256:" + "c" * 64)
        bad = self._build()
        bad["sourceProvenance"]["resolvedGitSource"]["revision"] = "d" * 40
        with self.assertRaisesRegex(p4.SupplyChainError, "BUILD_RESOLVED_SOURCE_MISMATCH"):
            p4.validate_build(bad, "a" * 40, "b" * 40)

    def test_provider_added_response_metadata_does_not_change_build_semantics(self) -> None:
        build = self._build()
        build["steps"][0]["status"] = "SUCCESS"
        build["steps"][0]["timing"] = {"startTime": "x", "endTime": "y"}
        build["options"]["dynamicSubstitutions"] = False
        self.assertEqual(
            p4.validate_build(build, "a" * 40, "b" * 40)["source_sha"],
            "a" * 40,
        )

    def test_build_request_mutation_fails(self) -> None:
        for key, value in (
            ("serviceAccount", "projects/x/serviceAccounts/wide@example.iam.gserviceaccount.com"),
            ("images", ["latest"]),
            ("timeout", "3600s"),
            ("queueTtl", "3600s"),
        ):
            build = self._build()
            build[key] = value
            with self.subTest(key=key), self.assertRaises(p4.SupplyChainError):
                p4.validate_build(build, "a" * 40, "b" * 40)

    def test_build_rejects_unapproved_behaviour_fields(self) -> None:
        mutations = (
            ("top-level substitutions", lambda b: b.__setitem__("substitutions", {"_X": "attacker"})),
            ("top-level availableSecrets", lambda b: b.__setitem__("availableSecrets", {"secretManager": []})),
            ("top-level dependencies", lambda b: b.__setitem__("dependencies", [{"gitSource": {"repository": {"url": "https://example.invalid/repo"}}}])),
            ("options env", lambda b: b["options"].__setitem__("env", ["X=1"])),
            ("options pool", lambda b: b["options"].__setitem__("pool", {"name": "projects/p/locations/l/workerPools/w"})),
            ("step allowFailure", lambda b: b["steps"][0].__setitem__("allowFailure", True)),
        )
        for label, mutate in mutations:
            build = self._build()
            mutate(build)
            with self.subTest(label=label), self.assertRaises(p4.SupplyChainError):
                p4.validate_build(build, "a" * 40, "b" * 40)

    def test_reuse_is_exact_and_ambiguous_reuse_fails(self) -> None:
        build = self._build()
        self.assertEqual(p4.select_existing_build([build], "a" * 40, "b" * 40), build["id"])
        with self.assertRaisesRegex(p4.SupplyChainError, "REUSABLE_BUILD_AMBIGUOUS"):
            p4.select_existing_build([build, copy.deepcopy(build)], "a" * 40, "b" * 40)

    def test_scan_requires_completed_discovery(self) -> None:
        good = {"occurrences": [{"discovered": {"analysisStatus": "FINISHED_SUCCESS", "analysisCompleted": {"analysisType": ["VULNERABILITY"]}}}]}
        self.assertEqual(p4.scan_disposition(good, {"occurrences": []}), "PASS")
        critical = {"occurrences": [{"vulnerability": {"effectiveSeverity": "CRITICAL"}}]}
        self.assertEqual(p4.scan_disposition(good, critical), "FAIL_CRITICAL")
        high = {"occurrences": [{"vulnerability": {"effectiveSeverity": "HIGH"}}]}
        self.assertEqual(p4.scan_disposition(good, high), "HIGH_REVIEW_REQUIRED")
        with self.assertRaisesRegex(p4.SupplyChainError, "VULNERABILITY_SCAN_UNAVAILABLE"):
            p4.scan_disposition({"occurrences": []}, {"occurrences": []})

    def test_pagination_exhausts_later_pages_and_fails_incomplete(self) -> None:
        discovery_pages = [
            {"occurrences": [{"discovered": {"analysisStatus": "FINISHED_SUCCESS", "analysisCompleted": {"analysisType": ["VULNERABILITY"]}}}], "nextPageToken": "next"},
            {"occurrences": []},
        ]
        vulnerability_pages = [
            {"occurrences": [], "nextPageToken": "next"},
            {"occurrences": [{"vulnerability": {"effectiveSeverity": "CRITICAL"}}]},
        ]
        discovery = p4.merge_paged_responses(discovery_pages, "occurrences")
        vulnerabilities = p4.merge_paged_responses(vulnerability_pages, "occurrences")
        self.assertEqual(p4.scan_disposition(discovery, vulnerabilities), "FAIL_CRITICAL")
        with self.assertRaisesRegex(p4.SupplyChainError, "PAGINATION_INCOMPLETE"):
            p4.merge_paged_responses([{"occurrences": [], "nextPageToken": "not-consumed"}], "occurrences")
        with self.assertRaisesRegex(p4.SupplyChainError, "PAGINATION_UNREACHABLE"):
            p4.merge_paged_responses([{"occurrences": [], "unreachable": ["us-central1"]}], "occurrences")

    def test_high_acceptance_requires_exact_owner_identity(self) -> None:
        image = p4.IMAGE_PREFIX + "@sha256:" + "d" * 64
        body = f"PHASE4_HIGH_ACCEPTED image={image}"
        non_owner = [{"body": body, "user": {"login": "someone-else", "id": p4.OWNER_ID}}]
        with self.assertRaisesRegex(p4.SupplyChainError, "HIGH_ACCEPTANCE_OWNER_DISPOSITION_INVALID"):
            p4.owner_high_acceptance(non_owner, image)
        owner = [{"body": body, "user": {"login": p4.OWNER_LOGIN, "id": p4.OWNER_ID}}]
        p4.owner_high_acceptance(owner, image)
        with self.assertRaisesRegex(p4.SupplyChainError, "HIGH_ACCEPTANCE_OWNER_DISPOSITION_INVALID"):
            p4.owner_high_acceptance(owner + copy.deepcopy(owner), image)

    def test_provider_evidence_and_runtime_readback_helpers_fail_closed(self) -> None:
        provenance = {"occurrences": [{"name": "projects/p/occurrences/x", "build": {"provenance": {"id": "build/12345678-abcd"}}}]}
        self.assertEqual(p4.provenance_occurrence(provenance, "12345678-abcd"), "projects/p/occurrences/x")
        sbom_bytes = b"sbom-bytes"
        sbom_response = {"occurrences": [{"name": "projects/p/occurrences/s", "sbomReference": {"payload": {"predicate": {"location": "gs://bucket/object", "digest": {"sha256": p4.sha256_bytes(sbom_bytes)}}}}}]}
        sbom = p4.sbom_reference(sbom_response)
        sbom = p4.bind_sbom_storage(sbom, {"bucket": "bucket", "name": "object", "generation": "123"}, sbom_bytes)
        image = p4.IMAGE_PREFIX + "@sha256:" + "d" * 64
        request = p4.cloud_run_service_request(image, "a" * 40)
        service = copy.deepcopy(request)
        service["latestReadyRevision"] = "projects/p/locations/l/services/s/revisions/r"
        service["uri"] = "https://example.run.app"
        readback = p4.verify_cloud_run_service(service, {"bindings": []}, image, "a" * 40)
        self.assertEqual(readback["uri"], "https://example.run.app")
        p4.verify_cloud_run_revision({"containers": [{"image": image}]}, image)
        p4.verify_health_response({"status": "ok", "source_sha": "a" * 40}, "a" * 40)
        with self.assertRaisesRegex(p4.SupplyChainError, "RUN_PUBLIC_PRINCIPAL_FORBIDDEN"):
            p4.verify_cloud_run_service(service, {"bindings": [{"members": ["allUsers"]}]}, image, "a" * 40)
        self.assertEqual(sbom["sha256"], p4.sha256_bytes(sbom_bytes))
        self.assertEqual(sbom["generation"], "123")

    def test_sbom_storage_binding_requires_exact_generation_and_content_digest(self) -> None:
        content = b"sbom-bytes"
        sbom = {"occurrence": "projects/p/occurrences/s", "location": "gs://bucket/path/object", "sha256": p4.sha256_bytes(content)}
        metadata = {"bucket": "bucket", "name": "path/object", "generation": "456"}
        bound = p4.bind_sbom_storage(sbom, metadata, content)
        self.assertEqual(bound["generation"], "456")
        with self.assertRaisesRegex(p4.SupplyChainError, "SBOM_STORAGE_OBJECT_MISMATCH"):
            p4.bind_sbom_storage(sbom, {"bucket": "other", "name": "path/object", "generation": "456"}, content)
        with self.assertRaisesRegex(p4.SupplyChainError, "SBOM_STORAGE_GENERATION_INVALID"):
            p4.bind_sbom_storage(sbom, {"bucket": "bucket", "name": "path/object", "generation": "0"}, content)
        with self.assertRaisesRegex(p4.SupplyChainError, "SBOM_STORAGE_DIGEST_MISMATCH"):
            p4.bind_sbom_storage(sbom, metadata, b"different-sbom-bytes")

    def test_transition_must_be_digest_bound_and_passed(self) -> None:
        source, workflow = "a" * 40, "b" * 40
        manifest = {
            "contract": "resilio-phase4-transition/v1",
            "build_id": "12345678-abcd",
            "source_sha": source,
            "source_tree_sha": "f" * 40,
            "workflow_sha": workflow,
            "build_request_sha256": p4.build_request_digest(source, workflow),
            "image": p4.IMAGE_PREFIX + "@sha256:" + "d" * 64,
            "provenance": {"occurrence": "projects/p/occurrences/build"},
            "vulnerability": {"result": "PASS"},
            "sbom": {"occurrence": "projects/p/occurrences/sbom", "location": "gs://bucket/object", "sha256": "e" * 64, "generation": "123"},
            "adjudication": "PASS",
        }
        self.assertEqual(p4.validate_transition_manifest(manifest), manifest)
        bad = copy.deepcopy(manifest); bad["image"] = p4.IMAGE_PREFIX + ":latest"
        with self.assertRaisesRegex(p4.SupplyChainError, "TRANSITION_IMAGE_INVALID"):
            p4.validate_transition_manifest(bad)
        bad = copy.deepcopy(manifest); bad["build_request_sha256"] = "0" * 64
        with self.assertRaisesRegex(p4.SupplyChainError, "TRANSITION_BUILD_REQUEST_DIGEST_MISMATCH"):
            p4.validate_transition_manifest(bad)
        bad = copy.deepcopy(manifest); del bad["sbom"]["generation"]
        with self.assertRaisesRegex(p4.SupplyChainError, "TRANSITION_SBOM_INVALID"):
            p4.validate_transition_manifest(bad)


class FoundationPhase4ContractTests(unittest.TestCase):
    def test_historical_sentinel_contract_remains_valid(self) -> None:
        document = {"resource": {"google_service_account": {"phase3_terraform_sentinel": dict(tfc.SENTINEL_RESOURCE)}}}
        self.assertEqual(tfc.validate_candidate_document(document), document)

    def _phase4_plan(self) -> dict:
        rows = [{
            "address": tfc.SENTINEL_ADDRESS, "mode": "managed", "type": "google_service_account",
            "name": "phase3_terraform_sentinel", "provider_name": "registry.terraform.io/hashicorp/google",
            "change": {"actions": ["no-op"], "before": {}, "after": {}, "after_unknown": {},
                       "before_sensitive": False, "after_sensitive": False, "replace_paths": [],
                       "before_identity": None, "after_identity": None},
        }]
        for address, (resource_type, name) in sorted(tfc.PHASE4_CREATE_ADDRESSES.items()):
            rows.append({
                "address": address, "mode": "managed", "type": resource_type, "name": name,
                "provider_name": "registry.terraform.io/hashicorp/google",
                "change": {"actions": ["create"], "before": None, "after": {}, "after_unknown": {},
                           "before_sensitive": False, "after_sensitive": False, "replace_paths": [],
                           "before_identity": None, "after_identity": None},
            })
        return {"format_version": "1.2", "terraform_version": "1.15.8", "applyable": True,
                "complete": True, "errored": False, "resource_changes": rows, "output_changes": {}}

    def test_phase4_material_effect_accepts_only_exact_creation_set(self) -> None:
        effect = tfc.material_effect(self._phase4_plan())
        self.assertEqual(len(effect["resource_changes"]), len(tfc.PHASE4_EFFECT_ADDRESSES))
        bad = self._phase4_plan(); bad["resource_changes"][1]["change"]["actions"] = ["delete", "create"]
        with self.assertRaisesRegex(tfc.ControlError, "PLAN_DESTRUCTIVE_ACTION_FORBIDDEN"):
            tfc.material_effect(bad)

    def test_exact_phase4_foundation_document_is_accepted(self) -> None:
        self.assertEqual(tfc.validate_candidate_document(copy.deepcopy(tfc.PHASE4_FOUNDATION_RESOURCE)),
                         tfc.PHASE4_FOUNDATION_RESOURCE)

    def test_phase4_document_is_closed_against_extra_resource(self) -> None:
        bad = copy.deepcopy(tfc.PHASE4_FOUNDATION_RESOURCE)
        bad["resource"]["google_storage_bucket"]["other"] = {"name": "other"}
        with self.assertRaisesRegex(tfc.ControlError, "PHASE4_FOUNDATION_CONFIGURATION_MISMATCH"):
            tfc.validate_candidate_document(bad)

    def test_phase4_resources_have_no_iam_and_are_literal(self) -> None:
        encoded = json.dumps(tfc.PHASE4_FOUNDATION_RESOURCE, sort_keys=True)
        self.assertNotIn("iam_", encoded)
        self.assertNotIn("${", encoded)
        self.assertNotIn("roles/", encoded)
        self.assertEqual(
            tfc.PHASE4_REPOSITORY_RESOURCE["depends_on"],
            ["google_project_service.control_artifactregistry"],
        )
        self.assertEqual(
            tfc.PHASE4_EVIDENCE_BUCKET_RESOURCE["soft_delete_policy"],
            [{"retention_duration_seconds": 0}],
        )


if __name__ == "__main__":
    unittest.main()
