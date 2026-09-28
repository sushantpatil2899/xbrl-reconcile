{#
  What the filings themselves say about each tag, from the presentation linkbase.

  A mart that only checked the tags we map would contain no news: all 44 of them
  already agree with the statement filers put them on. The news is in the tags we do
  not map, which is where the gaps come from. Salesforce has no cost of revenue for
  fiscal 2015 and 2016 because we exclude us-gaap:CostOfServices, and that tag is
  not in our config at all, so a mapped only report would never mention it.

  So this covers every tag any company presented on the three statements we hold
  concepts for, and says what the evidence is for each.

  The candidate rule needs two conditions, not one. A tag labelled "Total something"
  looks like a candidate, but on its own that finds AssetsCurrent, LiabilitiesCurrent
  and CostsAndExpenses, which are genuine totals of things that are not our concepts.
  Requiring that the company also has a gap on that statement takes the list from 189
  rows to 8, which is short enough to read.

  Nothing here proves anything. The presentation linkbase has no parent and child
  relationships, so a candidate is a suggestion. What settles it is the calculation
  linkbase saying the tag sits directly under a concept we map, and that is a later
  task. Acting on any of this is later still.
#}

{{ config(materialized='table') }}

with mappings as (

    {#- A tag maps to at most one concept, which the config loader enforces, so this
        join cannot fan out. -#}
    select distinct
        taxonomy || ':' || tag as qualified_tag,
        concept,
        statement
    from {{ ref('stg_tag_mappings') }}

),

{#- Statements where a company is missing a concept we expect it to have. This is
    what turns a noisy label heuristic into a worklist. -#}
gaps as (

    select distinct cik, statement
    from {{ ref('mart_mapping_coverage') }}
    where status = 'missing'

),

presented as (

    select
        lines.cik,
        lines.ticker,
        lines.statement,
        lines.taxonomy,
        lines.tag,
        lines.qualified_tag,
        bool_or(lines.is_custom) as is_custom,
        count(distinct lines.accession) as filings,
        count(*) as lines,
        min(lines.line) as min_line,
        max(lines.line) as max_line,
        min(submissions.period_of_report) as first_period,
        max(submissions.period_of_report) as last_period,
        -- Filers vary their own wording: HubSpot used four spellings of "Total other
        -- income (expense)" for one tag. The variation is itself evidence of how
        -- loosely a tag is being used.
        string_agg(distinct lines.filer_label, ' | ') as filer_labels,
        bool_or(lines.is_parenthetical) as ever_parenthetical,
        bool_and(lines.is_parenthetical) as always_parenthetical,
        -- A total the filer actually put on a line, rather than in brackets beside
        -- one. Something shown only parenthetically is never a statement total.
        count(*) filter (
            where lower(lines.filer_label) like 'total%' and not lines.is_parenthetical
        ) > 0 as presented_as_a_total
    from {{ ref('stg_fsds_presentation') }} as lines
    join {{ ref('stg_fsds_submissions') }} as submissions
        on submissions.accession = lines.accession
    where lines.statement is not null
    group by all

)

select
    presented.cik,
    presented.ticker,
    presented.statement,
    presented.taxonomy,
    presented.tag,
    presented.qualified_tag,
    presented.is_custom,
    mappings.qualified_tag is not null as is_mapped,
    mappings.concept as mapped_concept,
    mappings.statement as mapped_statement,
    mappings.statement = presented.statement as statement_agrees,
    presented.filer_labels,
    presented.presented_as_a_total,
    presented.filings,
    presented.lines,
    presented.first_period,
    presented.last_period,
    presented.min_line,
    presented.max_line,
    presented.ever_parenthetical,
    presented.always_parenthetical,
    gaps.cik is not null as company_has_a_gap_on_this_statement,
    case
        when mappings.qualified_tag is not null and mappings.statement = presented.statement
            then 'confirms_mapping'
        -- Not a fault. Cash closes the cash flow statement and net income opens it,
        -- so a tag legitimately appears on a statement other than its own.
        when mappings.qualified_tag is not null then 'mapped_elsewhere'
        when presented.presented_as_a_total and gaps.cik is not null then 'candidate'
        else 'unmapped'
    end as verdict
from presented
left join mappings on mappings.qualified_tag = presented.qualified_tag
left join gaps
    on gaps.cik = presented.cik
    and gaps.statement = presented.statement
