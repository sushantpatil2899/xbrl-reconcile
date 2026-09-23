-- Company config as a table so models can join ticker and group onto facts.
-- Read from the config snapshot the ingestion run wrote to the bucket, which
-- keeps config/companies.yml the single source of truth.
select
    cik,
    cik10,
    ticker,
    name as company_name,
    description,
    group_name,
    start_year,
    end_year,
    enabled,
    filename as source_file
from read_json(
    {{ newest_config_snapshot('companies') }},
    columns = {
        cik: 'BIGINT',
        cik10: 'VARCHAR',
        ticker: 'VARCHAR',
        name: 'VARCHAR',
        description: 'VARCHAR',
        group_name: 'VARCHAR',
        start_year: 'INTEGER',
        end_year: 'INTEGER',
        enabled: 'BOOLEAN'
    },
    format = 'array',
    filename = true
)
