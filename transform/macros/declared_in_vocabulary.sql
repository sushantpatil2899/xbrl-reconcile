{# Fails when a column holds a value config never declared.

   dbt's own accepted_values test needs the values written into the model yml, which
   is the duplication this replaces: the same list then lives in several files and in
   config, and nothing keeps them in step. This reads the values from the staged
   vocabulary instead, so config is the only place a value is declared.

   Written as an anti join rather than `not in`. If the subquery ever yielded a null,
   `column not in (subquery)` is null for every row and the test passes while checking
   nothing. That silent pass is the same shape as the null bug that once left 172 arc
   flags wrong, and a left join has no such failure mode.

   Nulls in the tested column are ignored. inputs_confidence is null on most rows by
   design, and a null is an absent value rather than an undeclared one.
#}
{% test declared_in_vocabulary(model, column_name, vocabulary) %}
-- depends_on: {{ ref('stg_vocabularies') }}
select
    tested.{{ column_name }} as undeclared_value,
    count(*) as rows_affected
from {{ model }} as tested
left join {{ ref('stg_vocabularies') }} as declared
    on declared.vocabulary = '{{ vocabulary }}'
    and declared.value = tested.{{ column_name }}
where tested.{{ column_name }} is not null
  and declared.value is null
group by 1
{% endtest %}
