terraform {
  required_version = ">= 1.9"

  # State lives in HCP Terraform. Organization and workspace come from the
  # TF_CLOUD_ORGANIZATION and TF_WORKSPACE environment variables.
  cloud {}

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.13"
    }
    b2 = {
      source  = "Backblaze/b2"
      version = "~> 0.14"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.13"
    }
  }
}
