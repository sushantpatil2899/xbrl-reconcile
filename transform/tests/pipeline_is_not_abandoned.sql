-- Fails when ingestion has been silent long enough that something is broken:
-- a stopped schedule, expired credentials, or a workflow paused by GitHub.
select
    last_run_at,
    days_since_run
from {{ ref('stg_ingest_state') }}
where days_since_run > {{ var('freshness_error_days') }}
