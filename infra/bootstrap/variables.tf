variable "billing_account_id" {
  description = "Cloud Billing account ID. Owner-local input; never commit a real value."
  type        = string
  sensitive   = true

  validation {
    condition     = trimspace(var.billing_account_id) != ""
    error_message = "billing_account_id must be supplied owner-locally."
  }
}

variable "control_project_id" {
  description = "Globally unique project ID for the Resilio control plane."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.control_project_id))
    error_message = "control_project_id must be a valid Google Cloud project ID."
  }
}

variable "reference_project_id" {
  description = "Globally unique project ID for the Resilio reference workload plane."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.reference_project_id))
    error_message = "reference_project_id must be a valid Google Cloud project ID."
  }
}

variable "project_creation_mode" {
  description = "managed-parent creates projects under an existing parent; precreated-import requires owner-local project creation and import before the authoritative plan."
  type        = string
  default     = "managed-parent"

  validation {
    condition     = contains(["managed-parent", "precreated-import"], var.project_creation_mode)
    error_message = "project_creation_mode must be managed-parent or precreated-import."
  }
}

variable "project_parent_type" {
  description = "Existing parent type for Terraform-managed project creation, or none for precreated-import."
  type        = string
  default     = "none"

  validation {
    condition     = contains(["organization", "folder", "none"], var.project_parent_type)
    error_message = "project_parent_type must be organization, folder, or none."
  }
}

variable "project_parent_id" {
  description = "Existing organisation or folder numeric ID. Leave null for precreated-import."
  type        = string
  default     = null
  nullable    = true
}

variable "remove_default_network" {
  description = "Set true only when the approved bootstrap must remove a default VPC created during project creation."
  type        = bool
  default     = false
}

variable "state_bucket_suffix" {
  description = "Non-secret state bucket suffix. Keep tfstate unless a verified global-name collision requires an owner-approved alternative."
  type        = string
  default     = "tfstate"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$", var.state_bucket_suffix))
    error_message = "state_bucket_suffix must contain lowercase letters, digits, and hyphens only."
  }
}
