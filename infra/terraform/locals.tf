# Applied to every Azure resource. Azure bills and groups by tag, so a resource with
# no tag is one you cannot account for later.
locals {
  azure_tags = {
    project    = var.github_repository
    managed_by = "terraform"
  }
}
