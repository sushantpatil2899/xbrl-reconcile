from pathlib import Path

import pytest

from xbrl_reconcile.config import ConfigError
from xbrl_reconcile.mappings import (
    COMPONENT_CONFIDENCE_LEVELS,
    CONFIDENCE_LEVELS,
    DEFAULT_COMPONENT_CONFIDENCE,
    DEFAULT_OVERRIDE_CONFIDENCE,
    STATEMENTS,
)
from xbrl_reconcile.vocabularies import load_vocabularies, parse_vocabularies

CONFIG = Path("config/vocabularies.yml")


def one(values: list[dict] | None = None, **vocabulary) -> dict:
    """A minimal valid config, so each test changes only what it is about.

    `values is None` rather than a falsy check, or passing an empty list would
    silently get the default and the test for an empty list would test nothing.
    """
    default = [{"value": "a", "description": "A."}]
    body = {"description": "A set.", "values": default if values is None else values}
    body.update(vocabulary)
    return {"vocabularies": {"thing": body}}


def test_values_keep_the_order_config_lists_them_in():
    """high before medium before low is meaningful, and alphabetical would lose it."""
    config = parse_vocabularies(
        one(
            [
                {"value": "high", "description": "Most sure."},
                {"value": "medium", "description": "Less sure."},
                {"value": "low", "description": "Least sure."},
            ]
        )
    )

    assert config.values_of("thing") == ("high", "medium", "low")
    assert [value.position for value in config.vocabularies["thing"].values] == [1, 2, 3]


def test_rows_are_flat_so_a_snapshot_can_be_read_as_a_table():
    rows = parse_vocabularies(one()).rows()

    assert rows == [
        {
            "vocabulary": "thing",
            "vocabulary_description": "A set.",
            "value": "a",
            "description": "A.",
            "position": 1,
        }
    ]


def test_a_folded_description_becomes_one_line():
    """YAML folding keeps the break it was wrapped at, which would reach the docs."""
    config = parse_vocabularies(
        one([{"value": "a", "description": "A sentence that was\nwrapped in the file."}])
    )

    assert config.vocabularies["thing"].values[0].description == (
        "A sentence that was wrapped in the file."
    )


def test_a_duplicate_value_is_rejected():
    with pytest.raises(ConfigError, match="'a' is listed twice"):
        parse_vocabularies(
            one([{"value": "a", "description": "A."}, {"value": "a", "description": "Again."}])
        )


def test_a_value_with_no_description_is_rejected():
    """The description is the point: an undescribed value is what this config prevents."""
    with pytest.raises(ConfigError, match="needs a description"):
        parse_vocabularies(one([{"value": "a"}]))


def test_an_empty_description_is_rejected_like_a_missing_one():
    with pytest.raises(ConfigError, match="needs a description"):
        parse_vocabularies(one([{"value": "a", "description": "   "}]))


def test_a_vocabulary_with_no_description_is_rejected():
    with pytest.raises(ConfigError, match="vocabulary thing needs a description"):
        parse_vocabularies({"vocabularies": {"thing": {"values": [{"value": "a"}]}}})


def test_a_vocabulary_with_no_values_is_rejected():
    with pytest.raises(ConfigError, match="values must be a non empty list"):
        parse_vocabularies(one(values=[]))


def test_a_misspelled_key_is_an_error_rather_than_ignored():
    with pytest.raises(ConfigError, match="unknown keys"):
        parse_vocabularies(one([{"value": "a", "description": "A.", "descriptoin": "typo"}]))


def test_an_empty_config_is_rejected():
    with pytest.raises(ConfigError, match="no vocabularies defined"):
        parse_vocabularies({"vocabularies": {}})


def test_the_real_config_loads_and_every_value_is_described():
    config = load_vocabularies(CONFIG)

    assert "confidence" in config.vocabularies
    assert config.values_of("confidence") == ("high", "medium", "low", "derived")
    # The mapping config may not declare a value as derived: that describes
    # arithmetic the pipeline did, not a judgement about a tag.
    assert config.values_of("mapping_confidence") == ("high", "medium", "low")
    assert all(row["description"] for row in config.rows())


def test_the_python_constants_match_the_declared_vocabularies():
    """mappings.py mirrors these sets instead of reading them, so this is the guard.

    It validates config before any network call and is a pure function of its input,
    which reading YAML at import time would break. The duplication is therefore
    deliberate, and this test is what stops it drifting in anything that ships.
    """
    config = load_vocabularies(CONFIG)

    assert CONFIDENCE_LEVELS == set(config.values_of("mapping_confidence"))
    assert STATEMENTS == set(config.values_of("statement"))


def test_the_component_rule_names_only_declared_levels():
    """A sum we assembled can never be high confidence.

    That is a rule about the vocabulary rather than a copy of it, so a strict subset
    rather than equality. What the test enforces is that the rule cannot come to
    name a level config does not declare.
    """
    levels = set(load_vocabularies(CONFIG).values_of("mapping_confidence"))

    assert COMPONENT_CONFIDENCE_LEVELS < levels
    assert DEFAULT_COMPONENT_CONFIDENCE in COMPONENT_CONFIDENCE_LEVELS
    assert DEFAULT_OVERRIDE_CONFIDENCE in levels
