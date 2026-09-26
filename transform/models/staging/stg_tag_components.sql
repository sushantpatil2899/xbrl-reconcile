-- Tags that sum to a concept, for filers that never report the total. One row
-- per set and tag, so SQL can group by position and add them up.
select
    concept,
    statement,
    unit,
    taxonomy,
    tag,
    position,
    component_count,
    confidence,
    note,
    filename as source_file
from read_json(
    {{ newest_config_snapshot('tag_components') }},
    columns = {
        concept: 'VARCHAR',
        statement: 'VARCHAR',
        unit: 'VARCHAR',
        taxonomy: 'VARCHAR',
        tag: 'VARCHAR',
        position: 'INTEGER',
        component_count: 'INTEGER',
        confidence: 'VARCHAR',
        note: 'VARCHAR'
    },
    format = 'array',
    filename = true
)
