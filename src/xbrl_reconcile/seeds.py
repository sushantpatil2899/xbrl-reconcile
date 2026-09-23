"""Generate dbt seed files from the config files."""

import csv
import os
from pathlib import Path

from xbrl_reconcile.config import Company, load_companies

COMPANY_COLUMNS = [
    "cik",
    "cik10",
    "ticker",
    "name",
    "description",
    "group_name",
    "start_year",
    "end_year",
    "enabled",
]


def build_companies_rows(companies: list[Company]) -> list[dict]:
    return [
        {
            "cik": c.cik,
            "cik10": c.cik10,
            "ticker": c.ticker,
            "name": c.name,
            "description": c.description,
            # `group` is a reserved word in SQL, so the column is group_name.
            "group_name": c.group,
            "start_year": c.start_year,
            "end_year": "" if c.end_year is None else c.end_year,
            "enabled": c.enabled,
        }
        for c in companies
    ]


def write_companies_seed(companies: list[Company], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COMPANY_COLUMNS)
        writer.writeheader()
        writer.writerows(build_companies_rows(companies))


def main() -> int:
    root = Path(__file__).parent.parent.parent
    config_path = Path(os.environ.get("CONFIG_PATH", root / "config" / "companies.yml"))
    seed_path = root / "transform" / "seeds" / "companies.csv"
    companies = load_companies(config_path)
    write_companies_seed(companies, seed_path)
    print(f"wrote {len(companies)} companies to {seed_path}")
    return 0
