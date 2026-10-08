{#
  One definition of each accounting identity, used everywhere one is checked.

  These were written out three times: in consistency_balance_sheet, in
  mart_confidence_report, and partially in int_facts_derived. Two agreed and the
  third did not: the derivation computed total liabilities as assets minus equity
  and ignored temporary equity, so a company reporting both would have had its
  liabilities overstated by the temporary equity. No company in this warehouse has
  both today, so nothing was wrong, which is exactly how a latent bug survives.

  The identities themselves are true by construction in accounting, so a failure
  means a mapping is wrong rather than a company being unusual.

  Temporary equity is redeemable convertible preferred stock, reported between
  liabilities and equity. Most companies have none, so it is zero when absent
  rather than making the identity unusable.
#}

{% macro balance_sheet_gap(assets, liabilities, temporary_equity, equity) %}
    ( {{ assets }} - {{ liabilities }} - coalesce({{ temporary_equity }}, 0) - {{ equity }} )
{% endmacro %}


{% macro gross_profit_gap(revenue, cost_of_revenue, gross_profit) %}
    ( {{ revenue }} - {{ cost_of_revenue }} - {{ gross_profit }} )
{% endmacro %}


{#
  A gap is material relative to the size of the statement, not in absolute dollars:
  a thousand dollars out on a balance sheet of billions is rounding, and the same
  thousand on a small one is a mapping error. greatest(..., 1) only guards against
  dividing the tolerance by a zero scale.
#}
{% macro identity_holds(gap, scale) %}
    abs( {{ gap }} ) <= {{ var('consistency_tolerance') }} * greatest( abs( {{ scale }} ), 1)
{% endmacro %}
