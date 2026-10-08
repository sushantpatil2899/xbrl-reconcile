{#
  What the ingestion job knows about each report's calculation linkbase.

  The same purpose as stg_fsds_quarters, for the same reason: arcs.json lands at a
  stable path per accession and is rewritten when the parser's output shape changes.
  That happened once already, when every one of the 259 filings was re-parsed from
  the stored XML to add the schema each concept is declared in.

  So the version marker is the later of fetched_at and reparsed_at, and the staging
  model compares against it rather than trusting that a path it has seen before still
  holds the same content.

  Filings with no calculation linkbase, and the one filing EDGAR does not serve, are
  kept here as rows with no arcs. They are facts about the source rather than gaps.
#}

select
    entry.key as accession,
    json_extract_string(entry.value, '$.ticker') as ticker,
    json_extract_string(entry.value, '$.form') as form,
    json_extract_string(entry.value, '$.linkbase') as linkbase_file,
    json_extract_string(entry.value, '$.arcs')::bigint as arcs,
    coalesce(json_extract_string(entry.value, '$.arcs_format')::bigint, 1) as arcs_format,
    coalesce(json_extract_string(entry.value, '$.unavailable')::boolean, false) as is_unavailable,
    -- Rewritten in place by a re-parse, so the later of the two timestamps is what
    -- says whether the stored arcs are the ones a staging model already read.
    greatest(
        try_strptime(json_extract_string(entry.value, '$.fetched_at'), '%Y-%m-%dT%H%M%SZ'),
        try_strptime(
            coalesce(
                json_extract_string(entry.value, '$.reparsed_at'),
                json_extract_string(entry.value, '$.fetched_at')
            ),
            '%Y-%m-%dT%H%M%SZ'
        )
    ) as parsed_at
from (
    select unnest(map_entries(content::json::map(varchar, json))) as entry
    from read_text('{{ var("raw_root") }}/linkbase/_state/filings.json')
)
