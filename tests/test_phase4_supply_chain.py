from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
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
        good = {"occurrences": [{"discovery": {"analysisStatus": "FINISHED_SUCCESS", "analysisCompleted": {"analysisType": ["VULNERABILITY"]}}}]}
        self.assertEqual(p4.scan_disposition(good, {"occurrences": []}), "PASS")
        critical = {"occurrences": [{"vulnerability": {"effectiveSeverity": "CRITICAL"}}]}
        self.assertEqual(p4.scan_disposition(good, critical), "FAIL_CRITICAL")
        high = {"occurrences": [{"vulnerability": {"effectiveSeverity": "HIGH"}}]}
        self.assertEqual(p4.scan_disposition(good, high), "HIGH_REVIEW_REQUIRED")
        with self.assertRaisesRegex(p4.SupplyChainError, "VULNERABILITY_SCAN_UNAVAILABLE"):
            p4.scan_disposition({"occurrences": []}, {"occurrences": []})
        legacy = {"occurrences": [{"discovered": {"analysisStatus": "FINISHED_SUCCESS", "analysisCompleted": {"analysisType": ["VULNERABILITY"]}}}]}
        with self.assertRaisesRegex(p4.SupplyChainError, "VULNERABILITY_SCAN_UNAVAILABLE"):
            p4.scan_disposition(legacy, {"occurrences": []})

    def test_pagination_exhausts_later_pages_and_fails_incomplete(self) -> None:
        discovery_pages = [
            {"occurrences": [{"discovery": {"analysisStatus": "FINISHED_SUCCESS", "analysisCompleted": {"analysisType": ["VULNERABILITY"]}}}], "nextPageToken": "next"},
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
        self.assertNotIn("invokerIamDisabled", request)
        service = copy.deepcopy(request)
        service["latestReadyRevision"] = "projects/p/locations/l/services/s/revisions/r"
        service["uri"] = "https://example.run.app"
        readback = p4.verify_cloud_run_service(service, {"bindings": []}, image, "a" * 40)
        self.assertEqual(readback["uri"], "https://example.run.app")
        p4.verify_cloud_run_revision({"containers": [{"image": image}]}, image)
        p4.verify_health_response({"status": "ok", "source_sha": "a" * 40}, "a" * 40)
        disabled = copy.deepcopy(service)
        disabled["invokerIamDisabled"] = True
        with self.assertRaisesRegex(p4.SupplyChainError, "RUN_ACCESS_POSTURE_MISMATCH"):
            p4.verify_cloud_run_service(disabled, {"bindings": []}, image, "a" * 40)
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


class GoogleApiDiagnosticTests(unittest.TestCase):
    def _files(self, directory: str, body: bytes, status: bytes = b"403\n") -> tuple[str, str]:
        response = Path(directory) / "response.json"
        status_file = Path(directory) / "response.http-status"
        response.write_bytes(body)
        status_file.write_bytes(status)
        return str(response), str(status_file)

    def _error(self, metadata: dict[str, str] | None = None) -> bytes:
        return json.dumps({"error": {
            "code": 403,
            "message": "Permission denied for caller 192.0.2.10 token=do-not-emit",
            "status": "PERMISSION_DENIED",
            "details": [{
                "@type": p4.GOOGLE_ERROR_INFO_TYPE,
                "reason": "IAM_PERMISSION_DENIED",
                "domain": "containeranalysis.googleapis.com",
                "metadata": metadata or {
                    "service": "containeranalysis.googleapis.com",
                    "permission": "containeranalysis.occurrences.list",
                },
            }],
        }}).encode()

    def test_representative_error_info_403_is_structured_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            response, status = self._files(directory, self._error())
            exit_code, diagnostic = p4.google_api_response_disposition(
                response, status, 0, "DISCOVERY", "33289172886",
                "ed34bfbe-b081-4e60-b787-393e6f600cce",
            )
        self.assertEqual(exit_code, 1)
        self.assertIsNotNone(diagnostic)
        assert diagnostic is not None
        self.assertEqual(diagnostic["http_code"], 403)
        self.assertEqual(diagnostic["google_error_code"], 403)
        self.assertEqual(diagnostic["google_error_status"], "PERMISSION_DENIED")
        self.assertEqual(diagnostic["message_category"], "PERMISSION_DENIED")
        self.assertEqual(diagnostic["error_info_reasons"], ["IAM_PERMISSION_DENIED"])
        self.assertEqual(diagnostic["error_info_domains"], ["containeranalysis.googleapis.com"])
        self.assertEqual(diagnostic["workflow_run_id"], "33289172886")
        self.assertEqual(diagnostic["preserved_build_id"], "ed34bfbe-b081-4e60-b787-393e6f600cce")

    def test_only_allowlisted_safe_metadata_values_are_emitted(self) -> None:
        metadata = {
            "service": "containeranalysis.googleapis.com",
            "permission": "containeranalysis.occurrences.list",
            "consumer": "projects/secret-billing-id",
            "resource": "//containeranalysis.googleapis.com/projects/secret-project",
            "credential": "Authorization: Bearer secret-token",
            "unknown_key": "192.0.2.10 arbitrary secret",
        }
        with tempfile.TemporaryDirectory() as directory:
            response, _ = self._files(directory, self._error(metadata))
            diagnostic = p4.sanitize_google_api_error(
                response, 403, "VULNERABILITY", "33289172886",
                "ed34bfbe-b081-4e60-b787-393e6f600cce",
            )
        encoded = p4.canonical_json_bytes(diagnostic).decode()
        self.assertEqual(diagnostic["metadata_keys"], sorted(metadata))
        self.assertEqual(diagnostic["safe_metadata_values"], {
            "permission": ["containeranalysis.occurrences.list"],
            "service": ["containeranalysis.googleapis.com"],
        })
        for forbidden in (
            "secret-billing-id", "secret-project", "secret-token", "192.0.2.10",
            "Authorization", "Bearer", "do-not-emit",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_unknown_metadata_keys_emit_keys_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            response, _ = self._files(directory, self._error({"futureMetadataKey": "private-value"}))
            diagnostic = p4.sanitize_google_api_error(
                response, 403, "PROVENANCE", "33289172886",
                "ed34bfbe-b081-4e60-b787-393e6f600cce",
            )
        self.assertEqual(diagnostic["metadata_keys"], ["futureMetadataKey"])
        self.assertNotIn("safe_metadata_values", diagnostic)
        self.assertNotIn("private-value", json.dumps(diagnostic))

    def test_malformed_and_oversized_responses_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            response, _ = self._files(directory, b"not-json")
            with self.assertRaisesRegex(p4.SupplyChainError, "GOOGLE_API_RESPONSE_JSON_INVALID"):
                p4.sanitize_google_api_error(
                    response, 403, "EXPORT_SBOM", "33289172886",
                    "ed34bfbe-b081-4e60-b787-393e6f600cce",
                )
            Path(response).write_bytes(b"x" * (p4.GOOGLE_API_RESPONSE_MAX_BYTES + 1))
            with self.assertRaisesRegex(p4.SupplyChainError, "GOOGLE_API_RESPONSE_SIZE_INVALID"):
                p4.sanitize_google_api_error(
                    response, 403, "EXPORT_SBOM", "33289172886",
                    "ed34bfbe-b081-4e60-b787-393e6f600cce",
                )

    def test_unknown_error_detail_structure_fails_closed(self) -> None:
        payload = {"error": {
            "code": 403,
            "status": "PERMISSION_DENIED",
            "details": [{
                "@type": "type.googleapis.com/google.rpc.DebugInfo",
                "stackEntries": ["Authorization: Bearer private-token"],
            }],
        }}
        with tempfile.TemporaryDirectory() as directory:
            response, _ = self._files(directory, json.dumps(payload).encode())
            with self.assertRaisesRegex(p4.SupplyChainError, "GOOGLE_API_ERROR_DETAIL_UNSUPPORTED"):
                p4.sanitize_google_api_error(
                    response, 403, "EXPORT_SBOM", "33289172886",
                    "ed34bfbe-b081-4e60-b787-393e6f600cce",
                )

    def test_success_is_silent_and_does_not_read_or_change_response(self) -> None:
        body = b"successful response remains byte-for-byte unchanged"
        with tempfile.TemporaryDirectory() as directory:
            response, status = self._files(directory, body, b"200\n")
            exit_code, diagnostic = p4.google_api_response_disposition(
                response, status, 0, "SBOM_REFERENCE", "33289172886",
                "ed34bfbe-b081-4e60-b787-393e6f600cce",
            )
            self.assertEqual(Path(response).read_bytes(), body)
        self.assertEqual((exit_code, diagnostic), (0, None))

    def test_transport_failure_is_separate_and_does_not_read_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            response = str(Path(directory) / "not-created.json")
            status = str(Path(directory) / "not-created.status")
            exit_code, diagnostic = p4.google_api_response_disposition(
                response, status, 6, "DISCOVERY", "33289172886",
                "ed34bfbe-b081-4e60-b787-393e6f600cce",
            )
        self.assertEqual(exit_code, 1)
        self.assertIsNotNone(diagnostic)
        assert diagnostic is not None
        self.assertEqual(diagnostic["message_category"], "TRANSPORT_FAILURE")
        self.assertEqual(diagnostic["curl_exit_code"], 6)
        self.assertNotIn("http_code", diagnostic)

    def test_cli_non_2xx_emits_only_diagnostic_and_returns_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            response, status = self._files(directory, self._error())
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/phase4_supply_chain.py"),
                "google-api-response", "--response-json", response,
                "--http-status-file", status, "--curl-exit-code", "0",
                "--request-category", "DISCOVERY", "--workflow-run-id", "33289172886",
                "--preserved-build-id", "ed34bfbe-b081-4e60-b787-393e6f600cce",
            ], check=False, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        diagnostic = json.loads(result.stdout)
        self.assertEqual(diagnostic["http_code"], 403)
        self.assertNotIn("do-not-emit", result.stdout)


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


class Phase4DeploymentEnvelopeTests(unittest.TestCase):
    def _envelope(self) -> dict:
        return copy.deepcopy(p4.PHASE4_DEPLOYMENT_ENVELOPE_EXPECTED)

    def _release(self, envelope: dict | None = None) -> str:
        value = envelope if envelope is not None else self._envelope()
        return p4.sha256_bytes(p4.canonical_json_bytes(value))

    def _write_envelope(self, directory: str, envelope: dict | None = None) -> tuple[str, str]:
        value = envelope if envelope is not None else self._envelope()
        path = Path(directory) / "envelope.json"
        path.write_bytes(p4.canonical_json_bytes(value))
        return str(path), self._release(value)

    def test_envelope_requires_exact_canonical_bytes_and_release_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path, release = self._write_envelope(directory)
            self.assertEqual(
                p4.load_deployment_envelope(path, release),
                p4.PHASE4_DEPLOYMENT_ENVELOPE_EXPECTED,
            )
            Path(path).write_bytes(Path(path).read_bytes() + b"\n")
            with self.assertRaisesRegex(p4.SupplyChainError, "DEPLOYMENT_ENVELOPE_NOT_CANONICAL"):
                p4.load_deployment_envelope(path, release)

    def test_envelope_rejects_release_and_risk_identity_substitution(self) -> None:
        envelope = self._envelope()
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self._write_envelope(directory, envelope)
            with self.assertRaisesRegex(p4.SupplyChainError, "DEPLOYMENT_RELEASE_ID_MISMATCH"):
                p4.load_deployment_envelope(path, "0" * 64)
            bad = self._envelope()
            bad["evidence"]["vulnerability"]["decision"]["comment_id"] += 1
            bad_path = Path(directory) / "bad.json"
            bad_path.write_bytes(p4.canonical_json_bytes(bad))
            bad_release = p4.sha256_bytes(bad_path.read_bytes())
            with self.assertRaisesRegex(p4.SupplyChainError, "DEPLOYMENT_ENVELOPE_MISMATCH"):
                p4.load_deployment_envelope(str(bad_path), bad_release)

    def test_owner_authority_and_attempt_bound_consumption_fail_closed(self) -> None:
        release = self._release()
        authority_id = 6000000001
        authority = {
            "id": authority_id,
            "issue_url": "https://api.github.com/repos/8ft0-ai/resilio/issues/90",
            "user": {"login": p4.OWNER_LOGIN, "id": p4.OWNER_ID},
            "body": (
                f"{p4.DEPLOYMENT_AUTHORITY_PREFIX} release_id={release} "
                f"envelope_commit={'a' * 40} service={p4.DEPLOYMENT_SERVICE} "
                "transition=CREATE_IF_ABSENT"
            ),
        }
        parsed = p4.validate_deployment_authority_comment(authority, authority_id)
        self.assertEqual(parsed["release_id"], release)
        with self.assertRaisesRegex(p4.SupplyChainError, "DEPLOYMENT_RUN_ATTEMPT_NOT_FIRST"):
            p4.deployment_consumption_body(authority_id, release, 123, 2)
        body = p4.deployment_consumption_body(authority_id, release, 123, 1)
        consumption = {
            "id": 6000000002,
            "user": {"login": p4.GITHUB_ACTIONS_LOGIN, "id": 41898282},
            "body": body,
        }
        result = p4.verify_deployment_consumption([[consumption]], authority_id, release, 123, 1)
        self.assertEqual(result["comment_id"], 6000000002)
        with self.assertRaisesRegex(p4.SupplyChainError, "DEPLOYMENT_CONSUMPTION_NOT_UNIQUE"):
            p4.verify_deployment_consumption(
                [[consumption, copy.deepcopy(consumption)]], authority_id, release, 123, 1
            )

    def test_risk_comment_substitution_is_rejected(self) -> None:
        envelope = self._envelope()
        decision = envelope["evidence"]["vulnerability"]["decision"]
        acceptance = envelope["evidence"]["vulnerability"]["acceptance"]
        consumption = envelope["evidence"]["vulnerability"]["consumption"]
        wrong = {
            "id": decision["comment_id"],
            "user": {"login": p4.OWNER_LOGIN, "id": p4.OWNER_ID},
            "body": "substituted",
        }
        acceptance_shape = {
            "id": acceptance["comment_id"],
            "user": {"login": p4.OWNER_LOGIN, "id": p4.OWNER_ID},
            "body": "irrelevant",
        }
        consumption_shape = {
            "id": consumption["comment_id"],
            "user": {"login": p4.GITHUB_ACTIONS_LOGIN, "id": 41898282},
            "body": "irrelevant",
        }
        with self.assertRaisesRegex(p4.SupplyChainError, "DEPLOYMENT_RISK_COMMENT_BODY_MISMATCH"):
            p4.verify_deployment_risk_comments(
                envelope, wrong, acceptance_shape, consumption_shape
            )

    def test_transition_must_bind_exact_envelope_tuple(self) -> None:
        envelope = self._envelope()
        artifact = envelope["artifact"]
        sbom = envelope["evidence"]["sbom"]
        transition = {
            "contract": "resilio-phase4-transition/v1",
            "build_id": artifact["build_id"],
            "source_sha": artifact["source_sha"],
            "source_tree_sha": artifact["source_tree_sha"],
            "workflow_sha": artifact["build_control_sha"],
            "build_request_sha256": artifact["build_request_sha256"],
            "image": artifact["image"],
            "provenance": {"occurrence": artifact["provenance_occurrence"]},
            "vulnerability": {"result": "PASS"},
            "sbom": {
                "occurrence": "projects/resilio-control-e882d4/occurrences/sbom",
                "location": sbom["object"],
                "sha256": sbom["sha256"],
                "generation": sbom["generation"],
            },
            "adjudication": "PASS",
        }
        p4.validate_deployment_transition_binding(envelope, transition)
        transition["source_sha"] = "b" * 40
        with self.assertRaises(p4.SupplyChainError):
            p4.validate_deployment_transition_binding(envelope, transition)

    def test_provider_operation_outcome_supports_read_only_reconciliation(self) -> None:
        operation = (
            "projects/resilio-reference-e882d4/locations/us-central1/"
            "operations/phase4-create-1"
        )
        self.assertEqual(
            p4.deployment_operation_outcome({"name": operation}, operation),
            {"disposition": "PENDING", "revision": None},
        )
        revision = (
            "projects/resilio-reference-e882d4/locations/us-central1/services/"
            "phase4-proof/revisions/phase4-proof-00001"
        )
        self.assertEqual(
            p4.deployment_operation_outcome(
                {
                    "name": operation,
                    "done": True,
                    "response": {
                        "latestCreatedRevision": revision,
                        "latestReadyRevision": revision,
                    },
                },
                operation,
            ),
            {"disposition": "PROVIDER_CREATED", "revision": revision},
        )
        self.assertEqual(
            p4.deployment_operation_outcome(
                {"name": operation, "done": True, "error": {"code": 13}},
                operation,
            ),
            {"disposition": "CREATE_FAILED_KNOWN", "revision": None},
        )
        self.assertEqual(
            p4.deployment_operation_outcome(
                {
                    "name": operation,
                    "done": True,
                    "response": {
                        "latestCreatedRevision": revision,
                        "latestReadyRevision": revision + "-other",
                    },
                },
                operation,
            ),
            {"disposition": "CREATE_OUTCOME_UNKNOWN", "revision": None},
        )
        with self.assertRaisesRegex(
            p4.SupplyChainError, "DEPLOYMENT_OPERATION_IDENTITY_MISMATCH"
        ):
            p4.deployment_operation_outcome(
                {"name": operation + "-other", "done": False},
                operation,
            )

    def test_create_request_and_verification_bind_exact_revision_and_traffic(self) -> None:
        envelope = self._envelope()
        request = p4.deployment_cloud_run_create_request(envelope)
        self.assertNotIn("name", request)
        self.assertEqual(
            request["traffic"],
            [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST", "percent": 100}],
        )
        revision = (
            "projects/resilio-reference-e882d4/locations/us-central1/services/"
            "phase4-proof/revisions/phase4-proof-00001"
        )
        service = copy.deepcopy(request)
        service.update({
            "name": p4.DEPLOYMENT_SERVICE,
            "latestCreatedRevision": revision,
            "latestReadyRevision": revision,
            "trafficStatuses": [{"revision": revision, "percent": 100}],
            "uri": "https://phase4-proof.example.run.app",
        })
        result = p4.verify_deployment_cloud_run_service(
            envelope, service, {"bindings": []}, revision
        )
        self.assertEqual(result["revision"], revision)
        wrong_traffic = copy.deepcopy(service)
        wrong_traffic["trafficStatuses"] = [{"revision": revision, "percent": 99}]
        with self.assertRaisesRegex(p4.SupplyChainError, "DEPLOYMENT_TRAFFIC_MISMATCH"):
            p4.verify_deployment_cloud_run_service(
                envelope, wrong_traffic, {"bindings": []}, revision
            )
        with self.assertRaisesRegex(p4.SupplyChainError, "DEPLOYMENT_PUBLIC_PRINCIPAL_FORBIDDEN"):
            p4.verify_deployment_cloud_run_service(
                envelope, service, {"bindings": [{"members": ["allUsers"]}]}, revision
            )


if __name__ == "__main__":
    unittest.main()
