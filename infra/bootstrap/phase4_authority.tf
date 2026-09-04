locals {
  phase4_control_seed_sha                  = "10e7a938046e2d2d28ffa08a470bf9dfeda40dac"
  phase4_evidence_workflow_sha             = "a9e4832b48cac4ad2e4f916e37aceafe7f93b9aa"
  phase4_build_workflow_ref                = "8ft0-ai/resilio/.github/workflows/phase4-build-reusable.yml@${local.phase4_control_seed_sha}"
  phase4_evidence_workflow_ref             = "8ft0-ai/resilio/.github/workflows/phase4-evidence-reusable.yml@${local.phase4_evidence_workflow_sha}"
  phase4_deploy_workflow_ref               = "8ft0-ai/resilio/.github/workflows/phase4-deploy-reusable.yml@c70afa19c487f6f8d18720028db8e6379fbeed44"
  phase4_transition_object_resource_prefix = "projects/_/buckets/resilio-control-e882d4-phase4-evidence/objects/transitions/"
}

resource "google_service_account" "phase4_build_initiator" {
  project      = google_project.control.project_id
  account_id   = "github-p4-build"
  display_name = "GitHub Phase 4 build initiator"

  depends_on = [
    google_project_service.control["iam.googleapis.com"],
  ]
}

resource "google_service_account" "phase4_builder" {
  project      = google_project.control.project_id
  account_id   = "cloudbuild-p4-builder"
  display_name = "Phase 4 Cloud Build builder"

  depends_on = [
    google_project_service.control["iam.googleapis.com"],
  ]
}

resource "google_service_account" "phase4_evidence" {
  project      = google_project.control.project_id
  account_id   = "github-p4-evidence"
  display_name = "GitHub Phase 4 evidence adjudicator"

  depends_on = [
    google_project_service.control["iam.googleapis.com"],
  ]
}

resource "google_service_account" "phase4_deployer" {
  project      = google_project.reference.project_id
  account_id   = "github-p4-deployer"
  display_name = "Phase 4 Cloud Run deployer"

  depends_on = [
    google_project_service.control["iam.googleapis.com"],
  ]
}

resource "google_service_account" "phase4_runtime" {
  project      = google_project.reference.project_id
  account_id   = "p4-proof-runtime"
  display_name = "Phase 4 proof runtime"

  depends_on = [
    google_project_service.control["iam.googleapis.com"],
  ]
}

resource "google_service_account" "phase4_verifier" {
  project      = google_project.reference.project_id
  account_id   = "github-p4-verifier"
  display_name = "Phase 4 verifier"

  depends_on = [
    google_project_service.control["iam.googleapis.com"],
  ]
}

resource "google_project_iam_custom_role" "phase4_foundation_control_reader" {
  project     = google_project.control.project_id
  role_id     = "resilio_p4_foundation_reader"
  title       = "Resilio Phase 4 foundation reader"
  description = "Read only the exact operational Phase 4 resource classes managed by foundation."
  permissions = [
    "artifactregistry.locations.get",
    "artifactregistry.locations.list",
    "artifactregistry.repositories.get",
    "artifactregistry.repositories.list",
    "resourcemanager.projects.get",
    "serviceusage.services.get",
    "serviceusage.services.list",
    "storage.buckets.get",
    "storage.buckets.list",
  ]
}

resource "google_project_iam_custom_role" "phase4_foundation_control_applier" {
  project     = google_project.control.project_id
  role_id     = "resilio_p4_foundation_apply"
  title       = "Resilio Phase 4 foundation applier"
  description = "Create or update only the exact non-IAM Phase 4 operational resources in the control project."
  permissions = [
    "artifactregistry.locations.get",
    "artifactregistry.locations.list",
    "artifactregistry.repositories.create",
    "artifactregistry.repositories.get",
    "artifactregistry.repositories.list",
    "artifactregistry.repositories.update",
    "resourcemanager.projects.get",
    "serviceusage.services.enable",
    "serviceusage.services.get",
    "serviceusage.services.list",
    "storage.buckets.create",
    "storage.buckets.get",
    "storage.buckets.list",
    "storage.buckets.update",
  ]
}

resource "google_project_iam_custom_role" "phase4_foundation_reference_reader" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p4_foundation_reader"
  title       = "Resilio Phase 4 foundation reader"
  description = "Read only the Phase 4 service-enable state managed by foundation in the reference project."
  permissions = [
    "resourcemanager.projects.get",
    "serviceusage.services.get",
    "serviceusage.services.list",
  ]
}

resource "google_project_iam_custom_role" "phase4_foundation_reference_applier" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p4_foundation_apply"
  title       = "Resilio Phase 4 foundation applier"
  description = "Enable and read only the accepted Phase 4 service state in the reference project."
  permissions = [
    "resourcemanager.projects.get",
    "serviceusage.services.enable",
    "serviceusage.services.get",
    "serviceusage.services.list",
  ]
}

resource "google_project_iam_custom_role" "phase4_build_initiator" {
  project     = google_project.control.project_id
  role_id     = "resilio_p4_build_initiator"
  title       = "Resilio Phase 4 build initiator"
  description = "Create and inspect Cloud Build builds without cancellation, deployment, registry or IAM authority."
  permissions = [
    "cloudbuild.builds.create",
    "cloudbuild.builds.get",
    "cloudbuild.builds.list",
  ]
}

resource "google_project_iam_custom_role" "phase4_builder_logging" {
  project     = google_project.control.project_id
  role_id     = "resilio_p4_builder_logging"
  title       = "Resilio Phase 4 builder logging"
  description = "Write Cloud Build log entries only."
  permissions = [
    "logging.logEntries.create",
    "logging.logEntries.route",
  ]
}

resource "google_project_iam_custom_role" "phase4_builder_registry" {
  project     = google_project.control.project_id
  role_id     = "resilio_p4_builder_registry"
  title       = "Resilio Phase 4 builder registry"
  description = "Read and write image content and tags without repository administration or artifact deletion."
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

resource "google_project_iam_custom_role" "phase4_evidence_analysis" {
  project     = google_project.control.project_id
  role_id     = "resilio_p4_evidence_analysis"
  title       = "Resilio Phase 4 evidence analysis"
  description = "Read exact build and Artifact Analysis occurrence evidence and export the provider-native SBOM."
  permissions = [
    "cloudbuild.builds.get",
    "containeranalysis.occurrences.create",
    "containeranalysis.occurrences.list",
    "serviceusage.services.use",
  ]
}

resource "google_project_iam_custom_role" "phase4_deployer" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p4_deployer"
  title       = "Resilio Phase 4 deployer"
  description = "Create or update the bounded Cloud Run service and read operation status without IAM mutation."
  permissions = [
    "run.operations.get",
    "run.services.create",
    "run.services.get",
    "run.services.update",
  ]
}

resource "google_project_iam_custom_role" "phase4_verifier" {
  project     = google_project.reference.project_id
  role_id     = "resilio_p4_verifier"
  title       = "Resilio Phase 4 verifier"
  description = "Read Cloud Run service/revision/IAM state and invoke the private proof service without mutation."
  permissions = [
    "run.revisions.get",
    "run.routes.invoke",
    "run.services.get",
    "run.services.getIamPolicy",
  ]
}

resource "google_project_iam_custom_role" "phase4_evidence_object_creator" {
  project     = google_project.control.project_id
  role_id     = "resilio_p4_evidence_create"
  title       = "Resilio Phase 4 evidence creator"
  description = "Create immutable Phase 4 evidence objects when resource-conditionally bound."
  permissions = [
    "storage.objects.create",
  ]
}

resource "google_project_iam_custom_role" "phase4_evidence_object_reader" {
  project     = google_project.control.project_id
  role_id     = "resilio_p4_evidence_read"
  title       = "Resilio Phase 4 evidence reader"
  description = "Read Phase 4 evidence objects when resource-conditionally bound."
  permissions = [
    "storage.objects.get",
  ]
}

resource "google_project_iam_member" "foundation_planner_phase4_control" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase4_foundation_control_reader.name
  member  = "serviceAccount:${google_service_account.foundation_planner.email}"
}

resource "google_project_iam_member" "foundation_applier_phase4_control" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase4_foundation_control_applier.name
  member  = "serviceAccount:${google_service_account.foundation_applier.email}"
}

resource "google_project_iam_member" "foundation_planner_phase4_reference" {
  project = google_project.reference.project_id
  role    = google_project_iam_custom_role.phase4_foundation_reference_reader.name
  member  = "serviceAccount:${google_service_account.foundation_planner.email}"
}

resource "google_project_iam_member" "foundation_applier_phase4_reference" {
  project = google_project.reference.project_id
  role    = google_project_iam_custom_role.phase4_foundation_reference_applier.name
  member  = "serviceAccount:${google_service_account.foundation_applier.email}"
}

resource "google_project_iam_member" "phase4_build_initiator" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase4_build_initiator.name
  member  = "serviceAccount:${google_service_account.phase4_build_initiator.email}"
}

resource "google_project_iam_member" "phase4_builder_logging" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase4_builder_logging.name
  member  = "serviceAccount:${google_service_account.phase4_builder.email}"
}

resource "google_project_iam_member" "phase4_evidence_analysis" {
  project = google_project.control.project_id
  role    = google_project_iam_custom_role.phase4_evidence_analysis.name
  member  = "serviceAccount:${google_service_account.phase4_evidence.email}"
}

resource "google_project_iam_member" "phase4_deployer" {
  project = google_project.reference.project_id
  role    = google_project_iam_custom_role.phase4_deployer.name
  member  = "serviceAccount:${google_service_account.phase4_deployer.email}"
}

resource "google_project_iam_member" "phase4_verifier" {
  project = google_project.reference.project_id
  role    = google_project_iam_custom_role.phase4_verifier.name
  member  = "serviceAccount:${google_service_account.phase4_verifier.email}"
}

resource "google_service_account_iam_member" "github_phase4_build" {
  service_account_id = google_service_account.phase4_build_initiator.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.phase4_build_workflow_ref}"

  depends_on = [
    google_iam_workload_identity_pool_provider.github,
  ]
}

resource "google_service_account_iam_member" "github_phase4_evidence" {
  service_account_id = google_service_account.phase4_evidence.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.phase4_evidence_workflow_ref}"

  depends_on = [
    google_iam_workload_identity_pool_provider.github,
  ]
}

resource "google_service_account_iam_member" "github_phase4_deployer" {
  service_account_id = google_service_account.phase4_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.phase4_deploy_workflow_ref}"

  depends_on = [
    google_iam_workload_identity_pool_provider.github,
  ]
}

resource "google_service_account_iam_member" "github_phase4_verifier" {
  service_account_id = google_service_account.phase4_verifier.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.phase4_deploy_workflow_ref}"

  depends_on = [
    google_iam_workload_identity_pool_provider.github,
  ]
}

resource "google_service_account_iam_member" "phase4_build_act_as_builder" {
  service_account_id = google_service_account.phase4_builder.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.phase4_build_initiator.email}"
}

resource "google_service_account_iam_member" "phase4_deployer_act_as_runtime" {
  service_account_id = google_service_account.phase4_runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.phase4_deployer.email}"
}

resource "google_artifact_registry_repository_iam_member" "phase4_builder_registry" {
  project    = "resilio-control-e882d4"
  location   = "us-central1"
  repository = "resilio-phase4"
  role       = google_project_iam_custom_role.phase4_builder_registry.name
  member     = "serviceAccount:${google_service_account.phase4_builder.email}"
}

resource "google_artifact_registry_repository_iam_member" "phase4_evidence_reader" {
  project    = "resilio-control-e882d4"
  location   = "us-central1"
  repository = "resilio-phase4"
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.phase4_evidence.email}"
}

resource "google_artifact_registry_repository_iam_member" "phase4_deployer_reader" {
  project    = "resilio-control-e882d4"
  location   = "us-central1"
  repository = "resilio-phase4"
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.phase4_deployer.email}"
}

resource "google_artifact_registry_repository_iam_member" "phase4_cloud_run_service_agent_reader" {
  project    = "resilio-control-e882d4"
  location   = "us-central1"
  repository = "resilio-phase4"
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:service-144158187163@serverless-robot-prod.iam.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "phase4_evidence_creator" {
  bucket = "resilio-control-e882d4-phase4-evidence"
  role   = google_project_iam_custom_role.phase4_evidence_object_creator.name
  member = "serviceAccount:${google_service_account.phase4_evidence.email}"

  condition {
    title       = "phase4-transition-create"
    description = "Create only immutable Phase 4 transition evidence objects."
    expression  = "resource.name.startsWith(\"${local.phase4_transition_object_resource_prefix}\")"
  }
}

resource "google_storage_bucket_iam_member" "phase4_evidence_reader" {
  bucket = "resilio-control-e882d4-phase4-evidence"
  role   = google_project_iam_custom_role.phase4_evidence_object_reader.name
  member = "serviceAccount:${google_service_account.phase4_evidence.email}"

  condition {
    title       = "phase4-transition-read"
    description = "Read only immutable Phase 4 transition evidence objects."
    expression  = "resource.name.startsWith(\"${local.phase4_transition_object_resource_prefix}\")"
  }
}

resource "google_storage_bucket_iam_member" "phase4_deployer_evidence_reader" {
  bucket = "resilio-control-e882d4-phase4-evidence"
  role   = google_project_iam_custom_role.phase4_evidence_object_reader.name
  member = "serviceAccount:${google_service_account.phase4_deployer.email}"

  condition {
    title       = "phase4-transition-read"
    description = "Read only immutable Phase 4 transition evidence objects."
    expression  = "resource.name.startsWith(\"${local.phase4_transition_object_resource_prefix}\")"
  }
}
