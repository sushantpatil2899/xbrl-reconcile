{#
  The subtraction, checked against quarters filers did file.

  A recovered quarter has no filed counterpart, which is why it was recovered, so
  nothing downstream can verify it. The sum to the year test cannot help either:
  Q1 + (half - Q1) + (nine_month - half) + (year - nine_month) collapses to the year
  by algebra whatever the inputs are, so it would pass on nonsense.

  What can be checked is the method. Where a filer did tag the discrete quarter, the
  same subtraction has a known answer, and this measures how often it lands. At the
  time the quarterly derivation was added that was 99.2 percent within one percent,
  across 3,494 pairs, once restated inputs were excluded.

  A warning rather than an error. These are reported quarters, so nothing published
  is wrong; what the count says is how much to trust the recovered ones, and it is
  expected to sit in the tens rather than at zero.
#}

{{ config(severity='warn') }}

with additive as (

    select cik, ticker, concept, basis, unit, period_start, period_kind, period_end,
           value, was_restated
    from {{ ref('int_facts') }}
    where period_kind in ('quarter', 'half', 'nine_month')
        and period_start is not null
        and concept in (
            select distinct concept from {{ ref('stg_tag_mappings') }} where is_additive
        )

),

{#- The same pairing the derivation uses, and the same restatement guard. -#}
implied as (

    select
        longer.ticker,
        longer.concept,
        longer.period_end as quarter_end,
        longer.period_kind as from_kind,
        longer.value - shorter.value as implied_value
    from additive as longer
    join additive as shorter
        on shorter.cik = longer.cik
        and shorter.concept = longer.concept
        and shorter.period_start = longer.period_start
        and shorter.basis = longer.basis
        and shorter.unit = longer.unit
        and ((longer.period_kind = 'half' and shorter.period_kind = 'quarter')
          or (longer.period_kind = 'nine_month' and shorter.period_kind = 'half'))
    where not coalesce(longer.was_restated, false)
        and not coalesce(shorter.was_restated, false)

)

select
    implied.ticker,
    implied.concept,
    implied.quarter_end,
    implied.from_kind,
    implied.implied_value,
    filed.value as filed_value,
    round(
        100.0 * (implied.implied_value - filed.value) / nullif(abs(filed.value), 0), 2
    ) as pct_out
from implied
join {{ ref('int_facts') }} as filed
    on filed.ticker = implied.ticker
    and filed.concept = implied.concept
    and filed.period_kind = 'quarter'
    and filed.period_end = implied.quarter_end
    and filed.confidence != 'derived'
where abs(implied.implied_value - filed.value)
    > {{ var('consistency_tolerance') }} * greatest(abs(filed.value), 1)
