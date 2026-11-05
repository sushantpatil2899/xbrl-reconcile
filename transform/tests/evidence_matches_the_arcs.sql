{#
  The evidence label on each value must agree with the arcs, computed independently.

  The label is a case expression over three joins, so a broken join would not fail; it
  would quietly mark everything `unexamined` and the column would look plausible while
  saying nothing. This recomputes every condition with correlated subqueries instead,
  which is the one thing a tautological check cannot do.

  Written as `exists` rather than as joins deliberately, so that a change to the
  cardinality of a join in the model, the failure mode most likely to go unnoticed,
  shows up here as a disagreement rather than being reproduced.

  This test caught the semantics change it is written against: when `contradicted`
  became conditional on a measured separation, the old version of this file reported
  24 disagreements, all of them Workday values that had correctly stopped being
  contradictions. A recomputation that needs updating when the meaning changes is
  working; one that does not is not watching anything.
#}

with published as (

    select
        accession,
        concept,
        source_tag,
        period_start,
        period_end,
        confidence,
        evidence
    from {{ ref('mart_financials') }}

),

recomputed as (

    select
        published.accession,
        published.concept,
        published.source_tag,
        published.period_end,
        published.evidence,
        case
            when published.confidence = 'derived'
                or published.source_tag like '%+%'
                or published.source_tag like 'fsds:%'
                then 'not_applicable'
            when exists (
                select 1
                from {{ ref('int_arc_separation') }} as separation
                where separation.accession = published.accession
                    and separation.concept = published.concept
                    and separation.qualified_tag = published.source_tag
                    and separation.period_start is not distinct from published.period_start
                    and separation.period_end = published.period_end
                    and not separation.part_equals_total
            ) then 'contradicted'
            when exists (
                select 1
                from {{ ref('int_arc_separation') }} as separation
                where separation.accession = published.accession
                    and separation.concept = published.concept
                    and separation.qualified_tag = published.source_tag
                    and separation.period_start is not distinct from published.period_start
                    and separation.period_end = published.period_end
            ) then 'equivalent'
            when exists (
                select 1
                from {{ ref('int_calculation_arcs') }} as arcs
                where arcs.accession = published.accession
            ) then 'confirmed'
            else 'unexamined'
        end as expected
    from published

)

select
    accession,
    concept,
    source_tag,
    period_end,
    evidence,
    expected
from recomputed
where evidence != expected
