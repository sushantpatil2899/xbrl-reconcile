{#
  The columns of a statement, generated from config.

  A wide statement needs a column per line, and the lines live in
  config/tag_mappings.yml. Writing them into SQL would put sixteen concept names
  in code, which is the one thing this project's design forbids, so the macro asks
  the database what the config says and writes the columns itself. Adding a concept
  to config adds a column here with no SQL edit, and reordering the config file
  reorders the statement.

  Each line becomes two columns: the value, and how it was obtained. A number
  whose confidence is out of sight is a number presented as more certain than it
  is, which is the failure this whole project exists to avoid.

  The ref() below is what registers the dependency on stg_tag_mappings. A model
  calling this macro also states it in a depends_on comment, because a ref that
  only appears inside a macro is easy for a reader to miss, and dbt needs the
  table to exist before the query runs.
#}
{% macro statement_lines(statement) %}

    {%- set query %}
        select concept
        from {{ ref('stg_tag_mappings') }}
        where statement = '{{ statement }}'
        group by concept
        order by min(position)
    {% endset -%}

    {%- if execute -%}
        {%- set concepts = run_query(query).columns[0].values() -%}
    {%- else -%}
        {#- During parsing nothing can be queried, so the model compiles empty. -#}
        {%- set concepts = [] -%}
    {%- endif -%}

    {%- for concept in concepts %}
    max(case when facts.concept = '{{ concept }}' then facts.value end) as {{ concept }},
    max(case when facts.concept = '{{ concept }}' then facts.confidence end)
        as {{ concept }}_confidence{{ "," if not loop.last }}
    {%- endfor -%}

{% endmacro %}
