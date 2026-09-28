{#
  The taxonomy a Data Set tag belongs to, read from its version string.

  A version looks like `us-gaap/2017`, or the accession number of the filing that
  declared the tag when the tag is the filer's own.

  SEC's Data Sets name the IFRS taxonomy `ifrs`, while the companyfacts API and
  config/tag_mappings.yml both name it `ifrs-full`. Left alone, no IFRS tag in the
  Data Sets ever matches a mapping rule, so Atlassian's dimensional facts could
  never be recovered and its mappings could never be verified against a linkbase.
  Nothing was numerically wrong, because no IFRS fact sits on a summable axis today,
  but the mechanism was dead for that filer and silently so.

  Normalising here rather than at each join means every model agrees on one spelling.
#}
{% macro taxonomy_from_version(version) %}
    case
        when split_part({{ version }}, '/', 1) = 'ifrs' then 'ifrs-full'
        else split_part({{ version }}, '/', 1)
    end
{%- endmacro %}
