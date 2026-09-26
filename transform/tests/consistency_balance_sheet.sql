{#
  Total assets should equal total liabilities plus temporary equity plus total
  equity. This identity is true by construction in accounting, so a failure means
  a mapping is wrong: equity mapped to the wrong variant, or
  LiabilitiesAndStockholdersEquity (which equals total assets) mistaken for total
  liabilities.

  Temporary equity is redeemable convertible preferred stock, reported between
  liabilities and equity. Most companies have none, so it is treated as zero when
  absent rather than excluding the period.
#}

{{ config(severity='warn') }}

with balances as (

    select
        ticker,
        period_end,
        basis,
        max(case when concept = 'total_assets' then value end) as total_assets,
        max(case when concept = 'total_liabilities' and confidence != 'derived' then value end)
            as total_liabilities,
        max(case when concept = 'total_equity' then value end) as total_equity,
        coalesce(max(case when concept = 'temporary_equity' then value end), 0)
            as temporary_equity
    from {{ ref('int_facts') }}
    where period_kind = 'instant'
    group by all

)

select
    ticker,
    period_end,
    basis,
    total_assets,
    total_liabilities,
    temporary_equity,
    total_equity,
    total_liabilities + temporary_equity + total_equity as expected_total_assets,
    round(
        100.0 * (total_assets - total_liabilities - temporary_equity - total_equity)
        / abs(total_assets), 2
    ) as pct_out
from balances
where total_assets is not null
    and total_liabilities is not null
    and total_equity is not null
    and abs(total_assets - total_liabilities - temporary_equity - total_equity)
        > {{ var('consistency_tolerance') }} * abs(total_assets)
