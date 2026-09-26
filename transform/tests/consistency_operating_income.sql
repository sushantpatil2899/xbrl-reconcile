{#
  gross profit minus operating expenses should be operating income. Catches an
  operating expense subtotal mapped as the total, which would overstate profit.
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
        max(case when concept = 'operating_expenses' then value end) as operating_expenses,
        max(case when concept = 'operating_income' then value end) as operating_income
    from {{ ref('int_facts') }}
    where confidence != 'derived'
    group by all

)

select
    ticker,
    period_end,
    period_kind,
    basis,
    gross_profit,
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
