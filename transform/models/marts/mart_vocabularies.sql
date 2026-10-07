-- The vocabularies, published so the API can describe every value it accepts.
--
-- Nothing is computed here. It is a projection of config, published as Parquet with
-- the rest of the marts so the serving layer reads one kind of thing from one place
-- rather than opening the config file as a second source that can drift.
select
    vocabulary,
    vocabulary_description,
    value,
    description,
    position
from {{ ref('stg_vocabularies') }}
order by vocabulary, position
