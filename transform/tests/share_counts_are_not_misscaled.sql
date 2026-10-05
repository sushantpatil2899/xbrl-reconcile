{#
  Diluted share counts that are wrong by orders of magnitude.

  Net income should be about diluted EPS times diluted shares. Two things make that a
  scale check rather than an identity test.

  The tolerance is scaled by shares, not by net income. EPS is reported to the cent,
  so the implied net income carries an uncertainty of half a cent times the share
  count, and a company whose net income is near zero fails any relative test on
  rounding alone.

  The threshold is three orders of magnitude, because the identity legitimately fails
  for pre IPO companies. Their EPS is computed on income attributable to common
  stockholders after preferred accretion, which can differ from net income by more
  than the figure itself. Figma's 2023 misses by 464 times the rounding allowance and
  is not an error; Box's 2015 by 174 times, likewise. The six real errors miss by
  between 55,681 and 997,530 times, so 500, 1000 and 5000 all catch exactly those six.

  What it finds: HubSpot tagged its 2014 interim share counts in thousands while
  tagging the annual in units, and Box did the same for its 2021 annual. The test
  reports them. It does not fix them, because correcting a filer's units needs a per
  company scale mechanism that the config does not have.
#}

{{ config(severity='warn') }}

with per_period as (

    select
        ticker,
        fiscal_year,
        period_kind,
        period_end,
        max(case when concept = 'net_income' then value end) as net_income,
        max(case when concept = 'eps_diluted' then value end) as eps_diluted,
        max(case when concept = 'shares_diluted' then value end) as shares_diluted
    from {{ ref('mart_financials') }}
    group by all

)

select
    ticker,
    fiscal_year,
    period_kind,
    period_end,
    net_income,
    eps_diluted,
    shares_diluted,
    eps_diluted * shares_diluted as implied_net_income,
    round(
        abs(net_income - eps_diluted * shares_diluted) / (0.005 * abs(shares_diluted))
    ) as multiples_of_the_rounding_allowance
from per_period
where net_income is not null
    and eps_diluted is not null
    and shares_diluted is not null
    and shares_diluted > 0
    and abs(net_income - eps_diluted * shares_diluted)
        > {{ var('share_scale_threshold') }} * 0.005 * abs(shares_diluted)
