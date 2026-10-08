"""Answer the serving layer's questions from the published Parquet, with no HTTP here.

Nothing in this module imports a web framework. The filtering, the year basis rule,
the balance sheet period translation and the pagination are the parts worth testing,
and keeping them here means they are testable from a REPL and reusable by the static
page, which runs the same queries in a browser rather than over HTTP.

The whole published set is about 1.4 MB across twelve files. DuckDB reads only the
columns and row groups a query touches, so one connection with a view per file is
enough and the serving layer never needs the 92 MB database. Measured against the
real marts: 4.3 ms for one company and concept, 4.2 ms for an income statement, and
9.4 ms to read every annual value at once. The views are created once but DuckDB
re-reads the file per query rather than caching it, which is why these are
milliseconds rather than microseconds, and is still far below the cost of the
network hop in front of them.

Two separate protections against injection, because neither covers the other. Every
value a caller supplies is a bound parameter, so it is data and not code. Every
identifier (a column, a sort, a mart name) comes from a module constant, because SQL
has no placeholder for an identifier and binding cannot protect one.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import duckdb

INDEX_NAME = "_index.json"

# The three statements, and the wide mart each one is read from.
STATEMENT_MARTS = {
    "income_statement": "mart_income_statement",
    "balance_sheet": "mart_balance_sheet",
    "cash_flow": "mart_cash_flow",
}

EVIDENCE_MARTS = {"mapping": "mart_mapping_evidence", "calculation": "mart_calculation_evidence"}
TAG_MARTS = {"unmapped": "mart_unmapped_tags", "custom": "mart_custom_tags"}

# Disables the period filter rather than naming a period. Not a period_kind, so it is
# not in the vocabulary and has to be allowed separately.
ANY_PERIOD = "all"

# Sorts are module constants, never built from a request. Each one is unique for its
# mart's grain, which is what makes offset pagination correct rather than roughly
# correct: without a deterministic order, two pages can overlap or skip invisibly.
SORTS = {
    "mart_financials": ("ticker", "concept", "period_end", "period_kind", "period_start"),
    "mart_income_statement": ("ticker", "period_end", "period_kind", "period_start"),
    "mart_balance_sheet": ("ticker", "period_end", "period_kind", "period_start"),
    "mart_cash_flow": ("ticker", "period_end", "period_kind", "period_start"),
    "mart_confidence_report": ("ticker", "statement", "period_end", "period_kind", "period_start"),
    "mart_mapping_coverage": ("ticker", "fiscal_year", "concept"),
    "mart_mapping_evidence": ("ticker", "statement", "qualified_tag"),
    "mart_calculation_evidence": ("ticker", "concept", "qualified_tag"),
    "mart_unmapped_tags": ("peers_using desc", "ticker", "taxonomy", "tag"),
    "mart_custom_tags": ("ticker", "qualified_tag"),
    "mart_concepts": ("statement", "position"),
    "mart_vocabularies": ("vocabulary", "position"),
}

# The columns a reader wants, out of the 38 on mart_financials. verbose returns them
# all, so nothing is hidden, but the common answer stays small.
FINANCIALS_COLUMNS = (
    "ticker",
    "company_name",
    "statement",
    "concept",
    "value",
    "unit",
    "period_start",
    "period_end",
    "period_kind",
    "fiscal_year",
    "fiscal_quarter",
    "calendar_year_equivalent",
    "confidence",
    "inputs_confidence",
    "source_tag",
    "evidence",
    "basis",
    "form",
    "was_restated",
    "is_coherent",
)

CONFIDENCE_COLUMNS = (
    "ticker",
    "statement",
    "period_end",
    "period_kind",
    "fiscal_year",
    "calendar_year_equivalent",
    "lines_present",
    "lines_expected",
    "is_complete",
    "high_lines",
    "medium_lines",
    "low_lines",
    "derived_lines",
    "ambiguous_lines",
    "restated_lines",
    "incoherent_lines",
    "confirmed_lines",
    "contradicted_lines",
    "identity_gap",
    "identity_holds",
    "trust",
)

COVERAGE_COLUMNS = (
    "ticker",
    "fiscal_year",
    "fiscal_year_end",
    "concept",
    "statement",
    "status",
    "value",
    "confidence",
    "source_tag",
    "basis",
    "period_end",
)

# The statement marts carry one value and one confidence column per line. These are
# everything else, so the lines can be found by difference rather than by a list that
# would need editing whenever config adds a concept.
STATEMENT_BASE_COLUMNS = (
    "ticker",
    "company_name",
    "period_start",
    "period_end",
    "period_kind",
    "period_days",
    "fiscal_year",
    "fiscal_quarter",
    "calendar_year_equivalent",
    "fiscal_year_end",
    "is_year_end",
    "basis",
    "statement_accession",
    "statement_form",
    "statement_filed_date",
    "statement_covers_whole",
    "incoherent_lines",
)


def _literal(path: Path) -> str:
    """A path as a SQL string literal, with quotes doubled as SQL escapes them."""
    return "'" + str(path).replace("'", "''") + "'"


class QueryError(Exception):
    """Something about the request was wrong, as opposed to something being broken."""


class UnknownValue(QueryError):
    """A filter named a value that does not exist in the data.

    Carries the valid values, because an empty result is indistinguishable from a
    typo and a caller who misspelled a ticker should be told what the choices are.
    """

    def __init__(self, field: str, value: str, valid: tuple[str, ...]):
        super().__init__(f"unknown {field}: {value!r}")
        self.field = field
        self.value = value
        self.valid = valid


class UnsupportedFilter(QueryError):
    """A filter cannot apply to this mart, for a reason worth stating."""

    def __init__(self, field: str, reason: str):
        super().__init__(f"{field} does not apply here: {reason}")
        self.field = field
        self.reason = reason


@dataclass(frozen=True)
class Filters:
    """What a caller asked to narrow to. None means not filtered, never an empty set.

    An empty tuple would be ambiguous between "everything" and "nothing", and that
    ambiguity reads as working right up until it quietly returns the whole table.

    year_basis is None rather than "calendar" so that an unset basis and an explicit
    one can be told apart. mart_mapping_coverage has no calendar year column, so it
    rejects an explicit calendar basis; if the default lived in this signature it
    would reject every request instead, including ones that never mentioned it.
    """

    tickers: tuple[str, ...] | None = None
    concepts: tuple[str, ...] | None = None
    period: str = "annual"
    from_year: int | None = None
    to_year: int | None = None
    year_basis: str | None = None
    basis: str | None = None
    confidence: tuple[str, ...] | None = None
    evidence: tuple[str, ...] | None = None
    restated: bool | None = None


@dataclass(frozen=True)
class Page:
    limit: int = 1000
    offset: int = 0


@dataclass(frozen=True)
class Result:
    rows: list[dict]
    total: int
    sort: tuple[str, ...]

    @property
    def has_more(self) -> bool:
        return len(self.rows) < self.total


class Where:
    """Collects predicates and their bound values, so a value never reaches the SQL.

    The year basis rule and the balance sheet period translation live here and only
    here. Written as an accumulator rather than a declarative spec per mart because
    the marts differ in ways worth seeing: coverage has no calendar year, the balance
    sheet is entirely instants, and the tag marts filter on ticker alone. Fifteen
    lines of visible composition per endpoint beats fifteen optional spec fields.
    """

    def __init__(self):
        self._parts: list[str] = []
        self._params: list = []

    def add(self, fragment: str, *params) -> None:
        self._parts.append(fragment)
        self._params.extend(params)

    def equals(self, column: str, value) -> None:
        if value is not None:
            self.add(f'"{column}" = ?', value)

    def in_list(self, column: str, values: tuple[str, ...] | None) -> None:
        if values is None:
            return
        placeholders = ", ".join("?" for _ in values)
        self.add(f'"{column}" in ({placeholders})', *values)

    def is_true(self, column: str, flag: bool | None) -> None:
        if flag is None:
            return
        # coalesce because a null flag would make the predicate null and drop the row
        # under both true and false, which reads as a filter and behaves as a deletion.
        self.add(f'coalesce("{column}", false) = ?', flag)

    def period(self, column: str, period: str, year_end_column: str | None = None) -> None:
        if period == ANY_PERIOD:
            return
        if year_end_column is None:
            self.add(f'"{column}" = ?', period)
            return

        # An instant mart. A balance sheet is a photograph on one date, so it has no
        # annual row: the annual balance sheet is the year end one. Translated rather
        # than exposed as a separate parameter, so a caller asking for the 2025 annual
        # statements gets all three without knowing which is made of instants.
        if period == "annual":
            self.add(f'coalesce("{year_end_column}", false)')
        elif period == "quarter":
            self.add(f'not coalesce("{year_end_column}", false)')
        elif period == "instant":
            return
        else:
            raise UnsupportedFilter("period", f"a balance sheet has no {period} period")

    def year_range(self, filters: Filters, fiscal: str | None, calendar: str | None) -> None:
        if filters.year_basis is None:
            # Unset: prefer the comparable label where the mart has one, because
            # comparing companies with different year ends is what the API is for.
            column = calendar or fiscal
        elif filters.year_basis == "fiscal":
            column = fiscal
        else:
            column = calendar

        if column is None:
            raise UnsupportedFilter(
                "year_basis",
                "this mart is keyed by fiscal year only, so a calendar range cannot apply",
            )
        if filters.from_year is not None:
            self.add(f'"{column}" >= ?', filters.from_year)
        if filters.to_year is not None:
            self.add(f'"{column}" <= ?', filters.to_year)

    @property
    def params(self) -> list:
        return list(self._params)

    def sql(self) -> str:
        return f"where {' and '.join(self._parts)}" if self._parts else ""


class MartStore:
    """One read only DuckDB connection with a view over each published Parquet file.

    A class rather than functions over a module global because tests need independent
    stores over different fixture directories, and the app holds one in its state.
    """

    def __init__(self, connection, index: dict, marts: tuple[str, ...]):
        self._connection = connection
        self.index = index
        self.marts = marts

    @classmethod
    def open(cls, path: Path) -> "MartStore":
        path = Path(path)
        index_path = path / INDEX_NAME
        if not index_path.exists():
            raise FileNotFoundError(f"no {INDEX_NAME} in {path}; run xbrl-fetch-marts")
        index = json.loads(index_path.read_text())

        connection = duckdb.connect()
        names = []
        for mart in index.get("marts", []):
            name = mart["name"]
            # DuckDB will not take a bound parameter inside CREATE VIEW, so this one
            # path is interpolated. It is the only place in the module that is, so the
            # name is checked against a plain identifier and the path is quoted the way
            # SQL expects. The values come from our own published index rather than
            # from a request, and the check is here so that stays true if that changes.
            if not name.replace("_", "").isalnum():
                raise ValueError(f"{name!r} in {INDEX_NAME} is not a usable mart name")
            parquet = path / f"{name}.parquet"
            if not parquet.exists():
                raise FileNotFoundError(f"{name} is in the index but not in {path}")
            connection.execute(
                f'create view "{name}" as select * from read_parquet({_literal(parquet)})'
            )
            names.append(name)
        return cls(connection, index, tuple(names))

    @property
    def as_of(self) -> str | None:
        return self.index.get("published_at")

    def close(self) -> None:
        self._connection.close()

    def query(self, sql: str, params: list | None = None) -> list[dict]:
        cursor = self._connection.execute(sql, params or [])
        columns = [description[0] for description in cursor.description]
        # Native types are kept: a date stays a date. Formatting one is presentation,
        # and a Python caller should not have to parse a string back.
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def column_names(self, mart: str) -> tuple[str, ...]:
        cursor = self._connection.execute(f'select * from "{mart}" limit 0')
        return tuple(description[0] for description in cursor.description)

    def page(
        self,
        mart: str,
        columns: tuple[str, ...] | None,
        where: Where,
        page: Page,
        sort: tuple[str, ...] | None = None,
    ) -> Result:
        """Rows plus the total they were drawn from, which is what pagination needs.

        Two queries, because the row query carries a LIMIT and so cannot report how
        many matched. The count reads only the filter columns and costs microseconds.
        """
        sort = sort or SORTS[mart]
        clause = where.sql()
        params = where.params

        total = self._connection.execute(
            f'select count(*) from "{mart}" {clause}', params
        ).fetchone()[0]

        selection = ", ".join(f'"{column}"' for column in columns) if columns else "*"
        rows = self.query(
            f'select {selection} from "{mart}" {clause} '
            f"order by {', '.join(sort)} limit ? offset ?",
            [*params, page.limit, page.offset],
        )
        return Result(rows=rows, total=total, sort=sort)

    # The valid value sets, read once from the published data so that adding a company
    # or a concept to config changes what the API accepts with no code change.

    def distinct(self, mart: str, column: str) -> tuple[str, ...]:
        rows = self._connection.execute(
            f'select distinct "{column}" from "{mart}" where "{column}" is not null order by 1'
        ).fetchall()
        return tuple(row[0] for row in rows)

    @property
    def tickers(self) -> tuple[str, ...]:
        return self.distinct("mart_financials", "ticker")

    @property
    def concept_names(self) -> tuple[str, ...]:
        return self.distinct("mart_concepts", "concept")

    @property
    def statements(self) -> tuple[str, ...]:
        return self.vocabulary_values("statement")

    def vocabulary_values(self, name: str) -> tuple[str, ...]:
        rows = self._connection.execute(
            "select value from mart_vocabularies where vocabulary = ? order by position", [name]
        ).fetchall()
        return tuple(row[0] for row in rows)


def validate(store: MartStore, filters: Filters) -> None:
    """Reject a filter value that does not exist, naming what would have worked.

    Here rather than in the HTTP layer because it is a property of the data, so the
    same guarantee holds for every caller rather than only for requests that arrive
    over HTTP. The serving layer's job is turning the exception into a status code.
    """
    _check(filters.tickers, "ticker", store.tickers)
    _check(filters.concepts, "concept", store.concept_names)
    _check(filters.confidence, "confidence", store.vocabulary_values("confidence"))
    _check(filters.evidence, "evidence", store.vocabulary_values("evidence"))
    if filters.basis is not None:
        _check((filters.basis,), "basis", store.vocabulary_values("basis"))

    periods = (*store.vocabulary_values("period_kind"), ANY_PERIOD)
    _check((filters.period,), "period", periods)
    if filters.year_basis is not None:
        _check((filters.year_basis,), "year_basis", store.vocabulary_values("year_basis"))


def _check(values: tuple[str, ...] | None, field: str, valid: tuple[str, ...]) -> None:
    for value in values or ():
        if value not in valid:
            raise UnknownValue(field, value, valid)


def index(store: MartStore) -> dict:
    """What this is, what is in it, how fresh. Reads the index, so it answers fast."""
    years = store.query(
        "select min(fiscal_year) as first, max(fiscal_year) as last from mart_financials"
    )[0]
    return {
        "as_of": store.as_of,
        "companies": len(store.tickers),
        "concepts": len(store.concept_names),
        "fiscal_years": years,
        "marts": store.index.get("marts", []),
    }


def companies(store: MartStore, page: Page | None = None) -> Result:
    """The companies and the span each one covers. 28 rows, so no filters."""
    rows = store.query(
        "select cik, ticker, any_value(company_name) as company_name, "
        "any_value(basis) as basis, month(max(fiscal_year_end)) as fiscal_year_end_month, "
        "min(period_end) as first_period_end, max(period_end) as last_period_end, "
        "count(distinct fiscal_year) as fiscal_years, count(*) as values "
        "from mart_financials group by cik, ticker order by ticker"
    )
    return Result(rows=rows, total=len(rows), sort=("ticker",))


def concepts(store: MartStore, statement: str | None = None) -> Result:
    """The canonical concepts in statement order, with how well covered each one is."""
    if statement is not None:
        _check((statement,), "statement", store.statements)
    where = Where()
    where.equals("statement", statement)
    return store.page("mart_concepts", None, where, Page(limit=100))


def vocabularies(store: MartStore) -> Result:
    """Every value the pipeline can produce, with what it means, straight from config."""
    return store.page("mart_vocabularies", None, Where(), Page(limit=200))


def financials(store: MartStore, filters: Filters, page: Page) -> Result:
    validate(store, filters)
    where = Where()
    where.in_list("ticker", filters.tickers)
    where.in_list("concept", filters.concepts)
    where.period("period_kind", filters.period)
    where.year_range(filters, "fiscal_year", "calendar_year_equivalent")
    where.equals("basis", filters.basis)
    where.in_list("confidence", filters.confidence)
    where.in_list("evidence", filters.evidence)
    where.is_true("was_restated", filters.restated)
    return store.page("mart_financials", FINANCIALS_COLUMNS, where, page)


def statement(
    store: MartStore, which: str, filters: Filters, page: Page, verbose: bool = False
) -> Result:
    """One statement per company and period, its lines in the order config lists them.

    The lines are built by looping over mart_concepts, so adding a concept to config
    grows the array with nothing to change here. Nested rather than returned flat
    because JSON object keys carry no order, and because pairing each value with its
    confidence structurally beats a naming convention the caller has to know.
    """
    if which not in STATEMENT_MARTS:
        raise UnknownValue("statement", which, tuple(STATEMENT_MARTS))
    mart = STATEMENT_MARTS[which]
    validate(store, filters)

    where = Where()
    where.in_list("ticker", filters.tickers)
    # The balance sheet is all instants, so period is translated against is_year_end.
    year_end = "is_year_end" if which == "balance_sheet" else None
    where.period("period_kind", filters.period, year_end)
    where.year_range(filters, "fiscal_year", "calendar_year_equivalent")
    where.equals("basis", filters.basis)

    result = store.page(mart, None, where, page)
    if verbose:
        return result

    lines = store.query(
        "select concept, position, unit from mart_concepts where statement = ? order by position",
        [which],
    )
    return Result(
        rows=[_with_lines(row, lines) for row in result.rows],
        total=result.total,
        sort=result.sort,
    )


def _with_lines(row: dict, lines: list[dict]) -> dict:
    nested = {column: row[column] for column in STATEMENT_BASE_COLUMNS if column in row}
    nested["lines"] = [
        {
            "concept": line["concept"],
            "position": line["position"],
            "unit": line["unit"],
            "value": row.get(line["concept"]),
            "confidence": row.get(f"{line['concept']}_confidence"),
        }
        for line in lines
        if line["concept"] in row
    ]
    return nested


def confidence(
    store: MartStore, filters: Filters, page: Page, statement: str | None = None, trust=None
) -> Result:
    """How much to trust a statement, rather than what its numbers are."""
    validate(store, filters)
    if statement is not None:
        _check((statement,), "statement", store.statements)
    _check(trust, "trust", store.vocabulary_values("trust"))

    where = Where()
    where.in_list("ticker", filters.tickers)
    where.equals("statement", statement)
    where.period("period_kind", filters.period)
    where.year_range(filters, "fiscal_year", "calendar_year_equivalent")
    where.equals("basis", filters.basis)
    where.in_list("trust", trust)
    return store.page("mart_confidence_report", CONFIDENCE_COLUMNS, where, page)


def coverage(store: MartStore, filters: Filters, page: Page, status=None) -> Result:
    """What is missing and why. Keyed by fiscal year, so no calendar range applies."""
    validate(store, filters)
    _check(status, "status", store.vocabulary_values("coverage_status"))

    where = Where()
    where.in_list("ticker", filters.tickers)
    where.in_list("concept", filters.concepts)
    # No calendar year column here, so an explicit calendar basis is rejected while
    # an unset one falls back to fiscal.
    where.year_range(filters, "fiscal_year", None)
    where.in_list("status", status)
    return store.page("mart_mapping_coverage", COVERAGE_COLUMNS, where, page)


def evidence(store: MartStore, kind: str, filters: Filters, page: Page, verdict=None) -> Result:
    """What the filings' own tags and arithmetic say about the mappings."""
    if kind not in EVIDENCE_MARTS:
        raise UnknownValue("evidence", kind, tuple(EVIDENCE_MARTS))
    mart = EVIDENCE_MARTS[kind]
    validate(store, filters)

    column = "verdict" if kind == "mapping" else "calculation_verdict"
    vocabulary = "mapping_verdict" if kind == "mapping" else "calculation_verdict"
    _check(verdict, column, store.vocabulary_values(vocabulary))

    where = Where()
    where.in_list("ticker", filters.tickers)
    where.in_list(column, verdict)
    if kind == "calculation":
        where.in_list("concept", filters.concepts)
    return store.page(mart, None, where, page)


def tags(store: MartStore, kind: str, filters: Filters, page: Page, mapped=None) -> Result:
    """The tags we do not map, and the ones companies invented.

    Sorted by how many peers use the same tag, which makes this the place to look for
    the next mapping worth adding rather than only a record of what is missing.
    """
    if kind not in TAG_MARTS:
        raise UnknownValue("tags", kind, tuple(TAG_MARTS))
    mart = TAG_MARTS[kind]
    validate(store, filters)

    where = Where()
    where.in_list("ticker", filters.tickers)
    if kind == "custom":
        where.is_true("is_mapped", mapped)
    return store.page(mart, None, where, page)
