-- Tag definitions from the landed quarters, including the custom flag and the
-- human label. A custom tag's version is the accession number of the filing that
-- declared it, so the same concept appears under a new version every filing. The
-- stable form is custom:<Tag>, scoped to a company by the facts that use it.
select distinct
    t.tag,
    t.version as declared_version,
    t.custom = '1' as is_custom,
    case when t.custom = '1' then 'custom' else split_part(t.version, '/', 1) end as taxonomy,
    t.abstract = '1' as is_abstract,
    t.datatype,
    t.iord as instant_or_duration,
    t.crdr as credit_or_debit,
    t.tlabel as label
from read_csv(
    {{ landed_quarters('tag') }},
    delim = '\t',
    header = true,
    quote = '',
    all_varchar = true
) t
