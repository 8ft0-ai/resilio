locals {
  phase5_control_sha = "9513cd2a93241a8f870d85b4261102327574da5b"

  phase5_build_workflow_ref         = "8ft0-ai/resilio/.github/workflows/phase5-build-reusable.yml@${local.phase5_control_sha}"
  phase5_evidence_workflow_ref      = "8ft0-ai/resilio/.github/workflows/phase5-evidence-reusable.yml@${local.phase5_control_sha}"
  phase5_deploy_workflow_ref        = "8ft0-ai/resilio/.github/workflows/phase5-deploy-reusable.yml@${local.phase5_control_sha}"
  phase5_verify_workflow_ref        = "8ft0-ai/resilio/.github/workflows/phase5-verify-reusable.yml@${local.phase5_control_sha}"
  phase5_acceptance_workflow_ref    = "8ft0-ai/resilio/.github/workflows/phase5-acceptance-reusable.yml@${local.phase5_control_sha}"
  phase5_product_plan_workflow_ref  = "8ft0-ai/resilio/.github/workflows/phase5-terraform-plan-reusable.yml@${local.phase5_control_sha}"
  phase5_product_apply_workflow_ref = "8ft0-ai/resilio/.github/workflows/phase5-terraform-apply-reusable.yml@${local.phase5_control_sha}"

  phase5_region                    = "us-central1"
  phase5_product_repository        = "resilio-product"
  phase5_product_evidence_bucket   = "resilio-control-e882d4-product-evidence"
  phase5_product_topic             = "resilio-deployment-events"
  phase5_state_object              = "projects/_/buckets/${google_storage_bucket.terraform_state.name}/objects/product/default.tfstate"
  phase5_lock_object               = "projects/_/buckets/${google_storage_bucket.terraform_state.name}/objects/product/default.tflock"
  phase5_plan_evidence_prefix      = "projects/_/buckets/${google_storage_bucket.terraform_state.name}/objects/plan-evidence/product/"
  phase5_product_evidence_prefix   = "projects/_/buckets/${local.phase5_product_evidence_bucket}/objects/"
  phase5_firestore_database_target = "projects/${google_project.reference.project_id}/databases/(default)"
  phase4_proof_service_resource    = "projects/${google_project.reference.project_id}/locations/${local.phase5_region}/services/phase4-proof"
  phase4_proof_revision_prefix     = "${local.phase4_proof_service_resource}/revisions/"
}

# Phase 5 identities are established by bootstrap only. Product resources remain
# owned by the separate product state domain and are not created by this file.
resource "google_service_account" "phase5_build_initiator" {
  project      = google_project.control.project_id
  account_id   = "github-p5-build"
  display_name = "GitHub Phase 5 build initiator"
}

resource "google_service_account" "phase5_builder" {
  project      = google_project.control.project_id
  account_id   = "cloudbuild-p5-builder"
  display_name = "Phase 5 Cloud Build builder"
}

resource "google_service_account" "phase5_evidence" {
  project      = google_project.control.project_id
  account_id   = "github-p5-evidence"
  display_name = "GitHub Phase 5 evidence adjudicator"
}

resource "google_service_account" "phase5_product_planner" {
  project      = google_project.control.project_id
  account_id   = "github-p5-product-planner"
  display_name = "GitHub Phase 5 product Terraform planner"
}

resource "google_service_account" "phase5_product_applier" {
  project      = google_project.control.project_id
  account_id   = "github-p5-product-applier"
  display_name = "GitHub Phase 5 product Terraform applier"
}

resource "google_service_account" "phase5_deployer" {
  project      = google_project.reference.project_id
  account_id   = "github-p5-deployer"
  display_name = "GitHub Phase 5 create-only product deployer"
}

resource "google_service_account" "phase5_acceptance" {
  project      = google_project.reference.project_id
  account_id   = "github-p5-acceptance"
  display_name = "GitHub Phase 5 acceptance and independent verifier"
}

resource "google_service_account" "phase5_ingest_runtime" {
  project      = google_project.reference.project_id
  account_id   = "p5-ingest-runtime"
  display_name = "Phase 5 ingest runtime"
}

resource "google_service_account" "phase5_processor_runtime" {
  project      = google_project.reference.project_id
  account_id   = "p5-processor-runtime"
  display_name = "Phase 5 processor runtime"
}

resource "google_service_account" "phase5_api_runtime" {
  project      = google_project.reference.project_id
  account_id   = "p5-api-runtime"
  display_name = "Phase 5 API runtime"
}

resource "google_service_account" "phase5_pubsub_push" {
  project      = google_project.reference.project_id
  account_id   = "p5-pubsub-push"
  display_name = "Phase 5 Pub/Sub push authentication"
}

# Exact immutable reusable-workflow federation subjects.
resource "google_service_account_iam_member" "github_phase5_build" {
  service_account_id = google_service_account.phase5_build_initiator.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.phase5_build_workflow_ref}"
}

resource "google_service_account_iam_member" "github_phase5_evidence" {
  service_account_id = google_service_account.phase5_evidence.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.phase5_evidence_workflow_ref}"
}

resource "google_service_account_iam_member" "github_phase5_deployer" {
  service_account_id = google_service_account.phase5_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.phase5_deploy_workflow_ref}"
}

resource "google_service_account_iam_member" "github_phase5_verifier" {
  service_account_id = google_service_account.phase5_acceptance.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.phase5_verify_workflow_ref}"
}

resource "google_service_account_iam_member" "github_phase5_acceptance" {
  service_account_id = google_service_account.phase5_acceptance.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.phase5_acceptance_workflow_ref}"
}

resource "google_service_account_iam_member" "github_phase5_product_planner" {
  service_account_id = google_service_account.phase5_product_planner.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.phase5_product_plan_workflow_ref}"
}

resource "google_service_account_iam_member" "github_phase5_product_applier" {
  service_account_id = google_service_account.phase5_product_applier.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.phase5_product_apply_workflow_ref}"
}

# Exact one-permission service-account impersonation roles.
resource "google_project_iam_custom_role" "phase5_control_act_as" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_control_act_as"
  title       = "Resilio Phase 5 control actAs"
  description = "Allow actAs only when bound directly on an exact Phase 5 control service account."
  permissions = ["iam.serviceAccounts.actAs"]
}

resource "google_project_iam_custom_role" "phase5_reference_act_as" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p5_reference_act_as"
  title       = "Resilio Phase 5 reference actAs"
  description = "Allow actAs only when bound directly on an exact Phase 5 reference service account."
  permissions = ["iam.serviceAccounts.actAs"]
}

resource "google_service_account_iam_member" "phase5_build_act_as_builder" {
  service_account_id = google_service_account.phase5_builder.name
  role               = google_project_iam_custom_role.phase5_control_act_as.name
  member             = "serviceAccount:${google_service_account.phase5_build_initiator.email}"
}

resource "google_service_account_iam_member" "phase5_deployer_act_as_ingest" {
  service_account_id = google_service_account.phase5_ingest_runtime.name
  role               = google_project_iam_custom_role.phase5_reference_act_as.name
  member             = "serviceAccount:${google_service_account.phase5_deployer.email}"
}

resource "google_service_account_iam_member" "phase5_deployer_act_as_processor" {
  service_account_id = google_service_account.phase5_processor_runtime.name
  role               = google_project_iam_custom_role.phase5_reference_act_as.name
  member             = "serviceAccount:${google_service_account.phase5_deployer.email}"
}

resource "google_service_account_iam_member" "phase5_deployer_act_as_api" {
  service_account_id = google_service_account.phase5_api_runtime.name
  role               = google_project_iam_custom_role.phase5_reference_act_as.name
  member             = "serviceAccount:${google_service_account.phase5_deployer.email}"
}

resource "google_service_account_iam_member" "phase5_product_applier_act_as_push" {
  service_account_id = google_service_account.phase5_pubsub_push.name
  role               = google_project_iam_custom_role.phase5_reference_act_as.name
  member             = "serviceAccount:${google_service_account.phase5_product_applier.email}"
}

# Build and evidence authority.
resource "google_project_iam_custom_role" "phase5_build_initiator" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_build_initiator"
  title       = "Resilio Phase 5 build initiator"
  description = "Create and inspect exact product builds without cancellation or deployment authority."
  permissions = [
    "cloudbuild.builds.create",
    "cloudbuild.builds.get",
    "cloudbuild.builds.list",
  ]
}

resource "google_project_iam_member" "phase5_build_initiator" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase5_build_initiator.name
  member  = "serviceAccount:${google_service_account.phase5_build_initiator.email}"
}

resource "google_project_iam_custom_role" "phase5_builder_logging" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_builder_logging"
  title       = "Resilio Phase 5 builder logging"
  description = "Write Cloud Build log entries only."
  permissions = [
    "logging.logEntries.create",
    "logging.logEntries.route",
  ]
}

resource "google_project_iam_member" "phase5_builder_logging" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase5_builder_logging.name
  member  = "serviceAccount:${google_service_account.phase5_builder.email}"
}

resource "google_project_iam_custom_role" "phase5_builder_registry" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_builder_registry"
  title       = "Resilio Phase 5 builder registry"
  description = "Read and write product image content without repository administration or artifact deletion."
  permissions = [
    "artifactregistry.dockerimages.get",
    "artifactregistry.dockerimages.list",
    "artifactregistry.files.download",
    "artifactregistry.files.get",
    "artifactregistry.files.list",
    "artifactregistry.files.update",
    "artifactregistry.files.upload",
    "artifactregistry.packages.get",
    "artifactregistry.packages.list",
    "artifactregistry.packages.update",
    "artifactregistry.repositories.downloadArtifacts",
    "artifactregistry.repositories.get",
    "artifactregistry.repositories.uploadArtifacts",
    "artifactregistry.tags.create",
    "artifactregistry.tags.get",
    "artifactregistry.tags.list",
    "artifactregistry.tags.update",
    "artifactregistry.versions.get",
    "artifactregistry.versions.list",
  ]
}


resource "google_project_iam_custom_role" "phase5_evidence_analysis" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_evidence_analysis"
  title       = "Resilio Phase 5 evidence analysis"
  description = "Read exact build and Artifact Analysis occurrence evidence and export provider-native evidence."
  permissions = [
    "cloudbuild.builds.get",
    "containeranalysis.occurrences.create",
    "containeranalysis.occurrences.list",
    "serviceusage.services.use",
  ]
}

resource "google_project_iam_member" "phase5_evidence_analysis" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase5_evidence_analysis.name
  member  = "serviceAccount:${google_service_account.phase5_evidence.email}"
}

resource "google_project_iam_custom_role" "phase5_object_creator" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_object_create"
  title       = "Resilio Phase 5 object creator"
  description = "Create immutable objects only when conditionally bound to an accepted prefix."
  permissions = ["storage.objects.create"]
}

resource "google_project_iam_custom_role" "phase5_object_reader" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_object_read"
  title       = "Resilio Phase 5 object reader"
  description = "Read objects only when conditionally bound to an accepted prefix."
  permissions = ["storage.objects.get"]
}

resource "google_project_iam_member" "phase5_evidence_product_creator" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase5_object_creator.name
  member  = "serviceAccount:${google_service_account.phase5_evidence.email}"

  condition {
    title       = "phase5-product-evidence-create"
    description = "Create only objects in the future Phase 5 product evidence bucket."
    expression  = "resource.name.startsWith(\"${local.phase5_product_evidence_prefix}\")"
  }
}

resource "google_project_iam_member" "phase5_evidence_product_reader" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase5_object_reader.name
  member  = "serviceAccount:${google_service_account.phase5_evidence.email}"

  condition {
    title       = "phase5-product-evidence-read"
    description = "Read only objects in the future Phase 5 product evidence bucket."
    expression  = "resource.name.startsWith(\"${local.phase5_product_evidence_prefix}\")"
  }
}

resource "google_project_iam_member" "phase5_deployer_product_evidence_reader" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase5_object_reader.name
  member  = "serviceAccount:${google_service_account.phase5_deployer.email}"

  condition {
    title       = "phase5-product-evidence-deployer-read"
    description = "Read only immutable product evidence required for exact deployment."
    expression  = "resource.name.startsWith(\"${local.phase5_product_evidence_prefix}\")"
  }
}




resource "google_project_iam_custom_role" "phase5_state_list" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_state_list"
  title       = "Resilio Phase 5 state list"
  description = "List-only access required by the product Terraform GCS backend."
  permissions = ["storage.objects.list"]
}

resource "google_project_iam_custom_role" "phase5_state_lock" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_state_lock"
  title       = "Resilio Phase 5 state lock"
  description = "Create, inspect and delete only the exact product Terraform lock object."
  permissions = [
    "storage.objects.create",
    "storage.objects.delete",
    "storage.objects.get",
  ]
}

resource "google_project_iam_custom_role" "phase5_state_writer" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_state_write"
  title       = "Resilio Phase 5 state writer"
  description = "Create or overwrite only the canonical product state object."
  permissions = [
    "storage.objects.create",
    "storage.objects.delete",
  ]
}

resource "google_storage_bucket_iam_member" "phase5_product_planner_list" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.phase5_state_list.name
  member = "serviceAccount:${google_service_account.phase5_product_planner.email}"
}

resource "google_storage_bucket_iam_member" "phase5_product_applier_list" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.phase5_state_list.name
  member = "serviceAccount:${google_service_account.phase5_product_applier.email}"
}

resource "google_storage_bucket_iam_member" "phase5_product_planner_state_reader" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.phase5_object_reader.name
  member = "serviceAccount:${google_service_account.phase5_product_planner.email}"
  condition {
    title       = "phase5-product-state-read"
    description = "Read only the canonical product state."
    expression  = "resource.name == \"${local.phase5_state_object}\""
  }
}

resource "google_storage_bucket_iam_member" "phase5_product_applier_state_reader" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.phase5_object_reader.name
  member = "serviceAccount:${google_service_account.phase5_product_applier.email}"
  condition {
    title       = "phase5-product-state-read"
    description = "Read only the canonical product state."
    expression  = "resource.name == \"${local.phase5_state_object}\""
  }
}

resource "google_storage_bucket_iam_member" "phase5_product_planner_lock" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.phase5_state_lock.name
  member = "serviceAccount:${google_service_account.phase5_product_planner.email}"
  condition {
    title       = "phase5-product-lock"
    description = "Operate only the canonical product lock."
    expression  = "resource.name == \"${local.phase5_lock_object}\""
  }
}

resource "google_storage_bucket_iam_member" "phase5_product_applier_lock" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.phase5_state_lock.name
  member = "serviceAccount:${google_service_account.phase5_product_applier.email}"
  condition {
    title       = "phase5-product-lock"
    description = "Operate only the canonical product lock."
    expression  = "resource.name == \"${local.phase5_lock_object}\""
  }
}

resource "google_storage_bucket_iam_member" "phase5_product_applier_state_writer" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.phase5_state_writer.name
  member = "serviceAccount:${google_service_account.phase5_product_applier.email}"
  condition {
    title       = "phase5-product-state-write"
    description = "Write only the canonical product state."
    expression  = "resource.name == \"${local.phase5_state_object}\""
  }
}

resource "google_storage_bucket_iam_member" "phase5_product_planner_evidence_creator" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.phase5_object_creator.name
  member = "serviceAccount:${google_service_account.phase5_product_planner.email}"
  condition {
    title       = "phase5-product-plan-evidence-create"
    description = "Create only immutable product plan evidence."
    expression  = "resource.name.startsWith(\"${local.phase5_plan_evidence_prefix}\")"
  }
}

resource "google_storage_bucket_iam_member" "phase5_product_applier_evidence_reader" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.phase5_object_reader.name
  member = "serviceAccount:${google_service_account.phase5_product_applier.email}"
  condition {
    title       = "phase5-product-plan-evidence-read"
    description = "Read only reviewed product plan evidence."
    expression  = "resource.name.startsWith(\"${local.phase5_plan_evidence_prefix}\")"
  }
}

# Product Terraform provider read/create envelope. Candidate grammar remains in
# the immutable Slice A control; these permissions cannot introduce IAM resources.
resource "google_project_iam_custom_role" "phase5_product_control_planner" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_product_control_plan"
  title       = "Resilio Phase 5 product control planner"
  description = "Read only product registry and evidence-bucket state."
  permissions = [
    "artifactregistry.locations.get",
    "artifactregistry.locations.list",
    "artifactregistry.repositories.get",
    "artifactregistry.repositories.list",
    "resourcemanager.projects.get",
    "storage.buckets.get",
    "storage.buckets.list",
  ]
}

resource "google_project_iam_custom_role" "phase5_product_control_applier" {
  project     = google_project.control.project_id
  role_id     = "resilio_p5_product_control_apply"
  title       = "Resilio Phase 5 product control applier"
  description = "Create only the accepted non-IAM control-project product resources."
  permissions = [
    "artifactregistry.locations.get",
    "artifactregistry.locations.list",
    "artifactregistry.repositories.create",
    "artifactregistry.repositories.get",
    "artifactregistry.repositories.list",
    "artifactregistry.repositories.update",
    "resourcemanager.projects.get",
    "storage.buckets.create",
    "storage.buckets.get",
    "storage.buckets.list",
    "storage.buckets.update",
  ]
}

resource "google_project_iam_member" "phase5_product_planner_control" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase5_product_control_planner.name
  member  = "serviceAccount:${google_service_account.phase5_product_planner.email}"
}

resource "google_project_iam_member" "phase5_product_applier_control" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase5_product_control_applier.name
  member  = "serviceAccount:${google_service_account.phase5_product_applier.email}"
}

resource "google_project_iam_custom_role" "phase5_product_reference_planner" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p5_product_reference_plan"
  title       = "Resilio Phase 5 product reference planner"
  description = "Read only accepted product service-enable, Firestore and Pub/Sub state."
  permissions = [
    "datastore.databases.get",
    "datastore.databases.list",
    "pubsub.subscriptions.get",
    "pubsub.subscriptions.list",
    "pubsub.topics.get",
    "pubsub.topics.list",
    "resourcemanager.projects.get",
    "serviceusage.services.get",
    "serviceusage.services.list",
  ]
}

resource "google_project_iam_custom_role" "phase5_product_reference_applier" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p5_product_reference_apply"
  title       = "Resilio Phase 5 product reference applier"
  description = "Create only accepted non-IAM Firestore, Pub/Sub and service-enable product resources."
  permissions = [
    "datastore.databases.create",
    "datastore.databases.get",
    "datastore.databases.list",
    "datastore.databases.update",
    "pubsub.subscriptions.create",
    "pubsub.subscriptions.get",
    "pubsub.subscriptions.list",
    "pubsub.subscriptions.update",
    "pubsub.topics.attachSubscription",
    "pubsub.topics.create",
    "pubsub.topics.get",
    "pubsub.topics.list",
    "pubsub.topics.update",
    "resourcemanager.projects.get",
    "serviceusage.services.enable",
    "serviceusage.services.get",
    "serviceusage.services.list",
  ]
}

resource "google_project_iam_member" "phase5_product_planner_reference" {
  project = google_project.reference.project_id
  role    = google_project_iam_custom_role.phase5_product_reference_planner.name
  member  = "serviceAccount:${google_service_account.phase5_product_planner.email}"
}

resource "google_project_iam_member" "phase5_product_applier_reference" {
  project = google_project.reference.project_id
  role    = google_project_iam_custom_role.phase5_product_reference_applier.name
  member  = "serviceAccount:${google_service_account.phase5_product_applier.email}"
}

# First product deployment remains exact create-only authority.
resource "google_project_iam_custom_role" "phase5_deployer" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p5_deployer"
  title       = "Resilio Phase 5 create-only deployer"
  description = "Create and read exactly the first three product services; no update, delete or IAM mutation."
  permissions = [
    "run.operations.get",
    "run.services.create",
    "run.services.get",
  ]
}

resource "google_project_iam_member" "phase5_deployer" {
  project = google_project.reference.project_id
  role    = google_project_iam_custom_role.phase5_deployer.name
  member  = "serviceAccount:${google_service_account.phase5_deployer.email}"
}

# Acceptance identity/envelope only. Service-level metadata and invocation grants
# are deliberately deferred to post-create Slice D.5.
resource "google_project_iam_custom_role" "phase5_acceptance_reader" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p5_acceptance_reader"
  title       = "Resilio Phase 5 acceptance reader"
  description = "Read exact product service, revision and IAM metadata when granted later at service scope."
  permissions = [
    "run.revisions.get",
    "run.services.get",
    "run.services.getIamPolicy",
  ]
}

# Runtime custom roles are declared here. Resource-level Pub/Sub and Artifact
# Registry bindings that require Slice C resources are deferred to the reviewed
# post-Slice-C / pre-Slice-D resource-level IAM activation stage.
resource "google_project_iam_custom_role" "phase5_ingest_publisher" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p5_ingest_publisher"
  title       = "Resilio Phase 5 ingest publisher"
  description = "Publish only when later bound on the exact deployment-events topic resource."
  permissions = ["pubsub.topics.publish"]
}


resource "google_project_iam_custom_role" "phase5_processor_store" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p5_processor_store"
  title       = "Resilio Phase 5 processor store"
  description = "Create and read only product Firestore documents when conditionally bound."
  permissions = [
    "datastore.entities.create",
    "datastore.entities.get",
  ]
}

resource "google_project_iam_member" "phase5_processor_store" {
  project = google_project.reference.project_id
  role    = google_project_iam_custom_role.phase5_processor_store.name
  member  = "serviceAccount:${google_service_account.phase5_processor_runtime.email}"
  condition {
    title       = "phase5-processor-firestore-only"
    description = "Restrict processor data authority to the exact default product database."
    expression  = "resource.name == \"${local.phase5_firestore_database_target}\""
  }
}

resource "google_project_iam_custom_role" "phase5_api_store" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p5_api_store"
  title       = "Resilio Phase 5 API store"
  description = "Read only product Firestore documents when conditionally bound."
  permissions = ["datastore.entities.get"]
}

resource "google_project_iam_member" "phase5_api_store" {
  project = google_project.reference.project_id
  role    = google_project_iam_custom_role.phase5_api_store.name
  member  = "serviceAccount:${google_service_account.phase5_api_runtime.email}"
  condition {
    title       = "phase5-api-firestore-only"
    description = "Restrict API data authority to the exact default product database."
    expression  = "resource.name == \"${local.phase5_firestore_database_target}\""
  }
}

# The product Terraform applier gets only actAs on the push-auth identity here.
# Pub/Sub service-agent token minting and push->processor invocation are deferred
# until their concrete resources exist in Slice D.5.
