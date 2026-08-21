locals {
  phase3_control_seed_sha             = "cbfe9821ec07ca6c0c869ebe75100bc500c92a04"
  phase3_drift_workflow_sha           = "2acbc425f688383375f724da7a4d80025dd9cc23"
  foundation_plan_workflow_ref        = "8ft0-ai/resilio/.github/workflows/terraform-plan-reusable.yml@${local.phase4_control_seed_sha}"
  foundation_apply_workflow_ref       = "8ft0-ai/resilio/.github/workflows/terraform-apply-reusable.yml@${local.phase4_control_seed_sha}"
  foundation_drift_workflow_ref       = "8ft0-ai/resilio/.github/workflows/terraform-drift-reusable.yml@${local.phase4_control_seed_sha}"
  state_bucket_object_resource_prefix = "projects/_/buckets/${google_storage_bucket.terraform_state.name}/objects/"
  foundation_state_resource_name      = "${local.state_bucket_object_resource_prefix}foundation/default.tfstate"
  foundation_lock_resource_name       = "${local.state_bucket_object_resource_prefix}foundation/default.tflock"
  foundation_evidence_resource_prefix = "${local.state_bucket_object_resource_prefix}plan-evidence/foundation/"
}

resource "google_service_account" "foundation_planner" {
  project      = google_project.control.project_id
  account_id   = "github-foundation-planner"
  display_name = "GitHub foundation planner"

  depends_on = [
    google_project_service.control["iam.googleapis.com"],
  ]
}

resource "google_service_account" "foundation_applier" {
  project      = google_project.control.project_id
  account_id   = "github-foundation-applier"
  display_name = "GitHub foundation applier"

  depends_on = [
    google_project_service.control["iam.googleapis.com"],
  ]
}

resource "google_service_account_iam_member" "github_foundation_planner" {
  service_account_id = google_service_account.foundation_planner.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.foundation_plan_workflow_ref}"

  depends_on = [
    google_iam_workload_identity_pool_provider.github,
  ]
}

resource "google_service_account_iam_member" "github_foundation_drift" {
  service_account_id = google_service_account.foundation_planner.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.foundation_drift_workflow_ref}"

  depends_on = [
    google_iam_workload_identity_pool_provider.github,
  ]
}

resource "google_service_account_iam_member" "github_foundation_applier" {
  service_account_id = google_service_account.foundation_applier.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.job_workflow_ref/${local.foundation_apply_workflow_ref}"

  depends_on = [
    google_iam_workload_identity_pool_provider.github,
  ]
}

resource "google_project_iam_custom_role" "foundation_planner" {
  project     = google_project.reference.project_id
  role_id     = "resilio_foundation_planner"
  title       = "Resilio foundation planner"
  description = "Read-only verification required by the Phase 3 foundation proof."
  permissions = [
    "iam.serviceAccountKeys.list",
    "iam.serviceAccounts.get",
    "iam.serviceAccounts.getIamPolicy",
    "resourcemanager.projects.getIamPolicy",
  ]
}

resource "google_project_iam_custom_role" "foundation_applier" {
  project     = google_project.reference.project_id
  role_id     = "resilio_foundation_applier"
  title       = "Resilio foundation applier"
  description = "Create and update only service accounts required by the Phase 3 foundation proof."
  permissions = [
    "iam.serviceAccounts.create",
    "iam.serviceAccounts.get",
    "iam.serviceAccounts.update",
  ]
}

resource "google_project_iam_member" "foundation_planner" {
  project = google_project.reference.project_id
  role    = google_project_iam_custom_role.foundation_planner.name
  member  = "serviceAccount:${google_service_account.foundation_planner.email}"
}

resource "google_project_iam_member" "foundation_applier" {
  project = google_project.reference.project_id
  role    = google_project_iam_custom_role.foundation_applier.name
  member  = "serviceAccount:${google_service_account.foundation_applier.email}"
}

resource "google_project_iam_custom_role" "foundation_state_list" {
  project     = google_project.control.project_id
  role_id     = "resilio_foundation_state_list"
  title       = "Resilio foundation state list"
  description = "List-only access required by the Terraform GCS backend workspace discovery."
  permissions = [
    "storage.objects.list",
  ]
}

resource "google_project_iam_custom_role" "foundation_object_reader" {
  project     = google_project.control.project_id
  role_id     = "resilio_foundation_object_reader"
  title       = "Resilio foundation object reader"
  description = "Read exact foundation state or reviewed-plan evidence objects when conditionally bound."
  permissions = [
    "storage.objects.get",
  ]
}

resource "google_project_iam_custom_role" "foundation_lock" {
  project     = google_project.control.project_id
  role_id     = "resilio_foundation_lock"
  title       = "Resilio foundation state lock"
  description = "Create, inspect and delete only the exact Terraform GCS lock object when conditionally bound."
  permissions = [
    "storage.objects.create",
    "storage.objects.delete",
    "storage.objects.get",
  ]
}

resource "google_project_iam_custom_role" "foundation_state_writer" {
  project     = google_project.control.project_id
  role_id     = "resilio_foundation_state_writer"
  title       = "Resilio foundation state writer"
  description = "Create and overwrite only the exact foundation state object when conditionally bound."
  permissions = [
    "storage.objects.create",
    "storage.objects.delete",
  ]
}

resource "google_project_iam_custom_role" "foundation_evidence_creator" {
  project     = google_project.control.project_id
  role_id     = "resilio_foundation_evidence_creator"
  title       = "Resilio foundation evidence creator"
  description = "Create immutable private reviewed-plan evidence objects without overwrite or delete authority."
  permissions = [
    "storage.objects.create",
  ]
}

resource "google_storage_bucket_iam_member" "foundation_planner_list" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.foundation_state_list.name
  member = "serviceAccount:${google_service_account.foundation_planner.email}"
}

resource "google_storage_bucket_iam_member" "foundation_applier_list" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.foundation_state_list.name
  member = "serviceAccount:${google_service_account.foundation_applier.email}"
}

resource "google_storage_bucket_iam_member" "foundation_planner_state_reader" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.foundation_object_reader.name
  member = "serviceAccount:${google_service_account.foundation_planner.email}"

  condition {
    title       = "foundation-state-read"
    description = "Read only the canonical foundation state object."
    expression  = "resource.name == \"${local.foundation_state_resource_name}\""
  }
}

resource "google_storage_bucket_iam_member" "foundation_applier_state_reader" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.foundation_object_reader.name
  member = "serviceAccount:${google_service_account.foundation_applier.email}"

  condition {
    title       = "foundation-state-read"
    description = "Read only the canonical foundation state object."
    expression  = "resource.name == \"${local.foundation_state_resource_name}\""
  }
}

resource "google_storage_bucket_iam_member" "foundation_planner_lock" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.foundation_lock.name
  member = "serviceAccount:${google_service_account.foundation_planner.email}"

  condition {
    title       = "foundation-lock"
    description = "Operate only the canonical foundation lock object."
    expression  = "resource.name == \"${local.foundation_lock_resource_name}\""
  }
}

resource "google_storage_bucket_iam_member" "foundation_applier_lock" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.foundation_lock.name
  member = "serviceAccount:${google_service_account.foundation_applier.email}"

  condition {
    title       = "foundation-lock"
    description = "Operate only the canonical foundation lock object."
    expression  = "resource.name == \"${local.foundation_lock_resource_name}\""
  }
}

resource "google_storage_bucket_iam_member" "foundation_applier_state_writer" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.foundation_state_writer.name
  member = "serviceAccount:${google_service_account.foundation_applier.email}"

  condition {
    title       = "foundation-state-write"
    description = "Write only the canonical foundation state object."
    expression  = "resource.name == \"${local.foundation_state_resource_name}\""
  }
}

resource "google_storage_bucket_iam_member" "foundation_planner_evidence_creator" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.foundation_evidence_creator.name
  member = "serviceAccount:${google_service_account.foundation_planner.email}"

  condition {
    title       = "foundation-plan-evidence-create"
    description = "Create only private foundation reviewed-plan evidence objects."
    expression  = "resource.name.startsWith(\"${local.foundation_evidence_resource_prefix}\")"
  }
}

resource "google_storage_bucket_iam_member" "foundation_applier_evidence_reader" {
  bucket = google_storage_bucket.terraform_state.name
  role   = google_project_iam_custom_role.foundation_object_reader.name
  member = "serviceAccount:${google_service_account.foundation_applier.email}"

  condition {
    title       = "foundation-plan-evidence-read"
    description = "Read only private foundation reviewed-plan evidence objects."
    expression  = "resource.name.startsWith(\"${local.foundation_evidence_resource_prefix}\")"
  }
}
