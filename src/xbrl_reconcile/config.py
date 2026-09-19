"""Load the company config, apply defaults and reject anything malformed."""

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_KEYS = {"start_year", "end_year", "enabled", "report_types"}
REQUIRED_COMPANY_KEYS = {"cik", "ticker", "name"}
DESCRIPTIVE_KEYS = {"description", "group", "events", "notes"}
ALLOWED_COMPANY_KEYS = REQUIRED_COMPANY_KEYS | DESCRIPTIVE_KEYS | DEFAULT_KEYS


class ConfigError(ValueError):
    """Raised when the config file is malformed."""


@dataclass(frozen=True)
class Event:
    year: int
    note: str


@dataclass(frozen=True)
class Company:
    cik: int
    ticker: str
    name: str
    start_year: int
    end_year: int | None
    enabled: bool
    report_types: tuple[str, ...]
    description: str = ""
    group: str = ""
    events: tuple[Event, ...] = ()
    notes: str = ""

    @property
    def cik10(self) -> str:
        """CIK zero padded to 10 digits, the form SEC uses in URLs."""
        return f"{self.cik:010d}"


def load_companies(path: Path) -> list[Company]:
    with open(path) as f:
        return parse_companies(yaml.safe_load(f))


def parse_companies(data: dict) -> list[Company]:
    if not isinstance(data, dict):
        raise ConfigError("config must be a mapping with 'defaults' and 'companies'")
    _reject_unknown(set(data), {"defaults", "companies"}, "top level")

    defaults = data.get("defaults") or {}
    _reject_unknown(set(defaults), DEFAULT_KEYS, "defaults")
    missing = DEFAULT_KEYS - set(defaults)
    if missing:
        raise ConfigError(f"defaults missing keys: {sorted(missing)}")

    companies = []
    seen_ciks = set()
    for index, raw in enumerate(data.get("companies") or []):
        company = _parse_company(raw, defaults, index)
        if company.cik in seen_ciks:
            raise ConfigError(f"duplicate cik {company.cik} ({company.ticker})")
        seen_ciks.add(company.cik)
        companies.append(company)

    if not companies:
        raise ConfigError("no companies defined")
    return companies


def _parse_company(raw: dict, defaults: dict, index: int) -> Company:
    if not isinstance(raw, dict):
        raise ConfigError(f"company entry {index} must be a mapping")
    label = raw.get("ticker", f"entry {index}")
    _reject_unknown(set(raw), ALLOWED_COMPANY_KEYS, f"company {label}")
    missing = REQUIRED_COMPANY_KEYS - set(raw)
    if missing:
        raise ConfigError(f"company {label} missing keys: {sorted(missing)}")

    merged = {**defaults, **raw}
    company = Company(
        cik=int(merged["cik"]),
        ticker=str(merged["ticker"]),
        name=str(merged["name"]),
        start_year=int(merged["start_year"]),
        end_year=None if merged["end_year"] is None else int(merged["end_year"]),
        enabled=bool(merged["enabled"]),
        report_types=tuple(str(t) for t in merged["report_types"]),
        description=str(merged.get("description", "")),
        group=str(merged.get("group", "")),
        events=tuple(_parse_event(e, label) for e in merged.get("events") or []),
        notes=str(merged.get("notes", "")),
    )
    if company.end_year is not None and company.end_year < company.start_year:
        raise ConfigError(f"company {label}: end_year is before start_year")
    return company


def _parse_event(raw: dict, label: str) -> Event:
    if not isinstance(raw, dict) or set(raw) != {"year", "note"}:
        raise ConfigError(f"company {label}: each event needs exactly 'year' and 'note'")
    return Event(year=int(raw["year"]), note=str(raw["note"]))


def _reject_unknown(keys: set, allowed: set, where: str) -> None:
    unknown = keys - allowed
    if unknown:
        raise ConfigError(f"unknown keys in {where}: {sorted(unknown)}")
