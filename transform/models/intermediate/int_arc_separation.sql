{#
  How far a declared part actually is from the total it is declared a part of, in
  the filing that said so and for the period in question.

  This model exists because the contradiction test was structural and the structure
  lies. `int_calculation_arcs` finds arcs where a tag we map to a concept is an input
  to another tag we map to the same concept, and the premise written there was that
  such a tag "cannot itself be that total". That is false whenever the other inputs
  come to nothing, and measuring found it false every single time: all 27 published
  contradictions were a part that equalled its own total.

  Two shapes, and both need answering separately.

  The first is a part that is the total's only input at weight 1. Workday declares
  NetIncomeLoss = ProfitLoss and nothing else in 5 of its annual reports, so the two
  tags are the same number by construction, not by coincidence. No values are needed
  to know that; the arc list alone says it.

  The second is a part with siblings, where only the numbers can say. Workday's
  earlier filings declare NetIncomeLoss = ProfitLoss less the accretion on redeemable
  preferred stock. In fiscal 2013 that accretion is 568,000 and the two tags really do
  differ, by exactly that. In fiscal 2014 the company reports the accretion as 0.0 and
  they are identical. Same arc, same company, opposite answers, one year apart. A
  structural test cannot tell those apart and this one has to.

  A sibling with no fact for the period contributes nothing. That is the same reading
  `int_facts_derived` takes of an absent optional term, and the balance sheet confirms
  it for the case that prompted this: CrowdStrike declares total equity as its parent
  only equity plus a noncontrolling interest it never reports, and assets equal
  liabilities plus temporary equity plus the parent only figure to the dollar in all
  three quarters. The interest is absent because it is nothing, not because the filing
  is incomplete. Counted in `siblings_unvalued` so the assumption stays visible.

  Custom siblings are the one case that cannot be read at all: companyfacts carries no
  custom tags, so a custom sibling has no value here at any period and absent cannot
  be distinguished from nothing. Those are counted separately and never called
  equivalent.

  The grain is one row per filing, concept, declared part and period. Roles are
  aggregated out, conservatively: a part counts as equivalent only where every network
  that declares it a part also makes it equal.
#}

{{ config(materialized='table') }}

with same_concept as (

    select distinct
        accession,
        role,
        parent_qualified_tag,
        child_qualified_tag,
        child_concept,
        weight
    from {{ ref('int_calculation_arcs') }}
    where is_same_concept

),

{#- Every input under one of those totals, in the same filing and network, so the
    siblings that separate the part from the whole can be found. -#}
siblings as (

    select distinct
        arcs.accession,
        arcs.role,
        arcs.parent_qualified_tag,
        arcs.child_qualified_tag,
        arcs.weight
    from {{ ref('stg_calculation_arcs') }} as arcs
    join (
        select distinct accession, role, parent_qualified_tag
        from same_concept
    ) as totals
        on totals.accession = arcs.accession
        and totals.role = arcs.role
        and totals.parent_qualified_tag = arcs.parent_qualified_tag

),

{#- Reported facts, qualified the way arcs are. Aggregated because nine rows in the
    warehouse repeat a tag and period inside one filing, one of them with two
    different values, and summing a sibling twice would invent a separation. -#}
facts as (

    select
        accession,
        taxonomy || ':' || concept as qualified_tag,
        period_start,
        period_end,
        max(value) as value
    from {{ ref('stg_sec_facts') }}
    where is_valid
    group by all

),

{#- Each declared part, for every period that filing reported it. -#}
parts as (

    select
        same_concept.accession,
        same_concept.role,
        same_concept.parent_qualified_tag,
        same_concept.child_qualified_tag,
        same_concept.child_concept,
        facts.period_start,
        facts.period_end,
        facts.value as part_value
    from same_concept
    join facts
        on facts.accession = same_concept.accession
        and facts.qualified_tag = same_concept.child_qualified_tag

),

{#- The siblings' contribution to the same total, for the same period. -#}
measured as (

    select
        parts.accession,
        parts.role,
        parts.parent_qualified_tag,
        parts.child_qualified_tag,
        parts.child_concept,
        parts.period_start,
        parts.period_end,
        parts.part_value,
        count(siblings.child_qualified_tag) as siblings_declared,
        count(sibling_facts.value) as siblings_valued,
        count(distinct siblings.child_qualified_tag) filter (
            where siblings.child_qualified_tag like 'custom:%'
        ) as siblings_custom,
        coalesce(sum(siblings.weight * sibling_facts.value), 0) as separation
    from parts
    left join siblings
        on siblings.accession = parts.accession
        and siblings.role = parts.role
        and siblings.parent_qualified_tag = parts.parent_qualified_tag
        and siblings.child_qualified_tag <> parts.child_qualified_tag
    left join facts as sibling_facts
        on sibling_facts.accession = parts.accession
        and sibling_facts.qualified_tag = siblings.child_qualified_tag
        and sibling_facts.period_start is not distinct from parts.period_start
        and sibling_facts.period_end = parts.period_end
    group by all

)

select
    accession,
    child_concept as concept,
    child_qualified_tag as qualified_tag,
    period_start,
    period_end,
    max(part_value) as part_value,
    max(siblings_declared) as siblings_declared,
    max(siblings_declared - siblings_valued) as siblings_unvalued,
    max(siblings_custom) as siblings_custom,
    max(abs(separation)) as separation,
    -- Equivalent where the part is the total's only input, or where what separates
    -- them is measurably nothing. A custom sibling is never nothing, only unknown.
    bool_and(
        siblings_declared = 0
        or (
            siblings_custom = 0
            and abs(separation)
                <= {{ var('separation_tolerance') }} * greatest(abs(part_value), 1)
        )
    ) as part_equals_total,
    -- How the answer was reached, so a reader can weigh it rather than take it.
    case
        when bool_or(siblings_custom > 0) then 'custom_sibling'
        when max(siblings_declared) = 0 then 'sole_input'
        when max(siblings_declared - siblings_valued) = 0 then 'siblings_measured'
        else 'siblings_absent'
    end as separation_basis
from measured
group by all
