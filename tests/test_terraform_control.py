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

    def test_empty_seed_candidate_allowed(self):
        self.assertEqual(tc.validate_candidate_payload({"resource":{}}),"empty")

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

    def test_effect_hash_changes_when_material_value_changes(self):
        a=tc.sha256_bytes(tc.canonical_bytes(tc.plan_effect(self.plan("a"))))
        b=tc.sha256_bytes(tc.canonical_bytes(tc.plan_effect(self.plan("b"))))
        self.assertNotEqual(a,b)

    def test_public_manifest_contains_actions_not_values(self):
        m=tc.public_manifest(self.plan(),{"head_sha":"a"*40,"root":"foundation"})
        encoded=tc.canonical_bytes(m).decode()
        self.assertIn('"actions":["create"]',encoded)
        self.assertNotIn("resilio-reference-e882d4",encoded)

    def test_review_rejects_state_generation_change(self):
        meta={"head_sha":"a"*40,"base_sha":"b"*40,"pr":17}
        ev=tc.private_evidence(self.plan(),self.state(),"10",meta)
        with self.assertRaises(tc.ContractError):
            tc.verify_reviewed(ev,self.plan(),self.state(),"11","a"*40)

    def test_review_rejects_same_actions_different_effect(self):
        meta={"head_sha":"a"*40,"base_sha":"b"*40,"pr":17}
        ev=tc.private_evidence(self.plan("a"),self.state(),"10",meta)
        with self.assertRaises(tc.ContractError):
            tc.verify_reviewed(ev,self.plan("b"),self.state(),"10","a"*40)

if __name__=="__main__":
    unittest.main()
