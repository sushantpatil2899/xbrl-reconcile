{# Returns the path of the newest config snapshot written by the ingestion run.
   Config is stored as data in the bucket, so there is one source of truth
   (config/companies.yml) and no copy committed to git. #}
{% macro newest_config_snapshot(name) %}
  {% set pattern = var('raw_root') ~ '/config/' ~ name ~ '/*.json' %}

  {% if execute %}
    {% set results = run_query("select max(file) as file from glob('" ~ pattern ~ "')") %}
    {% set newest = results.columns[0].values()[0] %}
    {% if newest is none %}
      {{ exceptions.raise_compiler_error("No config snapshot found at " ~ pattern) }}
    {% endif %}
    {{ return("'" ~ newest ~ "'") }}
  {% else %}
    {{ return("''") }}
  {% endif %}
{% endmacro %}
