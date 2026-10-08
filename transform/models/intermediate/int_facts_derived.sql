{#
  Concepts computed from other concepts, for companies that never report them.

  Intuit and Workday never tag gross profit. Autodesk reports only
  LiabilitiesAndStockholdersEquity, never total liabilities. All are computable
  from accounting identities that hold for every filer in every year.

  This model reads resolved values rather than per filing ones. A derived value
  is never reported by anyone, so taking all inputs from a single filing buys no
  provenance, while a statement that fails to add up is immediately visible. So
  gross profit here always equals the published revenue minus the published cost
  of revenue.

  Rules, in order of importance:

  1. A reported value is never replaced. A concept is derived only where the
     company reported nothing for it in that period.
  2. Inputs must share a basis and a period kind, so US GAAP revenue is never
     mixed with IFRS cost of sales.
  3. If any input is missing, no row is produced and the gap stays visible in
     the coverage report.
  4. Restatement metadata comes from the inputs: a derived value was restated if
     any input was, and its original is the same formula over the inputs'
     original values.

  The formulas live here rather than in config because they are universal
  identities, not judgements about companies. Which companies need them is
  discovered from the data, not configured.

  `optional_terms` are summed when present and never gate the derivation. Temporary
  equity is the only one: it belongs in the balance sheet identity, but most
  companies have none, so requiring it would stop total liabilities being derived
  for everyone. Leaving it out entirely was the older behaviour and disagreed with
  the same identity as written in consistency_balance_sheet and the confidence
  report, which would have overstated liabilities for any company reporting both.
  All three now read one definition, in macros/accounting_identities.sql.

  Operating income appears as both an input and an output below, because the same
  identity is useful in two directions. Operating expenses are derived from it where
  a filer reports no expense total, and it is derived from operating expenses where a
  filer reports no operating income. HubSpot's 2012 is the second case: its gross
  profit of 34.766 and operating expenses of 53.506 were both reported and the line
  between them was empty. Nothing can be derived from itself, because a derived value
  is only produced where the concept was not reported.
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
        "concept": "operating_income",
        "statement": "income_statement",
        "expression": "gross_profit-operating_expenses",
        "terms": [("gross_profit", "+"), ("operating_expenses", "-")],
    },
    {
        "concept": "total_liabilities",
        "statement": "balance_sheet",
        "expression": "total_assets-total_equity-temporary_equity",
        "terms": [("total_assets", "+"), ("total_equity", "-")],
        "optional_terms": [("temporary_equity", "-")],
    },
] %}

with resolved as (

    select *
    from {{ ref('int_facts_resolved') }}
    where period_kind != 'other'

),

candidates as (

{% for derivation in derivations %}
{% set all_terms = derivation.terms + derivation.get("optional_terms", []) %}
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
            {%- for term, sign in all_terms %}
                when '{{ term }}' then {{ sign }} value
            {%- endfor %}
            end
        ) as value,
        sum(
            case concept
            {%- for term, sign in all_terms %}
                when '{{ term }}' then {{ sign }} originally_reported_value
            {%- endfor %}
            end
        ) as originally_reported_value,
        'derived:{{ derivation.expression }}' as source_tag,
        basis,
        -- The inputs may come from different filings, so the metadata spans them.
        max(accession) as accession,
        max(form) as form,
        max(filed_date) as filed_date,
        min(first_filed_date) as first_filed_date,
        max(last_filed_date) as last_filed_date,
        max(filing_count) as filing_count,
        max(restatement_count) as restatement_count,
        bool_or(was_restated) as was_restated,
        -- The weakest input decides how good the ingredients were.
        max(
            case confidence
                when 'high' then 1
                when 'medium' then 2
                else 3
            end
        ) as inputs_confidence_rank
    from resolved
    where concept in (
        {%- for term, sign in all_terms %}
        '{{ term }}'{{ "," if not loop.last }}
        {%- endfor %}
    )
    group by cik, ticker, period_start, period_end, period_kind, basis
    -- Every required input must be present, or the concept is left unmapped. An
    -- optional one is counted when it is there and does not gate the derivation.
    having count(distinct concept) filter (
        where concept in (
            {%- for term, sign in derivation.terms %}
            '{{ term }}'{{ "," if not loop.last }}
            {%- endfor %}
        )
    ) = {{ derivation.terms | length }}
{{ "union all" if not loop.last }}
{% endfor %}

),

{#- A reported value always wins. -#}
not_reported as (

    select candidates.*
    from candidates
    where not exists (
        select 1
        from resolved reported
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
from not_reported
