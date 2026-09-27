{#
  Totals recovered by summing the members of one dimension, for concepts a
  company reports only as a breakdown.

  Workday never tags total cost of revenue. It reports SubscriptionServices and
  ProfessionalServices, which add to it. companyfacts drops both, because SEC
  excludes dimensional facts from that API, which is why 26 coverage cells were
  empty before this model existed.

  Six safeguards, because summing parts is exactly where double counting hides:

  1. Only axes listed in config. Whether an axis partitions a total is a
     judgement about that axis, not something to infer.
  2. Only facts with exactly one dimension. A fact split by product and by
     geography at once would be counted twice.
  3. At least two members. One member is not a breakdown.
  4. Only where the company reports no consolidated value for that tag, period
     and unit in any filing.
  5. Only where the company reports nothing for the concept that tag maps to,
     under any tag, in companyfacts. Autodesk taught this one: it reports
     CostOfRevenue as a consolidated total (650 million for fiscal 2026) and
     CostOfGoodsAndServicesSold as a two member breakdown summing to 553 million,
     which is part of cost of revenue rather than all of it. Guarding at the tag
     level alone would publish a competing total 15 percent short.
  6. Within one filing, one period end, one period kind and one unit.

  period_start is taken from the company's own periods, because the Data Sets
  give only a period end and a length. Matching the start the company already
  uses for other concepts is what lets a recovered value line up with the rest of
  its statement.
#}

{{ config(materialized='table') }}

with summable as (

    select axis, confidence from {{ ref('stg_tag_summable_axes') }}

),

{#- Which concept each tag means, so the guards can work at concept level. -#}
rules as (

    select concept, taxonomy, tag, unit
    from {{ ref('stg_tag_mappings') }}

),

{#- Concepts each company already reports in companyfacts, under any tag. -#}
already_reported as (

    select distinct
        facts.cik,
        rules.concept,
        facts.period_end,
        case
            when facts.period_type = 'instant' then 'instant'
            when facts.period_days between 80 and 100 then 'quarter'
            when facts.period_days between 170 and 190 then 'half'
            when facts.period_days between 260 and 285 then 'nine_month'
            when facts.period_days between 350 and 380 then 'annual'
            else 'other'
        end as period_kind
    from {{ ref('stg_sec_facts') }} facts
    join rules
        on rules.taxonomy = facts.taxonomy
        and rules.tag = facts.concept
        and rules.unit = facts.unit
    -- A form whose values are not published cannot count as evidence that the
    -- company reported a total either.
    join {{ ref('stg_companies') }} companies on companies.cik = facts.cik
    where facts.is_valid
        and {{ reported_in_a_configured_form('facts', 'companies') }}

),

dimensional as (

    select
        f.cik,
        f.ticker,
        f.accession,
        f.form,
        f.filed_date,
        f.taxonomy,
        f.tag,
        f.qualified_tag,
        rules.concept,
        f.period_end,
        f.period_kind,
        f.unit,
        f.axis,
        f.member,
        f.value,
        summable.confidence
    from {{ ref('stg_fsds_facts') }} f
    join summable on summable.axis = f.axis
    join rules on rules.taxonomy = f.taxonomy and rules.tag = f.tag and rules.unit = f.unit
    -- The Data Sets carry registration statements and earnings releases too.
    join {{ ref('stg_companies') }} c on c.cik = f.cik
    where f.dimension_count = 1
        and {{ reported_in_a_configured_form('f', 'c') }}

),

{#- A reported total always wins, so drop any tag and period the company reported
    without dimensions in any filing. -#}
without_reported_total as (

    select dimensional.*
    from dimensional
    where not exists (
        select 1
        from {{ ref('stg_fsds_facts') }} consolidated
        where consolidated.cik = dimensional.cik
            and consolidated.qualified_tag = dimensional.qualified_tag
            and consolidated.period_end = dimensional.period_end
            and consolidated.period_kind = dimensional.period_kind
            and consolidated.unit = dimensional.unit
            and consolidated.is_consolidated
    )
    -- And nothing the company already reports for this concept under any tag.
    and not exists (
        select 1
        from already_reported reported
        where reported.cik = dimensional.cik
            and reported.concept = dimensional.concept
            and reported.period_end = dimensional.period_end
            and reported.period_kind = dimensional.period_kind
    )

),

summed as (

    select
        cik,
        ticker,
        accession,
        form,
        filed_date,
        taxonomy,
        tag,
        qualified_tag,
        concept,
        period_end,
        period_kind,
        unit,
        axis,
        sum(value) as value,
        count(distinct member) as member_count,
        string_agg(distinct member, '+' order by member) as members,
        min(confidence) as confidence
    from without_reported_total
    group by all
    -- One member is not a breakdown of anything.
    having count(distinct member) >= 2

),

{#- The periods this company already uses, so a recovered value lines up with the
    rest of its statement rather than sitting beside it on a nearby date. -#}
company_periods as (

    select distinct cik, period_end, period_type, period_days, period_start
    from {{ ref('stg_sec_facts') }}
    where is_valid

),

aligned as (

    select
        summed.*,
        periods.period_start as matched_period_start
    from summed
    left join company_periods periods
        on periods.cik = summed.cik
        and periods.period_end = summed.period_end
        and case summed.period_kind
            when 'instant' then periods.period_type = 'instant'
            when 'quarter' then periods.period_days between 80 and 100
            when 'half' then periods.period_days between 170 and 190
            when 'nine_month' then periods.period_days between 260 and 285
            when 'annual' then periods.period_days between 350 and 380
            else false
        end

)

select
    cik,
    ticker,
    accession,
    form,
    filed_date,
    taxonomy,
    qualified_tag,
    concept,
    period_kind,
    period_end,
    -- Falls back to arithmetic only for a period no other concept covers.
    coalesce(
        matched_period_start,
        case period_kind
            when 'instant' then null
            when 'quarter' then period_end - interval 3 month + interval 1 day
            when 'half' then period_end - interval 6 month + interval 1 day
            when 'nine_month' then period_end - interval 9 month + interval 1 day
            when 'annual' then period_end - interval 12 month + interval 1 day
        end::date
    ) as period_start,
    matched_period_start is not null as period_start_matched,
    unit,
    value,
    axis,
    members,
    member_count,
    confidence,
    'fsds:' || qualified_tag || '@' || axis as source_tag
from aligned
