{#
  Tag definitions as each landed quarter declares them.

  The grain is (tag, declared_version, quarter), one row per quarter that carried a
  definition, which is what lets this model be incremental: it can record which
  quarters it has read. A quarter never changes once landed unless the ingestion job
  re-lands it, and then only that quarter's rows are replaced.

  Consumers want one row per tag and version, not one per quarter, so stg_fsds_tags
  sits over this and dedupes. That split exists only because an incremental model
  needs a ledger of what it has processed and a deduplicated one cannot carry it.
#}

{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='quarter'
) }}

{#- Every ref below sits inside the conditional branch, where dbt cannot see it
    while parsing. These hints declare them explicitly. -#}
-- depends_on: {{ ref('stg_fsds_quarters') }}

{#- What is still to read. Anything already stored at the version the ingestion
    job recorded is skipped, so a run with nothing new reads no raw files at all. -#}
{% set files_to_read = landed_quarters('tag', exclude_processed=is_incremental()) %}

{% if files_to_read == '[]' %}

{#- Nothing to read. Selecting the existing table's shape with no rows leaves it
    untouched, which is what a quiet day should cost. -#}
select * from {{ this }} where false

{% else %}

select distinct
    regexp_extract(t.filename, 'fsds/([0-9]{4}q[1-4])/', 1) as quarter,
    state.landed_at,
    t.tag,
    t.version as declared_version,
    t.custom = '1' as is_custom,
    case
        when t.custom = '1' then 'custom'
        else {{ taxonomy_from_version('t.version') }}
    end as taxonomy,
    t.abstract = '1' as is_abstract,
    t.datatype,
    t.iord as instant_or_duration,
    t.crdr as credit_or_debit,
    t.tlabel as label
from read_csv(
    {{ files_to_read }},
    delim = '\t',
    header = true,
    quote = '',
    filename = true,
    all_varchar = true
) t
join {{ ref('stg_fsds_quarters') }} state
    on state.quarter = regexp_extract(t.filename, 'fsds/([0-9]{4}q[1-4])/', 1)

{% endif %}
