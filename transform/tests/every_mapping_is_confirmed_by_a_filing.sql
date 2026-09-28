{#
  Every tag the config maps should appear, in some filing, on the statement the
  config assigns it to. All 44 do today.

  A mapping for a tag no filer ever presents is not necessarily wrong, since the
  Data Sets only cover filings we have landed, but it is a claim with nothing behind
  it, and the moment to notice that is when the mapping is added rather than years
  later. Hence a warning rather than an error.
#}

{{ config(severity='warn') }}

with mappings as (

    select distinct
        taxonomy || ':' || tag as qualified_tag,
        concept,
        statement
    from {{ ref('stg_tag_mappings') }}

)

select
    mappings.concept,
    mappings.qualified_tag,
    mappings.statement
from mappings
where not exists (
    select 1
    from {{ ref('mart_mapping_evidence') }} as evidence
    where evidence.qualified_tag = mappings.qualified_tag
        and evidence.verdict = 'confirms_mapping'
)
