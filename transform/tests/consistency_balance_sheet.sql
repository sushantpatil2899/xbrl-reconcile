{#
  Total assets should equal total liabilities plus temporary equity plus total
  equity. The identity is true by construction in accounting, so a failure means
  a mapping is wrong: equity mapped to the wrong variant, or
  LiabilitiesAndStockholdersEquity (which equals total assets) mistaken for total
  liabilities.

  The identity is checked on the statement as a single filing reported it, not on
  the latest figure filed for each line. Reading each line at its latest revision
  breaks 22 otherwise sound balance sheets, because a company can restate one line
  of an old statement and never re-publish the others. That is a property of how
  filers report, not a defect in a mapping, and it is published as data on the
  mart instead of warned about here.

  Temporary equity is redeemable convertible preferred stock, reported between
  liabilities and equity. Most companies have none, so it is treated as zero when
  absent rather than excluding the period.
#}

{{ config(severity='warn') }}

with chosen as (

    select *
    from {{ ref('int_statement_filings') }}
    where statement = 'balance_sheet'

),

{#- The statement as that one filing published it. -#}
as_filed as (

    select
        chosen.ticker,
        chosen.period_end,
        mapped.basis,
        mapped.concept,
        mapped.value
    from chosen
    join {{ ref('int_facts_mapped') }} as mapped
        on mapped.cik = chosen.cik
        and mapped.accession = chosen.statement_accession
        and mapped.period_start is not distinct from chosen.period_start
        and mapped.period_end = chosen.period_end
        and mapped.statement = 'balance_sheet'

),

balances as (

    select
        ticker,
        period_end,
        basis,
        max(case when concept = 'total_assets' then value end) as total_assets,
        max(case when concept = 'total_liabilities' then value end) as total_liabilities,
        max(case when concept = 'total_equity' then value end) as total_equity,
        coalesce(max(case when concept = 'temporary_equity' then value end), 0)
            as temporary_equity
    from as_filed
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
