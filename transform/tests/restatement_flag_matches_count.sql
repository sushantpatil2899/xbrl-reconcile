-- A restated period must have reported more than one distinct value. The
-- reverse does not hold: several values within the tolerance of each other are
-- the same figure reported again, not a restatement.
select cik, concept, period_end, restatement_count, was_restated
from {{ ref('int_facts_resolved') }}
where was_restated and restatement_count = 1
