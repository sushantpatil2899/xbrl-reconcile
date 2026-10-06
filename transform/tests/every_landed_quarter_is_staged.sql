{#
  Every quarter and filing the ingestion job landed must have rows in staging.

  The incremental macros decide what to read by comparing the ingestion job's state
  against what each model already stored. A mistake there does not fail: it quietly
  reads nothing, and the model keeps serving whatever it holds while looking healthy.
  This is the check that would catch that, by asserting the two sides agree.

  A quarter with no facts at all is possible in principle, since filtering keeps only
  our companies, but every landed quarter recorded a non zero fact count, so a
  landed quarter with no staged rows means the quarter was skipped.
#}

select
    'fsds' as layer,
    quarters.quarter as id,
    quarters.landed_at as version
from {{ ref('stg_fsds_quarters') }} as quarters
where quarters.facts > 0
    and not exists (
        select 1 from {{ ref('stg_fsds_facts') }} as facts
        where facts.quarter = quarters.quarter
    )

union all

select
    'linkbase',
    filings.accession,
    filings.parsed_at
from {{ ref('stg_linkbase_filings') }} as filings
where filings.arcs > 0
    and not exists (
        select 1 from {{ ref('stg_calculation_arcs') }} as arcs
        where arcs.accession = filings.accession
    )
