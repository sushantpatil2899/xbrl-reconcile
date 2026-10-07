"""Load the tag mapping config, which says how raw SEC tags become concepts.

A mapping mistake fails silently: a misspelled tag matches nothing, the concept
produces no rows, and a company's revenue is simply missing from the statement.
So the config is validated here, before dbt ever reads it.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from xbrl_reconcile.config import Company, ConfigError

# config/vocabularies.yml is where these sets are declared, for the dbt tests
# and the API documentation. They are mirrored here rather than read from there,
# because this module validates config before any network call and is a pure
# function of its input: a dict goes in, a config comes out, no filesystem. Reading
# YAML at import time would make that depend on the working directory, and threading
# the vocabulary through the five private parsers would touch every caller to pass
# three strings that never change.
#
# test_the_python_constants_match_the_declared_vocabularies keeps the mirror honest,
# so the two cannot drift in anything that ships.
CONFIDENCE_LEVELS = {"high", "medium", "low"}
STATEMENTS = {"income_statement", "balance_sheet", "cash_flow"}

CONCEPT_KEYS = {"statement", "unit", "tags", "components", "optional", "additive"}
COMPONENT_KEYS = {"tags", "confidence", "note"}
SUMMABLE_AXIS_KEYS = {"axis", "confidence", "note"}
TAG_KEYS = {"tag", "confidence", "note"}
OVERRIDE_KEYS = {
    "cik",
    "concept",
    "prefer",
    "ignore",
    "sum",
    "confidence",
    "from_year",
    "through_year",
    "note",
}

# A sum we assembled from parts is a weaker claim than a total the company
# reported itself, so a component set can never be high confidence.
COMPONENT_CONFIDENCE_LEVELS = {"medium", "low"}
DEFAULT_COMPONENT_CONFIDENCE = "medium"

# A tag used for one company on our judgement is a weaker claim than a sector
# wide standard tag, so an override that introduces a tag defaults to low.
DEFAULT_OVERRIDE_CONFIDENCE = "low"

PRIORITY_STEP = 10


@dataclass(frozen=True)
class TagMapping:
    concept: str
    taxonomy: str
    tag: str
    priority: int
    confidence: str
    note: str = ""

    @property
    def qualified_tag(self) -> str:
        return f"{self.taxonomy}:{self.tag}"


@dataclass(frozen=True)
class ComponentSet:
    """Tags that sum to a concept, for filers that never report the total."""

    concept: str
    taxonomy: str
    tags: tuple[str, ...]
    position: int
    confidence: str
    note: str = ""


@dataclass(frozen=True)
class ConceptSpec:
    name: str
    statement: str
    unit: str
    tags: tuple[TagMapping, ...] = ()
    components: tuple[ComponentSet, ...] = ()
    # True when most filers legitimately have none of this, so its absence is an
    # answer rather than a gap. Declared rather than inferred: nothing in the
    # facts distinguishes "the company has none" from "we failed to map it".
    optional: bool = False
    # False for a ratio or an average, whose periods cannot be added or
    # subtracted. Earnings per share and a weighted average share count both look
    # like ordinary numbers, so this cannot be inferred from the facts either.
    additive: bool = True
    # Where this line sits on its statement, taken from the order the concepts
    # appear in the config file. Inside a concept the order of `tags` already means
    # priority, so order carrying meaning is the file's existing convention.
    position: int = 0


@dataclass(frozen=True)
class CompanyOverride:
    cik: int
    concept: str
    prefer: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    # Tags to add together when a company reports a concept as parts with no total.
    # Scoped to one company deliberately: a custom tag name is not unique, and
    # CostOfRevenueSubscriptionAndSupport is used by two of these filers for
    # different things. A global component set would sum the wrong company's parts.
    sum: tuple[str, ...] = ()
    confidence: str = DEFAULT_OVERRIDE_CONFIDENCE
    from_year: int | None = None
    through_year: int | None = None
    note: str = ""


@dataclass(frozen=True)
class SummableAxis:
    """An axis whose members partition whatever they break down."""

    axis: str
    confidence: str
    note: str = ""


@dataclass(frozen=True)
class MappingConfig:
    concepts: dict[str, ConceptSpec] = field(default_factory=dict)
    overrides: tuple[CompanyOverride, ...] = ()
    summable_axes: tuple[SummableAxis, ...] = ()

    def concept_rows(self) -> list[dict]:
        """One row per concept and tag, the shape dbt reads."""
        return [
            {
                "concept": concept.name,
                "statement": concept.statement,
                "unit": concept.unit,
                "is_optional": concept.optional,
                "is_additive": concept.additive,
                "position": concept.position,
                "taxonomy": mapping.taxonomy,
                "tag": mapping.tag,
                "priority": mapping.priority,
                "confidence": mapping.confidence,
                "note": mapping.note,
            }
            for concept in self.concepts.values()
            for mapping in concept.tags
        ]

    def component_rows(self) -> list[dict]:
        """One row per component set and tag, so SQL can group and sum them."""
        return [
            {
                "concept": concept.name,
                "statement": concept.statement,
                "unit": concept.unit,
                "taxonomy": component.taxonomy,
                "tag": tag,
                "position": component.position,
                "component_count": len(component.tags),
                "confidence": component.confidence,
                "note": component.note,
            }
            for concept in self.concepts.values()
            for component in concept.components
            for tag in component.tags
        ]

    def summable_axis_rows(self) -> list[dict]:
        return [
            {"axis": entry.axis, "confidence": entry.confidence, "note": entry.note}
            for entry in self.summable_axes
        ]

    def override_rows(self) -> list[dict]:
        """One row per override and tag. Flat rows are far easier to join in SQL."""
        rows = []
        for override in self.overrides:
            for mode in ("prefer", "ignore", "sum"):
                for position, qualified in enumerate(getattr(override, mode), start=1):
                    taxonomy, tag = qualified.split(":", 1)
                    rows.append(
                        {
                            "cik": override.cik,
                            "concept": override.concept,
                            "mode": mode,
                            "taxonomy": taxonomy,
                            "tag": tag,
                            "position": position * PRIORITY_STEP,
                            "confidence": override.confidence,
                            "from_year": override.from_year,
                            "through_year": override.through_year,
                            "note": override.note,
                        }
                    )
        return rows


def load_mappings(path: Path) -> MappingConfig:
    with open(path) as f:
        return parse_mappings(yaml.safe_load(f))


def parse_mappings(data: dict) -> MappingConfig:
    if not isinstance(data, dict):
        raise ConfigError("mapping config must be a mapping with 'concepts'")
    _reject_unknown(set(data), {"concepts", "company_overrides", "summable_axes"}, "top level")

    raw_concepts = data.get("concepts") or {}
    if not raw_concepts:
        raise ConfigError("no concepts defined")

    concepts: dict[str, ConceptSpec] = {}
    tag_owner: dict[str, str] = {}
    for position, (name, raw) in enumerate(raw_concepts.items(), start=1):
        concept = _parse_concept(name, raw, line=position)
        for mapping in concept.tags:
            owner = tag_owner.get(mapping.qualified_tag)
            if owner is not None:
                raise ConfigError(
                    f"{mapping.qualified_tag} is mapped to both '{owner}' and '{name}'"
                )
            tag_owner[mapping.qualified_tag] = name
        concepts[name] = concept

    overrides = tuple(
        _parse_override(raw, concepts, index)
        for index, raw in enumerate(data.get("company_overrides") or [])
    )
    summable_axes = tuple(
        _parse_summable_axis(raw, index)
        for index, raw in enumerate(data.get("summable_axes") or [])
    )
    return MappingConfig(concepts=concepts, overrides=overrides, summable_axes=summable_axes)


def _parse_summable_axis(raw: dict, index: int) -> SummableAxis:
    label = f"summable axis {index}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{label} must be a mapping")
    _reject_unknown(set(raw), SUMMABLE_AXIS_KEYS, label)
    if not raw.get("axis"):
        raise ConfigError(f"{label} needs an axis name")
    confidence = str(raw.get("confidence", DEFAULT_COMPONENT_CONFIDENCE))
    if confidence not in COMPONENT_CONFIDENCE_LEVELS:
        raise ConfigError(
            f"{label}: confidence '{confidence}' is not allowed; a total recovered by "
            f"summing members must be one of {sorted(COMPONENT_CONFIDENCE_LEVELS)}"
        )
    return SummableAxis(axis=str(raw["axis"]), confidence=confidence, note=str(raw.get("note", "")))


def validate_against_companies(config: MappingConfig, companies: list[Company]) -> list[str]:
    """Check overrides point at real companies. Returns warnings; raises on errors."""
    by_cik = {c.cik: c for c in companies}
    warnings = []
    for override in config.overrides:
        company = by_cik.get(override.cik)
        if company is None:
            raise ConfigError(
                f"override for concept '{override.concept}' names cik {override.cik}, "
                "which is not in the company config"
            )
        if not company.enabled:
            warnings.append(
                f"override for concept '{override.concept}' targets {company.ticker}, "
                "which is disabled in the company config"
            )
    return warnings


def _parse_concept(name: str, raw: dict, line: int = 0) -> ConceptSpec:
    if not isinstance(raw, dict):
        raise ConfigError(f"concept {name} must be a mapping")
    _reject_unknown(set(raw), CONCEPT_KEYS, f"concept {name}")
    missing = {"statement", "unit", "tags"} - set(raw)
    if missing:
        raise ConfigError(f"concept {name} missing keys: {sorted(missing)}")
    if raw["statement"] not in STATEMENTS:
        raise ConfigError(
            f"concept {name}: unknown statement '{raw['statement']}', "
            f"expected one of {sorted(STATEMENTS)}"
        )

    raw_tags = raw["tags"] or []
    if not raw_tags:
        raise ConfigError(f"concept {name} has no tags")

    tags = []
    seen = set()
    for position, raw_tag in enumerate(raw_tags, start=1):
        mapping = _parse_tag(name, raw_tag, position * PRIORITY_STEP)
        if mapping.qualified_tag in seen:
            raise ConfigError(f"concept {name}: duplicate tag {mapping.qualified_tag}")
        seen.add(mapping.qualified_tag)
        tags.append(mapping)

    total_tags = {mapping.qualified_tag for mapping in tags}
    components = tuple(
        _parse_component(name, raw_component, position * PRIORITY_STEP, total_tags)
        for position, raw_component in enumerate(raw.get("components") or [], start=1)
    )

    return ConceptSpec(
        name=name,
        statement=raw["statement"],
        unit=str(raw["unit"]),
        tags=tuple(tags),
        components=components,
        optional=_parse_flag(name, raw, "optional", default=False),
        additive=_parse_flag(name, raw, "additive", default=True),
        position=line,
    )


def _parse_component(concept: str, raw: dict, position: int, total_tags: set[str]) -> ComponentSet:
    if not isinstance(raw, dict):
        raise ConfigError(f"concept {concept}: each component set must be a mapping")
    label = f"concept {concept} component set"
    _reject_unknown(set(raw), COMPONENT_KEYS, label)

    qualified = tuple(str(t) for t in raw.get("tags") or ())
    if len(qualified) < 2:
        # A single tag is a total, which belongs in `tags`. A partial sum would
        # understate the concept, which is the error this feature exists to fix.
        raise ConfigError(f"{label}: needs at least two tags")

    taxonomies, tags = set(), []
    for entry in qualified:
        taxonomy, tag = _split_qualified_tag(entry, label)
        taxonomies.add(taxonomy)
        tags.append(tag)
        if entry in total_tags:
            raise ConfigError(f"{label}: {entry} is already a total tag for this concept")
    if len(taxonomies) > 1:
        raise ConfigError(f"{label}: all tags must share one taxonomy, got {sorted(taxonomies)}")

    confidence = str(raw.get("confidence", DEFAULT_COMPONENT_CONFIDENCE))
    if confidence not in COMPONENT_CONFIDENCE_LEVELS:
        raise ConfigError(
            f"{label}: confidence '{confidence}' is not allowed; a sum assembled from "
            f"parts must be one of {sorted(COMPONENT_CONFIDENCE_LEVELS)}"
        )

    return ComponentSet(
        concept=concept,
        taxonomy=taxonomies.pop(),
        tags=tuple(tags),
        position=position,
        confidence=confidence,
        note=str(raw.get("note", "")),
    )


def _parse_tag(concept: str, raw: dict, priority: int) -> TagMapping:
    if not isinstance(raw, dict):
        raise ConfigError(f"concept {concept}: each tag must be a mapping")
    _reject_unknown(set(raw), TAG_KEYS, f"concept {concept} tag")
    missing = {"tag", "confidence"} - set(raw)
    if missing:
        raise ConfigError(f"concept {concept}: tag missing keys: {sorted(missing)}")

    taxonomy, tag = _split_qualified_tag(str(raw["tag"]), f"concept {concept}")
    confidence = str(raw["confidence"])
    if confidence not in CONFIDENCE_LEVELS:
        # 'derived' is assigned by the models when a value is computed, never declared.
        raise ConfigError(
            f"concept {concept}: unknown confidence '{confidence}', "
            f"expected one of {sorted(CONFIDENCE_LEVELS)}"
        )

    return TagMapping(
        concept=concept,
        taxonomy=taxonomy,
        tag=tag,
        priority=priority,
        confidence=confidence,
        note=str(raw.get("note", "")),
    )


def _parse_override(raw: dict, concepts: dict[str, ConceptSpec], index: int) -> CompanyOverride:
    if not isinstance(raw, dict):
        raise ConfigError(f"override {index} must be a mapping")
    label = f"override {index} (cik {raw.get('cik', 'missing')})"
    _reject_unknown(set(raw), OVERRIDE_KEYS, label)
    missing = {"cik", "concept"} - set(raw)
    if missing:
        raise ConfigError(f"{label} missing keys: {sorted(missing)}")

    concept = str(raw["concept"])
    if concept not in concepts:
        raise ConfigError(f"{label}: unknown concept '{concept}'")

    prefer = tuple(str(t) for t in raw.get("prefer") or ())
    ignore = tuple(str(t) for t in raw.get("ignore") or ())
    summed = tuple(str(t) for t in raw.get("sum") or ())
    if not prefer and not ignore and not summed:
        raise ConfigError(f"{label}: needs at least one of 'prefer', 'ignore' or 'sum'")
    if summed and len(summed) < 2:
        raise ConfigError(f"{label}: a sum needs at least two tags, got {len(summed)}")
    if len(set(summed)) != len(summed):
        raise ConfigError(f"{label}: a sum lists the same tag twice")
    for qualified in prefer + ignore + summed:
        _split_qualified_tag(qualified, label)

    confidence = str(raw.get("confidence", DEFAULT_OVERRIDE_CONFIDENCE))
    if confidence not in CONFIDENCE_LEVELS:
        raise ConfigError(
            f"{label}: unknown confidence '{confidence}', "
            f"expected one of {sorted(CONFIDENCE_LEVELS)}"
        )

    from_year = None if raw.get("from_year") is None else int(raw["from_year"])
    through_year = None if raw.get("through_year") is None else int(raw["through_year"])
    if from_year is not None and through_year is not None and through_year < from_year:
        raise ConfigError(f"{label}: through_year is before from_year")

    return CompanyOverride(
        cik=int(raw["cik"]),
        concept=concept,
        prefer=prefer,
        ignore=ignore,
        sum=summed,
        confidence=confidence,
        from_year=from_year,
        through_year=through_year,
        note=str(raw.get("note", "")),
    )


def _split_qualified_tag(qualified: str, where: str) -> tuple[str, str]:
    taxonomy, _, tag = qualified.partition(":")
    if not taxonomy or not tag:
        raise ConfigError(
            f"{where}: tag '{qualified}' needs a taxonomy prefix, for example us-gaap:Revenues"
        )
    return taxonomy, tag


def _parse_flag(name: str, raw: dict, key: str, default: bool) -> bool:
    """A flag must be written as a real boolean.

    `bool()` would accept anything, and a quoted "false" in YAML is a non empty
    string, so it would read as true and silently mean the opposite of what the
    config says.
    """
    if key not in raw:
        return default
    value = raw[key]
    if not isinstance(value, bool):
        raise ConfigError(f"concept {name}: {key} must be true or false, got {value!r}")
    return value


def _reject_unknown(keys: set, allowed: set, where: str) -> None:
    unknown = keys - allowed
    if unknown:
        raise ConfigError(f"unknown keys in {where}: {sorted(unknown)}")
