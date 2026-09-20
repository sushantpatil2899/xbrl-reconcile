"""Verify every configured CIK points at the company we think it does."""

import json
import os
from pathlib import Path

from xbrl_reconcile.config import Company, load_companies
from xbrl_reconcile.ingest.http import PoliteClient
from xbrl_reconcile.ingest.sec import SecApi

PROBLEM_STATUSES = {"MISMATCH", "ERROR"}


def check_company(company: Company, api) -> tuple[str, str]:
    """Return a status and either SEC's company name or the error message."""
    try:
        doc = json.loads(api.submissions(company.cik10))
    except Exception as err:
        return "ERROR", str(err)
    sec_name = doc.get("name", "")
    tickers = doc.get("tickers") or []
    if not tickers:
        return "NO TICKER", sec_name
    if company.ticker in tickers:
        return "OK", sec_name
    return "MISMATCH", sec_name


def main() -> int:
    companies = load_companies(Path(os.environ.get("CONFIG_PATH", "config/companies.yml")))
    email = os.environ.get("SEC_CONTACT_EMAIL")
    if not email:
        raise ValueError("missing environment variable SEC_CONTACT_EMAIL")
    api = SecApi(PoliteClient(user_agent=f"xbrl-reconcile {email}"))

    problems = 0
    for company in companies:
        status, detail = check_company(company, api)
        print(f"{status:<10} {company.ticker:<6} {company.cik:>8}  {detail}")
        problems += status in PROBLEM_STATUSES
    return 1 if problems else 0
