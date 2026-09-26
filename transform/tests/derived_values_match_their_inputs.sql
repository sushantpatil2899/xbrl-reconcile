-- A derived value must equal the identity applied to the published inputs. If it
-- does not, the statement it appears in will not add up for a reader.
with published as (
    select
        ticker,
        period_start,
        period_end,
        period_kind,
        max(case when concept = 'revenue' then value end) as revenue,
        max(case when concept = 'cost_of_revenue' then value end) as cost_of_revenue,
        max(case when concept = 'operating_income' then value end) as operating_income,
        max(case when concept = 'total_assets' then value end) as total_assets,
        max(case when concept = 'total_equity' then value end) as total_equity,
        max(case when concept = 'gross_profit' and confidence = 'derived' then value end)
            as derived_gross_profit,
        max(case when concept = 'operating_expenses' and confidence = 'derived' then value end)
            as derived_operating_expenses,
        max(case when concept = 'total_liabilities' and confidence = 'derived' then value end)
            as derived_total_liabilities
    from {{ ref('int_facts') }}
    group by all
)

select *
from published
where (
    derived_gross_profit is not null
    and abs(revenue - cost_of_revenue - derived_gross_profit)
        > {{ var('candidate_tolerance') }} * abs(derived_gross_profit)
) or (
    derived_operating_expenses is not null
    and abs(revenue - cost_of_revenue - operating_income - derived_operating_expenses)
        > {{ var('candidate_tolerance') }} * abs(derived_operating_expenses)
) or (
    derived_total_liabilities is not null
    and abs(total_assets - total_equity - derived_total_liabilities)
        > {{ var('candidate_tolerance') }} * abs(derived_total_liabilities)
)
