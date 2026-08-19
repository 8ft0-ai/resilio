#!/usr/bin/env python3
from __future__ import annotations
import copy, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import terraform_control as tc  # noqa:E402

class TerraformControlTests(unittest.TestCase):
    def plan(self,value="resilio-reference-e882d4"):
        return {
            "format_version":"1.2",
            "terraform_version":"1.15.8",
            "applyable":True,
            "complete":True,
            "errored":False,
            "resource_drift":[],
            "deferred_changes":[],
            "deferred_action_invocations":[],
            "action_invocations":[],
            "resource_changes":[{
                "address":"google_service_account.phase3_terraform_sentinel",
                "mode":"managed","type":"google_service_account",
                "name":"phase3_terraform_sentinel",
                "provider_name":"registry.terraform.io/hashicorp/google",
                "change":{"actions":["create"],"before":None,"after":{"project":value},"after_unknown":{},"before_sensitive":False,"after_sensitive":{}},
            }],
            "output_changes":{},
        }
    def state(self,serial=1):
        return {"lineage":"lineage-1","serial":serial,"version":4}
    def meta(self):
        return {
            "head_sha":"a"*40,"base_sha":"b"*40,"pr":17,"root":"foundation",
            "control_seed_sha":"c"*40,"backend_namespace":"foundation/default.tfstate",
        }

    def test_empty_seed_candidate_allowed(self):
        self.assertEqual(tc.validate_candidate_payload({}),"empty")

    def test_exact_sentinel_allowed(self):
        self.assertEqual(tc.validate_candidate_payload(tc.sentinel_candidate_payload()),"sentinel")

    def test_duplicate_key_rejected(self):
        with self.assertRaises(tc.ContractError):
            tc.load_json_strict_bytes(b'{"resource":{},"resource":{}}')

    def test_extra_construct_rejected(self):
        with self.assertRaises(tc.ContractError):
            tc.validate_candidate_payload({"resource":{},"output":{}})

    def test_interpolated_sentinel_rejected(self):
        p=tc.sentinel_candidate_payload()
        p["resource"][tc.SENTINEL_TYPE][tc.SENTINEL_NAME]["project"]="${var.project}"
        with self.assertRaises(tc.ContractError):
            tc.validate_candidate_payload(p)

    def test_exact_terraform_1158_top_level_schema_is_accepted(self):
        effect=tc.plan_effect(self.plan())
        self.assertTrue(effect["applyable"])
        self.assertTrue(effect["complete"])
        self.assertFalse(effect["errored"])

    def test_effect_records_explicit_singleton_index(self):
        effect=tc.plan_effect(self.plan())
        self.assertIn("index",effect["resource_changes"][0])
        self.assertIsNone(effect["resource_changes"][0]["index"])

    def test_effect_hash_changes_when_material_value_changes(self):
        a=tc.sha256_bytes(tc.canonical_bytes(tc.plan_effect(self.plan("a"))))
        b=tc.sha256_bytes(tc.canonical_bytes(tc.plan_effect(self.plan("b"))))
        self.assertNotEqual(a,b)

    def test_missing_applyability_rejected(self):
        p=self.plan(); del p["applyable"]
        with self.assertRaises(tc.ContractError): tc.plan_effect(p)

    def test_false_applyability_is_preserved_for_complete_nonerrored_plan(self):
        p=self.plan(); p["applyable"]=False; p["resource_changes"]=[]
        self.assertFalse(tc.plan_effect(p)["applyable"])

    def test_errored_plan_rejected(self):
        p=self.plan(); p["errored"]=True
        with self.assertRaises(tc.ContractError): tc.plan_effect(p)

    def test_resource_drift_rejected(self):
        p=self.plan(); p["resource_drift"]=[copy.deepcopy(p["resource_changes"][0])]
        with self.assertRaises(tc.ContractError): tc.plan_effect(p)

    def test_deferred_change_rejected(self):
        p=self.plan(); p["deferred_changes"]=[{"reason":"deferred","resource_change":copy.deepcopy(p["resource_changes"][0])}]
        with self.assertRaises(tc.ContractError): tc.plan_effect(p)

    def test_deferred_action_invocation_rejected(self):
        p=self.plan(); p["deferred_action_invocations"]=[{"reason":"deferred","action_invocation":{"address":"action.example"}}]
        with self.assertRaises(tc.ContractError): tc.plan_effect(p)

    def test_incomplete_plan_rejected(self):
        p=self.plan(); p["complete"]=False
        with self.assertRaises(tc.ContractError): tc.plan_effect(p)

    def test_action_invocation_rejected(self):
        p=self.plan(); p["action_invocations"]=[{"address":"action.example"}]
        with self.assertRaises(tc.ContractError): tc.plan_effect(p)

    def test_unrecognised_plan_structure_rejected(self):
        p=self.plan(); p["future_effects"]=[{"action":"create"}]
        with self.assertRaises(tc.ContractError): tc.plan_effect(p)

    def test_unknown_resource_class_rejected(self):
        p=self.plan(); p["resource_changes"][0]["type"]="google_project_iam_binding"
        with self.assertRaises(tc.ContractError): tc.plan_effect(p)

    def test_indexed_resource_rejected(self):
        p=self.plan(); p["resource_changes"][0]["index"]=0
        with self.assertRaises(tc.ContractError): tc.plan_effect(p)

    def test_output_effect_rejected_for_initial_grammar(self):
        p=self.plan(); p["output_changes"]={"secret":{"actions":["create"],"after":"value"}}
        with self.assertRaises(tc.ContractError): tc.plan_effect(p)

    def test_public_manifest_contains_actions_not_values(self):
        m=tc.public_manifest(self.plan(),self.meta())
        encoded=tc.canonical_bytes(m).decode()
        self.assertIn('"actions":["create"]',encoded)
        self.assertIn('"control_seed_sha":"'+"c"*40+'"',encoded)
        self.assertIn('"backend_namespace":"foundation/default.tfstate"',encoded)
        self.assertNotIn("resilio-reference-e882d4",encoded)

    def test_review_rejects_state_generation_change(self):
        ev=tc.private_evidence(self.plan(),self.state(),"10",self.meta())
        with self.assertRaises(tc.ContractError):
            tc.verify_reviewed(ev,self.plan(),self.state(),"11","a"*40,"c"*40)

    def test_review_rejects_same_actions_different_effect(self):
        ev=tc.private_evidence(self.plan("a"),self.state(),"10",self.meta())
        with self.assertRaises(tc.ContractError):
            tc.verify_reviewed(ev,self.plan("b"),self.state(),"10","a"*40,"c"*40)

    def test_review_rejects_different_control_seed(self):
        ev=tc.private_evidence(self.plan(),self.state(),"10",self.meta())
        with self.assertRaises(tc.ContractError):
            tc.verify_reviewed(ev,self.plan(),self.state(),"10","a"*40,"d"*40)

    def test_review_accepts_matching_state_effect_and_control(self):
        ev=tc.private_evidence(self.plan(),self.state(),"10",self.meta())
        tc.verify_reviewed(ev,self.plan(),self.state(),"10","a"*40,"c"*40)

if __name__=="__main__":
    unittest.main()
