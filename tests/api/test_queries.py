import pytest

from tests.api.fixtures import published_marts
from xbrl_reconcile.api.queries import (
    Filters,
    MartStore,
    Page,
    UnknownValue,
    UnsupportedFilter,
    Where,
    companies,
    concepts,
    coverage,
    financials,
    index,
    statement,
    vocabularies,
)


@pytest.fixture
def store(tmp_path):
    store = MartStore.open(published_marts(tmp_path / "marts"))
    yield store
    store.close()


def tickers_of(result):
    return [row["ticker"] for row in result.rows]


def values_of(result):
    return [row["value"] for row in result.rows]


# The year basis rule, which is the one most likely to be wrong and least likely to
# be noticed. WDAY's fiscal 2015 ran February 2014 to January 2015.


def test_a_calendar_year_finds_the_fiscal_year_that_mostly_falls_in_it(store):
    result = financials(
        store,
        Filters(tickers=("WDAY",), concepts=("revenue",), from_year=2014, to_year=2014),
        Page(),
    )

    assert values_of(result) == [787.86]
    assert result.rows[0]["fiscal_year"] == 2015
    assert result.rows[0]["calendar_year_equivalent"] == 2014


def test_the_fiscal_basis_finds_the_same_row_under_the_company_s_own_label(store):
    result = financials(
        store,
        Filters(
            tickers=("WDAY",),
            concepts=("revenue",),
            from_year=2015,
            to_year=2015,
            year_basis="fiscal",
        ),
        Page(),
    )

    assert values_of(result) == [787.86]


def test_the_two_bases_disagree_for_a_january_year_end_and_agree_for_december(store):
    calendar = financials(
        store, Filters(concepts=("revenue",), from_year=2015, to_year=2015), Page()
    )
    fiscal = financials(
        store,
        Filters(concepts=("revenue",), from_year=2015, to_year=2015, year_basis="fiscal"),
        Page(),
    )

    # NOW ends in December, so it appears under both. WDAY ends in January, so it
    # appears only under its own fiscal label.
    assert tickers_of(calendar) == ["NOW"]
    assert tickers_of(fiscal) == ["NOW", "WDAY"]


def test_both_year_labels_are_always_returned(store):
    """Neither label can mislead if the response carries both."""
    result = financials(store, Filters(tickers=("WDAY",), concepts=("revenue",)), Page())

    assert {"fiscal_year", "calendar_year_equivalent"} <= set(result.rows[0])


# Coverage is keyed by fiscal year alone, so the calendar basis cannot apply there.


def test_coverage_accepts_a_year_range_without_a_basis(store):
    result = coverage(store, Filters(from_year=2015, to_year=2015), Page())

    assert [row["fiscal_year"] for row in result.rows] == [2015, 2015]


def test_coverage_rejects_an_explicit_calendar_basis(store):
    """The default must not trigger this, which is why year_basis is None when unset."""
    with pytest.raises(UnsupportedFilter, match="fiscal year only"):
        coverage(store, Filters(from_year=2015, year_basis="calendar"), Page())


def test_coverage_can_still_filter_by_status(store):
    result = coverage(store, Filters(), Page(), status=("missing",))

    assert [(row["ticker"], row["concept"]) for row in result.rows] == [("NOW", "cost_of_revenue")]


# The balance sheet is entirely instants, so period is translated.


def test_an_annual_balance_sheet_means_the_year_end_one(store):
    result = statement(store, "balance_sheet", Filters(period="annual"), Page())

    assert [(row["ticker"], str(row["period_end"])) for row in result.rows] == [
        ("NOW", "2015-12-31"),
        ("WDAY", "2015-01-31"),
    ]


def test_a_quarterly_balance_sheet_means_the_other_snapshots(store):
    result = statement(store, "balance_sheet", Filters(period="quarter"), Page())

    assert [str(row["period_end"]) for row in result.rows] == ["2014-10-31"]


def test_a_balance_sheet_has_no_half_period_and_says_so(store):
    with pytest.raises(UnsupportedFilter, match="no half period"):
        statement(store, "balance_sheet", Filters(period="half"), Page())


def test_period_all_applies_no_period_filter(store):
    result = financials(
        store, Filters(tickers=("WDAY",), concepts=("revenue",), period="all"), Page()
    )

    assert sorted(row["period_kind"] for row in result.rows) == ["annual", "quarter"]


# Statement nesting, built from config order.


def test_statement_lines_come_back_in_the_order_config_lists_them(store):
    result = statement(store, "balance_sheet", Filters(period="annual", tickers=("NOW",)), Page())

    lines = result.rows[0]["lines"]
    assert [line["concept"] for line in lines] == ["total_assets", "cash"]
    assert [line["position"] for line in lines] == [9, 13]
    assert lines[0]["value"] == 1500.0
    assert lines[1]["confidence"] == "medium"


def test_a_statement_row_keeps_its_provenance_beside_the_lines(store):
    result = statement(store, "balance_sheet", Filters(period="annual", tickers=("NOW",)), Page())

    assert result.rows[0]["statement_form"] == "10-K"
    assert result.rows[0]["statement_covers_whole"] is True


def test_verbose_returns_the_flat_mart_row_instead(store):
    result = statement(
        store, "balance_sheet", Filters(period="annual", tickers=("NOW",)), Page(), verbose=True
    )

    assert "lines" not in result.rows[0]
    assert result.rows[0]["total_assets"] == 1500.0


def test_an_unknown_statement_names_the_three_that_exist(store):
    with pytest.raises(UnknownValue) as raised:
        statement(store, "pnl", Filters(), Page())

    assert raised.value.valid == ("income_statement", "balance_sheet", "cash_flow")


# Validation, which belongs to the data rather than to HTTP.


def test_an_unknown_ticker_is_rejected_with_the_valid_list(store):
    """An empty result would be indistinguishable from a typo."""
    with pytest.raises(UnknownValue) as raised:
        financials(store, Filters(tickers=("GOOGL",)), Page())

    assert raised.value.field == "ticker"
    assert raised.value.value == "GOOGL"
    assert "WDAY" in raised.value.valid


def test_an_unknown_concept_is_rejected(store):
    with pytest.raises(UnknownValue, match="unknown concept"):
        financials(store, Filters(concepts=("ebitda",)), Page())


def test_an_unknown_confidence_level_is_rejected_from_the_vocabulary(store):
    with pytest.raises(UnknownValue, match="unknown confidence"):
        financials(store, Filters(confidence=("certain",)), Page())


def test_a_declared_but_absent_confidence_level_is_accepted(store):
    """`low` is declared in config and has no rows, so it must filter to nothing
    rather than be rejected as unknown."""
    result = financials(store, Filters(confidence=("low",)), Page())

    assert result.rows == []
    assert result.total == 0


# Filtering the rest.


def test_confidence_filters_to_exactly_the_levels_asked_for(store):
    result = financials(store, Filters(confidence=("derived",), period="quarter"), Page())

    assert values_of(result) == [500.0]


def test_basis_separates_the_ifrs_filer(store):
    result = financials(store, Filters(basis="ifrs"), Page())

    assert tickers_of(result) == ["TEAM"]


def test_evidence_filters_on_what_the_filings_arcs_said(store):
    result = financials(store, Filters(evidence=("contradicted",)), Page())

    assert values_of(result) == [1933.0]


def test_restated_filters_on_the_flag(store):
    result = financials(store, Filters(restated=True), Page())

    assert values_of(result) == [1933.0]
    # The annual default still applies, and the result is in the endpoint's sort
    # order: ticker then concept, so WDAY's cost of revenue precedes its revenue.
    assert [
        (row["ticker"], row["concept"])
        for row in financials(store, Filters(restated=False), Page()).rows
    ] == [
        ("NOW", "revenue"),
        ("TEAM", "revenue"),
        ("WDAY", "cost_of_revenue"),
        ("WDAY", "revenue"),
    ]


# Pagination, and the stable sort it depends on.


def test_the_total_ignores_the_limit(store):
    result = financials(store, Filters(period="all"), Page(limit=2))

    assert len(result.rows) == 2
    assert result.total == 7
    assert result.has_more


def test_pages_do_not_overlap_and_together_are_the_whole_result(store):
    """The property a deterministic sort exists to provide."""
    whole = financials(store, Filters(period="all"), Page(limit=100))
    first = financials(store, Filters(period="all"), Page(limit=4, offset=0))
    second = financials(store, Filters(period="all"), Page(limit=4, offset=4))

    assert len(first.rows) == 4
    assert len(second.rows) == 3
    assert first.rows + second.rows == whole.rows


def test_the_applied_sort_travels_back_with_the_result(store):
    result = financials(store, Filters(), Page())

    assert result.sort == ("ticker", "concept", "period_end", "period_kind", "period_start")


# The binding mechanism itself.


def test_values_become_placeholders_rather_than_sql_text():
    where = Where()
    where.in_list("ticker", ("CRM", "WDAY"))
    where.equals("basis", "us_gaap")

    assert where.sql() == 'where "ticker" in (?, ?) and "basis" = ?'
    assert where.params == ["CRM", "WDAY", "us_gaap"]


def test_a_none_filter_adds_no_predicate():
    where = Where()
    where.in_list("ticker", None)
    where.equals("basis", None)
    where.is_true("was_restated", None)

    assert where.sql() == ""
    assert where.params == []


def test_a_boolean_filter_survives_a_null_in_the_column():
    """A bare `not column` would drop a null row under both true and false."""
    where = Where()
    where.is_true("was_restated", False)

    assert where.sql() == 'where coalesce("was_restated", false) = ?'


# Metadata.


def test_the_index_reports_freshness_and_what_is_in_the_set(store):
    answer = index(store)

    assert answer["as_of"] == "2026-10-08T00:00:00Z"
    assert answer["companies"] == 3
    assert answer["concepts"] == 4
    assert answer["fiscal_years"] == {"first": 2015, "last": 2019}


def test_companies_reports_the_span_each_one_covers(store):
    result = companies(store)

    rows = {row["ticker"]: row for row in result.rows}
    assert tickers_of(result) == ["NOW", "TEAM", "WDAY"]
    assert str(rows["WDAY"]["first_period_end"]) == "2014-04-30"
    assert rows["WDAY"]["fiscal_year_end_month"] == 1
    assert rows["TEAM"]["basis"] == "ifrs"


def test_concepts_can_be_narrowed_to_one_statement(store):
    result = concepts(store, statement="balance_sheet")

    assert [row["concept"] for row in result.rows] == ["total_assets", "cash"]


def test_vocabularies_carry_a_description_for_every_value(store):
    result = vocabularies(store)

    assert result.total == 22
    assert all(row["description"] for row in result.rows)
    confidence_values = [row["value"] for row in result.rows if row["vocabulary"] == "confidence"]
    assert confidence_values == ["high", "medium", "low", "derived"]


def test_opening_a_directory_with_no_index_says_what_to_run(tmp_path):
    with pytest.raises(FileNotFoundError, match="xbrl-fetch-marts"):
        MartStore.open(tmp_path)
