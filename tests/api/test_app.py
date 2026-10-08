import pytest
from fastapi.testclient import TestClient

from tests.api.fixtures import published_marts
from xbrl_reconcile.api.app import create_app
from xbrl_reconcile.api.queries import MartStore


@pytest.fixture
def store(tmp_path):
    store = MartStore.open(published_marts(tmp_path / "marts"))
    yield store
    store.close()


@pytest.fixture
def client(store):
    # A generous bucket, so the ordinary tests are not throttled by accident. The
    # limiter gets its own client with a tiny one.
    return TestClient(create_app(store, rate=1000.0, burst=1000))


def test_every_endpoint_answers(client):
    for url in (
        "/",
        "/healthz",
        "/companies",
        "/concepts",
        "/vocabularies",
        "/financials",
        "/statements/income_statement",
        "/statements/balance_sheet?period=annual",
        "/confidence?period=all",
        "/coverage",
    ):
        assert client.get(url).status_code == 200, url


def test_the_envelope_says_how_fresh_and_what_was_asked(client):
    body = client.get("/financials?tickers=wday&concepts=revenue").json()

    assert body["as_of"] == "2026-10-08T00:00:00Z"
    # The default the caller did not pass is echoed, which is what keeps it honest.
    assert body["filters_applied"]["period"] == "annual"
    assert body["filters_applied"]["year_basis"] == "calendar"
    assert body["filters_applied"]["tickers"] == ["WDAY"]


def test_a_lowercase_ticker_is_accepted(client):
    assert client.get("/financials?tickers=wday").json()["pagination"]["total_rows"] == 2


# Pagination.


def test_next_preserves_every_other_filter_and_only_moves_the_offset(client):
    body = client.get("/financials?period=all&concepts=revenue&limit=2").json()

    following = body["pagination"]["next"]
    assert "concepts=revenue" in following
    assert "period=all" in following
    assert "offset=2" in following
    assert body["pagination"]["previous"] is None


def test_the_second_page_can_go_back(client):
    body = client.get("/financials?period=all&limit=2&offset=2").json()

    assert "offset=0" in body["pagination"]["previous"]
    assert body["pagination"]["offset"] == 2


def test_the_last_page_has_no_next(client):
    body = client.get("/financials?period=all&limit=100").json()

    assert body["pagination"]["next"] is None
    assert body["pagination"]["has_more"] is False


def test_the_link_header_matches_the_body(client):
    response = client.get("/financials?period=all&limit=2")

    assert 'rel="next"' in response.headers["Link"]
    assert response.json()["pagination"]["next"] in response.headers["Link"]


def test_following_next_gives_the_rest_without_repeating_anything(client):
    first = client.get("/financials?period=all&limit=4").json()
    second = client.get(first["pagination"]["next"]).json()

    assert len(first["rows"]) == 4
    assert len(second["rows"]) == 3
    seen = [
        (row["ticker"], row["concept"], row["period_end"], row["period_kind"])
        for row in first["rows"] + second["rows"]
    ]
    # period_kind belongs in the key: ServiceNow's annual and its derived fourth
    # quarter both end on the same day, which is why the sort includes it.
    assert len(set(seen)) == 7


def test_a_limit_above_the_cap_is_rejected(client):
    assert client.get("/financials?limit=99999").status_code == 422


# Errors.


def test_an_unknown_ticker_is_a_400_naming_what_would_have_worked(client):
    response = client.get("/financials?tickers=GOOGL")

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "ticker"
    assert body["value"] == "GOOGL"
    assert "WDAY" in body["valid"]


def test_an_unknown_concept_is_a_400(client):
    assert client.get("/financials?concepts=ebitda").status_code == 400


def test_a_bad_period_is_a_422_from_the_type_itself(client):
    response = client.get("/financials?period=yearly")

    assert response.status_code == 422
    assert "yearly" in response.text


def test_an_unknown_statement_is_a_404(client):
    response = client.get("/statements/pnl")

    assert response.status_code == 422, "the path enum rejects it before the handler runs"


def test_a_balance_sheet_has_no_half_period_and_the_message_says_so(client):
    response = client.get("/statements/balance_sheet?period=half")

    assert response.status_code == 400
    assert "no half period" in response.json()["error"]


# The statement shape.


def test_a_statement_comes_back_as_ordered_lines(client):
    body = client.get("/statements/balance_sheet?period=annual&tickers=NOW").json()

    lines = body["rows"][0]["lines"]
    assert [line["concept"] for line in lines] == ["total_assets", "cash"]
    assert lines[0]["value"] == 1500.0
    assert lines[1]["confidence"] == "medium"
    assert body["rows"][0]["statement_covers_whole"] is True


def test_a_date_is_serialized_as_text(client):
    body = client.get("/statements/balance_sheet?period=annual&tickers=NOW").json()

    assert body["rows"][0]["period_end"] == "2015-12-31"


# Coverage does not offer what it cannot do.


def test_coverage_does_not_advertise_a_period_or_year_basis(client):
    schema = client.get("/openapi.json").json()
    names = {parameter["name"] for parameter in schema["paths"]["/coverage"]["get"]["parameters"]}

    assert "year_basis" not in names, "offering a parameter that always 400s is worse docs"
    assert "period" not in names
    assert {"tickers", "concepts", "from_year", "to_year", "status"} <= names


def test_coverage_still_answers_a_fiscal_year_range(client):
    body = client.get("/coverage?from_year=2015&to_year=2015").json()

    assert body["pagination"]["total_rows"] == 2


# The documentation, which is the part of this phase that has to be generated.


def test_the_openapi_document_lists_the_period_values_from_config(client):
    schema = client.get("/openapi.json").json()
    parameters = {
        parameter["name"]: parameter
        for parameter in schema["paths"]["/financials"]["get"]["parameters"]
    }

    assert parameters["period"]["schema"]["$ref"] or parameters["period"]["schema"].get("enum")


def test_a_parameter_description_carries_the_sentence_config_wrote(client):
    """The claim the whole phase rests on: no value's meaning is typed in Python."""
    schema = client.get("/openapi.json").json()
    period = next(
        parameter
        for parameter in schema["paths"]["/financials"]["get"]["parameters"]
        if parameter["name"] == "period"
    )

    # Straight out of the fixture's mart_vocabularies, which stands in for config.
    assert "What annual means." in period["description"]
    assert "disables this filter" in period["description"]


def test_the_overview_reaches_the_document(client):
    schema = client.get("/openapi.json").json()

    assert "XBRL" in schema["info"]["description"]
    assert "derived" in schema["info"]["description"]


def test_the_endpoints_are_grouped_into_sections(client):
    schema = client.get("/openapi.json").json()

    assert {tag["name"] for tag in schema["tags"]} == {
        "Metadata",
        "Statements",
        "Quality",
        "Evidence",
    }


def test_both_documentation_pages_render(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_the_tickers_in_the_documentation_come_from_the_data(client):
    schema = client.get("/openapi.json").json()
    tickers = next(
        parameter
        for parameter in schema["paths"]["/financials"]["get"]["parameters"]
        if parameter["name"] == "tickers"
    )

    assert "WDAY" in tickers["description"]
    assert "NOW" in tickers["description"]


# The limiter.


def test_requests_carry_their_remaining_allowance(client):
    response = client.get("/financials")

    assert response.headers["X-RateLimit-Limit"] == "1000"
    assert int(response.headers["X-RateLimit-Remaining"]) < 1000


def test_going_over_the_limit_is_a_429_that_says_when_to_retry(store):
    client = TestClient(create_app(store, rate=0.001, burst=2))

    assert client.get("/financials").status_code == 200
    assert client.get("/financials").status_code == 200
    response = client.get("/financials")

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


def test_health_checks_are_never_throttled(store):
    """A host whose checks hit a 429 marks the container unhealthy and kills it."""
    client = TestClient(create_app(store, rate=0.001, burst=1))
    client.get("/financials")
    assert client.get("/financials").status_code == 429

    for url in ("/healthz", "/", "/docs", "/openapi.json"):
        assert client.get(url).status_code == 200, url


def test_the_access_log_records_the_route_rather_than_the_url(client, caplog):
    import json
    import logging

    with caplog.at_level(logging.INFO, logger="xbrl_reconcile.api"):
        client.get("/financials?tickers=WDAY&concepts=revenue")

    entry = json.loads(caplog.records[-1].getMessage())
    assert entry["endpoint"] == "/financials"
    assert entry["filters"] == {"tickers": "WDAY", "concepts": "revenue"}
    assert entry["rows"] == 1
    assert entry["status"] == 200


def test_a_mart_that_was_not_published_is_a_clear_503(client):
    """The caller did nothing wrong, so this is not a 400, and it names the mart.

    Without the guard DuckDB raises a catalog error and the reader gets a 500 that
    tells them nothing they can act on.
    """
    response = client.get("/statements/cash_flow")

    assert response.status_code == 503
    assert response.json()["mart"] == "mart_cash_flow"
    assert "mart_income_statement" in response.json()["available"]


def test_the_root_points_at_the_parquet_for_bulk_reads(client):
    body = client.get("/").json()

    assert body["companies"] == 3
    assert "Parquet" in body["parquet_note"]
    assert len(body["marts"]) == 7


def test_the_most_useful_quality_query_finds_the_statements_worth_a_look(client):
    """`trust=check` is where an identity fails or a line was ambiguous."""
    body = client.get("/confidence?period=all&trust=check").json()

    assert body["pagination"]["total_rows"] == 1
    row = body["rows"][0]
    assert row["ticker"] == "NOW"
    assert row["identity_holds"] is False
    assert row["lines_present"] < row["lines_expected"]
