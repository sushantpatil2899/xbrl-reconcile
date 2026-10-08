{#
  The filers' own arithmetic: one row per parent, child and weight, from the
  calculation linkbase of every report, annual and quarterly.

  This is the only source in the project that says a tag is part of another tag.
  The presentation linkbase says where a tag sits; the Data Sets say what it was
  worth; only this says that CostOfServices is a component of CostOfRevenue for one
  filer and the cost line itself for another.

  Two things are typed rather than taken as written.

  `weight` is cast, because filers spell the same number differently. Salesforce
  wrote 1 in some years and 1.00 in others, for 354 and 71 arcs respectively, so any
  comparison on the raw text would split one weight into two.

  A concept is the filer's own when the schema declaring it is referenced
  relatively, because that schema sits in the filing's own directory. A standard
  concept is referenced by absolute URL to the taxonomy that defines it. That is
  definitional rather than a guess about prefixes, and a test asserts the two
  signals never contradict each other.

  The role is kept whole. A filing carries around a hundred networks, most of them
  footnote detail, and the role names are the filer's own words: one company wrote
  ConsolidatedStatementsOfCashFlows, StatementOfCashFlowsIndirect and
  StatementConsolidatedStatementsOfCashFlows across three years for the same
  statement. Classifying them is not a staging concern, and pre.txt already says
  which statement a tag appears on.
#}

{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns',
    unique_key='accession'
) }}

{#- Every ref below sits inside the conditional branch, where dbt cannot see it
    while parsing. These hints declare them explicitly. -#}
-- depends_on: {{ ref('stg_linkbase_filings') }}
-- depends_on: {{ ref('stg_companies') }}

{#- What is still to read. A filing is immutable, so the only reason to read one
    again is a re-parse, which the state file records. 259 files on the first run,
    none on a quiet one. -#}
{% set files_to_read = landed_linkbases(exclude_processed=is_incremental()) %}

{% if files_to_read == '[]' %}

select * from {{ this }} where false

{% else %}

with arcs as (

    select
        regexp_extract(a.filename, 'cik=([0-9]{10})/', 1) as cik10,
        regexp_extract(a.filename, 'cik=[0-9]{10}/([^/]+)/arcs.json', 1) as accession,
        a.role,
        a.parent,
        a.parent_schema,
        a.child,
        a.child_schema,
        try_cast(a.weight as double) as weight,
        try_cast(a."order" as double) as arc_order,
        a.filename as source_file
    from read_json(
        {{ files_to_read }},
        columns = {
            role: 'VARCHAR',
            parent: 'VARCHAR',
            parent_schema: 'VARCHAR',
            child: 'VARCHAR',
            child_schema: 'VARCHAR',
            weight: 'VARCHAR',
            "order": 'VARCHAR'
        },
        format = 'array',
        filename = true
    ) a

)

select
    arcs.accession,
    state.parsed_at,
    companies.cik,
    companies.ticker,
    arcs.role,
    -- The last segment, for reading. The full role is what identifies the network.
    regexp_extract(arcs.role, '([^/]+)$', 1) as role_name,
    regexp_replace(arcs.parent, '^[^_]+_', '') as parent_tag,
    case
        when arcs.parent_schema not like 'http%' then 'custom'
        else {{ normalised_taxonomy("split_part(arcs.parent, '_', 1)") }}
    end as parent_taxonomy,
    case
        when arcs.parent_schema not like 'http%'
            then 'custom:' || regexp_replace(arcs.parent, '^[^_]+_', '')
        else {{ normalised_taxonomy("split_part(arcs.parent, '_', 1)") }}
            || ':' || regexp_replace(arcs.parent, '^[^_]+_', '')
    end as parent_qualified_tag,
    regexp_replace(arcs.child, '^[^_]+_', '') as child_tag,
    case
        when arcs.child_schema not like 'http%' then 'custom'
        else {{ normalised_taxonomy("split_part(arcs.child, '_', 1)") }}
    end as child_taxonomy,
    case
        when arcs.child_schema not like 'http%'
            then 'custom:' || regexp_replace(arcs.child, '^[^_]+_', '')
        else {{ normalised_taxonomy("split_part(arcs.child, '_', 1)") }}
            || ':' || regexp_replace(arcs.child, '^[^_]+_', '')
    end as child_qualified_tag,
    arcs.weight,
    arcs.arc_order,
    arcs.parent_schema,
    arcs.child_schema,
    arcs.source_file
from arcs
join {{ ref('stg_companies') }} as companies on companies.cik10 = arcs.cik10
join {{ ref('stg_linkbase_filings') }} as state on state.accession = arcs.accession

{% endif %}
