"""Load the vocabulary config: every closed set of values the pipeline can produce.

Two problems this solves. The value lists were written into five model yml files as
accepted_values, so adding a value meant editing several places and the config rule
was quietly broken. And a value's meaning lived only in prose beside one of those
lists, which the API cannot read, so the same explanation would have been written
again by hand for the documentation and left to drift.

Declaring them here makes config the source in both directions: models are tested
against this file, so the pipeline cannot produce an undeclared value, and the API
generates its parameter documentation from these descriptions, so a value cannot
reach a caller without an explanation.

A missing description is an error rather than a default, because the description is
the whole point: an undocumented value is the thing this file exists to prevent.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from xbrl_reconcile.config import ConfigError

VOCABULARY_KEYS = {"description", "values"}
VALUE_KEYS = {"value", "description"}


@dataclass(frozen=True)
class VocabularyValue:
    value: str
    description: str
    position: int


@dataclass(frozen=True)
class Vocabulary:
    name: str
    description: str
    values: tuple[VocabularyValue, ...]


@dataclass(frozen=True)
class VocabularyConfig:
    vocabularies: dict[str, Vocabulary]

    def rows(self) -> list[dict]:
        """One row per value, flat, which is what read_json wants from a snapshot."""
        return [
            {
                "vocabulary": vocabulary.name,
                "vocabulary_description": vocabulary.description,
                "value": value.value,
                "description": value.description,
                "position": value.position,
            }
            for vocabulary in self.vocabularies.values()
            for value in vocabulary.values
        ]

    def values_of(self, name: str) -> tuple[str, ...]:
        return tuple(value.value for value in self.vocabularies[name].values)


def load_vocabularies(path: Path) -> VocabularyConfig:
    with open(path) as f:
        return parse_vocabularies(yaml.safe_load(f))


def parse_vocabularies(data: dict) -> VocabularyConfig:
    if not isinstance(data, dict):
        raise ConfigError("vocabulary config must be a mapping with 'vocabularies'")
    _reject_unknown(set(data), {"vocabularies"}, "top level")

    raw = data.get("vocabularies") or {}
    if not raw:
        raise ConfigError("no vocabularies defined")

    return VocabularyConfig(
        vocabularies={name: _parse_vocabulary(name, body) for name, body in raw.items()}
    )


def _parse_vocabulary(name: str, raw: dict) -> Vocabulary:
    if not isinstance(raw, dict):
        raise ConfigError(f"vocabulary {name} must be a mapping")
    _reject_unknown(set(raw), VOCABULARY_KEYS, f"vocabulary {name}")

    description = _description(raw, f"vocabulary {name}")
    raw_values = raw.get("values") or []
    if not isinstance(raw_values, list) or not raw_values:
        raise ConfigError(f"vocabulary {name}: values must be a non empty list")

    values: list[VocabularyValue] = []
    seen: set[str] = set()
    # Position comes from the order the file lists them, so high before medium before
    # low survives into the published mart and the documentation.
    for position, entry in enumerate(raw_values, start=1):
        value = _parse_value(name, entry, position)
        if value.value in seen:
            raise ConfigError(f"vocabulary {name}: '{value.value}' is listed twice")
        seen.add(value.value)
        values.append(value)

    return Vocabulary(name=name, description=description, values=tuple(values))


def _parse_value(vocabulary: str, raw: dict, position: int) -> VocabularyValue:
    where = f"vocabulary {vocabulary} value {position}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be a mapping with 'value' and 'description'")
    _reject_unknown(set(raw), VALUE_KEYS, where)

    value = raw.get("value")
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: value must be a non empty string, got {value!r}")

    return VocabularyValue(
        value=value,
        description=_description(raw, f"vocabulary {vocabulary} value '{value}'"),
        position=position,
    )


def _description(raw: dict, where: str) -> str:
    description = raw.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ConfigError(f"{where} needs a description")
    # Folded YAML keeps the line breaks it was wrapped at, which would reach the API
    # documentation as hard breaks mid sentence.
    return " ".join(description.split())


def _reject_unknown(keys: set, allowed: set, where: str) -> None:
    unknown = keys - allowed
    if unknown:
        raise ConfigError(f"unknown keys in {where}: {sorted(unknown)}")
