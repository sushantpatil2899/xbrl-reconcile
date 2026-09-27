{#
  The period spine: every period a company reports, labelled once.

  A fiscal year is not a calendar year. Sixteen of these companies end their year
  in January, nine in December, the rest in February, April, June, July or
  November, so one label year covers period ends 335 days apart. Two companies
  changed their year end outright: ServiceNow moved from June to December, Workday
  from December to January. Two more do not end on a fixed date at all, because
  Adobe and Samsara run 52/53 week years whose end drifts by a few days annually.

  So a period's fiscal year cannot be read off its end date, and cannot come from
  one anchor per company either. It comes from the company's own annual periods:
  a period belongs to the fiscal year that the next such year end closes. Where a
  period runs past the newest annual report, or more than a year before the
  nearest one, that year end is stepped whole years to reach it, which keeps the
  company's own month and day rather than assuming a calendar one.

  Two year labels are published, because they answer different questions.
  `fiscal_year` is what the company itself calls the year, which is what a reader
  checking a number against the filing needs. `calendar_year_equivalent` is the
  calendar year holding most of that fiscal year's days, which is what comparing
  companies needs: Salesforce fiscal 2026 and ServiceNow fiscal 2025 cover almost
  the same twelve months of real time, and only the second label says so.

  Both labels are properties of the fiscal year, not of the period, so every
  period inside a fiscal year carries the same pair. Nothing here relabels a
  period onto calendar quarters: a value is never published under a period the
  company did not report.
#}

with periods as (

    select distinct
        cik,
        ticker,
        period_start,
        period_end,
        period_kind
    from {{ ref('int_facts') }}

    union

    -- A derived fourth quarter is a period no filing covers, so it is absent from
    -- int_facts and would otherwise carry no label at all.
    select distinct
        cik,
        ticker,
        period_start,
        period_end,
        period_kind
    from {{ ref('int_facts_quarterly') }}

),

{#- Annual periods are what define a year end, so the fiscal calendar is read off
    the company's own filings rather than assumed. -#}
year_ends as (

    select distinct
        cik,
        period_end as year_end
    from {{ ref('int_facts') }}
    where period_kind = 'annual'

),

newest_year_end as (

    select
        cik,
        max(year_end) as year_end
    from year_ends
    group by cik

),

{#- The first year end at or after each period. The tolerance absorbs the few
    days a 52/53 week year drifts, so a year end landing just before its own
    period start still matches. -#}
matched as (

    select
        periods.cik,
        periods.ticker,
        periods.period_start,
        periods.period_end,
        periods.period_kind,
        min(year_ends.year_end) as next_year_end
    from periods
    left join year_ends
        on year_ends.cik = periods.cik
        and year_ends.year_end
            >= periods.period_end - interval {{ var('year_end_tolerance_days') }} day
    group by all

),

resolved as (

    select
        matched.cik,
        matched.ticker,
        matched.period_start,
        matched.period_end,
        matched.period_kind,
        coalesce(
            -- Stepped back when the matched year end is more than a year away,
            -- which happens for periods predating the oldest annual report.
            -- Normally the step is zero.
            case
                when matched.next_year_end is not null
                    then matched.next_year_end - to_years(
                        floor(
                            date_diff('day', matched.period_end, matched.next_year_end) / 365.25
                        )::int
                    )
                -- No annual report covers this period yet, so the newest year
                -- end is projected forward.
                else newest_year_end.year_end + to_years(
                    greatest(
                        1,
                        ceil(
                            date_diff('day', newest_year_end.year_end, matched.period_end) / 365.25
                        )::int
                    )
                )
            end,
            -- A company that has never reported an annual period has no
            -- observable fiscal calendar, so a calendar year is assumed.
            date_trunc('year', matched.period_end) + interval 1 year - interval 1 day
        -- Date arithmetic widens to a timestamp in DuckDB, so it is narrowed back
        -- here: every period column in this project is a date.
        )::date as fiscal_year_end
    from matched
    left join newest_year_end on newest_year_end.cik = matched.cik

)

select
    resolved.cik,
    resolved.ticker,
    resolved.period_start,
    resolved.period_end,
    resolved.period_kind,
    -- Stored rather than assumed, so a 52/53 week year is visible as 371 days
    -- instead of quietly passing as 365. Null for instants, which have no length.
    date_diff('day', resolved.period_start, resolved.period_end) as period_days,
    year(resolved.fiscal_year_end) as fiscal_year,
    -- Which quarter of the fiscal year the period closes. Counted back from the
    -- year end in quarters of 91.3 days, so the count holds whatever month the
    -- year ends in. Cumulative periods are not a quarter, so they carry none.
    case
        when resolved.period_kind in ('quarter', 'instant')
            then least(
                4,
                greatest(
                    1,
                    4 - round(
                        date_diff('day', resolved.period_end, resolved.fiscal_year_end) / 91.3
                    )
                )
            )::int
    end as fiscal_quarter,
    resolved.fiscal_year_end,
    -- The calendar year holding most of the fiscal year's days. Counting 183 days
    -- back from the year end lands in that year for any twelve month period.
    year(resolved.fiscal_year_end - interval 183 day) as calendar_year_equivalent,
    resolved.period_end = resolved.fiscal_year_end as is_year_end,
    -- False where the year end was projected or stepped rather than filed, which
    -- is how a not yet reported year, or a fiscal calendar change, shows itself.
    year_ends.year_end is not null as year_end_is_observed
from resolved
left join year_ends
    on year_ends.cik = resolved.cik
    and year_ends.year_end = resolved.fiscal_year_end
