{#
  One row per fact as SEC reported it. Nothing is deduplicated here: the same
  business key appears once per filing that reported it, which is how
  restatements stay visible downstream.

  The JSON schema is given explicitly rather than auto detected because `cik`
  is a number in most files and a zero padded string in others.
#}

{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='cik'
) }}

{#- ref() below sits inside a conditional branch, so dbt cannot see the
    dependency while parsing. This hint declares it explicitly. -#}
-- depends_on: {{ ref('stg_companies') }}

{#- Files still to process. When the table already exists, snapshots recorded in
    its source_file column are skipped, so a quiet day reads nothing. -#}
{% set snapshot_files = newest_snapshots('companyfacts', exclude_processed=is_incremental()) %}

{% set fact_struct %}
STRUCT("start" DATE, "end" DATE, val DOUBLE, accn VARCHAR, fy INT, fp VARCHAR,
       form VARCHAR, filed DATE, frame VARCHAR)
{% endset %}

{% set facts_schema %}
MAP(VARCHAR, MAP(VARCHAR, STRUCT(label VARCHAR, description VARCHAR,
    units MAP(VARCHAR, {{ fact_struct }}[]))))
{% endset %}

{% if snapshot_files == '[]' %}

-- Nothing new to process. Selecting no rows leaves the table untouched.
select * from {{ this }} where false

{% else %}

with files as (

    select
        cik as cik_raw,
        "entityName" as entity_name,
        facts,
        filename as source_file
    from read_json(
        {{ snapshot_files }},
        columns = {cik: 'VARCHAR', entityName: 'VARCHAR', facts: '{{ facts_schema }}'},
        filename = true
    )

),

taxonomies as (

    select
        cik_raw,
        entity_name,
        source_file,
        unnest(map_entries(facts)) as taxonomy_entry
    from files

),

concepts as (

    select
        cik_raw,
        entity_name,
        source_file,
        taxonomy_entry.key as taxonomy,
        unnest(map_entries(taxonomy_entry.value)) as concept_entry
    from taxonomies

),

units as (

    select
        cik_raw,
        entity_name,
        source_file,
        taxonomy,
        concept_entry.key as concept,
        concept_entry.value.label as concept_label,
        unnest(map_entries(concept_entry.value.units)) as unit_entry
    from concepts

),

flattened as (

    select
        cik_raw,
        entity_name,
        source_file,
        taxonomy,
        concept,
        concept_label,
        unit_entry.key as unit,
        unnest(unit_entry.value) as fact
    from units

)

select
    cast(f.cik_raw as bigint) as cik,
    f.entity_name,
    c.ticker,
    f.taxonomy,
    f.concept,
    f.concept_label,
    f.unit,
    f.fact."start" as period_start,
    f.fact."end" as period_end,
    case when f.fact."start" is null then 'instant' else 'duration' end as period_type,
    date_diff('day', f.fact."start", f.fact."end") as period_days,
    f.fact.val as value,
    f.fact.accn as accession,
    f.fact.form,
    f.fact.filed as filed_date,
    f.fact.frame,
    -- Rows that fail a data quality rule stay in staging so they can be counted
    -- and inspected. Downstream models read only rows where is_valid is true.
    (
        c.ticker is not null
        and f.fact.val is not null
        and f.fact.accn is not null
        and f.fact.filed is not null
    ) as is_valid,
    f.source_file
from flattened f
left join {{ ref('stg_companies') }} c
    on cast(f.cik_raw as bigint) = c.cik

{% endif %}
