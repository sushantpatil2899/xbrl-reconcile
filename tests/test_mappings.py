from datetime import date
from pathlib import Path

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
        "is_optional": False,
        "is_additive": True,
        "position": 1,
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
        parse_mappings({**make_config(), "summable_axes": [{"axis": "X", "confidence": "high"}]})


def test_a_summable_axis_needs_a_name():
    with pytest.raises(ConfigError, match="axis name"):
        parse_mappings({**make_config(), "summable_axes": [{"confidence": "medium"}]})


def test_concepts_are_required_unless_declared_optional():
    concepts = {
        "revenue": dict(REVENUE),
        "temporary_equity": {
            "statement": "balance_sheet",
            "unit": "USD",
            "optional": True,
            "tags": [{"tag": "us-gaap:TemporaryEquityCarryingAmount", "confidence": "high"}],
        },
    }
    config = parse_mappings(make_config(concepts))
    assert config.concepts["revenue"].optional is False
    assert config.concepts["temporary_equity"].optional is True


def test_optional_is_carried_into_the_snapshot_rows():
    concepts = {"revenue": {**REVENUE, "optional": True}}
    rows = parse_mappings(make_config(concepts)).concept_rows()
    assert all(row["is_optional"] for row in rows)


def test_concepts_are_additive_unless_declared_otherwise():
    """A sum can be split across periods; a ratio or an average cannot."""
    concepts = {
        "revenue": dict(REVENUE),
        "eps_diluted": {
            "statement": "income_statement",
            "unit": "USD/shares",
            "additive": False,
            "tags": [{"tag": "us-gaap:EarningsPerShareDiluted", "confidence": "high"}],
        },
    }
    config = parse_mappings(make_config(concepts))
    assert config.concepts["revenue"].additive is True
    assert config.concepts["eps_diluted"].additive is False


def test_additive_is_carried_into_the_snapshot_rows():
    concepts = {"revenue": {**REVENUE, "additive": False}}
    rows = parse_mappings(make_config(concepts)).concept_rows()
    assert not any(row["is_additive"] for row in rows)


def test_a_concepts_position_follows_the_order_of_the_config_file():
    """The file's order is the statement's order, as its `tags` order is priority."""
    concepts = {
        "revenue": dict(REVENUE),
        "cost_of_revenue": {
            "statement": "income_statement",
            "unit": "USD",
            "tags": [{"tag": "us-gaap:CostOfRevenue", "confidence": "high"}],
        },
    }
    config = parse_mappings(make_config(concepts))

    assert config.concepts["revenue"].position == 1
    assert config.concepts["cost_of_revenue"].position == 2


def test_position_is_not_confused_with_a_tags_priority():
    """Both are called position in the config's own language; only one is a line."""
    config = parse_mappings(make_config({"revenue": dict(REVENUE)}))
    revenue = config.concepts["revenue"]

    assert revenue.position == 1
    assert [tag.priority for tag in revenue.tags] == [10, 20, 30]


def test_position_is_carried_into_the_snapshot_rows():
    rows = parse_mappings(make_config({"revenue": dict(REVENUE)})).concept_rows()
    assert {row["position"] for row in rows} == {1}


def test_an_override_can_sum_parts_a_company_reports_without_a_total():
    """One part may be a custom tag, which companyfacts drops, so the sum is scoped
    to one company: a custom tag name is not unique across filers."""
    overrides = [
        {
            "cik": 1327811,
            "concept": "revenue",
            "sum": ["custom:SubscriptionRevenues", "us-gaap:TechnologyServicesRevenue"],
            "confidence": "medium",
            "from_year": 2014,
            "through_year": 2016,
        }
    ]
    config = parse_mappings(make_config(overrides=overrides))
    override = config.overrides[0]

    assert override.sum == ("custom:SubscriptionRevenues", "us-gaap:TechnologyServicesRevenue")
    assert (override.from_year, override.through_year) == (2014, 2016)

    rows = [row for row in config.override_rows() if row["mode"] == "sum"]
    assert [(row["taxonomy"], row["position"]) for row in rows] == [
        ("custom", 10),
        ("us-gaap", 20),
    ]


def test_a_sum_of_one_tag_is_rejected():
    """A single tag is a prefer, not a sum, and summing one part hides the mistake."""
    overrides = [{"cik": 1327811, "concept": "revenue", "sum": ["custom:Only"]}]
    with pytest.raises(ConfigError, match="needs at least two tags"):
        parse_mappings(make_config(overrides=overrides))


def test_a_sum_listing_the_same_tag_twice_is_rejected():
    """It would double count, which is the error the whole mechanism exists to avoid."""
    overrides = [{"cik": 1327811, "concept": "revenue", "sum": ["custom:A", "custom:A"]}]
    with pytest.raises(ConfigError, match="same tag twice"):
        parse_mappings(make_config(overrides=overrides))


def test_an_override_still_needs_to_do_something():
    with pytest.raises(ConfigError, match="'prefer', 'ignore' or 'sum'"):
        parse_mappings(make_config(overrides=[{"cik": 1327811, "concept": "revenue"}]))


def test_a_flag_written_as_text_is_rejected_rather_than_read_as_true():
    """A quoted "false" is a non empty string, so bool() would read it as true."""
    for flag in ("additive", "optional"):
        concepts = {"revenue": {**REVENUE, flag: "false"}}
        with pytest.raises(ConfigError, match=f"{flag} must be true or false"):
            parse_mappings(make_config(concepts))


MAPPINGS = Path(__file__).parent.parent / "config" / "tag_mappings.yml"

SCALE_BASE = {
    "concepts": {
        "shares_diluted": {
            "statement": "income_statement",
            "unit": "shares",
            "tags": [
                {
                    "tag": "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
                    "confidence": "high",
                }
            ],
        }
    }
}


def with_scale(**override):
    entry = {
        "cik": 1,
        "concept": "shares_diluted",
        "multiply_by": 1000,
        "accessions": ["0001564590-15-006500"],
    }
    entry.update(override)
    return SCALE_BASE | {"scale_overrides": [entry]}


def test_a_scale_override_produces_one_row_per_filing():
    """Flat rows, because the correction is applied by joining on the accession."""
    config = parse_mappings(with_scale(accessions=["0001564590-15-006500", "0001564590-15-009381"]))

    rows = config.scale_override_rows()
    assert [row["accession"] for row in rows] == [
        "0001564590-15-006500",
        "0001564590-15-009381",
    ]
    assert all(row["multiply_by"] == 1000.0 for row in rows)
    assert all(row["from_period_end"] is None for row in rows)


def test_period_bounds_are_optional_and_kept_when_given():
    """Only a mixed filing needs them: Datadog tagged current periods in thousands
    and left the prior year comparatives in the same document in units."""
    config = parse_mappings(with_scale(from_period_end=date(2019, 1, 1)))

    assert config.scale_override_rows()[0]["from_period_end"] == "2019-01-01"


def test_a_scale_override_for_an_unmapped_concept_is_rejected():
    with pytest.raises(ConfigError, match="not a mapped concept"):
        parse_mappings(with_scale(concept="ebitda"))


def test_a_multiplier_that_changes_nothing_is_rejected():
    """A factor of one reads as a correction that was applied and was not."""
    with pytest.raises(ConfigError, match="would change nothing"):
        parse_mappings(with_scale(multiply_by=1))


def test_a_multiplier_that_is_not_a_number_is_rejected():
    with pytest.raises(ConfigError, match="must be a number"):
        parse_mappings(with_scale(multiply_by="1000"))


def test_an_empty_accession_list_is_rejected():
    """Without a filing to point at, the override has no grain to apply on."""
    with pytest.raises(ConfigError, match="accessions must be a non empty list"):
        parse_mappings(with_scale(accessions=[]))


def test_a_backwards_period_window_is_rejected():
    with pytest.raises(ConfigError, match="is after"):
        parse_mappings(
            with_scale(from_period_end=date(2020, 1, 1), through_period_end=date(2019, 1, 1))
        )


def test_a_misspelled_scale_key_is_an_error_rather_than_ignored():
    with pytest.raises(ConfigError, match="unknown keys"):
        parse_mappings(with_scale(multiply_bye=1000))


def with_hints(hints):
    concept = dict(SCALE_BASE["concepts"]["shares_diluted"])
    concept["label_hints"] = hints
    return {"concepts": {"shares_diluted": concept}}


def test_label_hints_are_lowercased_so_matching_is_a_plain_substring_test():
    config = parse_mappings(with_hints(["Total Operating Expenses", "  Total Expenses  "]))

    assert config.concepts["shares_diluted"].label_hints == (
        "total operating expenses",
        "total expenses",
    )


def test_label_hint_rows_are_one_per_concept_and_phrase():
    config = parse_mappings(with_hints(["gross profit", "gross margin"]))

    assert config.label_hint_rows() == [
        {"concept": "shares_diluted", "phrase": "gross profit"},
        {"concept": "shares_diluted", "phrase": "gross margin"},
    ]


def test_a_concept_without_hints_produces_no_rows():
    """Hints are opt in: most concepts have a label space too wide to list."""
    assert parse_mappings(SCALE_BASE).label_hint_rows() == []


def test_an_empty_hint_list_is_rejected_rather_than_treated_as_absent():
    with pytest.raises(ConfigError, match="must be a non empty list"):
        parse_mappings(with_hints([]))


def test_a_hint_that_is_not_a_phrase_is_rejected():
    with pytest.raises(ConfigError, match="must be a phrase"):
        parse_mappings(with_hints(["gross profit", 7]))


def test_the_real_config_declares_hints_for_the_concepts_that_needed_them():
    """Workday's error was in operating expenses, found by investigation not by code."""
    config = load_mappings(MAPPINGS)

    assert "operating expenses" in config.concepts["operating_expenses"].label_hints
    assert config.concepts["gross_profit"].label_hints == ("gross profit",)
