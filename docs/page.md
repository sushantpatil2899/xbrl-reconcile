# The query page

[← back to the README](../README.md)

**Live:** https://sushantpatil2899.github.io/xbrl-reconcile/

## What this does

A single HTML file that loads the Parquet marts with DuckDB compiled to
WebAssembly and runs the queries **in the reader's browser**. No server, no
account, no cold start, no rate limit. Anyone can open it and write SQL against
the real data.

Four tabs:

| Tab | Shows |
|---|---|
| **Compare** | All 28 companies lined up on one calendar year, with the confidence on every figure |
| **One company** | One company's values with the XBRL tag behind each number |
| **What to distrust** | Statements where an identity fails, gaps in coverage, and mappings the filers' own arithmetic questions |
| **SQL** | A query box against all twelve marts |

The third tab is the point. A dataset that shows you its own weak spots before
you find them is making a different kind of claim from one that does not.

## How it works

The page is static. On load it fetches `_index.json`, starts a DuckDB WASM
worker from a CDN bundle, registers each Parquet file by URL, and from then on
every query runs locally against those files. DuckDB issues HTTP range requests,
so a filtered query reads a few kilobytes out of a 737 KB file rather than
downloading it.

**Freshness is handled by treating `_index.json` as the version marker.** It is
about a kilobyte, it already exists, and it changes on every publish. It is
fetched with `no-store`, and each Parquet is then requested as
`?v=<published_at>`. A new publish is therefore a new cache key, while an
unchanged one is served straight from browser cache. The page prints the
publish time, so staleness is visible rather than silent.

**The marts ship beside the page.** `.github/workflows/pages.yml` runs
`xbrl-fetch-marts` into the site directory and uploads both together, so the
page and the data it reads can never drift apart, and the browser needs no CORS
rules on the bucket because they share an origin. The workflow then asserts
that the live `_index.json` matches the bucket, which is what caught the site
being unreachable the first time it deployed.

## Decisions worth knowing

**Range requests were measured, not assumed.** The claim that a filtered query
costs kilobytes rather than the whole file depends on the host honouring HTTP
range requests and on the Parquet row groups being laid out usefully. Both were
checked against the real deployment rather than taken from documentation.

**A Pages site is public even when the repository is private.** Publishing this
exposes the data, which is intended, but it is a deliberate decision rather than
a side effect of turning Pages on. The workflow is guarded by a repository
variable, `PAGES_ENABLED`, so enabling it is a variable flip rather than a code
change, and leaving it off is the default.

## Run it yourself

```bash
MARTS_PATH=docs/site uv run xbrl-fetch-marts
```

```bash
cd docs/site && python3 -m http.server 8000
```

Then open `http://localhost:8000`. It needs no credentials, because the marts
are public.

## Verify

The page prints its own publish time. It should match the API's:

```bash
curl -s https://sushantpatil2899.github.io/xbrl-reconcile/_index.json | head -2
```

## Deeper

Section 15.12 of [design.md](design.md) is the page as built, 15.13 the range
request measurements, and 15.14 the traps found while building it.
