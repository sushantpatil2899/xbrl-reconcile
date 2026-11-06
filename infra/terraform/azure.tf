# Where the API runs.
#
# Azure Container Apps rather than a virtual machine or App Service, for one reason
# that decides it: an app scaled to zero replicas costs nothing at all. The consumption
# plan bills per second of allocated resource, and Microsoft gives every subscription
# 180,000 vCPU seconds, 360,000 GiB seconds and 2 million requests free each calendar
# month. At the smallest size Container Apps allows, that free grant alone covers about
# 200 hours of active runtime a month, which this API will not approach.
#
# Holding a replica warm around the clock is the thing that would cost money. A quarter
# of a vCPU for thirty days is 648,000 vCPU seconds, three and a half times the grant,
# and the overage bills at the idle rate. That works out near four dollars a month, so
# min_replicas stays at zero and the first request after a quiet spell pays a cold
# start instead. Raising min_replicas to one is the one setting to change if that
# trade stops being worth it.
#
# No Log Analytics workspace is attached. Omitting logs_destination leaves logs
# streamed only, which keeps the live log stream usable for debugging while storing
# nothing and charging nothing. Datadog is the observability story here, and it reaches
# the app from outside rather than through Azure Monitor.

resource "azurerm_resource_group" "api" {
  name     = "rg-${var.github_repository}"
  location = var.azure_location

  tags = local.azure_tags
}

resource "azurerm_container_app_environment" "api" {
  name                = "cae-${var.github_repository}"
  location            = azurerm_resource_group.api.location
  resource_group_name = azurerm_resource_group.api.name

  tags = local.azure_tags
}

resource "azurerm_container_app" "api" {
  name                         = "ca-${var.github_repository}-api"
  container_app_environment_id = azurerm_container_app_environment.api.id
  resource_group_name          = azurerm_resource_group.api.name

  # Single means one revision serves all traffic, so a deploy replaces what is live
  # rather than running beside it. Multiple would let two revisions split traffic,
  # which is a feature worth having when there is something to compare and only a
  # source of confusion before then.
  revision_mode = "Single"

  template {
    # Zero so a quiet API is a free API. Two so a burst has somewhere to go: extra
    # replicas bill only while they are actually running, and the rate limiter in
    # front of the app is the real defence against a flood.
    min_replicas = 0
    max_replicas = 2

    container {
      name = "api"

      # Deliberately a placeholder, and deliberately Microsoft's own. This step proves
      # the subscription, the region, the environment and the ingress all work before
      # our own image exists to be blamed for a failure. It is replaced by the image
      # built from this repository's Dockerfile once that is pushed to a registry.
      image = "mcr.microsoft.com/k8se/quickstart:latest"

      # The smallest pair Container Apps accepts. The API answers from Parquet files
      # baked into the image, so it needs very little of either.
      cpu    = 0.25
      memory = "0.5Gi"
    }
  }

  ingress {
    # Reachable from the internet, which is the point of hosting it.
    external_enabled = true

    # Port 80 is what the quickstart image listens on. Our own image listens on 8000,
    # so this changes in the same commit that changes the image.
    target_port = 80

    # Insecure connections are left disabled, the default, so plain HTTP is redirected
    # to HTTPS and the certificate Azure issues for the generated hostname is used.
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = local.azure_tags
}
