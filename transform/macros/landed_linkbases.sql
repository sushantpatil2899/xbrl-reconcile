{# Returns a SQL list of the landed calculation linkbase files. A filing is
   immutable once accepted, so there is no newest-per-filing rule here: every
   accession appears once. #}
{% macro landed_linkbases() %}
  {% set pattern = var('raw_root') ~ '/linkbase/cik=*/*/arcs.json' %}

  {% if execute %}
    {% set results = run_query("select file from glob('" ~ pattern ~ "') order by file") %}
    {% set files = results.columns[0].values() %}
    {% if files | length == 0 %}
      {{ exceptions.raise_compiler_error("No calculation linkbases found at " ~ pattern) }}
    {% endif %}
    {{ return("['" ~ files | join("', '") ~ "']") }}
  {% else %}
    {{ return("[]") }}
  {% endif %}
{% endmacro %}
