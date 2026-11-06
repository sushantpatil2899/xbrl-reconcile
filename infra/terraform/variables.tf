variable "github_owner" {
  description = "GitHub user or organization that owns the repository"
  type        = string
}

variable "github_repository" {
  description = "Repository name that runs the ingestion workflow"
  type        = string
}

variable "bucket_name" {
  description = "Globally unique B2 bucket name for raw data (6 to 63 characters, letters, digits, hyphens)"
  type        = string
}

variable "sec_contact_email" {
  description = "Contact email SEC requires in the User-Agent header"
  type        = string
  sensitive   = true
}

variable "azure_subscription_id" {
  description = "Azure subscription the API resources are created in, from the portal under Subscriptions"
  type        = string
}

variable "azure_location" {
  description = "Azure region for the API. Must be one the subscription policy permits, which is a much shorter list than Azure's."
  type        = string
  default     = "northcentralus"
}

variable "ghcr_read_token" {
  description = "Classic GitHub token with read:packages only, so Container Apps can pull the private image"
  type        = string
  sensitive   = true
}

variable "api_image_tag" {
  description = "Image tag Terraform sets. Once the deploy workflow owns rollouts and the image is added to ignore_changes, changing this will stop deploying anything."
  type        = string
  default     = "latest"
}
