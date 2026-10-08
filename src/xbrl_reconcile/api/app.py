"""The HTTP layer. Routes, validation, documentation, logging and a limiter.

Built by a factory rather than declared at module level, because FastAPI reads the
type annotations when the route decorator runs. An enum generated from the published
data therefore has to exist before the routes are declared, which a startup handler
is far too late for. The factory also gives every test an app over its own fixture.

Nothing here knows SQL. Everything reads through queries.py, so the filtering rules
stay testable without a web framework and the same functions can back the static
page. This module's job is HTTP: parse, validate, document, serialize, protect.

The vocabulary descriptions in the generated documentation come from
config/vocabularies.yml by way of mart_vocabularies. No value's meaning is written
here, which is the point of having published that mart.
"""

import json
import logging
import os
import time
from collections import OrderedDict
from enum import Enum
from importlib import resources
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from xbrl_reconcile.api import models, queries
from xbrl_reconcile.api.queries import (
    ANY_PERIOD,
    Filters,
    MartStore,
    MartUnavailable,
    Page,
    QueryError,
    UnknownValue,
    UnsupportedFilter,
)

log = logging.getLogger("xbrl_reconcile.api")

TITLE = "xbrl-reconcile"
SUMMARY = "SEC XBRL financial statements reconciled to canonical concepts, with confidence."

# Health checks must never be rationed: a host whose checks hit a 429 marks the
# container unhealthy and kills it. Discovery is not rationed either.
UNLIMITED_PATHS = frozenset({"/healthz", "/", "/docs", "/redoc", "/openapi.json"})

DEFAULT_LIMIT = 1000
MAX_LIMIT = 10000

TAGS = [
    {
        "name": "Metadata",
        "description": "What is in the dataset, how fresh it is, and what the values mean.",
    },
    {
        "name": "Statements",
        "description": (
            "The numbers, each with the tag it came from and how sure we are about it."
        ),
    },
    {
        "name": "Quality",
        "description": (
            "How much to trust a statement, and what is missing. Ask `/confidence?trust=check`"
            " for the statements worth a human look."
        ),
    },
    {
        "name": "Evidence",
        "description": (
            "The filings' own tags and declared arithmetic, and the tags we do not map."
            " This is what makes the confidence labels auditable rather than asserted."
        ),
    },
]


def overview() -> str:
    """The business context, packaged with the code so it ships in any deployment.

    In docs/ it would not be inside the wheel or the container, leaving a choice
    between a path guess that breaks on a host and a silent fallback that hides it.
    """
    return resources.files("xbrl_reconcile.api").joinpath("overview.md").read_text()


def _enum(name: str, values: tuple[str, ...]) -> type[Enum]:
    """A real enum, so FastAPI documents the values and rejects anything else itself."""
    return Enum(name, {value: value for value in values}, type=str)


def _described(store: MartStore, vocabulary: str, lead: str, extra: str = "") -> str:
    """A parameter description built from config, as a markdown list of value and meaning.

    OpenAPI has no standard field for per value descriptions, only `enum` for the list
    and `description` for the schema, so the convention is to put the list in the
    description. It renders correctly in both Swagger and ReDoc.
    """
    rows = store.query(
        "select value, description from mart_vocabularies where vocabulary = ? order by position",
        [vocabulary],
    )
    lines = "\n".join(f"- `{row['value']}`: {row['description']}" for row in rows)
    return f"{lead}\n\n{lines}\n{extra}".strip()


def _list_described(store: MartStore, vocabulary: str, lead: str) -> str:
    """For the comma separated parameters, which cannot be enums and so cannot be dropdowns."""
    return f"{_described(store, vocabulary, lead)}\n\nComma separated. Case insensitive."


def _split(value: str | None, upper: bool = False) -> tuple[str, ...] | None:
    """None means not filtered. An empty tuple would be ambiguous, so it never returns one."""
    if value is None:
        return None
    parts = tuple(part.strip() for part in value.split(",") if part.strip())
    if not parts:
        return None
    return tuple(part.upper() for part in parts) if upper else parts


class Bucket:
    """A token bucket. Correct at one instance, approximate beyond it, and said so."""

    __slots__ = ("tokens", "touched")

    def __init__(self, tokens: float, touched: float):
        self.tokens = tokens
        self.touched = touched


def create_app(store: MartStore, rate: float = 1.0, burst: int = 60) -> FastAPI:
    """Build the app over an already open store.

    rate is tokens per second and burst is the bucket size, so the defaults allow 60
    requests a minute with a full minute's worth available at once.
    """
    # Generated from the published data, so adding a company to config grows the
    # documentation with no code change. This is why the factory exists: these have to
    # be in hand before the decorators below run. Only the single value parameters get
    # one: a comma separated list cannot be an enum, so those are documented instead.
    Statement = _enum("Statement", store.statements)
    PeriodKind = _enum("PeriodKind", (*store.vocabulary_values("period_kind"), ANY_PERIOD))
    YearBasis = _enum("YearBasis", store.vocabulary_values("year_basis"))
    Basis = _enum("Basis", store.vocabulary_values("basis"))
    EvidenceKind = _enum("EvidenceKind", tuple(queries.EVIDENCE_MARTS))
    annual = PeriodKind("annual")
    TagKind = _enum("TagKind", tuple(queries.TAG_MARTS))

    tickers_doc = (
        f"Which companies to return. One or more of: {', '.join(store.tickers)}."
        " Comma separated, case insensitive. An unknown ticker is an error rather than"
        " an empty result, because a typo and a genuine absence would otherwise look"
        " identical."
    )
    concepts_doc = (
        f"Which canonical concepts to return, out of: {', '.join(store.concept_names)}."
        " Comma separated."
    )
    period_doc = _described(
        store,
        "period_kind",
        "Which kind of reporting period to return.",
        f"- `{ANY_PERIOD}`: disables this filter.\n\nDefaults to `annual`, because a company"
        " files several overlapping period kinds for the same year and an unfiltered answer"
        " looks like duplicated data. The filter in force is always echoed back.",
    )
    year_basis_doc = _described(
        store,
        "year_basis",
        "Which year label `from_year` and `to_year` apply to.",
        "Defaults to `calendar`, because sixteen of these companies end their fiscal year in"
        " January and comparing them is what this is for. Both labels are always returned.",
    )

    app = FastAPI(
        title=TITLE,
        summary=SUMMARY,
        description=overview(),
        version="0.1.0",
        openapi_tags=TAGS,
    )

    # Shared filters as a dependency. FastAPI expands this signature into every route's
    # documentation, so each endpoint still lists its parameters while they are
    # declared once. This is what dependencies are for; authentication is only the
    # famous example.
    def filter_params(
        tickers: Annotated[str | None, Query(description=tickers_doc)] = None,
        concepts: Annotated[str | None, Query(description=concepts_doc)] = None,
        period: Annotated[PeriodKind, Query(description=period_doc)] = annual,
        from_year: Annotated[int | None, Query(description="Earliest year, inclusive.")] = None,
        to_year: Annotated[int | None, Query(description="Latest year, inclusive.")] = None,
        year_basis: Annotated[YearBasis | None, Query(description=year_basis_doc)] = None,
        basis: Annotated[
            Basis | None, Query(description=_described(store, "basis", "Which rulebook."))
        ] = None,
        confidence: Annotated[
            str | None,
            Query(
                description=_list_described(
                    store, "confidence", "Return only values obtained these ways."
                )
            ),
        ] = None,
        evidence: Annotated[
            str | None,
            Query(
                description=_list_described(
                    store, "evidence", "Return only values whose tag the filings judged these ways."
                )
            ),
        ] = None,
        restated: Annotated[
            bool | None,
            Query(description="Only values a later filing revised, or only those it did not."),
        ] = None,
    ) -> Filters:
        return Filters(
            tickers=_split(tickers, upper=True),
            concepts=_split(concepts),
            period=period.value,
            from_year=from_year,
            to_year=to_year,
            year_basis=year_basis.value if year_basis else None,
            basis=basis.value if basis else None,
            confidence=_split(confidence),
            evidence=_split(evidence),
            restated=restated,
        )

    # Coverage is keyed by fiscal year and has no period or calendar year, so it does
    # not advertise either. Offering a parameter that always returns 400 is worse
    # documentation than not offering it.
    def coverage_params(
        tickers: Annotated[str | None, Query(description=tickers_doc)] = None,
        concepts: Annotated[str | None, Query(description=concepts_doc)] = None,
        from_year: Annotated[
            int | None, Query(description="Earliest fiscal year, inclusive.")
        ] = None,
        to_year: Annotated[int | None, Query(description="Latest fiscal year, inclusive.")] = None,
    ) -> Filters:
        return Filters(
            tickers=_split(tickers, upper=True),
            concepts=_split(concepts),
            period=ANY_PERIOD,
            from_year=from_year,
            to_year=to_year,
        )

    def paging(
        limit: Annotated[
            int, Query(ge=1, le=MAX_LIMIT, description="Rows per page.")
        ] = DEFAULT_LIMIT,
        offset: Annotated[int, Query(ge=0, description="Rows to skip.")] = 0,
    ) -> Page:
        return Page(limit=limit, offset=offset)

    FilterDep = Annotated[Filters, Depends(filter_params)]
    CoverageDep = Annotated[Filters, Depends(coverage_params)]
    PageDep = Annotated[Page, Depends(paging)]

    def envelope(request: Request, result: queries.Result, filters: Filters | None = None) -> dict:
        """Wrap rows with what was asked, what matched, and how to get the rest."""
        request.state.rows = len(result.rows)
        page = Page(
            limit=int(request.query_params.get("limit", DEFAULT_LIMIT)),
            offset=int(request.query_params.get("offset", 0)),
        )
        following = page.offset + page.limit
        # Built from the incoming URL so every other filter survives. Assembling the
        # query string by hand is how a parameter gets lost on page two.
        next_url = (
            str(request.url.include_query_params(offset=following))
            if following < result.total
            else None
        )
        previous_url = (
            str(request.url.include_query_params(offset=max(page.offset - page.limit, 0)))
            if page.offset > 0
            else None
        )
        return {
            "as_of": store.as_of,
            "filters_applied": _applied(filters),
            "pagination": {
                "limit": page.limit,
                "offset": page.offset,
                "row_count": len(result.rows),
                "total_rows": result.total,
                "has_more": next_url is not None,
                "sort": list(result.sort),
                "next": next_url,
                "previous": previous_url,
            },
            "rows": result.rows,
        }

    def respond(request: Request, result: queries.Result, filters: Filters | None = None):
        body = envelope(request, result, filters)
        response = JSONResponse(content=_jsonable(body))
        # RFC 8288, so generic HTTP clients page without reading our JSON shape.
        links = [
            f'<{body["pagination"][rel]}>; rel="{name}"'
            for rel, name in (("next", "next"), ("previous", "prev"))
            if body["pagination"][rel]
        ]
        if links:
            response.headers["Link"] = ", ".join(links)
        return response

    @app.get("/", tags=["Metadata"], response_model=models.Index)
    def root():
        """What this is, what is in it, and how fresh.

        Reads only the published index, so it answers even if a mart failed to publish.
        """
        answer = queries.index(store)
        return {
            "name": TITLE,
            "description": SUMMARY,
            **answer,
            "docs": "/docs",
            "redoc": "/redoc",
            "parquet_note": (
                "For the whole dataset rather than an answer, read the Parquet directly:"
                " one line of SQL beats paging through JSON."
            ),
        }

    @app.get("/healthz", tags=["Metadata"], response_model=models.Health)
    def healthz():
        """Readiness and liveness. Never rate limited, so a health check cannot be throttled."""
        store.query("select 1 as ok")
        return {"status": "ok", "as_of": store.as_of}

    @app.get("/companies", tags=["Metadata"], response_model=models.Envelope[models.CompanyRow])
    def companies(request: Request):
        """The companies in the dataset and the span each one covers.

        `fiscal_year_end_month` is what a reader needs to interpret the year labels:
        sixteen of these companies close their books in January.
        """
        return respond(request, queries.companies(store))

    @app.get("/concepts", tags=["Metadata"], response_model=models.Envelope[models.ConceptRow])
    def concepts(
        request: Request,
        statement: Annotated[
            Statement | None, Query(description="Narrow to one statement.")
        ] = None,
    ):
        """The 16 canonical concepts, in the order they appear on their statement.

        A projection of config: adding a concept to `tag_mappings.yml` adds a row here
        with no code change.
        """
        return respond(request, queries.concepts(store, statement.value if statement else None))

    @app.get(
        "/vocabularies", tags=["Metadata"], response_model=models.Envelope[models.VocabularyRow]
    )
    def vocabularies(request: Request):
        """Every value the pipeline can produce, and what each one means.

        The same descriptions this page uses for its parameters, served as data. They
        come from `config/vocabularies.yml`, so a value cannot reach a caller without
        an explanation.
        """
        return respond(request, queries.vocabularies(store))

    @app.get(
        "/financials", tags=["Statements"], response_model=models.Envelope[models.FinancialRow]
    )
    def financials(request: Request, filters: FilterDep, page: PageDep):
        """Specific values, each with the evidence for it.

        One row per company, period and concept, carrying the tag it came from, how
        confident the mapping is, and what the filing's own calculation linkbase said.

        **Worked example.** `?tickers=WDAY&concepts=cost_of_revenue&from_year=2014`
        returns 264,803,000 USD with `confidence: medium` and a `source_tag` of two
        tags joined by `+`, because Workday reported the two components of cost of
        revenue separately and never a total. A conventional financial API returns the
        number alone.

        **When not to use this.** For everything rather than an answer, read
        `mart_financials.parquet` directly. It is about 700 KB and one line of SQL
        reads it, which beats paging through 26 pages of JSON.
        """
        return respond(request, queries.financials(store, filters, page), filters)

    @app.get(
        "/statements/{statement}",
        tags=["Statements"],
        response_model=models.Envelope[models.StatementRow],
    )
    def statement(
        request: Request,
        statement: Statement,
        filters: FilterDep,
        page: PageDep,
        verbose: Annotated[
            bool, Query(description="Return the flat table row instead of nested lines.")
        ] = False,
    ):
        """A whole statement, readable top to bottom, with a confidence per line.

        The lines come back as an ordered array rather than object keys, because JSON
        keys carry no order and each value belongs beside its own confidence.

        **The balance sheet is a special case worth knowing.** Every balance sheet row
        is an instant, a photograph on one date, so there is no annual balance sheet:
        `period=annual` means the year end one. You can ask for the 2025 annual
        statements across all three without knowing which is made of instants.
        """
        result = queries.statement(store, statement.value, filters, page, verbose=verbose)
        return respond(request, result, filters)

    @app.get("/confidence", tags=["Quality"], response_model=models.Envelope[models.ConfidenceRow])
    def confidence(
        request: Request,
        filters: FilterDep,
        page: PageDep,
        statement: Annotated[
            Statement | None, Query(description="Narrow to one statement.")
        ] = None,
        trust: Annotated[
            str | None,
            Query(description=_list_described(store, "trust", "Narrow to these trust levels.")),
        ] = None,
    ):
        """Not what the number is, but how much to trust the statement it sits in.

        Counts by confidence level, how many lines were derived or restated, whether
        the accounting identity holds, and a one word `trust` summary.

        **`?trust=check` is the most useful query here.** Those are the statements where
        an identity fails or a line was ambiguous, which is where a human should look.
        """
        result = queries.confidence(
            store,
            filters,
            page,
            statement=statement.value if statement else None,
            trust=_split(trust),
        )
        return respond(request, result, filters)

    @app.get("/coverage", tags=["Quality"], response_model=models.Envelope[models.CoverageRow])
    def coverage(
        request: Request,
        filters: CoverageDep,
        page: PageDep,
        status: Annotated[
            str | None,
            Query(
                description=_list_described(
                    store,
                    "coverage_status",
                    "Narrow to these reasons a concept is or is not present.",
                )
            ),
        ] = None,
    ):
        """What is missing, and why.

        `?status=missing` is the honest question: it returns the cells where there is
        nothing and something could be done about it, as opposed to the ones where a
        company legitimately has none of a concept or the SEC has not published a
        quarter yet.

        This endpoint takes no `period` or `year_basis`, because the data behind it is
        keyed by fiscal year alone. A year range here always means fiscal year.
        """
        return respond(request, queries.coverage(store, filters, page, _split(status)), filters)

    @app.get("/evidence/{kind}", tags=["Evidence"], response_model=models.Envelope[dict[str, Any]])
    def evidence(
        request: Request,
        kind: EvidenceKind,
        filters: FilterDep,
        page: PageDep,
        verdict: Annotated[str | None, Query(description="Narrow to these verdicts.")] = None,
    ):
        """What the filings themselves say about the mappings.

        `mapping` is which tags a company presents on a statement and whether our
        mapping agrees. `calculation` is what the filing's own calculation linkbase
        declares a tag to be part of, which is the strongest evidence available: the
        parent of a calculation arc is the computed line, so a tag appearing as a child
        of something we already call a total contradicts calling it one.
        """
        result = queries.evidence(store, kind.value, filters, page, _split(verdict))
        return respond(request, result, filters)

    @app.get("/tags/{kind}", tags=["Evidence"], response_model=models.Envelope[dict[str, Any]])
    def tags(
        request: Request,
        kind: TagKind,
        filters: FilterDep,
        page: PageDep,
        mapped: Annotated[
            bool | None, Query(description="For custom tags, whether we map them.")
        ] = None,
    ):
        """The tags we do not map, and the ones companies invented.

        `unmapped` is sorted by how many peers use the same tag, which makes this the
        place to find the next mapping worth adding rather than only a record of what
        is absent. `custom` is the tags a company made up for itself.
        """
        result = queries.tags(store, kind.value, filters, page, mapped)
        return respond(request, result, filters)

    _install_handlers(app)
    _install_middleware(app, rate=rate, burst=burst)
    return app


def _applied(filters: Filters | None) -> dict:
    """The effective filters, defaults included, so a default never narrows silently."""
    if filters is None:
        return {}
    return {
        "tickers": list(filters.tickers) if filters.tickers else None,
        "concepts": list(filters.concepts) if filters.concepts else None,
        "period": filters.period,
        "from_year": filters.from_year,
        "to_year": filters.to_year,
        "year_basis": filters.year_basis or "calendar",
        "basis": filters.basis,
        "confidence": list(filters.confidence) if filters.confidence else None,
        "evidence": list(filters.evidence) if filters.evidence else None,
        "restated": filters.restated,
    }


def _jsonable(value):
    """Dates and anything else JSONResponse will not take, turned into text.

    The query layer keeps native types on purpose, so a Python caller is not handed
    strings to parse back. Converting is this layer's job, at its edge.
    """
    import datetime
    import decimal

    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime.date | datetime.datetime):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


def _install_handlers(app: FastAPI) -> None:
    @app.exception_handler(UnknownValue)
    def unknown_value(request: Request, error: UnknownValue):
        # 404 for a path that does not exist, 400 for a filter value that does not.
        status = 404 if f"/{error.value}" in request.url.path else 400
        return JSONResponse(
            status_code=status,
            content={
                "error": str(error),
                "field": error.field,
                "value": error.value,
                "valid": list(error.valid),
            },
        )

    @app.exception_handler(UnsupportedFilter)
    def unsupported(request: Request, error: UnsupportedFilter):
        return JSONResponse(
            status_code=400,
            content={"error": str(error), "field": error.field, "reason": error.reason},
        )

    @app.exception_handler(MartUnavailable)
    def unavailable(request: Request, error: MartUnavailable):
        # 503 rather than 500: the request was fine and the data is incomplete, which
        # is a condition a caller can retry and an operator can act on.
        return JSONResponse(
            status_code=503,
            content={"error": str(error), "mart": error.mart, "available": list(error.available)},
        )

    @app.exception_handler(QueryError)
    def other(request: Request, error: QueryError):
        return JSONResponse(status_code=400, content={"error": str(error)})


def _install_middleware(app: FastAPI, rate: float, burst: int) -> None:
    # Bounded, because a plain dict keyed by address grows without limit and turns the
    # limiter itself into the thing to worry about.
    buckets: OrderedDict[str, Bucket] = OrderedDict()
    capacity = 10_000

    @app.middleware("http")
    async def guard(request: Request, call_next):
        started = time.perf_counter()
        path = request.url.path

        if path not in UNLIMITED_PATHS:
            allowed, remaining, retry_after = _take(buckets, request, rate, burst, capacity)
            if not allowed:
                response = JSONResponse(
                    status_code=429,
                    content={"error": "rate limit exceeded", "retry_after_seconds": retry_after},
                )
                response.headers["Retry-After"] = str(retry_after)
                _rate_headers(response, burst, 0, retry_after)
                _access_log(request, response, started, limited=True)
                return response
        else:
            remaining = burst

        response = await call_next(request)
        _rate_headers(response, burst, remaining, int(burst / rate))
        _access_log(request, response, started)
        return response


def _take(buckets, request: Request, rate: float, burst: int, capacity: int):
    """One token from this caller's bucket, refilling by elapsed time.

    Keyed on the client address, which is the only identity available without issued
    keys. request.client.host is used rather than parsing X-Forwarded-For here:
    uvicorn's --proxy-headers already rewrites it and only trusts the proxies you
    configure, while parsing the header in app code would trust whoever sent it, so
    anyone could forge an address and the limiter would stop working.
    """
    now = time.monotonic()
    key = request.client.host if request.client else "unknown"

    bucket = buckets.get(key)
    if bucket is None:
        bucket = Bucket(tokens=float(burst), touched=now)
        buckets[key] = bucket
    else:
        bucket.tokens = min(burst, bucket.tokens + (now - bucket.touched) * rate)
        bucket.touched = now
        buckets.move_to_end(key)

    # Drop whatever has been idle long enough to be back at a full bucket anyway, then
    # cap, so memory is bounded even under addresses that never repeat.
    idle_for = burst / rate
    while buckets and now - next(iter(buckets.values())).touched > idle_for:
        buckets.popitem(last=False)
    while len(buckets) > capacity:
        buckets.popitem(last=False)

    if bucket.tokens < 1:
        return False, 0, max(1, int((1 - bucket.tokens) / rate))
    bucket.tokens -= 1
    return True, int(bucket.tokens), int(burst / rate)


def _rate_headers(response, limit: int, remaining: int, reset: int) -> None:
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset)


def _access_log(request: Request, response, started: float, limited: bool = False) -> None:
    """One structured line per request, to stdout, which every host captures.

    The route template rather than the raw URL, so the lines aggregate by endpoint and
    answer how many times each one was called. Without issued keys these count
    requests and not people, which is the limitation on record.
    """
    route = request.scope.get("route")
    entry = {
        "endpoint": getattr(route, "path", request.url.path),
        "filters": dict(request.query_params),
        "rows": getattr(request.state, "rows", None),
        "status": response.status_code,
        "ms": round((time.perf_counter() - started) * 1000, 1),
    }
    if limited:
        entry["limited"] = True
    log.info("%s", json.dumps(entry))


def store_from_environment() -> MartStore:
    """Open the marts the serving layer reads, from one setting."""
    return MartStore.open(os.environ.get("MARTS_PATH", "warehouse/parquet"))
