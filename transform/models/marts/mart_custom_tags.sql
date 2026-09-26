{#
  The custom tags each company has invented, with how much they are used.

  This is the evidence for the project's central claim: companies extend the
  standard taxonomy when they feel it does not fit. It is a mart rather than a
  mapping because reading it is how you decide whether a custom tag is worth
  mapping.

  peers_using_same_name is the column to read. A name several companies invented
  independently is a concept the standard taxonomy is missing, and a good
  candidate to map. A name only one company uses is specific to how that company
  describes itself.
#}

{{ config(materialized='table') }}

with custom_facts as (

    select
        cik,
        ticker,
        tag,
        qualified_tag,
        tag_label,
        period_end,
        value,
        accession
    from {{ ref('stg_fsds_facts') }}
    where is_custom

),

per_company as (

    select
        cik,
        ticker,
        tag,
        qualified_tag,
        max(tag_label) as tag_label,
        count(*) as facts,
        count(distinct accession) as filings,
        min(period_end) as first_period,
        max(period_end) as last_period
    from custom_facts
    group by all

),

{#- How many companies invented a tag of the same name. -#}
name_spread as (

    select tag, count(distinct cik) as peers_using_same_name
    from custom_facts
    group by all

),

mapped as (

    select distinct concept, taxonomy || ':' || tag as qualified_tag
    from {{ ref('stg_tag_mappings') }}

)

select
    per_company.cik,
    per_company.ticker,
    per_company.tag,
    per_company.qualified_tag,
    per_company.tag_label,
    per_company.facts,
    per_company.filings,
    per_company.first_period,
    per_company.last_period,
    name_spread.peers_using_same_name,
    mapped.concept is not null as is_mapped,
    mapped.concept as mapped_concept
from per_company
join name_spread on name_spread.tag = per_company.tag
left join mapped on mapped.qualified_tag = per_company.qualified_tag
