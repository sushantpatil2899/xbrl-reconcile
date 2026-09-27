{#
  How much to trust each statement, rather than what each number is.

  One row per statement in mart_income_statement, mart_balance_sheet and
  mart_cash_flow, at the same grain, so it joins to them one to one. Half of the
  income statements in this warehouse contain at least one value that is not a
  standard tag the company filed. Without this model that fact is invisible unless
  someone inspects the confidence column of every line.

  Completeness is measured against the lines that always apply, not against every
  mapped concept. Temporary equity is redeemable preferred stock and most companies
  have none, so counting it as a missing line would call 945 sound balance sheets
  incomplete. `is_optional` in the mapping config is what makes that distinction,
  and the coverage mart already reads it the same way.

  The two identities below are also checked by the consistency tests, on purpose
  rather than by oversight: the tests check them on the figures one filing
  published together, and this checks them on the latest figure for each line. Same
  arithmetic, different inputs, different questions. Where a company restated one
  line of an old statement and not the rest, the identity here cannot close, which
  is why `incoherent_lines` sits next to `identity_gap`: together they separate a
  wrong mapping from lines that simply come from different filings.

  The formulas stay in SQL rather than config because they are universal accounting
  identities, not judgements about companies, which is the reasoning
  int_facts_derived already records for the same decision.
#}

{{ config(materialized='table') }}

with concepts as (

    select distinct concept, is_optional
    from {{ ref('stg_tag_mappings') }}

),

{#- What a complete statement looks like: the concepts every filer should have. -#}
expected_lines as (

    select
        statement,
        count(distinct concept) as lines_expected
    from {{ ref('stg_tag_mappings') }}
    where not is_optional
    group by all

),

facts as (

    select
        facts.*,
        concepts.is_optional
    from {{ ref('mart_financials') }} as facts
    join concepts on concepts.concept = facts.concept

),

counted as (

    select
        cik,
        ticker,
        company_name,
        statement,
        period_start,
        period_end,
        period_kind,
        fiscal_year,
        fiscal_quarter,
        calendar_year_equivalent,
        -- Two Atlassian balance sheets carry lines under both rulebooks.
        string_agg(distinct basis, ' and ' order by basis) as basis,
        count(*) as lines_present,
        count(*) filter (where not is_optional) as required_lines_present,
        count(*) filter (where confidence = 'high') as high_lines,
        count(*) filter (where confidence = 'medium') as medium_lines,
        count(*) filter (where confidence = 'low') as low_lines,
        count(*) filter (where confidence = 'derived') as derived_lines,
        count(*) filter (where candidates_disagree) as ambiguous_lines,
        count(*) filter (where was_restated) as restated_lines,
        count(*) filter (where is_coherent = false) as incoherent_lines,
        max(statement_accession) as statement_accession,
        max(statement_form) as statement_form,
        max(statement_filed_date) as statement_filed_date,
        bool_and(coalesce(statement_covers_whole, true)) as statement_covers_whole,
        max(case when concept = 'total_assets' then value end) as total_assets,
        max(case when concept = 'total_liabilities' then value end) as total_liabilities,
        max(case when concept = 'total_equity' then value end) as total_equity,
        max(case when concept = 'temporary_equity' then value end) as temporary_equity,
        max(case when concept = 'revenue' then value end) as revenue,
        max(case when concept = 'cost_of_revenue' then value end) as cost_of_revenue,
        max(case when concept = 'gross_profit' then value end) as gross_profit
    from facts
    group by all

),

checked as (

    select
        counted.*,
        -- A balance sheet balances; revenue less cost of revenue is gross profit.
        -- A cash flow statement has no such identity in these concepts, so it is
        -- not claimed to have one.
        case
            when statement = 'balance_sheet'
                and total_assets is not null
                and total_liabilities is not null
                and total_equity is not null
                then total_assets - total_liabilities
                    - coalesce(temporary_equity, 0) - total_equity
            when statement = 'income_statement'
                and revenue is not null
                and cost_of_revenue is not null
                and gross_profit is not null
                then revenue - cost_of_revenue - gross_profit
        end as identity_gap,
        case
            when statement = 'balance_sheet' then abs(total_assets)
            when statement = 'income_statement' then abs(revenue)
        end as identity_scale
    from counted

)

select
    checked.cik,
    checked.ticker,
    checked.company_name,
    checked.statement,
    checked.period_start,
    checked.period_end,
    checked.period_kind,
    checked.fiscal_year,
    checked.fiscal_quarter,
    checked.calendar_year_equivalent,
    checked.basis,
    checked.lines_present,
    expected_lines.lines_expected,
    checked.required_lines_present >= expected_lines.lines_expected as is_complete,
    checked.high_lines,
    checked.medium_lines,
    checked.low_lines,
    checked.derived_lines,
    checked.ambiguous_lines,
    checked.restated_lines,
    checked.incoherent_lines,
    checked.identity_gap,
    case
        when checked.identity_gap is null then null
        else abs(checked.identity_gap) <= {{ var('consistency_tolerance') }} * greatest(checked.identity_scale, 1)
    end as identity_holds,
    checked.statement_accession,
    checked.statement_form,
    checked.statement_filed_date,
    checked.statement_covers_whole,
    {#- One word, because eight counts are not a summary. The order is a judgement
        and is stated here rather than left for a reader to infer: a possible error
        outranks a known approximation, and a weaker tag is a judgement about what
        a tag means while a derived value is arithmetic over reported ones. -#}
    case
        when (checked.identity_gap is not null
              and abs(checked.identity_gap) > {{ var('consistency_tolerance') }} * greatest(checked.identity_scale, 1))
            or checked.ambiguous_lines > 0
            then 'check'
        when checked.medium_lines > 0 or checked.low_lines > 0 then 'mapped'
        when checked.derived_lines > 0 then 'computed'
        else 'reported'
    end as trust
from checked
join expected_lines on expected_lines.statement = checked.statement
