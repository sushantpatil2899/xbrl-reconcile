# Reads B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY from the environment.
provider "b2" {}

# Reads GITHUB_TOKEN from the environment.
provider "github" {
  owner = var.github_owner
}
