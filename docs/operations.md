# Operations

[← back to the README](../README.md)

## What this does

Everything that runs the project: eight GitHub Actions workflows, Terraform for
the infrastructure, and the hosting. Total ongoing cost: **zero**.

## The workflows

| Workflow | Trigger | Does |
|---|---|---|
| `ci` | push, pull request | ruff and 278 pytest tests |
| `ingest` | cron, 06:00 UTC daily | SEC companyfacts and submissions |
| `ingest-datasets` | cron, 5th monthly | SEC quarterly Financial Statement Data Sets |
| `ingest-linkbase` | cron, 6th monthly | Calculation linkbase XML for new filings |
| `transform` | when `ingest` finishes | dbt build and test, publishes database and marts |
| `image` | when `transform` succeeds | Builds the API image with the marts inside, pushes to GHCR |
| `pages` | when `transform` succeeds | Publishes the page and the current marts together |
| `deploy` | when `image` succeeds | Rolls the new image onto Azure |

The chain is `ingest` → `transform` → `image` → `deploy`, with `pages`
branching off `transform`. **There is no server.** Every batch step is an
Actions runner that is wiped afterwards, which is why the database is fetched
from storage, rebuilt, and published back on every run.

`transform` runs even when `ingest` reports failure. Ingestion fails if any
single company fails, and the twenty seven that did land should still be
transformed. A genuinely stalled pipeline is caught by the freshness tests.

## Terraform

One root module, four providers, eleven resources, state in HCP Terraform.

| Provider | Creates |
|---|---|
| `b2` | The bucket, and a key scoped to it that cannot delete files |
| `github` | Three Actions secrets and two Actions variables |
| `azurerm` | The resource group, the Container Apps environment, the container app |
| `time` | A settle delay between the environment and the app |

**The ownership split is the important part.** Terraform owns the
infrastructure and explicitly ignores the running image. The `deploy` workflow
owns the image and touches nothing else. That means a daily data refresh can
never alter a resource group, and a `terraform apply` can never roll back
today's data. Both sides plan clean against each other.

Every credential is read from the environment, so none sits in a file:

| Variable | Read by | What it is |
|---|---|---|
| `TF_CLOUD_ORGANIZATION` | Terraform | HCP organisation holding the state |
| `TF_WORKSPACE` | Terraform | HCP workspace within it |
| `B2_APPLICATION_KEY_ID` | `b2` provider | Backblaze master key id, 12 characters |
| `B2_APPLICATION_KEY` | `b2` provider | Its secret |
| `GITHUB_TOKEN` | `github` provider | Token with `repo` scope |
| `TF_VAR_ghcr_read_token` | `azurerm` | Classic PAT with `read:packages`, for the container app to pull |

Azure needs no variable of its own: the `azurerm` provider takes its
credentials from `az login`, so no Azure password or client secret is ever
stored.

## Hosting, and why it costs nothing

**Azure Container Apps on the consumption plan, scaled to zero.** The app runs
no replicas until a request arrives. Azure's free monthly grant is 180,000 vCPU
seconds, 360,000 GiB seconds and 2 million requests per subscription. At 0.25
vCPU and 0.5 GiB, this stays inside it with room to spare, and the Azure for
Students subscription is spend capped rather than card backed, so it cannot
quietly start billing.

**The registry is GHCR, not Azure Container Registry.** ACR has no free tier and
bills a flat rate per day whether or not anything is pulled: 60.96 US dollars a
year for the Basic tier. GHCR is free for container storage and bandwidth. The
build has to happen in Actions anyway, because the Dockerfile mounts the bucket
credentials as a BuildKit secret so they touch exactly one layer and are
recorded in none, which a platform builder generally cannot do. GHCR also holds
the build cache, under a `buildcache` tag, for the reason in the decisions
below. The secret mount is recorded in no layer, so it reaches no cache either.

**The deploy uses OIDC, so no Azure secret is stored anywhere.** The app
registration carries a federated credential naming this repository and this
branch. Actions exchanges its own token for an Azure one at run time, and a
token issued for any other repository or branch is refused. The identity is
Contributor on one resource group and nothing else.

**The page is free**, and the marts are 1,397 KB inside Backblaze's free tier.

## Decisions worth knowing

**The chain sits exactly at GitHub's three level `workflow_run` limit.**
`ingest` → `transform` → `image` → `deploy` is three levels, so `deploy` fires
with zero headroom and anything chained after it would silently never run. This
is a real constraint on what can be added later, and it is recorded in section
17 of [design.md](design.md) along with the rest of the open items. The chain
first ran on its own on 2026-11-06 and the trigger did reach `deploy`, so three
levels work; a fourth would not.

**A workflow triggered one way is not tested for another.** That first automatic
run broke both leaves, each on configuration that had passed repeatedly under a
manual dispatch and could not work under `workflow_run`. The build cache now
lives in GHCR rather than the Actions cache, because GitHub grants only read
access to the default branch cache scope for triggers it treats as low trust and
`workflow_run` is one of them. The page's freshness check now polls for three
minutes instead of reading once, because `deploy-pages` returns when GitHub
accepts a deployment rather than when every CDN edge serves it. Section 17 of
[design.md](design.md) has both in full.

**A stalled Pages deploy is retried with a commit, not a re-run.** A Pages
deployment is keyed by the commit, and `deploy-pages` names that commit as the
deployment id when it gives up. Dispatching `pages` again on the same commit
therefore tries to recreate a deployment that was just cancelled, and times out
the same way; a new commit deploys immediately. The site keeps serving its last
published build throughout, so a failed deploy is a staleness problem rather
than an outage. Note also that the Pages API reports `status: null` for this
site whether or not a deploy just succeeded, because it is built by workflow
rather than the legacy builder, so that field says nothing about health.

**The GHCR pull token expires.** It is a classic personal access token with
`read:packages`, held as a Container Apps secret and therefore also present in
the Terraform state. Making the package public would remove the token, the
state exposure and the quiet deploy time failure together, but that requires
the repository to be public because the image carries the source.

## Run it yourself

```bash
cd infra/terraform && terraform init && terraform plan
```

## Verify

Both halves of the deploy chain report the same build:

```bash
curl -s https://ca-xbrl-reconcile-api.wonderfulwater-66905cf2.northcentralus.azurecontainerapps.io/healthz
```

```bash
curl -s https://sushantpatil2899.github.io/xbrl-reconcile/_index.json | head -2
```

## Deeper

Section 7.6 of [design.md](design.md) covers the schedule, 7.7 the Terraform
layout, 14 the running cost as built, and 17 what hosting left open along with
the traps found while building it.
