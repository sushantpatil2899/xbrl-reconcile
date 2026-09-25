-- Per company exceptions to the global mapping order. `prefer` puts a tag ahead
-- of the global list for that company; `ignore` removes a tag from
-- consideration entirely, which is different from ranking it last.
select
    cik,
    concept,
    mode,
    taxonomy,
    tag,
    position,
    from_year,
    through_year,
    note,
    filename as source_file
from read_json(
    {{ newest_config_snapshot('tag_mapping_overrides') }},
    columns = {
        cik: 'BIGINT',
        concept: 'VARCHAR',
        mode: 'VARCHAR',
        taxonomy: 'VARCHAR',
        tag: 'VARCHAR',
        position: 'INTEGER',
        from_year: 'INTEGER',
        through_year: 'INTEGER',
        note: 'VARCHAR'
    },
    format = 'array',
    filename = true
)
