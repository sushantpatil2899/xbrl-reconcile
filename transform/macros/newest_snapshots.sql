{# Returns a SQL list of the newest snapshot file per company for one dataset.
   Snapshots are cumulative, so only the newest is needed; older ones stay in
   the raw layer as history. Globbing lists keys without downloading files.

   With exclude_processed, files already recorded in the model's own
   source_file column are left out, so a run only reads what is new. The model
   itself is the record of what has been processed. #}
{% macro newest_snapshots(dataset, exclude_processed=false) %}
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
    {% if exclude_processed %}
    and file not in (select distinct source_file from {{ this }})
    {% endif %}
    order by file
  {% endset %}

  {% if execute %}
    {% set results = run_query(query) %}
    {% set files = results.columns[0].values() %}
    {% if files | length == 0 %}
      {% if exclude_processed %}
        {# Nothing new since the last run. The model handles this by selecting
           no rows, which leaves the existing table untouched. #}
        {{ return("[]") }}
      {% else %}
        {{ exceptions.raise_compiler_error("No snapshots found at " ~ pattern) }}
      {% endif %}
    {% endif %}
    {{ return("['" ~ files | join("', '") ~ "']") }}
  {% else %}
    {{ return("[]") }}
  {% endif %}
{% endmacro %}
