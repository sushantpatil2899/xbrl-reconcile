"""A small published mart set, shaped like the real one, written as Parquet.

Deliberately not a copy of production: the rows are chosen to exercise the rules that
are easy to get wrong. WDAY ends its fiscal year in January, so its fiscal 2015 is
calendar 2014 and the two year bases disagree. NOW ends in December, so they agree.
That disagreement is the whole reason year_basis exists.
"""

import json
from pathlib import Path

import duckdb


def fact(ticker, concept, value, start, end, kind, fiscal, calendar, year_end=None, **rest):
    row = {
        "cik": "1",
        "ticker": ticker,
        "company_name": f"{ticker} Inc.",
        "statement": "income_statement",
        "concept": concept,
        "unit": "USD",
        "value": value,
        "period_start": start,
        "period_end": end,
        "period_kind": kind,
        "fiscal_year": fiscal,
        "fiscal_quarter": None,
        "calendar_year_equivalent": calendar,
        # The fiscal year's end, not this period's, which is how a quarter still says
        # which month its company closes its books in.
        "fiscal_year_end": year_end or end,
        "confidence": "high",
        "inputs_confidence": None,
        "source_tag": f"us-gaap:{concept}",
        "evidence": "confirmed",
        "basis": "us_gaap",
        "form": "10-K",
        "was_restated": False,
        "is_coherent": True,
    }
    return row | rest


FACTS = [
    # A January year end: fiscal 2015 is calendar 2014.
    fact("WDAY", "revenue", 787.86, "2014-02-01", "2015-01-31", "annual", 2015, 2014),
    fact(
        "WDAY",
        "cost_of_revenue",
        264.803,
        "2014-02-01",
        "2015-01-31",
        "annual",
        2015,
        2014,
        confidence="medium",
        evidence="not_applicable",
    ),
    fact(
        "WDAY",
        "revenue",
        186.86,
        "2014-02-01",
        "2014-04-30",
        "quarter",
        2015,
        2014,
        year_end="2015-01-31",
    ),
    # A December year end: the two bases agree.
    fact("NOW", "revenue", 1005.0, "2015-01-01", "2015-12-31", "annual", 2015, 2015),
    fact(
        "NOW",
        "revenue",
        1933.0,
        "2016-01-01",
        "2016-12-31",
        "annual",
        2016,
        2016,
        evidence="contradicted",
        was_restated=True,
    ),
    # A derived fourth quarter, which no company files.
    fact(
        "NOW",
        "revenue",
        500.0,
        "2015-10-01",
        "2015-12-31",
        "quarter",
        2015,
        2015,
        confidence="derived",
        evidence="not_applicable",
    ),
    # IFRS, so basis filtering has something to find.
    fact(
        "TEAM",
        "revenue",
        1210.127,
        "2018-07-01",
        "2019-06-30",
        "annual",
        2019,
        2018,
        confidence="medium",
        basis="ifrs",
    ),
]


def balance(ticker, end, fiscal, calendar, year_end, assets, cash, cash_confidence="high"):
    return {
        "cik": "1",
        "ticker": ticker,
        "company_name": f"{ticker} Inc.",
        "period_start": None,
        "period_end": end,
        "period_kind": "instant",
        "period_days": None,
        "fiscal_year": fiscal,
        "fiscal_quarter": None,
        "calendar_year_equivalent": calendar,
        "fiscal_year_end": end,
        "is_year_end": year_end,
        "total_assets": assets,
        "total_assets_confidence": "high",
        "cash": cash,
        "cash_confidence": cash_confidence,
        "basis": "us_gaap",
        "statement_accession": "acc-1",
        "statement_form": "10-K",
        "statement_filed_date": end,
        "statement_covers_whole": True,
        "incoherent_lines": 0,
    }


BALANCES = [
    balance("WDAY", "2015-01-31", 2015, 2014, True, 2000.0, 500.0),
    balance("WDAY", "2014-10-31", 2015, 2014, False, 1800.0, 450.0),
    balance("NOW", "2015-12-31", 2015, 2015, True, 1500.0, 300.0, cash_confidence="medium"),
]


def income(ticker, end, fiscal, calendar, revenue, cost, cost_confidence="high"):
    return {
        "cik": "1",
        "ticker": ticker,
        "company_name": f"{ticker} Inc.",
        "period_start": None,
        "period_end": end,
        "period_kind": "annual",
        "period_days": 365,
        "fiscal_year": fiscal,
        "fiscal_quarter": None,
        "calendar_year_equivalent": calendar,
        "fiscal_year_end": end,
        "is_year_end": True,
        "revenue": revenue,
        "revenue_confidence": "high",
        "cost_of_revenue": cost,
        "cost_of_revenue_confidence": cost_confidence,
        "basis": "us_gaap",
        "statement_accession": "acc-1",
        "statement_form": "10-K",
        "statement_filed_date": end,
        "statement_covers_whole": True,
        "incoherent_lines": 0,
    }


INCOME = [
    income("WDAY", "2015-01-31", 2015, 2014, 787.86, 264.803, cost_confidence="medium"),
    income("NOW", "2015-12-31", 2015, 2015, 1005.0, 300.0),
]


def trust_row(ticker, end, fiscal, calendar, statement, trust, present, expected, holds=True):
    return {
        "cik": "1",
        "ticker": ticker,
        "company_name": f"{ticker} Inc.",
        "statement": statement,
        "period_start": None,
        "period_end": end,
        "period_kind": "annual" if statement != "balance_sheet" else "instant",
        "fiscal_year": fiscal,
        "fiscal_quarter": None,
        "calendar_year_equivalent": calendar,
        "basis": "us_gaap",
        "lines_present": present,
        "lines_expected": expected,
        "is_complete": present == expected,
        "high_lines": present,
        "medium_lines": 0,
        "low_lines": 0,
        "derived_lines": 0,
        "ambiguous_lines": 0,
        "restated_lines": 0,
        "incoherent_lines": 0,
        "confirmed_lines": present,
        "contradicted_lines": 0,
        "identity_gap": 0.0,
        "identity_holds": holds,
        "statement_accession": "acc-1",
        "statement_form": "10-K",
        "statement_filed_date": end,
        "statement_covers_whole": True,
        "trust": trust,
    }


CONFIDENCE = [
    trust_row("WDAY", "2015-01-31", 2015, 2014, "income_statement", "reported", 2, 2),
    trust_row("NOW", "2015-12-31", 2015, 2015, "income_statement", "check", 1, 2, holds=False),
    trust_row("NOW", "2015-12-31", 2015, 2015, "balance_sheet", "reported", 2, 2),
]

CONCEPT_COLUMNS = ("concept", "statement", "position", "unit", "is_additive", "is_optional")
CONCEPTS = [
    ("revenue", "income_statement", 1, "USD", True, False),
    ("cost_of_revenue", "income_statement", 2, "USD", True, False),
    ("total_assets", "balance_sheet", 9, "USD", True, False),
    ("cash", "balance_sheet", 13, "USD", True, False),
]

VOCABULARIES = [
    ("statement", "income_statement"),
    ("statement", "balance_sheet"),
    ("statement", "cash_flow"),
    ("confidence", "high"),
    ("confidence", "medium"),
    ("confidence", "low"),
    ("confidence", "derived"),
    ("period_kind", "annual"),
    ("period_kind", "quarter"),
    ("period_kind", "half"),
    ("period_kind", "instant"),
    ("basis", "us_gaap"),
    ("basis", "ifrs"),
    ("evidence", "confirmed"),
    ("evidence", "contradicted"),
    ("evidence", "not_applicable"),
    ("trust", "reported"),
    ("trust", "check"),
    ("coverage_status", "reported"),
    ("coverage_status", "missing"),
    ("year_basis", "calendar"),
    ("year_basis", "fiscal"),
]

COVERAGE_COLUMNS = (
    "cik",
    "ticker",
    "fiscal_year",
    "fiscal_year_end",
    "concept",
    "statement",
    "status",
    "value",
    "confidence",
    "source_tag",
    "basis",
    "period_end",
)
COVERAGE = [
    (
        "1",
        "WDAY",
        2015,
        None,
        "revenue",
        "income_statement",
        "reported",
        None,
        None,
        None,
        None,
        None,
    ),
    (
        "1",
        "WDAY",
        2015,
        None,
        "cost_of_revenue",
        "income_statement",
        "reported",
        None,
        None,
        None,
        None,
        None,
    ),
    (
        "1",
        "NOW",
        2016,
        None,
        "cost_of_revenue",
        "income_statement",
        "missing",
        None,
        None,
        None,
        None,
        None,
    ),
]

# What each column is, so the Parquet carries real types rather than everything as text.
TYPES = {
    "cik": "varchar",
    "ticker": "varchar",
    "company_name": "varchar",
    "statement": "varchar",
    "concept": "varchar",
    "unit": "varchar",
    "value": "double",
    "period_start": "date",
    "period_end": "date",
    "period_kind": "varchar",
    "period_days": "integer",
    "fiscal_year": "integer",
    "fiscal_quarter": "integer",
    "calendar_year_equivalent": "integer",
    "fiscal_year_end": "date",
    "is_year_end": "boolean",
    "confidence": "varchar",
    "inputs_confidence": "varchar",
    "source_tag": "varchar",
    "evidence": "varchar",
    "basis": "varchar",
    "form": "varchar",
    "was_restated": "boolean",
    "is_coherent": "boolean",
    "total_assets": "double",
    "total_assets_confidence": "varchar",
    "cash": "double",
    "cash_confidence": "varchar",
    "revenue": "double",
    "revenue_confidence": "varchar",
    "cost_of_revenue": "double",
    "cost_of_revenue_confidence": "varchar",
    "statement_accession": "varchar",
    "statement_form": "varchar",
    "statement_filed_date": "date",
    "statement_covers_whole": "boolean",
    "incoherent_lines": "integer",
    "lines_present": "integer",
    "lines_expected": "integer",
    "is_complete": "boolean",
    "high_lines": "integer",
    "medium_lines": "integer",
    "low_lines": "integer",
    "derived_lines": "integer",
    "ambiguous_lines": "integer",
    "restated_lines": "integer",
    "confirmed_lines": "integer",
    "contradicted_lines": "integer",
    "identity_gap": "double",
    "identity_holds": "boolean",
    "trust": "varchar",
    "position": "integer",
    "is_additive": "boolean",
    "is_optional": "boolean",
    "vocabulary": "varchar",
    "vocabulary_description": "varchar",
    "value_text": "varchar",
    "description": "varchar",
    "status": "varchar",
}


def _table(connection, name: str, columns: tuple[str, ...], rows: list[tuple]) -> None:
    definition = ", ".join(f'"{column}" {TYPES[column]}' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(f"create table {name} ({definition})")
    connection.executemany(f"insert into {name} values ({placeholders})", rows)


def _from_dicts(connection, name: str, records: list[dict]) -> None:
    columns = tuple(records[0])
    _table(connection, name, columns, [tuple(record[c] for c in columns) for record in records])


def published_marts(root: Path) -> Path:
    """Write the fixture marts as Parquet with an index, as the publisher would."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()

    _from_dicts(connection, "mart_financials", FACTS)
    _from_dicts(connection, "mart_balance_sheet", BALANCES)
    _from_dicts(connection, "mart_income_statement", INCOME)
    _from_dicts(connection, "mart_confidence_report", CONFIDENCE)
    _table(connection, "mart_concepts", CONCEPT_COLUMNS, CONCEPTS)
    _table(connection, "mart_mapping_coverage", COVERAGE_COLUMNS, COVERAGE)

    # value is a reserved-ish name shared with mart_financials' numeric column, so the
    # vocabulary table is built directly rather than through the shared type map.
    connection.execute(
        "create table mart_vocabularies (vocabulary varchar, vocabulary_description varchar, "
        "value varchar, description varchar, position integer)"
    )
    connection.executemany(
        "insert into mart_vocabularies values (?, ?, ?, ?, ?)",
        [
            (name, f"The {name} set.", value, f"What {value} means.", position)
            for position, (name, value) in enumerate(VOCABULARIES, start=1)
        ],
    )

    marts = []
    for name in (
        "mart_financials",
        "mart_balance_sheet",
        "mart_income_statement",
        "mart_confidence_report",
        "mart_concepts",
        "mart_vocabularies",
        "mart_mapping_coverage",
    ):
        path = root / f"{name}.parquet"
        connection.execute(f"copy (select * from {name}) to '{path}' (format parquet)")
        rows = connection.execute(f"select count(*) from {name}").fetchone()[0]
        marts.append({"name": name, "rows": rows, "bytes": path.stat().st_size})

    (root / "_index.json").write_text(
        json.dumps({"published_at": "2026-10-08T00:00:00Z", "marts": marts}, indent=2)
    )
    connection.close()
    return root
