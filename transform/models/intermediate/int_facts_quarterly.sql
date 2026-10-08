{#
  Quarters nobody filed, recovered by subtracting one cumulative period from another.

  A company files three 10-Qs and then a 10-K. The 10-Qs cover three months, six
  months and nine months, each counted from the start of the fiscal year. The
  10-K covers the whole year. No report ever covers the final three months alone,
  so the fourth quarter is a hole by construction rather than by omission.

  Subtraction closes it, and the same arithmetic closes three holes rather than one:

      Q4 = the year        - the nine months
      Q3 = the nine months - the half
      Q2 = the half        - the first quarter

  Q4 is the hole every filer has. The other two matter for the cash flow statement,
  where a 10-Q reports only the year to date and never the discrete quarter: 2,097
  cash flow quarters exist against 1,335 that these two subtractions can recover.
  On the income statement filers do tag the discrete quarter, so there are 12.

  All three work because the figures are cumulative from the same fiscal year start,
  which is also why they are matched on an identical period_start rather than on a
  year label.

  Four rules keep it honest:

  1. Only additive concepts. Earnings per share is a ratio and a weighted average
     share count is an average, so subtracting one period from another produces a
     number that means nothing. Which concepts those are is declared in
     config/tag_mappings.yml, because nothing in the facts reveals it.
  2. A reported quarter is never shadowed. Some filers do tag the final three
     months, and where a quarter already exists for that period end, no row is
     produced here.
  3. Balance sheet concepts are untouched. They are instants, and the fourth
     quarter balance sheet is the year end one, which is already reported.

  4. Neither input may be a restated figure. A restatement changes what a period
     covers, so the longer and shorter figures stop describing the same business and
     the difference means nothing. Measured against the quarters filers did tag:

         pairing                  neither restated     either restated
         half less the quarter    99.2% land           80.1% land
         year less nine months    98.7% land           34.5% land

     The guard costs 300 fourth quarters that used to be published, and roughly two
     thirds of those were wrong, which is the same trade this project made when
     Workday's overstated operating expenses became gaps.

  Every row is marked `derived`, and carries the weakest confidence among its two
  inputs, so a computed quarter can never be mistaken for a filed one.

  What this cannot check: a recovered quarter has no filed counterpart, which is why
  it was recovered. The accuracy above is measured where both exist, and
  quarters_match_when_also_filed keeps measuring it. The sum to the year test cannot
  help, because Q1 + (half - Q1) + (nine_month - half) + (year - nine_month) collapses
  to the year by algebra whatever the inputs are.
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
{% set subtractions = [
    ("annual", "nine_month"),
    ("nine_month", "half"),
    ("half", "quarter"),
] %}

pairs as (

{% for longer_kind, shorter_kind in subtractions %}
    select
        longer.cik,
        longer.ticker,
        longer.concept,
        longer.statement,
        shorter.period_end + interval 1 day as period_start,
        longer.period_end,
        longer.unit,
        longer.basis,
        longer.value - shorter.value as value,
        longer.originally_reported_value
            - shorter.originally_reported_value as originally_reported_value,
        'derived:{{ longer_kind }}-{{ shorter_kind }}' as source_tag,
        -- The two inputs come from different filings, so the metadata spans both.
        greatest(longer.accession, shorter.accession) as accession,
        greatest(longer.form, shorter.form) as form,
        greatest(longer.filed_date, shorter.filed_date) as filed_date,
        least(longer.first_filed_date, shorter.first_filed_date) as first_filed_date,
        greatest(longer.last_filed_date, shorter.last_filed_date) as last_filed_date,
        greatest(longer.filing_count, shorter.filing_count) as filing_count,
        greatest(longer.restatement_count, shorter.restatement_count) as restatement_count,
        longer.was_restated or shorter.was_restated as was_restated,
        -- The weaker of the two inputs decides how good the ingredients were. An
        -- input that was itself derived contributes its own inputs' confidence.
        greatest(
            {{ confidence_rank('longer') }},
            {{ confidence_rank('shorter') }}
        ) as inputs_confidence_rank
    from facts as longer
    join facts as shorter
        on shorter.cik = longer.cik
        and shorter.concept = longer.concept
        and shorter.period_start = longer.period_start
        and shorter.basis = longer.basis
        and shorter.unit = longer.unit
        and shorter.period_kind = '{{ shorter_kind }}'
    where longer.period_kind = '{{ longer_kind }}'
        -- A restatement changes what a period covers, so the two figures stop
        -- describing the same business and the difference means nothing.
        and not coalesce(longer.was_restated, false)
        and not coalesce(shorter.was_restated, false)
{{ "union all" if not loop.last }}
{% endfor %}

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
    source_tag,
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
