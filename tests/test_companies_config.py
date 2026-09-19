from pathlib import Path

from xbrl_reconcile.config import load_companies

CONFIG = Path(__file__).parent.parent / "config" / "companies.yml"
GROUPS = {"old_timer", "middle", "new", "gone", "rule_changer"}


def test_real_config_loads_and_is_consistent():
    companies = load_companies(CONFIG)
    assert len(companies) == 28
    assert len({c.cik for c in companies}) == 28
    assert len({c.ticker for c in companies}) == 28
    assert all(c.group in GROUPS for c in companies)
    assert all(c.description for c in companies)
