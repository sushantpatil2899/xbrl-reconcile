{#
  One row per company, concept and period, with the disagreement between
  filings resolved.

  `value` is the latest filed figure, which is today's best understanding.
  `originally_reported_value` is what the company said first, so a rewrite of
  history stays visible instead of being silently replaced.

  Two rules that are easy to get wrong:

  1. US GAAP wins over IFRS deliberately, not by filing date. Atlassian reports
     2021 under both, and the 10-K happens to be filed later than the 20-F, so
     recency alone would give the right answer by accident and the wrong one the
     moment the order flipped.
  2. Restatements are measured within one basis. Comparing an IFRS figure with a
     US GAAP one would label a rulebook change as a restatement, which it is not.
#}

{{ config(materialized='table') }}

with mapped as (

    select *
    from {{ ref('int_facts_mapped') }}

),

{#- The basis that represents each period: us_gaap where it exists at all. -#}
chosen_basis as (

    select
        cik,
        concept,
        period_start,
        period_end,
        min(case when basis = 'us_gaap' then 0 else 1 end) as basis_rank
    from mapped
    group by all

),

within_basis as (

    select mapped.*
    from mapped
    join chosen_basis
        on mapped.cik = chosen_basis.cik
        and mapped.concept = chosen_basis.concept
        -- Balance sheet facts are instants with no period_start. A plain
        -- equality never matches null, so these rows would all be dropped.
        and mapped.period_start is not distinct from chosen_basis.period_start
        and mapped.period_end = chosen_basis.period_end
    where case when mapped.basis = 'us_gaap' then 0 else 1 end = chosen_basis.basis_rank

),

ordered as (

    select
        *,
        row_number() over (
            partition by cik, concept, period_start, period_end
            order by filed_date desc, accession desc
        ) as recency_rank,
        first_value(value) over (
            partition by cik, concept, period_start, period_end
            order by filed_date, accession
        ) as first_reported_value,
        min(filed_date) over (
            partition by cik, concept, period_start, period_end
        ) as first_filed_date,
        max(filed_date) over (
            partition by cik, concept, period_start, period_end
        ) as last_filed_date,
        count(*) over (
            partition by cik, concept, period_start, period_end
        ) as filing_count,
        count(distinct value) over (
            partition by cik, concept, period_start, period_end
        ) as distinct_value_count,
        min(value) over (
            partition by cik, concept, period_start, period_end
        ) as min_value,
        max(value) over (
            partition by cik, concept, period_start, period_end
        ) as max_value
    from within_basis

)

select
    cik,
    ticker,
    concept,
    statement,
    period_start,
    period_end,
    period_kind,
    unit,
    value,
    first_reported_value as originally_reported_value,
    source_tag,
    confidence,
    basis,
    accession,
    form,
    filed_date,
    first_filed_date,
    last_filed_date,
    filing_count,
    distinct_value_count as restatement_count,
    -- Values a fraction apart are the same figure reported again (rounding to
    -- thousands, a cent of EPS). Only a real difference is a restatement.
    (max_value - min_value) > {{ var('restatement_tolerance') }}
        * greatest(abs(min_value), abs(max_value)) as was_restated,
    candidate_count,
    candidates_disagree
from ordered
where recency_rank = 1
