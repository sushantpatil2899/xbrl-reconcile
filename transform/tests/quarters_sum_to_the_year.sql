{#
  The four quarters of a fiscal year should add up to the year.

  Two restrictions make this a test of arithmetic rather than a list of things
  filers do:

  1. Additive concepts only. Earnings per share and a weighted average share count
     are a ratio and an average, so their quarters never sum to their year.
  2. Nothing restated, among any of the five values. Where a later filing revised
     the year and not its quarters, the sum cannot hold, and that is the same
     restatement mixture the balance sheet test hit. Salesforce revised its 2017
     operating income from 64.2 million to 218.0 million and never revised the
     four quarters, which still sum to 64.2 million. Both figures are what
     Salesforce filed; `was_restated` is how a reader sees it.

  What survives is a real disagreement inside one company's own reporting. Intuit
  is most of it: its quarterly cost of revenue for 2019 sums to 20 million more
  than the annual figure it published.
#}

{{ config(severity='warn') }}

with additive as (

    select distinct concept
    from {{ ref('stg_tag_mappings') }}
    where is_additive

),

quarters as (

    select
        facts.cik,
        facts.ticker,
        facts.concept,
        facts.fiscal_year_end,
        sum(facts.value) as four_quarters,
        count(*) as quarters,
        bool_or(facts.was_restated) as any_restated,
        count(*) filter (where facts.confidence = 'derived') as derived_quarters
    from {{ ref('mart_financials') }} as facts
    join additive on additive.concept = facts.concept
    where facts.period_kind = 'quarter'
    group by all

),

years as (

    select
        facts.cik,
        facts.concept,
        facts.fiscal_year_end,
        facts.fiscal_year,
        facts.value as annual,
        facts.was_restated as annual_restated
    from {{ ref('mart_financials') }} as facts
    join additive on additive.concept = facts.concept
    where facts.period_kind = 'annual'

)

select
    quarters.ticker,
    quarters.concept,
    years.fiscal_year,
    quarters.fiscal_year_end,
    quarters.derived_quarters,
    quarters.four_quarters,
    years.annual,
    quarters.four_quarters - years.annual as difference
from quarters
join years
    on years.cik = quarters.cik
    and years.concept = quarters.concept
    and years.fiscal_year_end = quarters.fiscal_year_end
where quarters.quarters = 4
    and not quarters.any_restated
    and not years.annual_restated
    and abs(quarters.four_quarters - years.annual)
        > {{ var('consistency_tolerance') }} * greatest(abs(years.annual), 1)
