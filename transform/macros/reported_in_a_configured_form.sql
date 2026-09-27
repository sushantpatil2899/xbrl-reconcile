{#
  Whether a fact came from a form that counts as a report.

  config/companies.yml lists the forms: 10-K, 10-Q, 20-F and their amendments.
  SEC's companyfacts response ignores that list and returns facts from every form
  a company ever filed, including proxy statements and earnings releases whose
  XBRL is tagged for a different purpose, at a different scale, and sometimes
  against the wrong period. A proxy is filed after the 10-K, so under a latest
  filed rule it wins, and Elastic's net income was published five years running
  from its pay versus performance table, a thousand times too small.

  The list is config, so a company that needs another form gets it without a code
  change.
#}
{% macro reported_in_a_configured_form(facts, companies) %}
    list_contains({{ companies }}.report_types, {{ facts }}.form)
{%- endmacro %}
