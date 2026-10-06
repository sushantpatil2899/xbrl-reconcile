{# Returns a SQL list of the landed calculation linkbase files.

   Same shape and same reason as landed_quarters. arcs.json lands at a stable path
   per accession and is rewritten when the parser's output shape changes, which has
   happened once already, so a path that has been read before may now hold different
   content. stg_linkbase_filings carries the later of fetched_at and reparsed_at, and
   the model records what it read.

   A filing in the bucket but absent from the state file is read rather than skipped,
   for the same reason as there. #}
{% macro landed_linkbases(exclude_processed=false) %}
  {% set pattern = var('raw_root') ~ '/linkbase/cik=*/*/arcs.json' %}
  {#- Whether the stored table can say what it has already processed. On the run
      that first turns this model incremental the existing table predates these
      columns, so there is nothing to compare against and everything is read. -#}
  {% set has_marker = false %}
  {% if exclude_processed %}
    {% set stored_columns = adapter.get_columns_in_relation(this) | map(attribute='name') | map('lower') | list %}
    {% set has_marker = 'parsed_at' in stored_columns and 'accession' in stored_columns %}
  {% endif %}

  {% set query %}
    with landed as (
      select file, regexp_extract(file, 'cik=[0-9]{10}/([^/]+)/arcs.json', 1) as accession
      from glob('{{ pattern }}')
    )
    select landed.file
    from landed
    left join {{ ref('stg_linkbase_filings') }} as state on state.accession = landed.accession
    {%- if exclude_processed and has_marker %}
    left join (
      -- Columns qualified deliberately. Unqualified, a column missing from the
      -- target silently resolves to one of the outer tables, which turns this into
      -- a correlated aggregate and fails as "LATERAL join cannot contain
      -- aggregates" rather than as the missing column it is.
      select stored.accession as accession,
             max(stored.parsed_at) as processed_at
      from {{ this }} as stored
      group by stored.accession
    ) as processed on processed.accession = landed.accession
    where processed.accession is null
       or state.parsed_at is null
       or state.parsed_at > processed.processed_at
    {%- endif %}
    order by landed.file
  {% endset %}

  {% if execute %}
    {% set results = run_query(query) %}
    {% set files = results.columns[0].values() %}
    {% if files | length == 0 %}
      {% if exclude_processed %}
        {{ return("[]") }}
      {% else %}
        {{ exceptions.raise_compiler_error("No calculation linkbases found at " ~ pattern) }}
      {% endif %}
    {% endif %}
    {{ return("['" ~ files | join("', '") ~ "']") }}
  {% else %}
    {{ return("[]") }}
  {% endif %}
{% endmacro %}
