locals {
  phase4_control_seed_sha = "10e7a938046e2d2d28ffa08a470bf9dfeda40dac"
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
  display_name = "GitHub Phase 4 deployer"

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
  display_name = "GitHub Phase 4 verifier"

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
    "containeranalysis.occurrences.list",
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
