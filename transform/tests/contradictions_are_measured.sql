{#
  A contradiction has to be a difference, not a shape.

  The structural test this replaced called 27 published values contradicted and every
  one of them was a part that equalled its own total. So two things are asserted here,
  and the second is the one that will catch a regression.

  First, nothing published as `contradicted` may have a separation of nothing. That is
  the bug itself, and it fails rather than warns, because it is a statement about the
  column's meaning and not about the filers.

  Second, the equivalence has to keep being measured rather than assumed. `equivalent`
  values are counted by `equivalents_are_still_counted` alongside this, in the same
  spirit as `quarters_match_when_also_filed` outliving the quarter derivation: the
  moment a mechanism stops being watched is the moment it stops being true.
#}

{{ config(severity='error') }}

select
    financials.ticker,
    financials.concept,
    financials.period_end,
    financials.source_tag,
    financials.evidence,
    separation.separation,
    separation.separation_basis
from {{ ref('mart_financials') }} as financials
join {{ ref('int_arc_separation') }} as separation
    on separation.accession = financials.accession
    and separation.concept = financials.concept
    and separation.qualified_tag = financials.source_tag
    and separation.period_end = financials.period_end
where financials.evidence = 'contradicted'
    and separation.part_equals_total
