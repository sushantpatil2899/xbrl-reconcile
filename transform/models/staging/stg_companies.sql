-- Company config as a table so models can join ticker and group onto facts.
select
    cik,
    cik10,
    ticker,
    name as company_name,
    description,
    group_name,
    start_year,
    end_year,
    enabled
from {{ ref('companies') }}
