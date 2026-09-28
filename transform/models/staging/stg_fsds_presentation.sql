{#
  Where each tag sits on each statement, from the presentation linkbase.

  SEC flattens every filing's presentation linkbase into pre.txt, which Phase 4 has
  been landing since it started and which nothing has read until now. Phase 4's
  filter touches three of its columns to decide which rows belong to our companies
  and stores the rest as published.

  This is evidence a calculation linkbase cannot give. `stmt` says which statement
  the filer put a tag on, `line` says where, and `plabel` is the label the filer
  chose for it. The label is the only evidence available for a tag like
  EarningsPerShareBasicAndDiluted, where our mapping rests on a semantic
  equivalence rather than on arithmetic: a filer labelling it "Diluted net loss per
  share" meant it as the diluted figure. `inpth` marks a tag shown parenthetically
  beside a line rather than as a line, which is something no total should ever be.

  Three column names here are certain, because Phase 4's byte level filter looks
  adsh, tag and version up by name and 69 quarters have landed. The rest come from
  SEC's published schema. `all_varchar` with selection by name is what makes that
  safe: a name that is wrong fails the build naming the column, rather than shifting
  a field silently.

  `stmt` is translated into the statement vocabulary the rest of the project uses,
  the same way stg_fsds_facts translates `qtrs` into period_kind. The raw code is
  kept beside it, and the statements we have no concepts for stay null rather than
  being forced into one of ours.
#}

with lines as (

    select
        p.adsh as accession,
        try_cast(p.report as integer) as report,
        try_cast(p.line as integer) as line,
        p.stmt as statement_code,
        p.tag,
        p.version as declared_version,
        nullif(p.plabel, '') as filer_label,
        p.inpth = '1' as is_parenthetical,
        p.negating = '1' as is_negated,
        regexp_extract(p.filename, 'fsds/([0-9]{4}q[1-4])/', 1) as quarter
    from read_csv(
        {{ landed_quarters('pre') }},
        delim = '\t',
        header = true,
        quote = '',
        filename = true,
        all_varchar = true
    ) p

)

select
    lines.accession,
    submissions.cik,
    submissions.ticker,
    lines.report,
    lines.line,
    lines.statement_code,
    -- The statements we hold concepts for. EQ, CI, CP and UN stay null: the rows are
    -- kept because they are evidence about tags we may map later.
    case lines.statement_code
        when 'IS' then 'income_statement'
        when 'BS' then 'balance_sheet'
        when 'CF' then 'cash_flow'
    end as statement,
    lines.tag,
    lines.declared_version,
    -- A custom tag's version is the accession of the filing that declared it, so the
    -- stable form is custom:<Tag>, exactly as the fact and tag models do it.
    coalesce(tags.taxonomy, {{ taxonomy_from_version('lines.declared_version') }}) as taxonomy,
    coalesce(tags.taxonomy, {{ taxonomy_from_version('lines.declared_version') }})
        || ':' || lines.tag as qualified_tag,
    coalesce(tags.is_custom, false) as is_custom,
    lines.filer_label,
    lines.is_parenthetical,
    lines.is_negated,
    lines.quarter
from lines
join {{ ref('stg_fsds_submissions') }} as submissions
    on submissions.accession = lines.accession
left join {{ ref('stg_fsds_tags') }} as tags
    on tags.tag = lines.tag
    and tags.declared_version = lines.declared_version
