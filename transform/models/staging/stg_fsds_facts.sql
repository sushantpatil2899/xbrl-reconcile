{#
  One row per fact from the landed Data Set quarters. These carry what
  companyfacts drops: facts broken down by dimension, and custom tags.

  Two translations happen here.

  `qtrs` becomes period_kind, using the same vocabulary as the rest of the
  project: 0 is an instant, 1 a quarter, 2 a half, 3 nine months, 4 a year.

  `segments` is parsed only when it holds exactly one Axis=Member pair. A fact
  broken down by two dimensions at once cannot be summed with its siblings
  without double counting, so those keep the raw string and are excluded from
  any total. That is the safety mechanism the dimension summing relies on.
#}

{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='quarter'
) }}

{#- Every ref below sits inside the conditional branch, where dbt cannot see it
    while parsing. These hints declare them explicitly. -#}
-- depends_on: {{ ref('stg_fsds_quarters') }}
-- depends_on: {{ ref('stg_fsds_submissions') }}
-- depends_on: {{ ref('stg_fsds_tags') }}

{#- What is still to read. Anything already stored at the version the ingestion
    job recorded is skipped, so a run with nothing new reads no raw files at all. -#}
{% set files_to_read = landed_quarters('num', exclude_processed=is_incremental()) %}

{% if files_to_read == '[]' %}

{#- Nothing to read. Selecting the existing table's shape with no rows leaves it
    untouched, which is what a quiet day should cost. -#}
select * from {{ this }} where false

{% else %}

with raw_facts as (

    select
        regexp_extract(n.filename, 'fsds/([0-9]{4}q[1-4])/', 1) as quarter,
        n.adsh as accession,
        n.tag,
        n.version as declared_version,
        n.ddate,
        n.qtrs,
        n.uom as unit,
        nullif(n.segments, '') as segments,
        nullif(n.coreg, '') as coregistrant,
        try_cast(n.value as double) as value
    from read_csv(
        {{ files_to_read }},
        delim = '\t',
        header = true,
        quote = '',
        filename = true,
        all_varchar = true
    ) n

),

with_dimensions as (

    select
        *,
        -- Segments look like `Axis=Member;` and may repeat. One pair can be
        -- parsed; several cannot be treated as a breakdown of one total.
        length(segments) - length(replace(segments, ';', '')) as pair_count
    from raw_facts

)

select
    f.quarter,
    state.landed_at,
    f.accession,
    s.cik,
    s.ticker,
    s.form,
    s.filed_date,
    f.tag,
    f.declared_version,
    t.is_custom,
    coalesce(t.taxonomy, {{ taxonomy_from_version('f.declared_version') }}) as taxonomy,
    -- The stable name a mapping rule can refer to, matching the config's
    -- taxonomy:Tag convention.
    coalesce(t.taxonomy, {{ taxonomy_from_version('f.declared_version') }}) || ':' || f.tag
        as qualified_tag,
    t.label as tag_label,
    try_strptime(f.ddate, '%Y%m%d')::date as period_end,
    case f.qtrs
        when '0' then 'instant'
        when '1' then 'quarter'
        when '2' then 'half'
        when '3' then 'nine_month'
        when '4' then 'annual'
        else 'other'
    end as period_kind,
    f.unit,
    f.value,
    f.segments,
    coalesce(f.pair_count, 0) as dimension_count,
    f.segments is null as is_consolidated,
    case when f.pair_count = 1 then split_part(f.segments, '=', 1) end as axis,
    case when f.pair_count = 1 then rtrim(split_part(f.segments, '=', 2), ';') end as member,
    f.coregistrant
from with_dimensions f
join {{ ref('stg_fsds_submissions') }} s on s.accession = f.accession
join {{ ref('stg_fsds_quarters') }} state on state.quarter = f.quarter
left join {{ ref('stg_fsds_tags') }} t
    on t.tag = f.tag and t.declared_version = f.declared_version
where f.value is not null

{% endif %}
