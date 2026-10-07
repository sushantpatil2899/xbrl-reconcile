-- The canonical concepts, published so the API can present a statement in order.
--
-- position, is_additive and is_optional all exist in config and reach staging, but
-- none of them is published, so a reader of the Parquet can see that revenue and
-- cost_of_revenue belong to the income statement and not which comes first. The
-- statement marts encode the order in their column order, which JSON cannot carry.
--
-- Deliberately free of counts. How many companies report a concept is a measurement
-- over mart_financials, which a caller can take at query time for nothing, and
-- mixing it in here would turn a projection of config into something half measured.
select distinct
    concept,
    statement,
    position,
    unit,
    is_additive,
    is_optional
from {{ ref('stg_tag_mappings') }}
order by statement, position
