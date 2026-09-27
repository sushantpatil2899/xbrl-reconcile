{#
  The fourth quarter, which no company files.

  A company files three 10-Qs and then a 10-K. The 10-Qs cover three months, six
  months and nine months, each counted from the start of the fiscal year. The
  10-K covers the whole year. No report ever covers the final three months alone,
  so the fourth quarter is a hole by construction rather than by omission.

  Subtraction closes it: the full year minus the nine months is the last quarter.
  This works because both figures are cumulative from the same fiscal year start,
  which is also why the two are matched on an identical period_start rather than
  on a year label. Cash flow statements are cumulative in the same way, so the
  same arithmetic holds for them.

  Three rules keep it honest:

  1. Only additive concepts. Earnings per share is a ratio and a weighted average
     share count is an average, so subtracting one period from another produces a
     number that means nothing. Which concepts those are is declared in
     config/tag_mappings.yml, because nothing in the facts reveals it.
  2. A reported quarter is never shadowed. Some filers do tag the final three
     months, and where a quarter already exists for that period end, no row is
     produced here.
  3. Balance sheet concepts are untouched. They are instants, and the fourth
     quarter balance sheet is the year end one, which is already reported.

  Every row is marked `derived`, and carries the weakest confidence among its two
  inputs, so a computed quarter can never be mistaken for a filed one.
#}

{{ config(materialized='table') }}

with facts as (

    select
        facts.*,
        mappings.is_additive
    from {{ ref('int_facts') }} as facts
    join (
        select distinct concept, is_additive
        from {{ ref('stg_tag_mappings') }}
    ) as mappings on mappings.concept = facts.concept
    where mappings.is_additive

),

{#- Both periods run from the same fiscal year start, so period_start is the
    join key. A year label is not used: it would be the same for the two halves
    of a fiscal calendar change. -#}
pairs as (

    select
        annual.cik,
        annual.ticker,
        annual.concept,
        annual.statement,
        nine_month.period_end + interval 1 day as period_start,
        annual.period_end,
        annual.unit,
        annual.basis,
        annual.value - nine_month.value as value,
        annual.originally_reported_value
            - nine_month.originally_reported_value as originally_reported_value,
        -- The two inputs come from different filings, so the metadata spans both.
        greatest(annual.accession, nine_month.accession) as accession,
        greatest(annual.form, nine_month.form) as form,
        greatest(annual.filed_date, nine_month.filed_date) as filed_date,
        least(annual.first_filed_date, nine_month.first_filed_date) as first_filed_date,
        greatest(annual.last_filed_date, nine_month.last_filed_date) as last_filed_date,
        greatest(annual.filing_count, nine_month.filing_count) as filing_count,
        greatest(annual.restatement_count, nine_month.restatement_count) as restatement_count,
        annual.was_restated or nine_month.was_restated as was_restated,
        -- The weaker of the two inputs decides how good the ingredients were. An
        -- input that was itself derived contributes its own inputs' confidence.
        greatest(
            {{ confidence_rank('annual') }},
            {{ confidence_rank('nine_month') }}
        ) as inputs_confidence_rank
    from facts as annual
    join facts as nine_month
        on nine_month.cik = annual.cik
        and nine_month.concept = annual.concept
        and nine_month.period_start = annual.period_start
        and nine_month.basis = annual.basis
        and nine_month.unit = annual.unit
        and nine_month.period_kind = 'nine_month'
    where annual.period_kind = 'annual'

),

{#- A quarter someone filed for this period end wins, whether it was reported or
    derived from an identity. -#}
not_already_present as (

    select pairs.*
    from pairs
    where not exists (
        select 1
        from {{ ref('int_facts') }} as existing
        where existing.cik = pairs.cik
            and existing.concept = pairs.concept
            and existing.period_end = pairs.period_end
            and existing.period_kind = 'quarter'
    )

)

select
    cik,
    ticker,
    concept,
    statement,
    period_start::date as period_start,
    period_end,
    'quarter' as period_kind,
    unit,
    value,
    originally_reported_value,
    'derived:annual-nine_month' as source_tag,
    'derived' as confidence,
    case inputs_confidence_rank
        when 1 then 'high'
        when 2 then 'medium'
        else 'low'
    end as inputs_confidence,
    basis,
    accession,
    form,
    filed_date,
    first_filed_date,
    last_filed_date,
    filing_count,
    restatement_count,
    was_restated
from not_already_present
