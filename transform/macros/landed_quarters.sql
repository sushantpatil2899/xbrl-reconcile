{# Returns a SQL list of the landed Data Set files for one part (sub, num, pre,
   tag).

   Globbing lists keys without downloading anything, so the cost of a transform run
   is in which files are then read. Without exclude_processed that is all 69
   quarters, four files each, on every run.

   With exclude_processed, a quarter is read only when it is new or when the
   ingestion job has re-landed it since this model last read it. That cannot be
   decided from the path: Data Set files land at a stable path and are overwritten
   when a company is added whose history the quarter should cover. stg_fsds_quarters
   carries the ingestion job's own landed_at, and each model records the landed_at of
   every row it stored, so the comparison is between two versions rather than two
   paths.

   A quarter present in the bucket but absent from the state file is read rather than
   skipped. Losing the state should degrade to doing the work, never to silently
   publishing nothing. #}
{% macro landed_quarters(part, exclude_processed=false) %}
  {% set pattern = var('raw_root') ~ '/fsds/*/' ~ part ~ '.tsv.gz' %}
  {#- Whether the stored table can say what it has already processed. On the run
      that first turns this model incremental the existing table predates these
      columns, so there is nothing to compare against and everything is read. -#}
  {% set has_marker = false %}
  {% if exclude_processed %}
    {% set stored_columns = adapter.get_columns_in_relation(this) | map(attribute='name') | map('lower') | list %}
    {% set has_marker = 'landed_at' in stored_columns and 'quarter' in stored_columns %}
  {% endif %}

  {% set query %}
    with landed as (
      select file, regexp_extract(file, 'fsds/([0-9]{4}q[1-4])/', 1) as quarter
      from glob('{{ pattern }}')
    )
    select landed.file
    from landed
    left join {{ ref('stg_fsds_quarters') }} as state on state.quarter = landed.quarter
    {%- if exclude_processed and has_marker %}
    left join (
      -- Columns qualified deliberately. Unqualified, a column missing from the
      -- target silently resolves to one of the outer tables, which turns this into
      -- a correlated aggregate and fails as "LATERAL join cannot contain
      -- aggregates" rather than as the missing column it is.
      select stored.quarter as quarter,
             max(stored.landed_at) as processed_at
      from {{ this }} as stored
      group by stored.quarter
    ) as processed on processed.quarter = landed.quarter
    where processed.quarter is null
       or state.landed_at is null
       or state.landed_at > processed.processed_at
    {%- endif %}
    order by landed.file
  {% endset %}

  {% if execute %}
    {% set results = run_query(query) %}
    {% set files = results.columns[0].values() %}
    {% if files | length == 0 %}
      {% if exclude_processed %}
        {# Nothing re-landed and nothing new. The model selects no rows, which leaves
           the existing table untouched. #}
        {{ return("[]") }}
      {% else %}
        {{ exceptions.raise_compiler_error("No Data Set quarters found at " ~ pattern) }}
      {% endif %}
    {% endif %}
    {{ return("['" ~ files | join("', '") ~ "']") }}
  {% else %}
    {{ return("[]") }}
  {% endif %}
{% endmacro %}
