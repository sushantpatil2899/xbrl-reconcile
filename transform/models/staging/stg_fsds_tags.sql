{#
  One row per tag and declared version, which is the grain every consumer joins on.

  A definition for a given version is identical in every quarter that carries it, so
  the newest quarter's copy is taken and the rest are collapsed. The per quarter rows
  live in stg_fsds_tags_by_quarter, which is incremental because it can record which
  quarters it has read; this cannot, because the quarter is not in its grain.

  A view rather than a table: it is a projection of a table that is already stored.
#}

{{ config(materialized='view') }}

select
    tag,
    declared_version,
    is_custom,
    taxonomy,
    is_abstract,
    datatype,
    instant_or_duration,
    credit_or_debit,
    label
from {{ ref('stg_fsds_tags_by_quarter') }}
qualify row_number() over (
    partition by tag, declared_version
    order by quarter desc
) = 1
