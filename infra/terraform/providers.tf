# Reads B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY from the environment.
#
# endpoint is pinned rather than left to default, because the provider also reads it
# from B2_ENDPOINT and this project exports that name with the S3 compatible endpoint,
# which everything else here speaks. Inherited, it sends a native API call to the S3
# host and Backblaze answers NotImplemented, which reads like a credential problem and
# is not one. One variable name cannot serve two incompatible APIs, so this provider
# stops reading it.
provider "b2" {
  endpoint = "production"
}

# Reads GITHUB_TOKEN from the environment.
provider "github" {
  owner = var.github_owner
}

# Reads ARM_SUBSCRIPTION_ID and ARM_TENANT_ID from the environment, or takes the
# subscription from the variable below. Authentication itself comes from whatever is
# available: an az login on a laptop, or a federated OIDC token in GitHub Actions, so
# no Azure password or client secret is ever stored.
#
# The features block is required even when empty. It is where provider wide behaviour
# such as whether deleting a resource group also deletes what is inside it would be
# configured, and the defaults are what we want.
provider "azurerm" {
  subscription_id = var.azure_subscription_id

  # A subscription cannot create a kind of resource until its resource provider is
  # registered, and a new subscription has almost none registered. Declaring it here
  # means a fresh subscription is brought to a working state by terraform apply,
  # rather than by a command somebody has to remember to run first.
  #
  # Microsoft.App owns Container Apps. Microsoft.OperationalInsights is deliberately
  # absent, because no Log Analytics workspace is created.
  resource_provider_registrations = "none"
  resource_providers_to_register  = ["Microsoft.App"]

  features {}
}
