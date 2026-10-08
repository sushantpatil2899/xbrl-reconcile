-- Phrases a filer's own presentation label is expected to contain for a tag mapped
-- to a concept. Read from the snapshot the ingestion run wrote, so the expectation
-- lives in config beside the mapping it guards.
select
    concept,
    phrase,
    filename as source_file
from read_json(
    {{ newest_config_snapshot('tag_label_hints') }},
    columns = {concept: 'VARCHAR', phrase: 'VARCHAR'},
    format = 'array',
    filename = true
)
