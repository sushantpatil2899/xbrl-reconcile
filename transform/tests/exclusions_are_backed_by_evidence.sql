{#
  The acceptance test for the whole linkbase phase.

  Five tags are excluded from config by hand, each found by inspecting values and
  noticing a total that was too small or too large:

    us-gaap:SalesRevenueServicesNet
    us-gaap:CostsAndExpenses
    us-gaap:LiabilitiesAndStockholdersEquity
    us-gaap:CostOfServices
    us-gaap:CostOfGoodsSold

  Every one should be visible in the filings' own arithmetic standing in a
  relationship to a line we do map, because that is why excluding it was right. The
  relationship runs in either direction, and the first version of this test only
  looked one way, which is how it caught its own flaw:

    as an input to a mapped line   the tag is a part of something we already map, so
                                   it is not that concept's total. CostOfServices is
                                   an input to CostOfRevenue.
    as a line computed from one    the tag is a larger total that contains something
                                   we map, so it is not that concept either.
                                   Autodesk computes LiabilitiesAndStockholdersEquity
                                   from nine children, one of them StockholdersEquity,
                                   and it is an input to nothing at all.

  If the arcs can show neither for a tag, then our exclusion rests on nothing the
  filings say, and the engine built to check such things is not working.

  This is a warning rather than an error because it depends on what filers publish
  rather than on our own logic, and a filer dropping a relationship should not stop
  the pipeline. The count is what matters: it should be zero.
#}

{{ config(severity='warn') }}

with excluded as (

    select unnest([
        'us-gaap:SalesRevenueServicesNet',
        'us-gaap:CostsAndExpenses',
        'us-gaap:LiabilitiesAndStockholdersEquity',
        'us-gaap:CostOfServices',
        'us-gaap:CostOfGoodsSold'
    ]) as qualified_tag

)

select
    excluded.qualified_tag,
    'no arc relates this tag to a mapped line, in either direction'
        as why_the_exclusion_is_unsupported
from excluded
where not exists (
    select 1
    from {{ ref('int_calculation_arcs') }} as arcs
    where (arcs.child_qualified_tag = excluded.qualified_tag and arcs.parent_concept is not null)
        or (arcs.parent_qualified_tag = excluded.qualified_tag and arcs.child_concept is not null)
)
