{#
  Tags a company reports that match no mapping rule, most used first. This is
  the raw material for writing new config: the coverage report says a concept is
  missing, and this says what the company reports instead.

  peers_using is the signal worth reading. A tag used by many companies and
  mapped by none is probably a concept worth adding; a tag used by one company is
  probably specific to it.
#}

{{ config(materialized='table') }}

with mapped_tags as (

    select taxonomy, tag from {{ ref('stg_tag_mappings') }}
    union
    select taxonomy, tag from {{ ref('stg_tag_components') }}
    union
    select taxonomy, tag from {{ ref('stg_tag_overrides') }}

),

facts as (

    select
        cik,
        ticker,
        taxonomy,
        concept as tag,
        period_kind_flag.period_kind,
        period_end
    from (
        select
            cik,
            ticker,
            taxonomy,
            concept,
            period_end,
            case
                when period_type = 'instant' then 'instant'
                when period_days between 350 and 380 then 'annual'
                else 'other'
            end as period_kind
        from {{ ref('stg_sec_facts') }}
        where is_valid
            -- Only the two taxonomies that carry financial statements.
            and taxonomy in ('us-gaap', 'ifrs-full')
    ) period_kind_flag

),

unmapped as (

    select facts.*
    from facts
    where not exists (
        select 1
        from mapped_tags
        where mapped_tags.taxonomy = facts.taxonomy
            and mapped_tags.tag = facts.tag
    )

),

peer_counts as (

    select taxonomy, tag, count(distinct cik) as peers_using
    from unmapped
    group by all

)

select
    unmapped.cik,
    unmapped.ticker,
    unmapped.taxonomy,
    unmapped.tag,
    count(*) as facts,
    count(distinct unmapped.period_end) filter (where unmapped.period_kind = 'annual')
        as annual_periods,
    count(distinct unmapped.period_end) filter (where unmapped.period_kind = 'instant')
        as instant_periods,
    max(peer_counts.peers_using) as peers_using
from unmapped
join peer_counts
    on peer_counts.taxonomy = unmapped.taxonomy
    and peer_counts.tag = unmapped.tag
group by all
