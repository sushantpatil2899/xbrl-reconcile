# Reads B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY from the environment.
provider "b2" {}

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
