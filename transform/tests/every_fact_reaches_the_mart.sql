{#
  The mart publishes every fact the intermediate layer resolved, minus the
  duplicate period starts it collapses. A silent drop here would be a join that
  lost rows, which is the easiest mistake to make and the hardest to notice.
#}

with expected as (

    select count(*) as rows
    from (
        select distinct cik, concept, period_kind, period_end
        from (
            select cik, concept, period_kind, period_end from {{ ref('int_facts') }}
            union all
            select cik, concept, period_kind, period_end from {{ ref('int_facts_quarterly') }}
        )
    )

),

published as (

    select count(*) as rows from {{ ref('mart_financials') }}

)

select expected.rows as expected_rows, published.rows as published_rows
from expected, published
where expected.rows != published.rows
