-- The mapping rules as a table: which raw tag means which canonical concept,
-- in which order, with what confidence. Read from the snapshot the ingestion
-- run wrote, so config/tag_mappings.yml stays the single source of truth.
select
    concept,
    statement,
    unit,
    is_optional,
    is_additive,
    taxonomy,
    tag,
    priority,
    confidence,
    note,
    filename as source_file
from read_json(
    {{ newest_config_snapshot('tag_mappings') }},
    columns = {
        concept: 'VARCHAR',
        statement: 'VARCHAR',
        unit: 'VARCHAR',
        is_optional: 'BOOLEAN',
        is_additive: 'BOOLEAN',
        taxonomy: 'VARCHAR',
        tag: 'VARCHAR',
        priority: 'INTEGER',
        confidence: 'VARCHAR',
        note: 'VARCHAR'
    },
    format = 'array',
    filename = true
)
