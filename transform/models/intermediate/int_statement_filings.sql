{#
  Which single filing to read a whole statement from.

  Every value is resolved on its own, taking the latest figure filed for it. That
  is the right answer to "what is this number", and the wrong one to "show me a
  balance sheet", because a company can restate one line of an old statement and
  never re-report the rest. Salesforce revised its equity at 31 January 2017 from
  7,500.1 million to 8,230.0 million when ASC 606 took effect, and never published
  assets or liabilities for that date again. Assembling the latest of each leaves
  the balance sheet 729.9 million out.

  So a statement also needs a source: one filing that reported it as a whole. The
  filing chosen here covers the most of the statement's published concepts, and
  among equals the most recently filed. Coverage comes first deliberately. Most
  recent first would select the 2020 10-K that reports Salesforce's 2017 equity
  alone, and call one line a balance sheet.

  Only reported values count. A derived value is computed from resolved figures
  rather than taken from a filing, so it has no filed counterpart and is left out
  of both the choice and the coverage count.

  This model picks the filing. The values it holds are attached to the facts in
  the mart, where the row grain lives.
#}

{{ config(materialized='table') }}

with published as (

    select
        cik,
        ticker,
        statement,
        concept,
        period_start,
        period_end,
        basis
    from {{ ref('int_facts') }}
    where confidence != 'derived'

),

statement_size as (

    select
        cik,
        statement,
        period_start,
        period_end,
        count(*) as concepts_published
    from published
    group by all

),

{#- How much of the published statement each filing reported. Matching on basis
    keeps an IFRS filing from being credited for US GAAP values. -#}
candidates as (

    select
        published.cik,
        published.ticker,
        published.statement,
        published.period_start,
        published.period_end,
        mapped.accession,
        mapped.form,
        mapped.filed_date,
        count(*) as concepts_covered
    from published
    join {{ ref('int_facts_mapped') }} as mapped
        on mapped.cik = published.cik
        and mapped.concept = published.concept
        -- Balance sheet facts are instants with no start date, and a plain
        -- equality never matches null.
        and mapped.period_start is not distinct from published.period_start
        and mapped.period_end = published.period_end
        and mapped.basis = published.basis
    group by all

),

ranked as (

    select
        candidates.*,
        statement_size.concepts_published,
        row_number() over (
            partition by
                candidates.cik,
                candidates.statement,
                candidates.period_start,
                candidates.period_end
            -- Coverage first, then recency. The accession only breaks a tie
            -- between two filings of the same day, so the choice is stable.
            order by
                candidates.concepts_covered desc,
                candidates.filed_date desc,
                candidates.accession desc
        ) as pick
    from candidates
    join statement_size
        on statement_size.cik = candidates.cik
        and statement_size.statement = candidates.statement
        and statement_size.period_start is not distinct from candidates.period_start
        and statement_size.period_end = candidates.period_end

)

select
    cik,
    ticker,
    statement,
    period_start,
    period_end,
    accession as statement_accession,
    form as statement_form,
    filed_date as statement_filed_date,
    concepts_covered,
    concepts_published,
    -- False where no single filing reported everything the mart publishes, so a
    -- statement read from one source will have a hole in it.
    concepts_covered = concepts_published as covers_whole_statement
from ranked
where pick = 1
