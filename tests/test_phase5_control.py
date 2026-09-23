"""Credential-free Phase 5 supply-chain, authority and Terraform-control tests."""
from __future__ import annotations
import copy, json
from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"scripts"))
from phase5_supply_chain import (
    CONTROL_PROJECT, OWNER_ID, OWNER_LOGIN, REFERENCE_PROJECT, SERVICES,
    Phase5Error, acceptance_readback, build_request, cloud_run_create_request,
    deployment_authority, deployment_consumption_available,
    deployment_consumption_body, image_tag, release_envelope, validate_build,
    validate_release, verify_deployment_consumption, verify_service_config,
)
from phase5_release_record import record_body, validate_record
from phase5_terraform_control import (
    BASE_ADDRESSES, ProductTerraformError, expected_creates,
    material_effect, resource_document, state_identity, validate_candidate,
)
from services.resilio_app.server import PUSH_PATH
SOURCE="1"*40
CONTROL="2"*40
DIGEST="sha256:"+"a"*64
def successful_build():
    value=build_request(SOURCE,CONTROL)
    value.update({"id":"12345678-abcd","status":"SUCCESS",
        "sourceProvenance":{"resolvedGitSource":{"revision":SOURCE}},
        "results":{"images":[{"name":image_tag(SOURCE),"digest":DIGEST}]}})
    return value
def release():
    return release_envelope(successful_build(),SOURCE,CONTROL,
        "sbom/12345678-abcd.spdx.json","b"*64,123,
        "artifactanalysis://"+image_tag(SOURCE).replace(":source-"+SOURCE,"@"+DIGEST),
        "c"*64,"PASS")
def comment(comment_id:int,body:str):
    return {"id":comment_id,"issue_url":"https://api.github.com/repos/8ft0-ai/resilio/issues/109",
            "body":body,"user":{"login":OWNER_LOGIN,"id":OWNER_ID}}
class SupplyChainTests(unittest.TestCase):
    def test_build_is_exact_source_control_and_one_image(self):
        result=validate_build(successful_build(),SOURCE,CONTROL)
        self.assertEqual(result["source_sha"],SOURCE);self.assertEqual(result["control_sha"],CONTROL)
        self.assertEqual(result["image"],f"us-central1-docker.pkg.dev/{CONTROL_PROJECT}/resilio-product/resilio-app@{DIGEST}")
        bad=successful_build();bad["steps"][0]["args"]=["/workspace/unauthorised.py"]
        with self.assertRaises(Phase5Error): validate_build(bad,SOURCE,CONTROL)
    def test_release_is_one_digest_three_independent_runtime_principals(self):
        value=release();rid=validate_release(value);self.assertEqual(len(rid),64)
        self.assertEqual(set(value["services"]),set(SERVICES))
        self.assertEqual(len({v["runtime_service_account"] for v in value["services"].values()}),3)
        self.assertEqual({v["image"] for v in value["services"].values()},{value["image"]})
        bad=copy.deepcopy(value);bad["services"]["fourth"]={}
        with self.assertRaises(Phase5Error): validate_release(bad)
    def test_create_request_has_no_update_or_iam_surface(self):
        value=release();rid=validate_release(value)
        for service in SERVICES:
            request=cloud_run_create_request(value,rid,service);raw=json.dumps(request,sort_keys=True)
            self.assertIn(value["image"],raw);self.assertNotIn("iamPolicy",raw);self.assertNotIn("updateMask",raw)
        with self.assertRaises(Phase5Error): cloud_run_create_request(value,rid,"fourth-service")
    def test_created_service_must_match_exact_release(self):
        value=release();rid=validate_release(value);service="resilio-ingest";config=value["services"][service]
        observed={"name":config["resource"],"uri":"https://resilio-ingest-abc-uc.a.run.app",
            "latestReadyRevision":config["resource"]+"/revisions/resilio-ingest-00001-abc",
            "template":{"serviceAccount":config["runtime_service_account"],"timeout":"10s",
                "maxInstanceRequestConcurrency":10,"scaling":{"minInstanceCount":0,"maxInstanceCount":1},
                "containers":[{"image":value["image"],"env":[
                    {"name":"GOOGLE_CLOUD_PROJECT","value":REFERENCE_PROJECT},
                    {"name":"RESILIO_COMPONENT","value":"ingest"}]}]}}
        self.assertEqual(verify_service_config(observed,value,rid,service)["uri"],observed["uri"])
        observed["template"]["serviceAccount"]=SERVICES["resilio-api"]["runtime_service_account"]
        with self.assertRaises(Phase5Error): verify_service_config(observed,value,rid,service)
    def test_owner_deployment_authority_and_consumption_are_exactly_once(self):
        rid=validate_release(release());body=f"PHASE5_DEPLOYMENT_AUTHORITY_V1 release_id={rid} release_generation=7"
        authority=deployment_authority(comment(101,body),"101");self.assertEqual(authority["release_id"],rid)
        consumption=deployment_consumption_body("101",rid,"55",1);comments=[comment(202,consumption)]
        with self.assertRaises(Phase5Error): deployment_consumption_available(comments,"101",rid)
        self.assertEqual(verify_deployment_consumption(comments,"101",rid,"55",1)["comment_id"],"202")
        wrong=comment(102,body);wrong["user"]["id"]=1
        with self.assertRaises(Phase5Error): deployment_authority(wrong,"102")
    def test_release_record_is_canonical_and_bound(self):
        value=release();rid=validate_release(value);body=record_body(value,"7","99",1)
        decoded,meta=validate_record(comment(303,body),"303")
        self.assertEqual(decoded,value);self.assertEqual(meta["release_id"],rid)
    def test_acceptance_readback_binds_replay_metadata(self):
        response={"event_id":"d"*64,"payload_sha256":"e"*64,"observed":{"schema_version":1},
                  "first_observed_at":"2026-09-23T00:00:00+00:00"}
        bound=acceptance_readback(response,"d"*64,"e"*64)
        self.assertEqual(bound["first_observed_at"],response["first_observed_at"])
    def test_pubsub_push_application_route_is_exact_processor_uri_root(self):
        self.assertEqual(PUSH_PATH,"/")
class TerraformControlTests(unittest.TestCase):
    @staticmethod
    def candidate(stage,uri=None):
        return {"contract":"resilio-product-terraform-candidate/v1","stage":stage,"processor_uri":uri}
    def test_closed_candidate_stages(self):
        for stage in ("empty","base"): self.assertEqual(validate_candidate(self.candidate(stage))["stage"],stage)
        routing=self.candidate("routing","https://resilio-processor-abc-uc.a.run.app")
        self.assertEqual(validate_candidate(routing)["stage"],"routing")
        for bad in (
            {"contract":"resilio-product-terraform-candidate/v1","stage":"base","processor_uri":"x"},
            {"contract":"resilio-product-terraform-candidate/v1","stage":"other","processor_uri":None},
            {"contract":"resilio-product-terraform-candidate/v1","stage":"routing","processor_uri":"http://bad"},
            {**self.candidate("base"),"iam":"forbidden"}):
            with self.assertRaises(ProductTerraformError): validate_candidate(bad)
    def test_generated_base_has_exact_non_iam_resource_classes(self):
        resources=resource_document(self.candidate("base"))["resource"]
        self.assertEqual(set(resources),{"google_project_service","google_artifact_registry_repository",
            "google_storage_bucket","google_firestore_database","google_pubsub_topic"})
        self.assertEqual(expected_creates("base"),tuple(sorted(BASE_ADDRESSES)))
    def test_routing_is_exact_authenticated_processor_push(self):
        uri="https://resilio-processor-abc-uc.a.run.app"
        sub=resource_document(self.candidate("routing",uri))["resource"]["google_pubsub_subscription"]["deployment_events_push"]
        oidc=sub["push_config"][0]["oidc_token"][0]
        self.assertEqual(sub["push_config"][0]["push_endpoint"],uri);self.assertEqual(oidc["audience"],uri)
        self.assertEqual(oidc["service_account_email"],f"p5-pubsub-push@{REFERENCE_PROJECT}.iam.gserviceaccount.com")
    def test_material_effect_is_create_only_and_stage_exact(self):
        rows=[]
        for address in sorted(BASE_ADDRESSES):
            rtype,name=address.split(".",1)
            rows.append({"address":address,"mode":"managed","type":rtype,"name":name,
                "provider_name":"registry.terraform.io/hashicorp/google",
                "change":{"actions":["create"],"before":None,"after":{}}})
        plan={"format_version":"1.2","terraform_version":"1.15.8","errored":False,"complete":True,
              "applyable":True,"resource_changes":rows,"resource_drift":[],"deferred_changes":[],
              "deferred_action_invocations":[],"action_invocations":[],"output_changes":{}}
        self.assertEqual([r["address"] for r in material_effect(plan,"base")],sorted(BASE_ADDRESSES))
        bad=copy.deepcopy(plan);bad["resource_changes"][0]["change"]["actions"]=["update"]
        with self.assertRaises(ProductTerraformError): material_effect(bad,"base")
    def test_absent_state_is_explicit(self):
        state=state_identity({},"ABSENT");self.assertEqual(state["generation"],"ABSENT")
        with self.assertRaises(ProductTerraformError): state_identity({"resources":[]},"ABSENT")
if __name__=="__main__": unittest.main()
