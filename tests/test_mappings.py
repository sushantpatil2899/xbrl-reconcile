import pytest

from xbrl_reconcile.config import Company
from xbrl_reconcile.mappings import (
    ComponentSet,
    ConfigError,
    TagMapping,
    load_mappings,
    parse_mappings,
    validate_against_companies,
)

REVENUE = {
    "statement": "income_statement",
    "unit": "USD",
    "tags": [
        {
            "tag": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "confidence": "high",
        },
        {"tag": "us-gaap:Revenues", "confidence": "high"},
        {"tag": "us-gaap:SalesRevenueNet", "confidence": "medium", "note": "Retired in 2018"},
    ],
}


def make_config(concepts=None, overrides=None):
    return {
        "concepts": {"revenue": dict(REVENUE)} if concepts is None else concepts,
        "company_overrides": overrides or [],
    }


def company(cik=796343, ticker="ADBE", enabled=True):
    return Company(
        cik=cik,
        ticker=ticker,
        name=ticker,
        start_year=2009,
        end_year=None,
        enabled=enabled,
        report_types=("10-K",),
    )


def test_list_order_becomes_priority():
    config = parse_mappings(make_config())
    [concept] = config.concepts.values()
    assert [(t.tag, t.priority) for t in concept.tags] == [
        ("RevenueFromContractWithCustomerExcludingAssessedTax", 10),
        ("Revenues", 20),
        ("SalesRevenueNet", 30),
    ]


def test_taxonomy_is_split_from_the_tag():
    config = parse_mappings(make_config())
    first = config.concepts["revenue"].tags[0]
    assert first == TagMapping(
        concept="revenue",
        taxonomy="us-gaap",
        tag="RevenueFromContractWithCustomerExcludingAssessedTax",
        priority=10,
        confidence="high",
        note="",
    )


def test_concept_metadata_is_kept():
    concept = parse_mappings(make_config()).concepts["revenue"]
    assert concept.statement == "income_statement"
    assert concept.unit == "USD"


def test_tag_without_a_taxonomy_is_rejected():
    concepts = {"revenue": {**REVENUE, "tags": [{"tag": "Revenues", "confidence": "high"}]}}
    with pytest.raises(ConfigError, match="taxonomy"):
        parse_mappings(make_config(concepts))


def test_unknown_confidence_is_rejected():
    concepts = {"revenue": {**REVENUE, "tags": [{"tag": "us-gaap:Revenues", "confidence": "hgih"}]}}
    with pytest.raises(ConfigError, match="hgih"):
        parse_mappings(make_config(concepts))


def test_derived_confidence_cannot_be_declared_in_config():
    concepts = {
        "revenue": {**REVENUE, "tags": [{"tag": "us-gaap:Revenues", "confidence": "derived"}]}
    }
    with pytest.raises(ConfigError, match="derived"):
        parse_mappings(make_config(concepts))


def test_unknown_statement_is_rejected():
    concepts = {"revenue": {**REVENUE, "statement": "income statement"}}
    with pytest.raises(ConfigError, match="statement"):
        parse_mappings(make_config(concepts))


def test_unknown_key_in_a_concept_is_rejected():
    concepts = {"revenue": {**REVENUE, "untis": "USD"}}
    with pytest.raises(ConfigError, match="untis"):
        parse_mappings(make_config(concepts))


def test_duplicate_tag_within_a_concept_is_rejected():
    concepts = {
        "revenue": {
            **REVENUE,
            "tags": [
                {"tag": "us-gaap:Revenues", "confidence": "high"},
                {"tag": "us-gaap:Revenues", "confidence": "low"},
            ],
        }
    }
    with pytest.raises(ConfigError, match="duplicate tag"):
        parse_mappings(make_config(concepts))


def test_same_tag_in_two_concepts_is_rejected():
    concepts = {
        "revenue": dict(REVENUE),
        "other_revenue": {
            "statement": "income_statement",
            "unit": "USD",
            "tags": [{"tag": "us-gaap:Revenues", "confidence": "low"}],
        },
    }
    with pytest.raises(ConfigError, match="us-gaap:Revenues"):
        parse_mappings(make_config(concepts))


def test_concept_without_tags_is_rejected():
    with pytest.raises(ConfigError, match="no tags"):
        parse_mappings(make_config({"revenue": {**REVENUE, "tags": []}}))


def test_no_concepts_is_rejected():
    with pytest.raises(ConfigError, match="no concepts"):
        parse_mappings(make_config({}))


def test_override_is_parsed():
    overrides = [
        {
            "cik": 796343,
            "concept": "revenue",
            "ignore": ["us-gaap:SalesRevenueServicesNet"],
            "note": "A component of Revenues",
        }
    ]
    [override] = parse_mappings(make_config(overrides=overrides)).overrides
    assert override.cik == 796343
    assert override.ignore == ("us-gaap:SalesRevenueServicesNet",)
    assert override.prefer == ()
    assert override.from_year is None and override.through_year is None


def test_override_for_an_unknown_concept_is_rejected():
    overrides = [{"cik": 1, "concept": "revenu", "ignore": ["us-gaap:X"]}]
    with pytest.raises(ConfigError, match="revenu"):
        parse_mappings(make_config(overrides=overrides))


def test_override_without_prefer_or_ignore_is_rejected():
    overrides = [{"cik": 1, "concept": "revenue", "note": "does nothing"}]
    with pytest.raises(ConfigError, match="prefer"):
        parse_mappings(make_config(overrides=overrides))


def test_override_with_an_impossible_year_range_is_rejected():
    overrides = [
        {
            "cik": 1,
            "concept": "revenue",
            "prefer": ["us-gaap:X"],
            "from_year": 2020,
            "through_year": 2015,
        }
    ]
    with pytest.raises(ConfigError, match="through_year"):
        parse_mappings(make_config(overrides=overrides))


def test_rows_flatten_concepts_and_overrides_for_the_snapshot():
    overrides = [
        {"cik": 796343, "concept": "revenue", "ignore": ["us-gaap:SalesRevenueServicesNet"]}
    ]
    config = parse_mappings(make_config(overrides=overrides))

    concept_rows = config.concept_rows()
    assert concept_rows[0] == {
        "concept": "revenue",
        "statement": "income_statement",
        "unit": "USD",
        "taxonomy": "us-gaap",
        "tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "priority": 10,
        "confidence": "high",
        "note": "",
    }
    assert len(concept_rows) == 3

    assert config.override_rows() == [
        {
            "cik": 796343,
            "concept": "revenue",
            "mode": "ignore",
            "taxonomy": "us-gaap",
            "tag": "SalesRevenueServicesNet",
            "position": 10,
            "confidence": "low",
            "from_year": None,
            "through_year": None,
            "note": "",
        }
    ]


def test_cross_check_rejects_an_override_for_an_unknown_cik():
    overrides = [{"cik": 796433, "concept": "revenue", "ignore": ["us-gaap:X"]}]
    config = parse_mappings(make_config(overrides=overrides))
    with pytest.raises(ConfigError, match="796433"):
        validate_against_companies(config, [company()])


def test_cross_check_warns_about_an_override_for_a_disabled_company():
    overrides = [{"cik": 796343, "concept": "revenue", "ignore": ["us-gaap:X"]}]
    config = parse_mappings(make_config(overrides=overrides))

    warnings = validate_against_companies(config, [company(enabled=False)])

    assert len(warnings) == 1
    assert "ADBE" in warnings[0]


def test_cross_check_is_silent_when_everything_matches():
    overrides = [{"cik": 796343, "concept": "revenue", "ignore": ["us-gaap:X"]}]
    config = parse_mappings(make_config(overrides=overrides))
    assert validate_against_companies(config, [company()]) == []


def test_load_mappings_reads_yaml(tmp_path):
    path = tmp_path / "tag_mappings.yml"
    path.write_text(
        "concepts:\n"
        "  revenue:\n"
        "    statement: income_statement\n"
        "    unit: USD\n"
        "    tags:\n"
        '      - { tag: "us-gaap:Revenues", confidence: high }\n'
        "company_overrides: []\n"
    )
    config = load_mappings(path)
    assert config.concepts["revenue"].tags[0].tag == "Revenues"


def test_override_confidence_defaults_to_low():
    """A tag used for one company on our judgement is a weaker claim."""
    overrides = [{"cik": 1, "concept": "revenue", "prefer": ["us-gaap:X"]}]
    [override] = parse_mappings(make_config(overrides=overrides)).overrides
    assert override.confidence == "low"


def test_override_confidence_can_be_stated():
    overrides = [{"cik": 1, "concept": "revenue", "prefer": ["us-gaap:X"], "confidence": "medium"}]
    [override] = parse_mappings(make_config(overrides=overrides)).overrides
    assert override.confidence == "medium"


def test_override_with_unknown_confidence_is_rejected():
    overrides = [{"cik": 1, "concept": "revenue", "prefer": ["us-gaap:X"], "confidence": "certain"}]
    with pytest.raises(ConfigError, match="certain"):
        parse_mappings(make_config(overrides=overrides))


COMPONENTS = [
    {
        "tags": ["us-gaap:CostOfServices", "us-gaap:CostOfGoodsSold"],
        "confidence": "medium",
        "note": "Filers without a total tag report these two parts",
    }
]


def test_component_set_is_parsed():
    concepts = {"revenue": {**REVENUE, "components": COMPONENTS}}
    [component] = parse_mappings(make_config(concepts)).concepts["revenue"].components
    assert component == ComponentSet(
        concept="revenue",
        taxonomy="us-gaap",
        tags=("CostOfServices", "CostOfGoodsSold"),
        position=10,
        confidence="medium",
        note="Filers without a total tag report these two parts",
    )


def test_component_confidence_defaults_to_medium():
    components = [{"tags": ["us-gaap:A", "us-gaap:B"]}]
    [component] = (
        parse_mappings(make_config({"revenue": {**REVENUE, "components": components}}))
        .concepts["revenue"]
        .components
    )
    assert component.confidence == "medium"


def test_component_set_cannot_be_high_confidence():
    """A sum we assembled is a weaker claim than a total the company reported."""
    components = [{"tags": ["us-gaap:A", "us-gaap:B"], "confidence": "high"}]
    with pytest.raises(ConfigError, match="high"):
        parse_mappings(make_config({"revenue": {**REVENUE, "components": components}}))


def test_component_set_needs_at_least_two_tags():
    components = [{"tags": ["us-gaap:A"]}]
    with pytest.raises(ConfigError, match="at least two"):
        parse_mappings(make_config({"revenue": {**REVENUE, "components": components}}))


def test_component_tags_must_share_a_taxonomy():
    components = [{"tags": ["us-gaap:A", "ifrs-full:B"]}]
    with pytest.raises(ConfigError, match="taxonomy"):
        parse_mappings(make_config({"revenue": {**REVENUE, "components": components}}))


def test_a_tag_cannot_be_both_a_total_and_a_component():
    components = [{"tags": ["us-gaap:Revenues", "us-gaap:Other"]}]
    with pytest.raises(ConfigError, match="us-gaap:Revenues"):
        parse_mappings(make_config({"revenue": {**REVENUE, "components": components}}))


def test_component_rows_are_flat_for_sql():
    concepts = {"revenue": {**REVENUE, "components": COMPONENTS}}
    rows = parse_mappings(make_config(concepts)).component_rows()
    assert rows == [
        {
            "concept": "revenue",
            "statement": "income_statement",
            "unit": "USD",
            "taxonomy": "us-gaap",
            "tag": "CostOfServices",
            "position": 10,
            "component_count": 2,
            "confidence": "medium",
            "note": "Filers without a total tag report these two parts",
        },
        {
            "concept": "revenue",
            "statement": "income_statement",
            "unit": "USD",
            "taxonomy": "us-gaap",
            "tag": "CostOfGoodsSold",
            "position": 10,
            "component_count": 2,
            "confidence": "medium",
            "note": "Filers without a total tag report these two parts",
        },
    ]


def test_summable_axes_are_parsed():
    config = parse_mappings(
        {
            **make_config(),
            "summable_axes": [{"axis": "ProductOrService", "confidence": "medium", "note": "n"}],
        }
    )
    assert config.summable_axis_rows() == [
        {"axis": "ProductOrService", "confidence": "medium", "note": "n"}
    ]


def test_a_summable_axis_cannot_be_high_confidence():
    with pytest.raises(ConfigError, match="high"):
        parse_mappings(
            {**make_config(), "summable_axes": [{"axis": "X", "confidence": "high"}]}
        )


def test_a_summable_axis_needs_a_name():
    with pytest.raises(ConfigError, match="axis name"):
        parse_mappings({**make_config(), "summable_axes": [{"confidence": "medium"}]})
