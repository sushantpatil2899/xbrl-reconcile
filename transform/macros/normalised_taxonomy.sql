{#
  One spelling for a taxonomy name.

  SEC's Data Sets and its concept prefixes both say `ifrs`, while the companyfacts
  API and config/tag_mappings.yml say `ifrs-full`. Left alone, no IFRS tag from
  either source ever matches a mapping rule, which is how Atlassian's dimensional
  facts became unreachable without any number looking wrong.
#}
{% macro normalised_taxonomy(prefix) %}
    case when {{ prefix }} = 'ifrs' then 'ifrs-full' else {{ prefix }} end
{%- endmacro %}
