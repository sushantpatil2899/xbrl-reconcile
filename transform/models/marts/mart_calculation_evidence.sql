{#
  Whether the filings' own arithmetic supports each tag we map, per company.

  One row per company, concept and candidate tag, where a candidate is any tag our
  config considered for that concept and the company reported. Runners up are
  included deliberately: the 123 values where two tags disagreed are exactly the ones
  evidence should adjudicate, and the loser is half of that question.

  The verdict rests on one relationship. Where a tag is an input to another tag our
  config maps to the same concept, the filer is saying it is a part rather than the
  whole, so treating it as that concept's total contradicts the filing. Where no
  such arc exists, nothing contradicts the mapping, which is weaker than proof and is
  labelled as such.

  A tag absent from every linkbase is not disproved. Six annual reports carry no
  calculation linkbase at all, all of them recent filings from HubSpot and Box, so
  silence has to be a verdict of its own rather than an implied pass.
#}

{{ config(materialized='table') }}

with candidates as (

    {#- Every tag we considered for a concept, per company, including the ones that
        lost. -#}
    select distinct
        cik,
        ticker,
        concept,
        source_tag as qualified_tag
    from {{ ref('int_facts_mapped') }}

),

arcs as (

    select *
    from {{ ref('int_calculation_arcs') }}

),

{#- Arcs where this tag is the input and the computed line is the same concept. -#}
as_component as (

    select
        arcs.cik,
        arcs.child_concept as concept,
        arcs.child_qualified_tag as qualified_tag,
        count(distinct arcs.accession) as filings_saying_component,
        count(*) filter (where arcs.is_statement_level) as statement_arcs,
        string_agg(distinct arcs.parent_qualified_tag, ' | ') as declared_part_of,
        min(arcs.weight) as weight
    from arcs
    where arcs.is_same_concept
    group by all

),

{#- What the filer computes from this tag, whatever the concept, for context. -#}
as_input as (

    select
        cik,
        child_qualified_tag as qualified_tag,
        string_agg(distinct parent_qualified_tag, ' | ') as input_to
    from arcs
    group by all

),

{#- Components the filer declares under this tag, which is what a real total has. -#}
as_total as (

    select
        cik,
        parent_qualified_tag as qualified_tag,
        count(distinct child_qualified_tag) as declared_components
    from arcs
    group by all

),

{#- Whether the company has any linkbase evidence at all. Six annual reports carry
    none, so a tag can be unexamined rather than unsupported. -#}
coverage as (

    select
        cik,
        count(distinct accession) as filings_with_arcs
    from arcs
    group by all

)

select
    candidates.cik,
    candidates.ticker,
    candidates.concept,
    candidates.qualified_tag,
    coalesce(coverage.filings_with_arcs, 0) as filings_with_arcs,
    coalesce(as_component.filings_saying_component, 0) as filings_saying_component,
    coalesce(as_component.statement_arcs, 0) as statement_arcs,
    as_component.declared_part_of,
    as_component.weight as weight_as_component,
    as_input.input_to,
    coalesce(as_total.declared_components, 0) as declared_components,
    case
        when as_component.qualified_tag is not null then 'component_of_same_concept'
        when coalesce(coverage.filings_with_arcs, 0) = 0 then 'no_arcs'
        else 'confirmed_total'
    end as calculation_verdict
from candidates
left join as_component
    on as_component.cik = candidates.cik
    and as_component.concept = candidates.concept
    and as_component.qualified_tag = candidates.qualified_tag
left join as_input
    on as_input.cik = candidates.cik
    and as_input.qualified_tag = candidates.qualified_tag
left join as_total
    on as_total.cik = candidates.cik
    and as_total.qualified_tag = candidates.qualified_tag
left join coverage on coverage.cik = candidates.cik
