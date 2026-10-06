-- One row per filing in the landed Data Set quarters. This is the only file that
-- maps a filing (adsh) to a company, so every other model joins through it.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns',
    unique_key='quarter'
) }}

{#- Every ref below sits inside the conditional branch, where dbt cannot see it
    while parsing. These hints declare them explicitly. -#}
-- depends_on: {{ ref('stg_fsds_quarters') }}
-- depends_on: {{ ref('stg_companies') }}

{#- What is still to read. Anything already stored at the version the ingestion
    job recorded is skipped, so a run with nothing new reads no raw files at all. -#}
{% set files_to_read = landed_quarters('sub', exclude_processed=is_incremental()) %}

{% if files_to_read == '[]' %}

{#- Nothing to read. Selecting the existing table's shape with no rows leaves it
    untouched, which is what a quiet day should cost. -#}
select * from {{ this }} where false

{% else %}

select
    s.adsh as accession,
    s.cik,
    c.ticker,
    s.name as filer_name,
    s.form,
    -- SEC writes dates as YYYYMMDD integers in these files.
    try_strptime(s.period::varchar, '%Y%m%d')::date as period_of_report,
    try_strptime(s.filed::varchar, '%Y%m%d')::date as filed_date,
    s.fy as filing_fiscal_year,
    s.fp as filing_fiscal_period,
    s.detail = 1 as has_detailed_tagging,
    regexp_extract(s.filename, 'fsds/([0-9]{4}q[1-4])/', 1) as quarter,
    state.landed_at
from read_csv(
    {{ files_to_read }},
    delim = '\t',
    header = true,
    quote = '',
    filename = true,
    all_varchar = true
) s
join {{ ref('stg_companies') }} c on c.cik = cast(s.cik as bigint)
join {{ ref('stg_fsds_quarters') }} state
    on state.quarter = regexp_extract(s.filename, 'fsds/([0-9]{4}q[1-4])/', 1)

{% endif %}
