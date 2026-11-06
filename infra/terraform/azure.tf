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
# The region is not a free choice. An Azure for Students subscription carries a policy
# assignment named "Allowed resource deployment regions" that permits only norwayeast,
# swedencentral, denmarkeast, westus and northcentralus, and denies everything else
# outright with RequestDisallowedByAzure. Denmark East has no Container Apps, which
# leaves four. North Central US is Illinois and the nearest of them to the east coast.
#
# The policy runs in Indexed mode, so it skips resource groups. That is why a resource
# group can be created in a forbidden region and only the resources inside it fail,
# which makes the error look like a problem with the resource rather than the region.
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

  # Declared because Azure creates it whether we ask or not, and leaving it out of the
  # configuration is not a neutral omission. The provider documentation is explicit:
  # an environment created with profiles must always keep at least one, and removing
  # them all forces the resource to be recreated. So an absent block here reads as a
  # request to strip every profile, which made every plan propose a modification to the
  # environment, and the read that follows that modification is what kept returning a
  # spurious 404 and aborting the apply.
  #
  # maximum_count and minimum_count are left out deliberately. They are optional, and
  # instance counts mean nothing for a Consumption profile, where Azure allocates per
  # request rather than per instance.
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }

  tags = local.azure_tags
}

# A pause between creating the environment and asking Azure to read it back.
#
# Azure's management API is eventually consistent, and the first apply of this file
# proved how expensive that is. The environment was created successfully, the container
# app's immediate read of it returned 404, the apply aborted, and because the provider
# never got its confirming read the environment was never written to state. Azure had
# the resource, Terraform did not, and the next apply failed with "already exists".
# Recovering it took a terraform import.
#
# Thirty seconds is a wide margin on a lag measured in seconds, and it is paid only
# when the environment is actually created. The trigger is the environment's id, so a
# replaced environment forces a fresh pause, while an ordinary apply that changes only
# the app waits for nothing.
resource "time_sleep" "environment_settled" {
  create_duration = "30s"

  triggers = {
    environment_id = azurerm_container_app_environment.api.id
  }
}

resource "azurerm_container_app" "api" {
  name                         = "ca-${var.github_repository}-api"
  container_app_environment_id = azurerm_container_app_environment.api.id
  resource_group_name          = azurerm_resource_group.api.name

  # Not the environment directly. Depending on the pause is what keeps the read that
  # failed last time from happening too early.
  depends_on = [time_sleep.environment_settled]

  # Azure assigns this on its own and reports it back, so declaring it is simply saying
  # what is already true. Left out, every plan proposed setting it to null, which Azure
  # then ignored, and the same change was proposed again on the next run.
  workload_profile_name = "Consumption"

  # Three fields Azure will not let us own, each confirmed by applying the change and
  # reading the resource back unaltered.
  #
  # cooldown_period_in_seconds and polling_interval_in_seconds are platform managed.
  # Azure stores nothing for them and reports zero, meaning use my defaults, while the
  # provider defaults to 300 and 30 when they are omitted. Writing 0 here would stop
  # the drift by stating something false, because 0 cooldown means scale down instantly
  # and what we actually want is Azure's default.
  #
  # traffic_weight is required by the provider but is not read back from Azure, so it
  # reads as missing on every refresh. It is inert under Single revision mode, where one
  # revision takes everything. If this ever moves to Multiple revision mode and traffic
  # is genuinely split, remove it from this list, or a real change will be hidden.
  #
  # Without these, every plan proposed a modification that altered nothing, which costs
  # twenty seconds and teaches a reader that a clean plan is not achievable here.
  lifecycle {
    ignore_changes = [
      template[0].cooldown_period_in_seconds,
      template[0].polling_interval_in_seconds,
      ingress[0].traffic_weight,
    ]
  }

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

    # Also declared because Azure creates it by default. Ten concurrent requests to a
    # replica before another is started, which for an API answering from local Parquet
    # is generous, and leaving it undeclared meant every plan proposed deleting it.
    http_scale_rule {
      name                = "http-scaler"
      concurrent_requests = 10
    }

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

    # Azure normalises auto to http and reports http, so declaring http avoids a change
    # being proposed on every plan. The two behave identically for an HTTP/1.1 API.
    transport = "http"

    # Insecure connections are left disabled, the default, so plain HTTP is redirected
    # to HTTPS and the certificate Azure issues for the generated hostname is used.
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = local.azure_tags
}
