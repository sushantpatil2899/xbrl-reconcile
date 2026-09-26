-- One row per filing in the landed Data Set quarters. This is the only file that
-- maps a filing (adsh) to a company, so every other model joins through it.
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
    regexp_extract(s.filename, 'fsds/([0-9]{4}q[1-4])/', 1) as quarter
from read_csv(
    {{ landed_quarters('sub') }},
    delim = '\t',
    header = true,
    quote = '',
    filename = true,
    all_varchar = true
) s
join {{ ref('stg_companies') }} c on c.cik = cast(s.cik as bigint)
