-- Corrections to the scale a filer tagged a value at, read from the snapshot the
-- ingestion run wrote. Not a mapping: the tag is right and the number is out by a
-- factor, which XBRL's `decimals` attribute records and companyfacts does not expose.
-- One row per override and filing, because that is the grain the error has.
select
    cik,
    concept,
    multiply_by,
    accession,
    from_period_end,
    through_period_end,
    note,
    filename as source_file
from read_json(
    {{ newest_config_snapshot('tag_scale_overrides') }},
    columns = {
        cik: 'BIGINT',
        concept: 'VARCHAR',
        multiply_by: 'DOUBLE',
        accession: 'VARCHAR',
        from_period_end: 'DATE',
        through_period_end: 'DATE',
        note: 'VARCHAR'
    },
    format = 'array',
    filename = true
)
