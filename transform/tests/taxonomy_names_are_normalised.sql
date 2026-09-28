{#
  No model should publish `ifrs` as a taxonomy name.

  SEC's Data Sets spell it `ifrs`, the companyfacts API and the mapping config spell
  it `ifrs-full`, and a join across the two silently matches nothing. That is how
  Atlassian's dimensional facts became unreachable without any number looking wrong,
  so the spelling is asserted rather than trusted.
#}

select 'stg_fsds_tags' as model, taxonomy, count(*) as rows
from {{ ref('stg_fsds_tags') }} where taxonomy = 'ifrs' group by all

union all

select 'stg_fsds_facts', taxonomy, count(*)
from {{ ref('stg_fsds_facts') }} where taxonomy = 'ifrs' group by all

union all

select 'stg_fsds_presentation', taxonomy, count(*)
from {{ ref('stg_fsds_presentation') }} where taxonomy = 'ifrs' group by all
