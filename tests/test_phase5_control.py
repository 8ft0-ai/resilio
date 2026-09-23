"""Credential-free Phase 5 supply-chain, authority and Terraform-control tests."""
from __future__ import annotations
import copy, json
from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"scripts"))
from phase5_supply_chain import (
    ACCEPTANCE_READER_ROLE, CONTROL_PROJECT, OWNER_ID, OWNER_LOGIN,
    REFERENCE_PROJECT, SERVICES, Phase5Error, acceptance_readback, build_request,
    cloud_run_create_request, d5_reconciliation_body, deployment_authority,
    deployment_consumption_available, deployment_consumption_body, image_tag,
    processor_routing_binding_body, release_envelope, validate_build,
    validate_d5_reconciliation, validate_release, verify_deployment_consumption,
    verify_service, verify_service_config,
)
from phase5_release_record import record_body, validate_record
from phase5_terraform_control import (
    BASE_ADDRESSES, PROCESSOR_RESOURCE, ProductTerraformError, expected_creates,
    material_effect, resource_document, routing_binding_from_documents,
    state_identity, validate_candidate, verify_caller_context,
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
    def test_exact_service_iam_graph_and_d5_project_negative_reconciliation(self):
        value=release();rid=validate_release(value)
        acceptance=f"serviceAccount:github-p5-acceptance@{REFERENCE_PROJECT}.iam.gserviceaccount.com"
        push=f"serviceAccount:p5-pubsub-push@{REFERENCE_PROJECT}.iam.gserviceaccount.com"
        expected={
            "resilio-ingest":{"roles/run.servicesInvoker":[acceptance],ACCEPTANCE_READER_ROLE:[acceptance]},
            "resilio-processor":{"roles/run.invoker":[push],ACCEPTANCE_READER_ROLE:[acceptance]},
            "resilio-api":{"roles/run.servicesInvoker":[acceptance],ACCEPTANCE_READER_ROLE:[acceptance]},
        }
        def observed(service):
            config=value["services"][service]
            return {"name":config["resource"],"uri":f"https://{service}-abc-uc.a.run.app",
                "latestReadyRevision":config["resource"]+f"/revisions/{service}-00001-abc",
                "template":{"serviceAccount":config["runtime_service_account"],"timeout":"10s",
                    "maxInstanceRequestConcurrency":10,"scaling":{"minInstanceCount":0,"maxInstanceCount":1},
                    "containers":[{"image":value["image"],"env":[
                        {"name":"GOOGLE_CLOUD_PROJECT","value":REFERENCE_PROJECT},
                        {"name":"RESILIO_COMPONENT","value":SERVICES[service]["component"]}]}]}}
        for service,roles in expected.items():
            policy={"bindings":[{"role":role,"members":members} for role,members in roles.items()]}
            self.assertEqual(verify_service(observed(service),policy,value,rid,service)["service"],value["services"][service]["resource"])
            missing=copy.deepcopy(policy);missing["bindings"].pop()
            with self.assertRaises(Phase5Error): verify_service(observed(service),missing,value,rid,service)
            extra=copy.deepcopy(policy);extra["bindings"][0]["members"].append("serviceAccount:unexpected@example.iam.gserviceaccount.com")
            with self.assertRaises(Phase5Error): verify_service(observed(service),extra,value,rid,service)
        bad={"bindings":[{"role":r,"members":m} for r,m in expected["resilio-processor"].items()]+[{"role":"roles/run.servicesInvoker","members":[acceptance]}]}
        with self.assertRaises(Phase5Error): verify_service(observed("resilio-processor"),bad,value,rid,"resilio-processor")
        bad={"bindings":[{"role":r,"members":m} for r,m in expected["resilio-ingest"].items()]+[{"role":"roles/run.invoker","members":[push]}]}
        with self.assertRaises(Phase5Error): verify_service(observed("resilio-ingest"),bad,value,rid,"resilio-ingest")
        bad={"bindings":[{"role":r,"members":m} for r,m in expected["resilio-api"].items()]+[{"role":"roles/run.invoker","members":[push]}]}
        with self.assertRaises(Phase5Error): verify_service(observed("resilio-api"),bad,value,rid,"resilio-api")
        d5_body=d5_reconciliation_body(CONTROL,"3"*40,"321",1)
        d5_comment={"id":222,"issue_url":"https://api.github.com/repos/8ft0-ai/resilio/issues/109","body":d5_body,"user":{"login":"github-actions[bot]","id":41898282}}
        d5_run={"id":321,"run_attempt":1,"status":"completed","conclusion":"success","head_branch":"main","head_sha":"3"*40,
            "path":".github/workflows/phase5-d5-iam-reconcile.yml@main","head_repository":{"full_name":"8ft0-ai/resilio"},"repository":{"full_name":"8ft0-ai/resilio"}}
        self.assertEqual(validate_d5_reconciliation(d5_comment,"222",CONTROL,d5_run)["caller_sha"],"3"*40)
        bad_run=copy.deepcopy(d5_run);bad_run["path"]=".github/workflows/unrelated.yml@main"
        with self.assertRaises(Phase5Error): validate_d5_reconciliation(d5_comment,"222",CONTROL,bad_run)
        wrong_ref=copy.deepcopy(d5_run);wrong_ref["path"]=".github/workflows/phase5-d5-iam-reconcile.yml@feature"
        with self.assertRaises(Phase5Error): validate_d5_reconciliation(d5_comment,"222",CONTROL,wrong_ref)
        bad_comment=copy.deepcopy(d5_comment);bad_comment["body"]=bad_comment["body"].replace("acceptance_project_run_roles=ABSENT","acceptance_project_run_roles=PRESENT")
        with self.assertRaises(Phase5Error): validate_d5_reconciliation(bad_comment,"222",CONTROL,d5_run)

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
                  "first_pubsub_message_id":"message-1",
                  "first_observed_at":"2026-09-23T00:00:00+00:00"}
        bound=acceptance_readback(response,"d"*64,"e"*64,"message-1")
        self.assertEqual(bound["first_observed_at"],response["first_observed_at"])
        self.assertEqual(bound["first_pubsub_message_id"],"message-1")
        with self.assertRaises(Phase5Error):
            acceptance_readback(response,"d"*64,"e"*64,"different-message")
    def test_pubsub_push_application_route_is_exact_processor_uri_root(self):
        self.assertEqual(PUSH_PATH,"/")
class TerraformControlTests(unittest.TestCase):
    @staticmethod
    def candidate(stage,uri=None,verification_comment_id=None):
        return {"contract":"resilio-product-terraform-candidate/v1","stage":stage,
                "processor_uri":uri,
                "processor_verification_comment_id":verification_comment_id}
    def test_closed_candidate_stages(self):
        for stage in ("empty","base"): self.assertEqual(validate_candidate(self.candidate(stage))["stage"],stage)
        routing=self.candidate("routing","https://resilio-processor-abc-uc.a.run.app","123")
        self.assertEqual(validate_candidate(routing)["stage"],"routing")
        for bad in (
            {"contract":"resilio-product-terraform-candidate/v1","stage":"base","processor_uri":"x",
             "processor_verification_comment_id":None},
            {"contract":"resilio-product-terraform-candidate/v1","stage":"other","processor_uri":None,
             "processor_verification_comment_id":None},
            {"contract":"resilio-product-terraform-candidate/v1","stage":"routing","processor_uri":"http://bad",
             "processor_verification_comment_id":"123"},
            self.candidate("routing","https://resilio-processor-abc-uc.a.run.app",None),
            {**self.candidate("base"),"iam":"forbidden"}):
            with self.assertRaises(ProductTerraformError): validate_candidate(bad)
    def test_generated_base_has_exact_non_iam_resource_classes(self):
        resources=resource_document(self.candidate("base"))["resource"]
        self.assertEqual(set(resources),{"google_project_service","google_artifact_registry_repository",
            "google_storage_bucket","google_firestore_database","google_pubsub_topic"})
        self.assertEqual(expected_creates("base"),tuple(sorted(BASE_ADDRESSES)))
    def test_routing_is_exact_authenticated_processor_push(self):
        uri="https://resilio-processor-abc-uc.a.run.app"
        sub=resource_document(self.candidate("routing",uri,"123"))["resource"]["google_pubsub_subscription"]["deployment_events_push"]
        oidc=sub["push_config"][0]["oidc_token"][0]
        self.assertEqual(sub["push_config"][0]["push_endpoint"],uri);self.assertEqual(oidc["audience"],uri)
        self.assertEqual(oidc["service_account_email"],f"p5-pubsub-push@{REFERENCE_PROJECT}.iam.gserviceaccount.com")
    def test_privileged_caller_must_be_protected_main_first_attempt(self):
        verify_caller_context("8ft0-ai/resilio","refs/heads/main","true","1")
        for args in (
            ("fork/resilio","refs/heads/main","true","1"),
            ("8ft0-ai/resilio","refs/heads/feature","false","1"),
            ("8ft0-ai/resilio","refs/heads/main","true","2"),
        ):
            with self.assertRaises(ProductTerraformError):
                verify_caller_context(*args)

    def test_routing_binding_requires_exact_independent_processor_observation(self):
        uri="https://resilio-processor-abc-uc.a.run.app"
        candidate=self.candidate("routing",uri,"123")
        caller_sha="3"*40
        d5_body=d5_reconciliation_body(CONTROL,"4"*40,"321",1)
        d5_comment={"id":222,"issue_url":"https://api.github.com/repos/8ft0-ai/resilio/issues/109","body":d5_body,"user":{"login":"github-actions[bot]","id":41898282}}
        d5_run={"id":321,"run_attempt":1,"status":"completed","conclusion":"success","head_branch":"main","head_sha":"4"*40,
            "path":".github/workflows/phase5-d5-iam-reconcile.yml@main","head_repository":{"full_name":"8ft0-ai/resilio"},"repository":{"full_name":"8ft0-ai/resilio"}}
        body=processor_routing_binding_body("f"*64,uri,CONTROL,"222",caller_sha,"456",1)
        comment={"id":123,"issue_url":"https://api.github.com/repos/8ft0-ai/resilio/issues/109",
                 "body":body,"user":{"login":"github-actions[bot]","id":41898282}}
        run={"id":456,"run_attempt":1,"status":"completed","conclusion":"success","head_branch":"main","head_sha":caller_sha,
             "path":".github/workflows/phase5-verify.yml@main","head_repository":{"full_name":"8ft0-ai/resilio"},"repository":{"full_name":"8ft0-ai/resilio"},
             "referenced_workflows":[{"path":f"8ft0-ai/resilio/.github/workflows/phase5-verify-reusable.yml@{CONTROL}","sha":CONTROL}]}
        binding=routing_binding_from_documents(candidate,CONTROL,comment,run,d5_comment,d5_run)
        self.assertEqual(binding["processor_resource"],PROCESSOR_RESOURCE)
        self.assertEqual(binding["d5_reconciliation_comment_id"],"222")
        unrelated=self.candidate("routing","https://unrelated-abc-uc.a.run.app","123")
        with self.assertRaises(ProductTerraformError): routing_binding_from_documents(unrelated,CONTROL,comment,run,d5_comment,d5_run)
        hostile=copy.deepcopy(run);hostile["path"]=".github/workflows/other-protected-main.yml@main"
        with self.assertRaises(ProductTerraformError): routing_binding_from_documents(candidate,CONTROL,comment,hostile,d5_comment,d5_run)
        hostile=copy.deepcopy(run);hostile["path"]=".github/workflows/phase5-verify.yml@feature"
        with self.assertRaises(ProductTerraformError): routing_binding_from_documents(candidate,CONTROL,comment,hostile,d5_comment,d5_run)
        hostile=copy.deepcopy(run);hostile["referenced_workflows"][0]["sha"]="9"*40
        with self.assertRaises(ProductTerraformError): routing_binding_from_documents(candidate,CONTROL,comment,hostile,d5_comment,d5_run)

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
