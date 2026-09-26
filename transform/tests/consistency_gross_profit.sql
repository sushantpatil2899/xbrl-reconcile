{#
  revenue minus cost of revenue should be gross profit.

  This is an indirect check on mapping correctness: there is no answer key for
  "what was Adobe's 2019 revenue", but a component tag mapped as a total breaks
  this identity immediately.

  Only periods where all three are reported are checked, so a gap never fails.
  Derived rows are excluded because int_facts_derived computes them from these
  same values, which would make the check circular.
#}

{{ config(severity='warn') }}

with statements as (

    select
        ticker,
        period_start,
        period_end,
        period_kind,
        basis,
        max(case when concept = 'revenue' then value end) as revenue,
        max(case when concept = 'cost_of_revenue' then value end) as cost_of_revenue,
        max(case when concept = 'gross_profit' and confidence != 'derived' then value end)
            as gross_profit
    from {{ ref('int_facts') }}
    group by all

)

select
    ticker,
    period_end,
    period_kind,
    basis,
    revenue,
    cost_of_revenue,
    gross_profit,
    revenue - cost_of_revenue as expected_gross_profit,
    round(100.0 * (revenue - cost_of_revenue - gross_profit) / abs(gross_profit), 2) as pct_out
from statements
where revenue is not null
    and cost_of_revenue is not null
    and gross_profit is not null
    and abs(revenue - cost_of_revenue - gross_profit)
        > {{ var('consistency_tolerance') }} * abs(gross_profit)
