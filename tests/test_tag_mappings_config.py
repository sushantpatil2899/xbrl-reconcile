from pathlib import Path

from xbrl_reconcile.config import load_companies
from xbrl_reconcile.mappings import load_mappings, validate_against_companies

ROOT = Path(__file__).parent.parent
MAPPINGS = ROOT / "config" / "tag_mappings.yml"
COMPANIES = ROOT / "config" / "companies.yml"

EXPECTED_CONCEPTS = {
    "revenue",
    "cost_of_revenue",
    "gross_profit",
    "operating_expenses",
    "operating_income",
    "net_income",
    "eps_diluted",
    "shares_diluted",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "cash",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "temporary_equity",
}
UNITS = {"USD", "USD/shares", "shares"}


def test_real_config_loads():
    config = load_mappings(MAPPINGS)
    assert set(config.concepts) == EXPECTED_CONCEPTS


def test_every_concept_has_a_high_confidence_tag_first():
    """The first tag is what wins by default, so it must not be a guess."""
    for concept in load_mappings(MAPPINGS).concepts.values():
        assert concept.tags[0].confidence == "high", concept.name


def test_units_are_known():
    for concept in load_mappings(MAPPINGS).concepts.values():
        assert concept.unit in UNITS, concept.name


def test_ifrs_tags_are_never_the_default_choice():
    """IFRS follows different rules, so a us-gaap tag must outrank it."""
    for concept in load_mappings(MAPPINGS).concepts.values():
        ifrs = [t for t in concept.tags if t.taxonomy == "ifrs-full"]
        us_gaap = [t for t in concept.tags if t.taxonomy == "us-gaap"]
        for tag in ifrs:
            assert tag.confidence == "medium", f"{concept.name}:{tag.tag}"
            assert all(tag.priority > u.priority for u in us_gaap), f"{concept.name}:{tag.tag}"


def test_overrides_match_the_company_config():
    config = load_mappings(MAPPINGS)
    assert validate_against_companies(config, load_companies(COMPANIES)) == []


def test_snapshot_rows_are_complete():
    config = load_mappings(MAPPINGS)
    rows = config.concept_rows()
    assert len(rows) == sum(len(c.tags) for c in config.concepts.values())
    assert all(row["taxonomy"] and row["tag"] and row["priority"] for row in rows)
    assert all(row["unit"] in UNITS for row in rows)
    assert config.override_rows(), "the Splunk net income override should produce a row"
