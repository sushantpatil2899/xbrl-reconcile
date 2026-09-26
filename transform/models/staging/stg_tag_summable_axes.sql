-- Axes whose members partition whatever they break down. Summing the members of
-- such an axis recovers a total the company never tagged. Listing an axis here is
-- a claim about the axis: that its members are disjoint parts of one whole.
select
    axis,
    confidence,
    note,
    filename as source_file
from read_json(
    {{ newest_config_snapshot('tag_summable_axes') }},
    columns = {axis: 'VARCHAR', confidence: 'VARCHAR', note: 'VARCHAR'},
    format = 'array',
    filename = true
)
