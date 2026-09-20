output "control_project_id" {
  value       = google_project.control.project_id
  description = "Canonical control project ID."
}

output "control_project_number" {
  value       = google_project.control.number
  description = "Canonical control project number."
}

output "reference_project_id" {
  value       = google_project.reference.project_id
  description = "Canonical reference project ID."
}

output "reference_project_number" {
  value       = google_project.reference.number
  description = "Canonical reference project number."
}

output "terraform_state_bucket" {
  value       = google_storage_bucket.terraform_state.name
  description = "Private remote-state bucket name."
}

output "workload_identity_provider" {
  value       = google_iam_workload_identity_pool_provider.github.name
  description = "Canonical GitHub Workload Identity Provider resource name."
}

output "federation_probe_service_account" {
  value       = google_service_account.federation_probe.email
  description = "Least-privilege service account used only for keyless federation proof."
}

output "github_main_subject" {
  value       = local.github_main_subject
  description = "Exact immutable GitHub OIDC subject authorised for federation."
}

output "foundation_planner_service_account" {
  value       = google_service_account.foundation_planner.email
  description = "Dedicated read-only foundation planner service account."
}

output "foundation_applier_service_account" {
  value       = google_service_account.foundation_applier.email
  description = "Dedicated bounded foundation applier service account."
}

output "foundation_plan_workflow_ref" {
  value       = local.foundation_plan_workflow_ref
  description = "Exact immutable reusable-workflow identity authorised to impersonate the foundation planner."
}

output "foundation_apply_workflow_ref" {
  value       = local.foundation_apply_workflow_ref
  description = "Exact immutable reusable-workflow identity authorised to impersonate the foundation applier."
}

output "foundation_drift_workflow_ref" {
  value       = local.foundation_drift_workflow_ref
  description = "Exact immutable reusable-workflow identity authorised to impersonate the foundation drift planner."
}

output "phase4_control_seed_sha" {
  value       = local.phase4_control_seed_sha
  description = "Immutable reviewed Phase 4 reusable-workflow/control seed."
}

output "phase4_build_workflow_ref" {
  value       = local.phase4_build_workflow_ref
  description = "Exact immutable Phase 4 reusable build-workflow identity authorised for the build initiator."
}

output "phase4_evidence_workflow_ref" {
  value       = local.phase4_evidence_workflow_ref
  description = "Exact immutable Phase 4 reusable evidence-workflow identity authorised for the evidence adjudicator."
}

output "phase4_deploy_workflow_ref" {
  value       = local.phase4_deploy_workflow_ref
  description = "Exact immutable Phase 4 reusable deploy-workflow identity authorised for deployer and verifier federation."
}

output "phase4_build_initiator_service_account" {
  value       = google_service_account.phase4_build_initiator.email
  description = "Phase 4 build-initiation identity bound only to the immutable trusted build workflow."
}

output "phase4_builder_service_account" {
  value       = google_service_account.phase4_builder.email
  description = "Phase 4 Cloud Build execution identity with bounded logging and repository-content authority."
}

output "phase4_evidence_service_account" {
  value       = google_service_account.phase4_evidence.email
  description = "Phase 4 evidence adjudication identity bound only to the immutable trusted evidence workflow."
}

output "phase4_deployer_service_account" {
  value       = google_service_account.phase4_deployer.email
  description = "Phase 4 exact-digest Cloud Run deployer bound only to the immutable trusted deploy workflow."
}

output "phase4_runtime_service_account" {
  value       = google_service_account.phase4_runtime.email
  description = "Phase 4 proof runtime identity with no project role."
}

output "phase4_verifier_service_account" {
  value       = google_service_account.phase4_verifier.email
  description = "Phase 4 independent verifier bound only to the immutable trusted deploy workflow."
}
