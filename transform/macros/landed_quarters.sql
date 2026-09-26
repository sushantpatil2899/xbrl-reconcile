{# Returns a SQL list of the landed Data Set files for one part (sub, num, pre,
   tag). Each quarter is a folder, and a quarter is never revised by SEC, so
   there is no newest-per-company rule here: every landed quarter counts. #}
{% macro landed_quarters(part) %}
  {% set pattern = var('raw_root') ~ '/fsds/*/' ~ part ~ '.tsv.gz' %}

  {% if execute %}
    {% set results = run_query("select file from glob('" ~ pattern ~ "') order by file") %}
    {% set files = results.columns[0].values() %}
    {% if files | length == 0 %}
      {{ exceptions.raise_compiler_error("No Data Set quarters found at " ~ pattern) }}
    {% endif %}
    {{ return("['" ~ files | join("', '") ~ "']") }}
  {% else %}
    {{ return("[]") }}
  {% endif %}
{% endmacro %}
