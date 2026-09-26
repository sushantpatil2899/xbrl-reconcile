{#
  What is mapped and what is not, one row per company, concept and fiscal year.

  This is a worklist rather than a test: it answers "what config should I write
  next?", which is the question when onboarding a company. A missing value
  produces no fact, so the grid is built from a spine and left joined.

  Two things this model has to get right:

  1. The spine uses each company's observed fiscal years, not a fixed range, so a
     company is never faulted for years before it was public.
  2. Balance sheet concepts are instants, not durations. An instant is matched to
     the fiscal year whose end date it falls on, because an instant dated three
     months after a January year end belongs to the following year.
#}

{{ config(materialized='table') }}

with facts as (

    select *
    from {{ ref('int_facts') }}

),

{#- Each company's fiscal years, taken from its annual periods, which is what
    defines a fiscal year end date. -#}
fiscal_years as (

    select
        cik,
        ticker,
        year(period_end) as fiscal_year,
        max(period_end) as fiscal_year_end
    from facts
    where period_kind = 'annual'
    group by all

),

concepts as (

    select distinct concept, statement, is_optional
    from {{ ref('stg_tag_mappings') }}

),

spine as (

    select
        fiscal_years.cik,
        fiscal_years.ticker,
        fiscal_years.fiscal_year,
        fiscal_years.fiscal_year_end,
        concepts.concept,
        concepts.statement,
        concepts.is_optional
    from fiscal_years
    cross join concepts

),

{#- Durations are matched by fiscal year; instants by landing on the year end. -#}
year_facts as (

    select
        facts.cik,
        facts.concept,
        fiscal_years.fiscal_year,
        facts.value,
        facts.confidence,
        facts.inputs_confidence,
        facts.source_tag,
        facts.basis,
        facts.period_end,
        facts.was_restated,
        facts.restatement_count,
        facts.candidates_disagree
    from facts
    join fiscal_years
        on fiscal_years.cik = facts.cik
        and case
            when facts.period_kind = 'instant' then facts.period_end = fiscal_years.fiscal_year_end
            when facts.period_kind = 'annual' then year(facts.period_end) = fiscal_years.fiscal_year
            else false
        end

),

{#- US rules require three years of income statements but only two balance
    sheets, so a company's earliest fiscal year has no balance sheet anywhere in
    the data. That gap can never be filled, so it is labelled rather than left in
    the worklist as if it were actionable. -#}
earliest_year as (

    select cik, min(fiscal_year) as first_fiscal_year
    from fiscal_years
    group by all

),

{#- A shifting year end can put two periods in one fiscal year; keep the later. -#}
one_per_year as (

    select *
    from year_facts
    qualify row_number() over (
        partition by cik, concept, fiscal_year
        order by period_end desc
    ) = 1

)

select
    spine.cik,
    spine.ticker,
    spine.fiscal_year,
    spine.fiscal_year_end,
    spine.concept,
    spine.statement,
    case
        when facts.value is null
            and spine.statement = 'balance_sheet'
            and spine.fiscal_year = earliest_year.first_fiscal_year
            then 'no_balance_sheet'
        -- An optional concept is one most filers legitimately have none of, so
        -- its absence is an answer rather than something to go and map.
        when facts.value is null and spine.is_optional then 'not_applicable'
        when facts.value is null then 'missing'
        when facts.confidence = 'derived' then 'derived'
        when facts.candidates_disagree then 'ambiguous'
        else 'reported'
    end as status,
    facts.value,
    facts.confidence,
    facts.inputs_confidence,
    facts.source_tag,
    facts.basis,
    facts.period_end,
    facts.was_restated,
    facts.restatement_count
from spine
join earliest_year on earliest_year.cik = spine.cik
left join one_per_year facts
    on facts.cik = spine.cik
    and facts.concept = spine.concept
    and facts.fiscal_year = spine.fiscal_year
