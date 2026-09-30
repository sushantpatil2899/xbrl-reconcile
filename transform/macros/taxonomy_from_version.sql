{#
  The taxonomy a Data Set tag belongs to, read from its version string.

  A version looks like `us-gaap/2017`, or the accession number of the filing that
  declared the tag when the tag is the filer's own. The spelling rule itself lives
  in normalised_taxonomy, which the calculation arcs share.
#}
{% macro taxonomy_from_version(version) %}
    {{ normalised_taxonomy("split_part(" ~ version ~ ", '/', 1)") }}
{%- endmacro %}
