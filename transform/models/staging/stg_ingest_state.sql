-- One row describing the last ingestion run. `last_run` is written on every
-- run, including runs that download nothing, so it reports whether ingestion
-- is alive rather than whether companies happened to file anything.
select
    strptime(last_run, '%Y-%m-%dT%H%M%SZ') as last_run_at,
    date_diff('day', strptime(last_run, '%Y-%m-%dT%H%M%SZ'), now()::timestamp) as days_since_run,
    len(json_keys(companies)) as companies_tracked
from read_json(
    {{ state_file() }},
    columns = {last_run: 'VARCHAR', companies: 'JSON'}
)
