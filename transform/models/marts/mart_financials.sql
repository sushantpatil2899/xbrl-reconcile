{#
  The published financial facts: one row per company, concept and period.

  This is the mart everything else reads, and the first model in the project a
  person would query directly. It is long rather than wide because a column per
  concept cannot be written without naming the concepts in SQL, and the concepts
  live in config. Task 5 builds the wide statements from that config instead.

  Three numbers, answering three different questions:

    value                      the latest figure filed for this line
    originally_reported_value  what the company said the first time
    value_as_filed             what the chosen statement filing said, so a whole
                               statement adds up

  For Salesforce's equity at 31 January 2017 those are 8,230.0 million, 7,500.1
  million and 7,500.1 million. All three are true statements about the same line.

  The grain drops period_start from the key that int_facts uses. Adobe reports the
  same period twice with start dates one day apart, so at this grain those would
  be two rows for one quarter and anything summing quarters would double count.
  Where that happens the version more filings agree on wins, which picks the
  company's settled convention rather than a context typo in a single filing.
#}

{{ config(materialized='table') }}

with facts as (

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
        confidence,
        inputs_confidence,
        basis,
        accession,
        form,
        filed_date,
        first_filed_date,
        last_filed_date,
        filing_count,
        restatement_count,
        was_restated,
        candidates_disagree
    from {{ ref('int_facts') }}

    union all

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
        confidence,
        inputs_confidence,
        basis,
        accession,
        form,
        filed_date,
        first_filed_date,
        last_filed_date,
        filing_count,
        restatement_count,
        was_restated,
        false as candidates_disagree
    from {{ ref('int_facts_quarterly') }}

),

{#- One row per period, keeping the start date more filings reported. -#}
deduplicated as (

    select *
    from facts
    qualify row_number() over (
        partition by cik, concept, period_kind, period_end
        order by filing_count desc, last_filed_date desc, period_start
    ) = 1

),

{#- The chosen filing's own figure for this line. Matched on period kind rather
    than start date, because one filing can report a quarter and a half ending on
    the same day, and because the start date is the thing being deduplicated. -#}
as_filed as (

    select
        cik,
        accession,
        concept,
        period_kind,
        period_end,
        value as value_as_filed
    from {{ ref('int_facts_mapped') }}
    qualify row_number() over (
        partition by cik, accession, concept, period_kind, period_end
        order by period_start
    ) = 1

)

select
    deduplicated.cik,
    deduplicated.ticker,
    companies.company_name,
    deduplicated.statement,
    deduplicated.concept,
    deduplicated.unit,
    deduplicated.period_start,
    deduplicated.period_end,
    deduplicated.period_kind,
    periods.period_days,
    periods.fiscal_year,
    periods.fiscal_quarter,
    periods.calendar_year_equivalent,
    periods.fiscal_year_end,
    periods.is_year_end,
    periods.year_end_is_observed,
    deduplicated.value,
    deduplicated.originally_reported_value,
    as_filed.value_as_filed,
    deduplicated.confidence,
    deduplicated.inputs_confidence,
    deduplicated.candidates_disagree,
    deduplicated.basis,
    deduplicated.source_tag,
    deduplicated.accession,
    deduplicated.form,
    deduplicated.filed_date,
    deduplicated.first_filed_date,
    deduplicated.last_filed_date,
    deduplicated.filing_count,
    deduplicated.restatement_count,
    deduplicated.was_restated,
    statements.statement_accession,
    statements.statement_form,
    statements.statement_filed_date,
    -- Null for a derived value, which is computed from resolved figures and so has
    -- no filed counterpart. False where the chosen filing did not carry this line
    -- at all, because then no single statement holds it.
    case
        when deduplicated.confidence = 'derived' then null
        when as_filed.value_as_filed is null then false
        else abs(deduplicated.value - as_filed.value_as_filed)
            <= {{ var('restatement_tolerance') }} * greatest(abs(deduplicated.value), 1)
    end as is_coherent,
    statements.covers_whole_statement as statement_covers_whole
from deduplicated
join {{ ref('int_periods') }} as periods
    on periods.cik = deduplicated.cik
    and periods.period_start is not distinct from deduplicated.period_start
    and periods.period_end = deduplicated.period_end
join {{ ref('stg_companies') }} as companies on companies.cik = deduplicated.cik
left join {{ ref('int_statement_filings') }} as statements
    on statements.cik = deduplicated.cik
    and statements.statement = deduplicated.statement
    and statements.period_start is not distinct from deduplicated.period_start
    and statements.period_end = deduplicated.period_end
left join as_filed
    on as_filed.cik = deduplicated.cik
    and as_filed.accession = statements.statement_accession
    and as_filed.concept = deduplicated.concept
    and as_filed.period_kind = deduplicated.period_kind
    and as_filed.period_end = deduplicated.period_end
