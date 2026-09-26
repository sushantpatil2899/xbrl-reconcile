{#
  Concepts computed from other concepts, for companies that never report them.

  Intuit and Workday never tag gross profit. Intuit reports CostsAndExpenses
  instead of OperatingExpenses. Autodesk reports only
  LiabilitiesAndStockholdersEquity, never total liabilities. All are computable
  from accounting identities that hold for every filer in every year.

  Rules, in order of importance:

  1. A reported value is never replaced. A concept is derived only where the
     company reported nothing for it in any filing for that period.
  2. Every input comes from the same filing, so the result is a number that
     filing could have contained. That is why this model sits before
     int_facts_resolved rather than after it.
  3. Inputs must share a basis and a period kind, so US GAAP revenue is never
     mixed with IFRS cost of sales.
  4. If any input is missing, no row is produced and the gap stays visible in
     the coverage report.

  The formulas live here rather than in config because they are universal
  identities, not judgements about companies. Which companies need them is
  discovered from the data, not configured.
#}

{{ config(materialized='table') }}

{% set derivations = [
    {
        "concept": "gross_profit",
        "statement": "income_statement",
        "expression": "revenue-cost_of_revenue",
        "terms": [("revenue", "+"), ("cost_of_revenue", "-")],
    },
    {
        "concept": "operating_expenses",
        "statement": "income_statement",
        "expression": "revenue-cost_of_revenue-operating_income",
        "terms": [("revenue", "+"), ("cost_of_revenue", "-"), ("operating_income", "-")],
    },
    {
        "concept": "total_liabilities",
        "statement": "balance_sheet",
        "expression": "total_assets-total_equity",
        "terms": [("total_assets", "+"), ("total_equity", "-")],
    },
] %}

with mapped as (

    select *
    from {{ ref('int_facts_mapped') }}
    where period_kind != 'other'

),

candidates as (

{% for derivation in derivations %}
    select
        cik,
        ticker,
        '{{ derivation.concept }}' as concept,
        '{{ derivation.statement }}' as statement,
        period_start,
        period_end,
        period_kind,
        'USD' as unit,
        sum(
            case concept
            {%- for term, sign in derivation.terms %}
                when '{{ term }}' then {{ sign }} value
            {%- endfor %}
            end
        ) as value,
        'derived:{{ derivation.expression }}' as source_tag,
        basis,
        accession,
        form,
        filed_date,
        -- The weakest input decides how good the ingredients were.
        max(
            case confidence
                when 'high' then 1
                when 'medium' then 2
                else 3
            end
        ) as inputs_confidence_rank
    from mapped
    where concept in (
        {%- for term, sign in derivation.terms %}
        '{{ term }}'{{ "," if not loop.last }}
        {%- endfor %}
    )
    group by cik, ticker, period_start, period_end, period_kind, basis, accession, form, filed_date
    -- Every input must be present, or the concept is left unmapped.
    having count(distinct concept) = {{ derivation.terms | length }}
{{ "union all" if not loop.last }}
{% endfor %}

),

{#- A reported value always wins, so drop any period the company reported
    itself, in any filing. -#}
not_reported as (

    select candidates.*
    from candidates
    where not exists (
        select 1
        from mapped reported
        where reported.cik = candidates.cik
            and reported.concept = candidates.concept
            and reported.period_start is not distinct from candidates.period_start
            and reported.period_end = candidates.period_end
    )

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
    source_tag,
    basis,
    accession,
    form,
    filed_date,
    'derived' as confidence,
    case inputs_confidence_rank
        when 1 then 'high'
        when 2 then 'medium'
        else 'low'
    end as inputs_confidence
from not_reported
