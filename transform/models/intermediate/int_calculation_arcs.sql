{#
  Calculation arcs with what each end means to us, and whether the arc is on a
  primary statement.

  Two enrichments, and both are needed before any verdict can be reached.

  The first is what our config maps each end to, so an arc between two tags of the
  same concept can be told from an arc between two different concepts. That
  distinction carries the whole engine: `CostOfServices` under `CostOfRevenue` is a
  component of a total we already map, while `CostOfServices` under `GrossProfit` is
  the cost line itself being used to compute a different concept.

  The second is whether the arc belongs to a primary statement rather than a
  footnote. Role names cannot answer that: one company wrote
  ConsolidatedStatementsOfCashFlows, StatementOfCashFlowsIndirect and
  StatementConsolidatedStatementsOfCashFlows across three years for the same
  statement. So the answer comes from pre.txt, which already records which statement
  a tag appears on, and an arc counts as statement level when both of its ends are
  statement lines for that company.

  A note on direction, because it is the opposite of what it looks like. The parent
  of an arc is the line the filer computes, not the larger figure. Salesforce
  declares NetIncomeLoss = ProfitLoss less noncontrolling interests, so ProfitLoss at
  69.7 million is a child of NetIncomeLoss at 64.5 million. Any rule that assumes the
  parent is the bigger total is wrong half the time.
#}

{{ config(materialized='table') }}

with mappings as (

    select distinct
        concept,
        taxonomy || ':' || tag as qualified_tag
    from {{ ref('stg_tag_mappings') }}

),

{#- Tags a company presents on one of the three statements we hold concepts for. -#}
statement_tags as (

    select distinct
        cik,
        qualified_tag
    from {{ ref('stg_fsds_presentation') }}
    where statement is not null

)

select
    arcs.accession,
    arcs.cik,
    arcs.ticker,
    arcs.role,
    arcs.role_name,
    arcs.parent_qualified_tag,
    parent_mapping.concept as parent_concept,
    arcs.child_qualified_tag,
    child_mapping.concept as child_concept,
    arcs.weight,
    arcs.arc_order,
    -- The contradiction this engine looks for: a tag that is an input to another tag
    -- we also treat as the same concept's total cannot itself be that total.
    -- Wrapped because an unmapped end makes the comparison null rather than false,
    -- and a three valued flag would quietly drop those arcs from every filter.
    coalesce(parent_mapping.concept = child_mapping.concept, false) as is_same_concept,
    parent_lines.qualified_tag is not null
        and child_lines.qualified_tag is not null as is_statement_level
from {{ ref('stg_calculation_arcs') }} as arcs
left join mappings as parent_mapping
    on parent_mapping.qualified_tag = arcs.parent_qualified_tag
left join mappings as child_mapping
    on child_mapping.qualified_tag = arcs.child_qualified_tag
left join statement_tags as parent_lines
    on parent_lines.cik = arcs.cik
    and parent_lines.qualified_tag = arcs.parent_qualified_tag
left join statement_tags as child_lines
    on child_lines.cik = arcs.cik
    and child_lines.qualified_tag = arcs.child_qualified_tag
