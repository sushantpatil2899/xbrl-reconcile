{# Path of the ingestion state file, which carries the last_run heartbeat. #}
{% macro state_file() %}
  {{ return("'" ~ var('raw_root') ~ "/sec/_state/last_seen.json'") }}
{% endmacro %}
