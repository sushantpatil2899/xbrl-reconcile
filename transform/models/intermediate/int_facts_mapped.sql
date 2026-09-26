{#
  Raw SEC tags resolved to canonical concepts, one row per company, concept,
  period and filing.

  Resolution is per filing on purpose. Two filings can report the same period
  with different values (a restatement), and mixing them here would decide that
  question by accident. int_facts_resolved handles it deliberately.

  Note the join below: stg_sec_facts.concept holds the SEC tag name, because SEC
  calls its tags concepts. stg_tag_mappings.concept holds ours. So facts join to
  mappings on tag, and this model outputs `concept` meaning ours and
  `source_tag` meaning SEC's.
#}

{{ config(materialized='table') }}

with global_rules as (

    select
        concept,
        statement,
        unit,
        taxonomy,
        tag,
        priority,
        confidence,
        cast(null as bigint) as cik,
        cast(null as integer) as from_year,
        cast(null as integer) as through_year
    from {{ ref('stg_tag_mappings') }}

),

concept_specs as (

    select distinct concept, statement, unit
    from {{ ref('stg_tag_mappings') }}

),

{#- A prefer override can introduce a tag that is not in the global list, which
    is how a company reporting something nobody else uses gets mapped. Splunk
    reports no NetIncomeLoss, for example. -#}
preferred_rules as (

    select
        overrides.concept,
        specs.statement,
        specs.unit,
        overrides.taxonomy,
        overrides.tag,
        -overrides.position as priority,
        overrides.confidence,
        overrides.cik,
        overrides.from_year,
        overrides.through_year
    from {{ ref('stg_tag_overrides') }} overrides
    join concept_specs specs on specs.concept = overrides.concept
    where overrides.mode = 'prefer'

),

mappings as (

    select * from global_rules
    union all
    select * from preferred_rules

),

facts as (

    select
        f.cik,
        f.ticker,
        f.taxonomy,
        f.concept as sec_tag,
        f.unit,
        f.period_start,
        f.period_end,
        f.period_type,
        f.period_days,
        f.value,
        f.accession,
        f.form,
        f.filed_date
    from {{ ref('stg_sec_facts') }} f
    where f.is_valid

),

candidates as (

    select
        facts.cik,
        facts.ticker,
        mappings.concept,
        mappings.statement,
        facts.period_start,
        facts.period_end,
        -- Period length is banded rather than exact: fiscal quarters are 13
        -- weeks and 52/53 week years drift by a few days.
        case
            when facts.period_type = 'instant' then 'instant'
            when facts.period_days between 80 and 100 then 'quarter'
            when facts.period_days between 170 and 190 then 'half'
            when facts.period_days between 260 and 285 then 'nine_month'
            when facts.period_days between 350 and 380 then 'annual'
            else 'other'
        end as period_kind,
        facts.unit,
        facts.value,
        facts.taxonomy || ':' || facts.sec_tag as source_tag,
        mappings.confidence as configured_confidence,
        case when facts.taxonomy = 'ifrs-full' then 'ifrs' else 'us_gaap' end as basis,
        facts.accession,
        facts.form,
        facts.filed_date,
        mappings.priority as effective_priority
    from facts
    join mappings
        on facts.taxonomy = mappings.taxonomy
        and facts.sec_tag = mappings.tag
        -- A global rule applies to every company; a rule a prefer override
        -- introduced applies only to that company, within its year range.
        and (mappings.cik is null or mappings.cik = facts.cik)
        and coalesce(mappings.from_year, 0) <= year(facts.period_end)
        and coalesce(mappings.through_year, 9999) >= year(facts.period_end)
        -- The unit must be the one the concept is measured in, so a per share
        -- value can never land in a total.
        and facts.unit = mappings.unit
        -- Balance sheet concepts are point in time; income and cash flow
        -- concepts cover a period.
        and (
            (mappings.statement = 'balance_sheet' and facts.period_type = 'instant')
            or (mappings.statement != 'balance_sheet' and facts.period_type = 'duration')
        )
    -- `ignore` removes a tag from consideration for that company entirely,
    -- which is different from ranking it last.
    where not exists (
        select 1
        from {{ ref('stg_tag_overrides') }} ignored
        where ignored.mode = 'ignore'
            and ignored.cik = facts.cik
            and ignored.concept = mappings.concept
            and ignored.taxonomy = facts.taxonomy
            and ignored.tag = facts.sec_tag
            and coalesce(ignored.from_year, 0) <= year(facts.period_end)
            and coalesce(ignored.through_year, 9999) >= year(facts.period_end)
    )

),

{#- A tag can match both a global rule and a prefer rule for the same company.
    Keep one candidate per tag, the one with the strongest priority. -#}
deduplicated as (

    select *
    from candidates
    qualify row_number() over (
        partition by cik, concept, period_start, period_end, accession, source_tag
        order by effective_priority
    ) = 1

),

{#- Filers that never tag a total report it as parts. Summing them is only
    valid when every part is present and no total tag matched, so a reported
    total always wins and a partial sum is never published. -#}
component_sums as (

    select
        facts.cik,
        facts.ticker,
        components.concept,
        components.statement,
        facts.period_start,
        facts.period_end,
        case
            when facts.period_type = 'instant' then 'instant'
            when facts.period_days between 80 and 100 then 'quarter'
            when facts.period_days between 170 and 190 then 'half'
            when facts.period_days between 260 and 285 then 'nine_month'
            when facts.period_days between 350 and 380 then 'annual'
            else 'other'
        end as period_kind,
        facts.unit,
        sum(facts.value) as value,
        string_agg(facts.taxonomy || ':' || facts.sec_tag, '+' order by facts.sec_tag) as source_tag,
        min(components.confidence) as configured_confidence,
        case when facts.taxonomy = 'ifrs-full' then 'ifrs' else 'us_gaap' end as basis,
        facts.accession,
        facts.form,
        facts.filed_date,
        -- Component sums rank behind every total tag.
        1000 + min(components.position) as effective_priority
    from facts
    join {{ ref('stg_tag_components') }} components
        on facts.taxonomy = components.taxonomy
        and facts.sec_tag = components.tag
        and facts.unit = components.unit
        and (
            (components.statement = 'balance_sheet' and facts.period_type = 'instant')
            or (components.statement != 'balance_sheet' and facts.period_type = 'duration')
        )
    group by
        facts.cik, facts.ticker, components.concept, components.statement,
        facts.period_start, facts.period_end, facts.period_type, facts.period_days,
        facts.unit, facts.taxonomy, facts.accession, facts.form, facts.filed_date,
        components.position, components.component_count
    -- Every part must be present in this filing, or the sum understates the total.
    having count(distinct facts.sec_tag) = min(components.component_count)

),

{#- A component sum is used only where no total tag matched for that company,
    concept, period and filing. -#}
usable_sums as (

    select component_sums.*
    from component_sums
    where not exists (
        select 1
        from deduplicated totals
        where totals.cik = component_sums.cik
            and totals.concept = component_sums.concept
            and totals.period_start is not distinct from component_sums.period_start
            and totals.period_end = component_sums.period_end
            and totals.accession = component_sums.accession
    )

),

all_candidates as (

    select * from deduplicated
    union all
    select * from usable_sums

),

ranked as (

    select
        *,
        row_number() over (
            partition by cik, concept, period_start, period_end, accession
            order by effective_priority, source_tag
        ) as rank_in_filing,
        count(*) over (
            partition by cik, concept, period_start, period_end, accession
        ) as candidate_count,
        -- The runner up is kept so a disagreement can be inspected rather than
        -- just counted.
        lead(source_tag) over (
            partition by cik, concept, period_start, period_end, accession
            order by effective_priority, source_tag
        ) as runner_up_tag,
        lead(value) over (
            partition by cik, concept, period_start, period_end, accession
            order by effective_priority, source_tag
        ) as runner_up_value
    from all_candidates

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
    candidate_count,
    runner_up_tag,
    runner_up_value,
    -- Candidates that agree mean the choice did not matter, so confidence is
    -- kept. Candidates that disagree mean we picked a side, so it drops a level.
    candidate_count > 1
        and runner_up_value is not null
        and abs(value - runner_up_value)
            > {{ var('candidate_tolerance') }} * greatest(abs(value), abs(runner_up_value))
        as candidates_disagree,
    case
        when candidate_count > 1
            and runner_up_value is not null
            and abs(value - runner_up_value)
                > {{ var('candidate_tolerance') }} * greatest(abs(value), abs(runner_up_value))
        then case configured_confidence
            when 'high' then 'medium'
            when 'medium' then 'low'
            else 'low'
        end
        else configured_confidence
    end as confidence
from ranked
where rank_in_filing = 1
