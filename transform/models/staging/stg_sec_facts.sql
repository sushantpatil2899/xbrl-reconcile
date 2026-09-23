{#
  One row per fact as SEC reported it. Nothing is deduplicated here: the same
  business key appears once per filing that reported it, which is how
  restatements stay visible downstream.

  The JSON schema is given explicitly rather than auto detected because `cik`
  is a number in most files and a zero padded string in others.
#}

{% set fact_struct %}
STRUCT("start" DATE, "end" DATE, val DOUBLE, accn VARCHAR, fy INT, fp VARCHAR,
       form VARCHAR, filed DATE, frame VARCHAR)
{% endset %}

{% set facts_schema %}
MAP(VARCHAR, MAP(VARCHAR, STRUCT(label VARCHAR, description VARCHAR,
    units MAP(VARCHAR, {{ fact_struct }}[]))))
{% endset %}

with files as (

    select
        cik as cik_raw,
        "entityName" as entity_name,
        facts,
        filename as source_file
    from read_json(
        {{ newest_snapshots('companyfacts') }},
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
    f.source_file
from flattened f
left join {{ ref('stg_companies') }} c
    on cast(f.cik_raw as bigint) = c.cik
