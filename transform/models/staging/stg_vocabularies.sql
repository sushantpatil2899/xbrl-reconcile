-- The vocabularies as a table: every value the pipeline can produce and what it
-- means. Read from the snapshot the ingestion run wrote, so config/vocabularies.yml
-- stays the single source of truth. The declared_in_vocabulary test reads this, which
-- is what stops a model producing a value nobody described.
select
    vocabulary,
    vocabulary_description,
    value,
    description,
    position,
    filename as source_file
from read_json(
    {{ newest_config_snapshot('vocabularies') }},
    columns = {
        vocabulary: 'VARCHAR',
        vocabulary_description: 'VARCHAR',
        value: 'VARCHAR',
        description: 'VARCHAR',
        position: 'INTEGER'
    },
    format = 'array',
    filename = true
)
