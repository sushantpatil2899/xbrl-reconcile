import csv
from pathlib import Path

from xbrl_reconcile.config import Company, load_companies
from xbrl_reconcile.seeds import build_companies_rows, write_companies_seed


def company(**kwargs):
    base = dict(
        cik=1108524,
        ticker="CRM",
        name="Salesforce",
        start_year=2009,
        end_year=None,
        enabled=True,
        report_types=("10-K",),
        description="Sales software",
        group="old_timer",
    )
    return Company(**{**base, **kwargs})


def test_rows_carry_config_fields():
    [row] = build_companies_rows([company()])
    assert row == {
        "cik": 1108524,
        "cik10": "0001108524",
        "ticker": "CRM",
        "name": "Salesforce",
        "description": "Sales software",
        "group_name": "old_timer",
        "start_year": 2009,
        "end_year": "",
        "enabled": True,
    }


def test_seed_file_is_written_with_header(tmp_path):
    path = tmp_path / "companies.csv"
    write_companies_seed([company(), company(cik=1, ticker="AAA", name="A")], path)
    rows = list(csv.DictReader(path.open()))
    assert [r["ticker"] for r in rows] == ["CRM", "AAA"]
    assert rows[0]["cik10"] == "0001108524"


def test_generated_seed_matches_config():
    """The committed seed must match config/companies.yml."""
    root = Path(__file__).parent.parent
    expected = build_companies_rows(load_companies(root / "config" / "companies.yml"))
    actual = list(csv.DictReader((root / "transform" / "seeds" / "companies.csv").open()))
    assert len(actual) == len(expected)
    assert [r["ticker"] for r in actual] == [r["ticker"] for r in expected]
    assert [r["cik10"] for r in actual] == [r["cik10"] for r in expected]
