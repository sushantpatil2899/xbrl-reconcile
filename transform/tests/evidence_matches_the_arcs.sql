{#
  The evidence label on each value must agree with the arcs, computed independently.

  The label is a case expression over two joins, so a broken join would not fail; it
  would quietly mark everything `unexamined` and the column would look plausible
  while saying nothing. This recomputes both conditions from int_calculation_arcs and
  compares, which is the one thing a tautological check cannot do.
#}

with published as (

    select
        accession,
        concept,
        source_tag,
        confidence,
        evidence
    from {{ ref('mart_financials') }}

),

recomputed as (

    select
        published.accession,
        published.concept,
        published.source_tag,
        published.evidence,
        case
            when published.confidence = 'derived'
                or published.source_tag like '%+%'
                or published.source_tag like 'fsds:%'
                then 'not_applicable'
            when exists (
                select 1
                from {{ ref('int_calculation_arcs') }} as arcs
                where arcs.accession = published.accession
                    and arcs.child_concept = published.concept
                    and arcs.child_qualified_tag = published.source_tag
                    and arcs.is_same_concept
            ) then 'contradicted'
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
    evidence,
    expected
from recomputed
where evidence != expected
