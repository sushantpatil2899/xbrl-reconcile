import pytest

from xbrl_reconcile.config import Company, ConfigError, Event, load_companies, parse_companies

DEFAULTS = {
    "start_year": 2009,
    "end_year": None,
    "enabled": True,
    "report_types": ["10-K", "10-Q"],
}


def make_config(*companies, defaults=None):
    return {
        "defaults": dict(DEFAULTS if defaults is None else defaults),
        "companies": list(companies),
    }


def test_company_inherits_defaults():
    [company] = parse_companies(
        make_config({"cik": 1108524, "ticker": "CRM", "name": "Salesforce"})
    )
    assert company == Company(
        cik=1108524,
        ticker="CRM",
        name="Salesforce",
        start_year=2009,
        end_year=None,
        enabled=True,
        report_types=("10-K", "10-Q"),
    )


def test_company_value_overrides_default():
    [company] = parse_companies(
        make_config({"cik": 1, "ticker": "A", "name": "A", "start_year": 2018, "enabled": False})
    )
    assert company.start_year == 2018
    assert company.enabled is False


def test_descriptive_fields_and_events_are_parsed():
    [company] = parse_companies(
        make_config(
            {
                "cik": 1,
                "ticker": "A",
                "name": "A",
                "description": "Software",
                "group": "old_timer",
                "events": [{"year": 2021, "note": "Acquired Slack"}],
                "notes": "Free text",
            }
        )
    )
    assert company.events == (Event(year=2021, note="Acquired Slack"),)
    assert company.description == "Software"
    assert company.group == "old_timer"
    assert company.notes == "Free text"


def test_cik10_is_zero_padded():
    [company] = parse_companies(make_config({"cik": 1108524, "ticker": "CRM", "name": "S"}))
    assert company.cik10 == "0001108524"


def test_unknown_company_key_is_rejected():
    with pytest.raises(ConfigError, match="strat_year"):
        parse_companies(make_config({"cik": 1, "ticker": "A", "name": "A", "strat_year": 2010}))


def test_unknown_default_key_is_rejected():
    with pytest.raises(ConfigError, match="colour"):
        parse_companies(
            make_config({"cik": 1, "ticker": "A", "name": "A"}, defaults={**DEFAULTS, "colour": 1})
        )


def test_missing_default_key_is_rejected():
    defaults = {k: v for k, v in DEFAULTS.items() if k != "report_types"}
    with pytest.raises(ConfigError, match="report_types"):
        parse_companies(make_config({"cik": 1, "ticker": "A", "name": "A"}, defaults=defaults))


def test_missing_required_company_key_is_rejected():
    with pytest.raises(ConfigError, match="cik"):
        parse_companies(make_config({"ticker": "A", "name": "A"}))


def test_duplicate_cik_is_rejected():
    with pytest.raises(ConfigError, match="duplicate cik 1"):
        parse_companies(
            make_config(
                {"cik": 1, "ticker": "A", "name": "A"}, {"cik": 1, "ticker": "B", "name": "B"}
            )
        )


def test_end_year_before_start_year_is_rejected():
    with pytest.raises(ConfigError, match="end_year"):
        parse_companies(make_config({"cik": 1, "ticker": "A", "name": "A", "end_year": 2000}))


def test_malformed_event_is_rejected():
    with pytest.raises(ConfigError, match="event"):
        parse_companies(
            make_config({"cik": 1, "ticker": "A", "name": "A", "events": [{"year": 2020}]})
        )


def test_empty_company_list_is_rejected():
    with pytest.raises(ConfigError, match="no companies"):
        parse_companies(make_config())


def test_load_companies_reads_yaml(tmp_path):
    path = tmp_path / "companies.yml"
    path.write_text(
        "defaults:\n"
        "  start_year: 2009\n"
        "  end_year: null\n"
        "  enabled: true\n"
        "  report_types: [10-K, 10-Q]\n"
        "companies:\n"
        "  - cik: 1108524\n"
        "    ticker: CRM\n"
        "    name: Salesforce\n"
    )
    [company] = load_companies(path)
    assert company.ticker == "CRM"
    assert company.report_types == ("10-K", "10-Q")
