{#
  The two signals about whether a tag is the filer's own must not contradict.

  A concept declared in the filing's own schema is referenced relatively, and its
  prefix is the filer's short name. A standard concept is referenced by absolute URL
  and its prefix is the taxonomy. If a concept ever appears with a relative schema
  but a standard prefix, or the reverse, then one of the two signals is wrong and the
  custom determination cannot be trusted.

  Nothing in the landed data does this today. The test exists because the rule is
  definitional only as long as filers keep referencing standard taxonomies by URL.
#}

with concepts as (

    select parent_qualified_tag as qualified_tag, parent_schema as schema, parent_taxonomy as taxonomy
    from {{ ref('stg_calculation_arcs') }}

    union

    select child_qualified_tag, child_schema, child_taxonomy
    from {{ ref('stg_calculation_arcs') }}

)

select
    qualified_tag,
    schema,
    taxonomy
from concepts
where
    -- Declared in the filer's own schema, yet named as though standard.
    (taxonomy = 'custom' and split_part(qualified_tag, ':', 2) like '%-%')
    -- Or referenced from a taxonomy URL, yet the prefix is not a taxonomy we know.
    or (taxonomy not in ('custom', 'us-gaap', 'ifrs-full', 'dei', 'srt', 'us-gaap-sup'))
