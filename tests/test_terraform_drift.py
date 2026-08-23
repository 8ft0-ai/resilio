from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import terraform_control as control  # noqa: E402
import terraform_drift as drift  # noqa: E402
import validate_terraform_control as validator  # noqa: E402


class DriftManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {
            "lineage": "lineage-1",
            "serial": 1,
            "generation": "123",
            "managed_resource_count": 0,
        }
        self.plan = {
            "format_version": "1.2",
            "terraform_version": "1.15.8",
            "applyable": False,
            "complete": True,
            "errored": False,
            "resource_drift": [],
            "resource_changes": [],
            "output_changes": {},
        }

    def _manifest(self, plan: dict | None = None, state: dict | None = None,
                  candidate_digest: str = "b" * 64) -> dict:
        return drift.build_drift_manifest(
            plan=self.plan if plan is None else plan,
            state_identity=self.state if state is None else state,
            main_sha="a" * 40,
            candidate_digest=candidate_digest,
            trusted_workflow_sha="c" * 40,
            provider_lock_digest="d" * 64,
            workflow_run_id="1234",
        )

    def _sentinel_row(self, actions: list[str], *, after: dict | None = None) -> dict:
        return {
            "address": control.SENTINEL_ADDRESS,
            "mode": "managed",
            "type": "google_service_account",
            "name": "phase3_terraform_sentinel",
            "provider_name": "registry.terraform.io/hashicorp/google",
            "change": {
                "actions": actions,
                "before": None,
                "after": after,
                "after_unknown": {},
                "before_sensitive": False,
                "after_sensitive": False,
                "replace_paths": [],
                "before_identity": None,
                "after_identity": None,
            },
        }

    def _resource_row(self, address: str, resource_type: str, name: str,
                      actions: list[str], *, after: dict | None = None) -> dict:
        row = self._sentinel_row(actions, after=after)
        row.update({
            "address": address,
            "type": resource_type,
            "name": name,
        })
        return row

    def test_empty_root_no_drift_is_sanitised(self) -> None:
        manifest = self._manifest()
        self.assertEqual(manifest["status"], "NO_DRIFT")
        self.assertEqual(manifest["findings"], [])
        self.assertEqual(manifest["root"], "foundation")
        self.assertEqual(manifest["backend_namespace"], control.BACKEND_NAMESPACE)
        self.assertEqual(manifest["state"], {"lineage": "lineage-1", "serial": 1, "generation": "123"})

    def test_exact_sentinel_noop_is_not_drift(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["resource_changes"] = [self._sentinel_row(["no-op"], after={"email": "secret@example.invalid"})]
        manifest = self._manifest(plan)
        self.assertEqual(manifest["status"], "NO_DRIFT")
        self.assertNotIn("secret@example.invalid", json.dumps(manifest, sort_keys=True))

    def test_expected_non_sentinel_noop_is_not_drift(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["resource_changes"] = [self._resource_row(
            "google_storage_bucket.phase4_evidence",
            "google_storage_bucket",
            "phase4_evidence",
            ["no-op"],
            after={"name": "secret-bucket-value"},
        )]
        manifest = self._manifest(plan)
        self.assertEqual(manifest["status"], "NO_DRIFT")
        self.assertEqual(manifest["findings"], [])
        self.assertNotIn("secret-bucket-value", json.dumps(manifest, sort_keys=True))

    def test_planned_sentinel_change_is_drift_without_values(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["applyable"] = True
        plan["resource_changes"] = [self._sentinel_row(["update"], after={"description": "sensitive-value"})]
        manifest = self._manifest(plan)
        self.assertEqual(manifest["status"], "DRIFT")
        self.assertEqual(manifest["findings"], [{
            "source": "planned_change",
            "address": control.SENTINEL_ADDRESS,
            "actions": ["update"],
            "classification": "sentinel",
        }])
        self.assertNotIn("sensitive-value", json.dumps(manifest, sort_keys=True))

    def test_refresh_observation_with_noop_plan_is_not_actionable_drift(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["resource_drift"] = [self._resource_row(
            "google_artifact_registry_repository.phase4",
            "google_artifact_registry_repository",
            "phase4",
            ["update"],
            after={"update_time": "secret-provider-metadata"},
        )]
        plan["resource_changes"] = [self._resource_row(
            "google_artifact_registry_repository.phase4",
            "google_artifact_registry_repository",
            "phase4",
            ["no-op"],
        )]
        manifest = self._manifest(plan)
        self.assertEqual(manifest["status"], "NO_DRIFT")
        self.assertEqual(manifest["findings"], [])
        self.assertNotIn("secret-provider-metadata", json.dumps(manifest, sort_keys=True))

    def test_resource_drift_without_planned_row_remains_drift(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["resource_drift"] = [self._resource_row(
            "google_storage_bucket.unexpected",
            "google_storage_bucket",
            "unexpected",
            ["update"],
            after={"updated": "secret-provider-metadata"},
        )]
        manifest = self._manifest(plan)
        self.assertEqual(manifest["status"], "DRIFT")
        self.assertEqual(manifest["findings"], [{
            "source": "resource_drift",
            "address": "google_storage_bucket.unexpected",
            "actions": ["update"],
            "classification": "unexpected-resource",
        }])
        self.assertNotIn("secret-provider-metadata", json.dumps(manifest, sort_keys=True))

    def test_resource_drift_with_planned_update_remains_drift(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["applyable"] = True
        plan["resource_drift"] = [self._sentinel_row(["update"], after={"display_name": "changed-live"})]
        plan["resource_changes"] = [self._sentinel_row(["update"], after={"display_name": "changed-live"})]
        manifest = self._manifest(plan)
        self.assertEqual(manifest["status"], "DRIFT")
        self.assertEqual({finding["source"] for finding in manifest["findings"]}, {"resource_drift", "planned_change"})
        self.assertNotIn("changed-live", json.dumps(manifest, sort_keys=True))

    def test_unexpected_resource_is_classified_without_attributes(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["applyable"] = True
        row = self._resource_row(
            "google_storage_bucket.unexpected",
            "google_storage_bucket",
            "unexpected",
            ["delete"],
            after={"secret": "do-not-publish"},
        )
        plan["resource_changes"] = [row]
        manifest = self._manifest(plan)
        self.assertEqual(manifest["status"], "DRIFT")
        self.assertEqual(manifest["findings"][0]["classification"], "unexpected-resource")
        self.assertNotIn("do-not-publish", json.dumps(manifest, sort_keys=True))

    def test_duplicate_resource_address_fails_closed(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["resource_changes"] = [
            self._sentinel_row(["no-op"]),
            self._sentinel_row(["no-op"]),
        ]
        with self.assertRaisesRegex(control.ControlError, "DRIFT_RESOURCE_ADDRESS_DUPLICATE"):
            self._manifest(plan)

    def test_fingerprint_is_stable_across_state_generation(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["applyable"] = True
        plan["resource_changes"] = [self._sentinel_row(["create"])]
        first = self._manifest(plan)
        changed_state = dict(self.state, generation="999", serial=9)
        second = self._manifest(plan, changed_state)
        self.assertEqual(first["drift_fingerprint"], second["drift_fingerprint"])

    def test_fingerprint_changes_with_candidate_identity(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["applyable"] = True
        plan["resource_changes"] = [self._sentinel_row(["create"])]
        self.assertNotEqual(
            self._manifest(plan, candidate_digest="b" * 64)["drift_fingerprint"],
            self._manifest(plan, candidate_digest="e" * 64)["drift_fingerprint"],
        )

    def test_output_changes_fail_closed(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["output_changes"] = {"unexpected": {"actions": ["update"]}}
        with self.assertRaisesRegex(control.ControlError, "DRIFT_OUTPUT_CHANGES_FORBIDDEN"):
            self._manifest(plan)

    def test_deferred_or_action_invocation_fails_closed(self) -> None:
        for field, value, error in (
            ("deferred_changes", [{"reason": "unknown"}], "DRIFT_DEFERRED_CHANGES"),
            ("deferred_action_invocations", [{"reason": "unknown"}], "DRIFT_DEFERRED_ACTION_INVOCATIONS"),
            ("action_invocations", [{"address": "action.foo"}], "DRIFT_ACTION_INVOCATIONS"),
        ):
            plan = json.loads(json.dumps(self.plan))
            plan[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(control.ControlError, error):
                self._manifest(plan)

    def test_supported_terraform_1158_action_sequences_are_accepted(self) -> None:
        for actions in sorted(drift.SAFE_DRIFT_ACTION_SEQUENCES):
            plan = json.loads(json.dumps(self.plan))
            plan["applyable"] = actions != ("no-op",)
            plan["resource_changes"] = [self._sentinel_row(list(actions))]
            with self.subTest(actions=actions):
                self._manifest(plan)

    def test_malformed_known_action_sequences_fail_closed(self) -> None:
        for actions in (
            ["create", "update"],
            ["update", "create"],
            ["no-op", "delete"],
            ["create", "create"],
            ["forget", "create"],
            ["create", "forget", "delete"],
        ):
            plan = json.loads(json.dumps(self.plan))
            plan["applyable"] = True
            plan["resource_changes"] = [self._sentinel_row(actions)]
            with self.subTest(actions=actions), self.assertRaisesRegex(control.ControlError, "DRIFT_ACTION_SEQUENCE_INVALID"):
                self._manifest(plan)

    def test_unknown_future_action_fails_closed(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["applyable"] = True
        plan["resource_changes"] = [self._sentinel_row(["future-action"])]
        with self.assertRaisesRegex(control.ControlError, "DRIFT_ACTION_SEQUENCE_INVALID"):
            self._manifest(plan)

    def test_unknown_plan_structure_fails_closed(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["future_field"] = {}
        with self.assertRaisesRegex(control.ControlError, "DRIFT_PLAN_STRUCTURE_UNRECOGNISED"):
            self._manifest(plan)

    def test_workflow_call_only_guard_rejects_active_triggers(self) -> None:
        callable_only = """name: Test reusable

on:
  workflow_call:
    inputs:
      value:
        required: false
        type: string

jobs:
  test:
    runs-on: ubuntu-latest
"""
        errors: list[str] = []
        validator.check_workflow_call_only("test.yml", callable_only, errors)
        self.assertEqual(errors, [])
        for event in ("push", "schedule", "repository_dispatch"):
            text = callable_only.replace("  workflow_call:\n", f"  workflow_call:\n  {event}:\n", 1)
            errors = []
            validator.check_workflow_call_only("test.yml", text, errors)
            with self.subTest(event=event):
                self.assertTrue(errors)
                self.assertIn("workflow_call-only", errors[0])


if __name__ == "__main__":
    unittest.main()
