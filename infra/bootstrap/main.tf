locals {
  github_main_subject = "repo:8ft0-ai@130460431/resilio@1335801159:ref:refs/heads/main"

  control_services = toset([
    "billingbudgets.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ])

  control_org_id    = var.project_parent_type == "organization" ? var.project_parent_id : null
  control_folder_id = var.project_parent_type == "folder" ? var.project_parent_id : null
  state_bucket_name = "${var.control_project_id}-${var.state_bucket_suffix}"

  project_creation_configuration_valid = (
    var.project_creation_mode == "precreated-import"
    ? (
      var.project_parent_type == "none" &&
      var.project_parent_id == null
    )
    : (
      contains(["organization", "folder"], var.project_parent_type) &&
      try(trimspace(var.project_parent_id), "") != ""
    )
  )
}

resource "google_project" "control" {
  name                = "Resilio Control"
  project_id          = var.control_project_id
  billing_account     = var.billing_account_id
  org_id              = local.control_org_id
  folder_id           = local.control_folder_id
  auto_create_network = !var.remove_default_network
  deletion_policy     = "PREVENT"

  labels = {
    system = "resilio"
    role   = "control"
  }

  lifecycle {
    precondition {
      condition     = local.project_creation_configuration_valid
      error_message = "managed-parent mode requires an existing organization/folder parent; precreated-import must use project_parent_type=none with no parent ID and both owner-created projects imported before the authoritative plan."
    }
  }
}

resource "google_project" "reference" {
  name                = "Resilio Reference"
  project_id          = var.reference_project_id
  billing_account     = var.billing_account_id
  org_id              = local.control_org_id
  folder_id           = local.control_folder_id
  auto_create_network = !var.remove_default_network
  deletion_policy     = "PREVENT"

  labels = {
    system = "resilio"
    role   = "reference"
  }

  lifecycle {
    precondition {
      condition     = local.project_creation_configuration_valid
      error_message = "managed-parent mode requires an existing organization/folder parent; precreated-import must use project_parent_type=none with no parent ID and both owner-created projects imported before the authoritative plan."
    }
  }
}

resource "google_project_service" "control" {
  for_each = local.control_services

  project            = google_project.control.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "terraform_state" {
  project                     = google_project.control.project_id
  name                        = local.state_bucket_name
  location                    = "us-central1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  labels = {
    system = "resilio"
    role   = "terraform-state"
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [
    google_project_service.control["storage.googleapis.com"],
  ]
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = google_project.control.project_id
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [
    google_project_service.control["iam.googleapis.com"],
  ]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = google_project.control.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "resilio"
  display_name                       = "Resilio trusted main"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.job_workflow_ref" = "assertion.job_workflow_ref"
    "attribute.job_workflow_sha" = "assertion.job_workflow_sha"
  }

  attribute_condition = "assertion.sub == \"${local.github_main_subject}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "federation_probe" {
  project      = google_project.control.project_id
  account_id   = "github-federation-probe"
  display_name = "GitHub federation probe"

  depends_on = [
    google_project_service.control["iam.googleapis.com"],
  ]
}

resource "google_service_account_iam_member" "github_federation_probe" {
  service_account_id = google_service_account.federation_probe.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/subject/${local.github_main_subject}"
}

resource "google_billing_budget" "reference" {
  billing_account = var.billing_account_id
  display_name    = "Resilio reference monthly engineering ceiling"

  budget_filter {
    projects = [
      "projects/${google_project.control.number}",
      "projects/${google_project.reference.number}",
    ]
    calendar_period = "MONTH"
  }

  amount {
    specified_amount {
      units = var.budget_units
    }
  }

  threshold_rules {
    threshold_percent = 0.5
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 0.8
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  deletion_policy = "PREVENT"

  depends_on = [
    google_project_service.control["billingbudgets.googleapis.com"],
  ]
}
