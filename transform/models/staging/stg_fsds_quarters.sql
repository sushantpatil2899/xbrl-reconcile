{#
  What the ingestion job knows about each landed Data Set quarter.

  This exists so the warehouse can tell a quarter it has already read from one that
  has been re-landed. Data Set files land at a stable path, `fsds/2013q3/num.tsv.gz`,
  and Phase 4's self healing overwrites a quarter when a company is added whose
  history it should cover. So a path alone cannot say whether a quarter is new, and
  excluding by path would silently serve stale rows for the newly added company.

  The ingestion job already records the answer. `landed_at` is the version marker the
  incremental staging models compare against, and the CIK list is the record of which
  companies a quarter was filtered for, which is what makes the re-landing decision
  in the first place.

  Worth noting plainly: section 7.4 of the design says raw snapshots are written once
  and never overwritten. The Data Set layer does not follow that, and neither does
  arcs.json. Versioning those paths would mean re-landing 69 quarters, which is 40 GB
  pulled from SEC, so the state file is the authority instead.
#}

select
    entry.key as quarter,
    try_strptime(json_extract_string(entry.value, '$.landed_at'), '%Y-%m-%dT%H%M%SZ') as landed_at,
    (entry.value -> '$.ciks')::bigint[] as ciks,
    json_extract_string(entry.value, '$.filings')::bigint as filings,
    json_extract_string(entry.value, '$.facts')::bigint as facts
from (
    select unnest(map_entries(content::json::map(varchar, json))) as entry
    from read_text('{{ var("raw_root") }}/fsds/_state/quarters.json')
)
