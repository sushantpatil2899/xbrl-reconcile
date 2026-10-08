{#
  A tag mapped to a concept whose filer never labels it anything we expect.

  This is the check a candidate list cannot make. Finding a new mapping means reading
  the eight tags a company presents and picking one; nothing in that loop questions a
  mapping already in config. Workday labels us-gaap:OperatingExpenses "Total costs and
  expenses" while twenty six other filers label it "Total operating expenses", and its
  figure therefore includes cost of revenue. It overstated operating expenses in 92
  published values and was found by investigation, not by the pipeline.

  The rule is "no label matches", not "some label is rejected". Filers reuse one tag
  across contexts and carry several labels for it: Workday's cost of goods tag carries
  "Total costs and expenses" alongside "Cost of goods and services sold", and failing
  on the bad one would call a sound mapping an error.

  Tags a company already ignores are excluded. The override is the answer to this
  question having been asked once, so leaving them in would fail the build forever on
  a decision already taken.

  Severity is error on purpose. A label that matches nothing means either a filer
  means something different by the tag, or the expectation is incomplete. Both want a
  person, and publishing a number while the question is open is how the Workday
  figures survived thirteen years.
#}

with expected as (

    select concept, phrase
    from {{ ref('stg_label_hints') }}

),

{#- One row per mapped tag and each label its filer gives it. -#}
labelled as (

    select
        evidence.cik,
        evidence.ticker,
        evidence.mapped_concept as concept,
        evidence.qualified_tag,
        evidence.filer_labels,
        lower(trim(label)) as label
    from {{ ref('mart_mapping_evidence') }} as evidence,
        unnest(string_split(evidence.filer_labels, ' | ')) as parts(label)
    where evidence.is_mapped
        and evidence.filer_labels is not null
        and evidence.mapped_concept in (select concept from expected)

),

matched as (

    select
        labelled.cik,
        labelled.ticker,
        labelled.concept,
        labelled.qualified_tag,
        any_value(labelled.filer_labels) as filer_labels,
        bool_or(labelled.label like '%' || expected.phrase || '%') as any_label_expected
    from labelled
    left join expected on expected.concept = labelled.concept
    group by labelled.cik, labelled.ticker, labelled.concept, labelled.qualified_tag

)

select
    ticker,
    concept,
    qualified_tag,
    filer_labels,
    (
        select string_agg(phrase, ', ')
        from expected
        where expected.concept = matched.concept
    ) as expected_one_of
from matched
where not any_label_expected
    and not exists (
        select 1
        from {{ ref('stg_tag_overrides') }} as ignored
        where ignored.mode = 'ignore'
            and ignored.cik = matched.cik
            and ignored.concept = matched.concept
            and ignored.taxonomy || ':' || ignored.tag = matched.qualified_tag
    )
