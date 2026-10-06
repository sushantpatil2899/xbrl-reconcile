{#
  Totals summed from parts a company reports with no total of its own, where at
  least one part is a custom tag.

  This exists because of one case and is written to generalise to others. Workday
  reported cost of revenue for 2014 to 2016 as two lines, "Costs of subscription
  services" and "Costs of professional services", and never a total. One of the two
  is a custom tag, which SEC's companyfacts API drops entirely, so the existing
  component mechanism cannot see it. The Data Sets keep custom tags, which is why
  Phase 4 exists.

  The evidence for the pair is unusually strong. The same two tags reproduce the
  published total exactly in four other years by two unrelated mechanisms: 65.368
  and 116.535 for 2012 and 2013, which is what Workday tagged as CostOfRevenue, and
  483.545 and 629.413 for 2017 and 2018, which is what dimension recovery produces.
  Those four bracket the three gap years on both sides.

  Three rules make the sum trustworthy:

  1. Scoped to one company. A custom tag name is not unique, and
     CostOfRevenueSubscriptionAndSupport is used by two of these filers, so the
     company comes from the override rather than from the tag.
  2. Every named part must be present for the period, or no row is produced. A sum
     missing a part understates the total, which is the Intuit error from Phase 3.
  3. Consolidated facts only. A dimensional row is a breakdown of one of these parts
     and would be counted twice.

  The deduplication is not optional. A Data Set fact appears once per landed quarter
  that carried it, so Workday's 69.195 for 2014 is present three times. Summing
  without collapsing first would treble the total. One value per company, tag and
  period is taken from the most recently filed accession, which is the same rule the
  rest of the project resolves restatements by.
#}

{{ config(materialized='table') }}

with sum_rules as (

    select
        cik,
        concept,
        taxonomy || ':' || tag as qualified_tag,
        position,
        confidence,
        from_year,
        through_year
    from {{ ref('stg_tag_overrides') }}
    where mode = 'sum'

),

{#- How many parts each rule names, so a period missing one can be rejected. -#}
rule_size as (

    select
        cik,
        concept,
        count(*) as parts_required,
        min(confidence) as confidence,
        min(from_year) as from_year,
        max(through_year) as through_year,
        string_agg(qualified_tag, '+' order by position) as source_tag
    from sum_rules
    group by all

),

{#- One value per company, tag and period, from the filing that reported it last. -#}
parts as (

    select
        facts.cik,
        facts.ticker,
        rules.concept,
        facts.qualified_tag,
        facts.period_end,
        facts.period_kind,
        facts.unit,
        facts.value,
        facts.accession,
        facts.form,
        facts.filed_date
    from {{ ref('stg_fsds_facts') }} as facts
    join sum_rules as rules
        on rules.cik = facts.cik
        and rules.qualified_tag = facts.qualified_tag
    where facts.is_consolidated
        and facts.value is not null
    qualify row_number() over (
        partition by facts.cik, rules.concept, facts.qualified_tag,
                     facts.period_end, facts.period_kind, facts.unit
        order by facts.filed_date desc, facts.accession desc
    ) = 1

),

{#- The periods this company already uses, so a summed value lines up with the rest
    of its statement rather than sitting beside it on a nearby date. Data Set facts
    carry only an end date and a period length, and a duration with no start date
    would collide in the period spine with the instants, which legitimately have
    none. The same alignment the dimension recovery does, for the same reason. -#}
company_periods as (

    select distinct cik, period_end, period_type, period_days, period_start
    from {{ ref('stg_sec_facts') }}
    where is_valid

),

summed as (

    select
        parts.cik,
        parts.ticker,
        parts.concept,
        parts.period_end,
        parts.period_kind,
        parts.unit,
        sum(parts.value) as value,
        count(*) as parts_present,
        max(parts.accession) as accession,
        max(parts.form) as form,
        max(parts.filed_date) as filed_date
    from parts
    group by all

)

select
    summed.cik,
    summed.ticker,
    summed.concept,
    periods.period_start,
    summed.period_end,
    summed.period_kind,
    summed.unit,
    summed.value,
    rule_size.source_tag,
    rule_size.confidence,
    summed.accession,
    summed.form,
    summed.filed_date,
    summed.parts_present
from summed
join rule_size
    on rule_size.cik = summed.cik
    and rule_size.concept = summed.concept
-- Inner joined deliberately. A summed duration whose start date this company never
-- reported cannot be placed on its statement, and publishing it with no start would
-- collide in the period spine with the instants. Better absent than misplaced.
join company_periods periods
    on periods.cik = summed.cik
    and periods.period_end = summed.period_end
    and case summed.period_kind
        when 'quarter' then periods.period_days between 80 and 100
        when 'half' then periods.period_days between 170 and 190
        when 'nine_month' then periods.period_days between 260 and 285
        when 'annual' then periods.period_days between 350 and 380
        else false
    end
-- Every named part present, or the sum understates the total.
where summed.parts_present = rule_size.parts_required
    and (rule_size.from_year is null or year(summed.period_end) >= rule_size.from_year)
    and (rule_size.through_year is null or year(summed.period_end) <= rule_size.through_year)
