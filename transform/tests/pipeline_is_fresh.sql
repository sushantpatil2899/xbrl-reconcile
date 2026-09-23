-- Warns when ingestion has not run recently. The data is still correct, just
-- old, so this does not fail the build.
{{ config(severity='warn') }}

select
    last_run_at,
    days_since_run
from {{ ref('stg_ingest_state') }}
where days_since_run > {{ var('freshness_warn_days') }}
