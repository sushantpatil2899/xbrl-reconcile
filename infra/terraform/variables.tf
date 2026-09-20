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
