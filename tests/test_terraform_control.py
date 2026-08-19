from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import terraform_control as control  # noqa: E402


class CandidateContractTests(unittest.TestCase):
    def test_slice_a_empty_payload_is_valid(self) -> None:
        self.assertEqual(control.validate_candidate_document({}), {})

    def test_exact_sentinel_payload_is_valid(self) -> None:
        document = {"resource": {"google_service_account": {"phase3_terraform_sentinel": dict(control.SENTINEL_RESOURCE)}}}
        self.assertEqual(control.validate_candidate_document(document), document)

    def test_duplicate_keys_fail_closed(self) -> None:
        with self.assertRaisesRegex(control.ControlError, "DUPLICATE_JSON_KEY"):
            control.load_json_strict_bytes(b'{"resource":{},"resource":{}}')

    def test_provider_block_is_forbidden(self) -> None:
        with self.assertRaisesRegex(control.ControlError, "CANDIDATE_TOP_LEVEL_FORBIDDEN"):
            control.validate_candidate_document({"provider": {"google": {}}})

    def test_expression_string_is_forbidden(self) -> None:
        document = {"resource": {"google_service_account": {"phase3_terraform_sentinel": {**control.SENTINEL_RESOURCE, "project": "${var.project}"}}}}
        with self.assertRaisesRegex(control.ControlError, "EXPRESSION_STRING_FORBIDDEN"):
            control.validate_candidate_document(document)

    def test_sentinel_configuration_must_match_exactly(self) -> None:
        document = {"resource": {"google_service_account": {"phase3_terraform_sentinel": {**control.SENTINEL_RESOURCE, "deletion_policy": "DELETE"}}}}
        with self.assertRaisesRegex(control.ControlError, "SENTINEL_CONFIGURATION_MISMATCH"):
            control.validate_candidate_document(document)

    def test_canonical_candidate_bytes_are_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resources.tf.json"
            path.write_text("{\n}\n", encoding="utf-8")
            self.assertEqual(control.canonicalise_candidate(path), b"{}\n")


class MaterialEffectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = {
            "format_version": "1.2",
            "terraform_version": "1.15.8",
            "applyable": True,
            "complete": True,
            "errored": False,
            "resource_changes": [{
                "address": control.SENTINEL_ADDRESS,
                "mode": "managed",
                "type": "google_service_account",
                "name": "phase3_terraform_sentinel",
                "provider_name": "registry.terraform.io/hashicorp/google",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"account_id": "phase3-terraform-sentinel"},
                    "after_unknown": {"email": True},
                    "before_sensitive": False,
                    "after_sensitive": {"email": False},
                    "replace_paths": [],
                    "before_identity": None,
                    "after_identity": {"email": None},
                },
            }],
            "output_changes": {},
        }
        self.state = {"lineage": "lineage-1", "serial": 1, "generation": "123", "managed_resource_count": 0}

    def _effect(self, plan: dict | None = None) -> dict:
        return control.build_private_effect(
            plan=self.plan if plan is None else plan,
            state_identity=self.state,
            pr_number=18,
            base_sha="0" * 40,
            candidate_sha="a" * 40,
            candidate_digest="b" * 64,
            trusted_workflow_sha="c" * 40,
            trusted_tree_digest="d" * 64,
            provider_lock_digest="e" * 64,
        )

    def test_full_material_effect_is_preserved_privately(self) -> None:
        change = self._effect()["effect"]["resource_changes"][0]["change"]
        self.assertEqual(change["after"]["account_id"], "phase3-terraform-sentinel")
        self.assertEqual(change["after_unknown"], {"email": True})
        self.assertEqual(change["replace_paths"], [])
        self.assertEqual(change["after_identity"], {"email": None})

    def test_realistic_terraform_1158_envelope_is_accepted(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan.update({
            "variables": {},
            "planned_values": {},
            "prior_state": {},
            "configuration": {},
            "relevant_attributes": [],
            "checks": {},
            "timestamp": "2026-08-19T04:00:00Z",
        })
        self.assertEqual(self._effect(plan)["effect"]["terraform_version"], "1.15.8")

    def test_incomplete_or_errored_plan_fails_closed(self) -> None:
        for field, value in (("complete", False), ("errored", True), ("applyable", False)):
            plan = json.loads(json.dumps(self.plan))
            plan[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(control.ControlError, "PLAN_NOT_APPLYABLE_COMPLETE_SUCCESS"):
                self._effect(plan)

    def test_drift_deferred_and_actions_fail_closed(self) -> None:
        cases = (
            ("resource_drift", [{"address": control.SENTINEL_ADDRESS}], "PLAN_RESOURCE_DRIFT"),
            ("deferred_changes", [{"reason": "unknown"}], "PLAN_DEFERRED_CHANGES"),
            ("deferred_action_invocations", [{"reason": "unknown"}], "PLAN_DEFERRED_ACTION_INVOCATIONS"),
            ("action_invocations", [{"address": "action.foo"}], "PLAN_ACTION_INVOCATIONS"),
        )
        for field, value, error in cases:
            plan = json.loads(json.dumps(self.plan))
            plan[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(control.ControlError, error):
                self._effect(plan)

    def test_unrecognised_plan_or_change_structure_fails_closed(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["future_effect"] = {}
        with self.assertRaisesRegex(control.ControlError, "PLAN_TOP_LEVEL_STRUCTURE_UNRECOGNISED"):
            self._effect(plan)
        plan = json.loads(json.dumps(self.plan))
        plan["resource_changes"][0]["change"]["future_change"] = 1
        with self.assertRaisesRegex(control.ControlError, "PLAN_CHANGE_STRUCTURE_UNRECOGNISED"):
            self._effect(plan)

    def test_unknown_resource_class_fails_closed(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        plan["resource_changes"][0]["type"] = "google_storage_bucket"
        with self.assertRaisesRegex(control.ControlError, "PLAN_RESOURCE_CLASS_FORBIDDEN"):
            self._effect(plan)

    def test_public_manifest_does_not_expose_attribute_values(self) -> None:
        effect = self._effect()
        manifest = control.public_manifest(
            effect,
            workflow_run_id="1234",
            evidence_object="plan-evidence/foundation/pr-18-" + "a" * 40 + ".json",
        )
        encoded = json.dumps(manifest, sort_keys=True)
        self.assertNotIn("account_id", encoded)
        self.assertNotIn("phase3-terraform-sentinel", encoded)
        self.assertEqual(manifest["resource_actions"], [{"address": control.SENTINEL_ADDRESS, "actions": ["create"]}])
        self.assertEqual(manifest["policy_result"], "PASS")
        self.assertEqual(manifest["cost_class"], "known-negligible/control-plane")
        self.assertEqual(manifest["pr_number"], 18)
        self.assertEqual(manifest["base_sha"], "0" * 40)
        self.assertEqual(manifest["backend_namespace"], control.BACKEND_NAMESPACE)

    def test_private_effect_binds_review_identity(self) -> None:
        effect = self._effect()
        self.assertEqual(effect["pr_number"], 18)
        self.assertEqual(effect["base_sha"], "0" * 40)
        self.assertEqual(effect["candidate_sha"], "a" * 40)
        self.assertEqual(effect["trusted_workflow_sha"], "c" * 40)
        self.assertEqual(effect["backend_namespace"], control.BACKEND_NAMESPACE)

    def test_material_difference_fails_closed(self) -> None:
        expected = self._effect()
        changed = json.loads(json.dumps(self.plan))
        changed["resource_changes"][0]["change"]["after"]["account_id"] = "other"
        with self.assertRaisesRegex(control.ControlError, "MATERIAL_EFFECT_MISMATCH"):
            control.compare_private_effects(expected, self._effect(changed))

    def test_state_generation_difference_fails_closed(self) -> None:
        expected = self._effect()
        actual = json.loads(json.dumps(expected))
        actual["state"]["generation"] = "124"
        with self.assertRaisesRegex(control.ControlError, "MATERIAL_EFFECT_MISMATCH"):
            control.compare_private_effects(expected, actual)

    def test_state_identity_counts_managed_blocks(self) -> None:
        state = {"lineage": "lineage-1", "serial": 3,
                 "resources": [{"mode": "managed", "type": "google_service_account"}, {"mode": "data", "type": "google_client_config"}]}
        self.assertEqual(control.state_identity_from_state(state, "42"),
                         {"lineage": "lineage-1", "serial": 3, "generation": "42", "managed_resource_count": 1})


class IdentityGuardTests(unittest.TestCase):
    def test_only_explicit_service_accounts_are_allowed(self) -> None:
        for account in control.ALLOWED_SERVICE_ACCOUNTS:
            self.assertEqual(control.validate_service_account(account), account)
        with self.assertRaisesRegex(control.ControlError, "SERVICE_ACCOUNT_NOT_APPROVED"):
            control.validate_service_account("owner@example.iam.gserviceaccount.com")

    def test_evidence_object_is_bound_to_pr_and_head(self) -> None:
        good = "plan-evidence/foundation/pr-12-" + "f" * 40 + ".json"
        self.assertRegex(good, control.SAFE_EVIDENCE_OBJECT)
        self.assertNotRegex("plan-evidence/foundation/latest.json", control.SAFE_EVIDENCE_OBJECT)


if __name__ == "__main__":
    unittest.main()
