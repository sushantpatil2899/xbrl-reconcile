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
  {% set query %}
    with landed as (
      select file, regexp_extract(file, 'cik=[0-9]{10}/([^/]+)/arcs.json', 1) as accession
      from glob('{{ pattern }}')
    )
    select landed.file
    from landed
    left join {{ ref('stg_linkbase_filings') }} as state on state.accession = landed.accession
    {%- if exclude_processed %}
    left join (
      select accession, max(parsed_at) as processed_at
      from {{ this }}
      group by accession
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
