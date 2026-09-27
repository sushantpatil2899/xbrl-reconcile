{#
  One statement as a person reads it: a row per period, a column per line.

  The grain is the period, not the fiscal year. ServiceNow has two fiscal years
  both labelled 2011, because it moved its year end from June to December, and
  keying on the period lets both appear as their own row instead of forcing a
  choice between them.

  Only the latest figure for each line is shown. Where a later filing revised one
  line of an old statement on its own, `incoherent_lines` counts it, and the long
  mart holds the figure the chosen filing actually published.
#}
{% macro statement_view(statement) %}

select
    facts.cik,
    facts.ticker,
    facts.company_name,
    facts.period_start,
    facts.period_end,
    facts.period_kind,
    facts.period_days,
    facts.fiscal_year,
    facts.fiscal_quarter,
    facts.calendar_year_equivalent,
    facts.fiscal_year_end,
    facts.is_year_end,
    {{ statement_lines(statement) }},
    -- Two Atlassian balance sheets carry lines under both rulebooks, so this is
    -- aggregated rather than assumed to be one value.
    string_agg(distinct facts.basis, ' and ' order by facts.basis) as basis,
    max(facts.statement_accession) as statement_accession,
    max(facts.statement_form) as statement_form,
    max(facts.statement_filed_date) as statement_filed_date,
    bool_and(coalesce(facts.statement_covers_whole, true)) as statement_covers_whole,
    count(*) filter (where facts.is_coherent = false) as incoherent_lines
from {{ ref('mart_financials') }} as facts
where facts.statement = '{{ statement }}'
group by all

{% endmacro %}
