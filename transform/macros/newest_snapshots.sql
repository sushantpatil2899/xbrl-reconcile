{# Returns a SQL list of the newest snapshot file per company for one dataset.
   Snapshots are cumulative, so only the newest is needed; older ones stay in
   the raw layer as history. Globbing lists keys without downloading files. #}
{% macro newest_snapshots(dataset) %}
  {% set pattern = var('raw_root') ~ '/sec/' ~ dataset ~ '/cik=*/*.json.gz' %}
  {% set query %}
    select file
    from (
      select file,
             row_number() over (
               partition by regexp_extract(file, 'cik=(\d+)', 1)
               order by file desc
             ) as rn
      from glob('{{ pattern }}')
    )
    where rn = 1
    order by file
  {% endset %}

  {% if execute %}
    {% set results = run_query(query) %}
    {% set files = results.columns[0].values() %}
    {% if files | length == 0 %}
      {{ exceptions.raise_compiler_error("No snapshots found at " ~ pattern) }}
    {% endif %}
    {{ return("['" ~ files | join("', '") ~ "']") }}
  {% else %}
    {{ return("[]") }}
  {% endif %}
{% endmacro %}
