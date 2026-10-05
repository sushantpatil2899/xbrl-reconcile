{#
  Gross profit minus operating expenses should be operating income. Catches an
  operating expense tag that means something other than this concept.

  The first version required all three figures to be reported, and that blind spot
  hid the error it was written to find. Workday never tags gross profit, so its gross
  profit is always derived, so Workday was excluded from the test for all 13 of the
  years in which it overstated operating expenses by exactly its cost of revenue.

  What the test actually needs is that the two figures it is judging are the
  company's own, and that neither was computed from the other:

    operating_expenses must be reported, since it is what is under suspicion
    operating_income must be reported, or it may have been derived from the very
      subtraction being checked
    gross_profit may be derived, because deriving it from reported revenue and cost
      of revenue makes the comparison sharper rather than circular

  Excluding a derived operating expense is not squeamishness: it is derived as
  revenue less cost less operating income, which satisfies this identity by
  construction and would tell us nothing.
#}

{{ config(severity='warn') }}

with statements as (

    select
        ticker,
        period_start,
        period_end,
        period_kind,
        basis,
        max(case when concept = 'gross_profit' then value end) as gross_profit,
        max(case when concept = 'gross_profit' then confidence end) as gross_profit_confidence,
        max(case when concept = 'operating_expenses' then value end) as operating_expenses,
        max(case when concept = 'operating_income' then value end) as operating_income
    from {{ ref('int_facts') }}
    where concept = 'gross_profit' or confidence != 'derived'
    group by all

)

select
    ticker,
    period_end,
    period_kind,
    basis,
    gross_profit,
    gross_profit_confidence,
    operating_expenses,
    operating_income,
    gross_profit - operating_expenses as expected_operating_income,
    round(
        100.0 * (gross_profit - operating_expenses - operating_income) / abs(operating_income), 2
    ) as pct_out
from statements
where gross_profit is not null
    and operating_expenses is not null
    and operating_income is not null
    and abs(gross_profit - operating_expenses - operating_income)
        > {{ var('consistency_tolerance') }} * abs(operating_income)
