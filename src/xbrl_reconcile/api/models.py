"""What the API returns, and a sentence per field.

These descriptions are the documentation for the data. Column names like
`value_as_filed`, `inputs_confidence` and `statement_covers_whole` are not self
explanatory, and a reference that lists them without saying what they mean is a
reference only for someone who already knows. They render in the same page as the
parameters, under each endpoint's response schema.

The values in the vocabulary enums are described in config rather than here, and the
parameter descriptions are generated from it. These are field descriptions, which is
a different thing: what the column is, not what its values mean.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class Pagination(BaseModel):
    limit: int = Field(description="How many rows this response holds at most.")
    offset: int = Field(description="How many matching rows were skipped.")
    row_count: int = Field(description="How many rows this response actually holds.")
    total_rows: int = Field(description="How many rows matched the filters, ignoring the limit.")
    has_more: bool = Field(description="Whether anything matched beyond this page.")
    sort: list[str] = Field(
        description=(
            "The order rows were returned in. Unique for the table's grain, which is what"
            " makes paging by offset safe: without it two pages could overlap or skip rows."
        )
    )
    next: str | None = Field(
        default=None,
        description=(
            "The same request with the offset advanced, or null on the last page. Every"
            " other filter is preserved."
        ),
    )
    previous: str | None = Field(
        default=None,
        description="The same request with the offset moved back, or null on page one.",
    )


class Envelope[RowT](BaseModel):
    as_of: str | None = Field(
        description=(
            "When the pipeline last published this data. Every answer states its own"
            " freshness, because a financial figure without a date is not an answer."
        )
    )
    filters_applied: dict[str, Any] = Field(
        description=(
            "The filters actually in force, including defaults you did not pass. This is"
            " what keeps a default from quietly narrowing a result without saying so."
        )
    )
    pagination: Pagination
    rows: list[RowT]


class Period(BaseModel):
    """The period fields every statement row and fact carries."""

    period_start: date | None = Field(
        description="First day of the span. Null for an instant, such as a balance sheet date."
    )
    period_end: date = Field(description="Last day of the span, or the date of an instant.")
    period_kind: str = Field(description="Which kind of span this is.")
    fiscal_year: int = Field(description="The year the company itself calls this period.")
    fiscal_quarter: int | None = Field(
        default=None, description="1 to 4 for a quarter, null otherwise."
    )
    calendar_year_equivalent: int | None = Field(
        default=None,
        description=(
            "The calendar year most of the fiscal year falls in. Comparing companies with"
            " different year ends uses this one, not fiscal_year."
        ),
    )


class FinancialRow(Period):
    ticker: str
    company_name: str | None = None
    statement: str = Field(description="Which statement this concept belongs to.")
    concept: str = Field(description="The canonical concept, not the tag the company used.")
    value: float | None = Field(description="The latest figure filed for this line, unscaled.")
    unit: str | None = Field(
        description="What the figure is measured in. Not every line on a statement is money."
    )
    confidence: str = Field(
        description=(
            "How this value was obtained. `derived` means computed by exact arithmetic"
            " rather than reported, which is a different claim from `medium`, not a weaker one."
        )
    )
    inputs_confidence: str | None = Field(
        default=None,
        description=(
            "For a derived value, the weakest confidence among the values it was computed"
            " from. The arithmetic is certain; this is what it rests on."
        ),
    )
    source_tag: str | None = Field(
        default=None,
        description=(
            "The XBRL tag behind the number. Tags joined by `+` mean the value is their"
            " sum, because the company reported the parts and no total. A `derived:` prefix"
            " means arithmetic rather than a tag."
        ),
    )
    evidence: str | None = Field(
        default=None,
        description=(
            "What the filing's own calculation linkbase says about that tag. Where the"
            " filer calls the tag a part of something we also call this concept's total,"
            " the parts are added up: `equivalent` means the rest come to nothing, so the"
            " part is the total. `contradicted` means they really differ, and is returned"
            " rather than withheld, because it is a reason to look."
        ),
    )
    basis: str | None = Field(description="Which accounting rulebook the filing used.")
    form: str | None = Field(
        default=None,
        description=(
            "The SEC form the figure came from. Only forms config counts as a report appear"
            " here, because a proxy statement tags net income at a different scale."
        ),
    )
    was_restated: bool | None = Field(
        default=None, description="Whether a later filing revised this figure."
    )
    is_coherent: bool | None = Field(
        default=None,
        description=(
            "Whether the latest figure agrees with the one in the filing chosen for the"
            " whole statement. False means a later filing revised this line and not the"
            " rest. Null for a derived value, which has no filed counterpart."
        ),
    )


class StatementLine(BaseModel):
    concept: str
    position: int = Field(
        description=(
            "Where this line sits on the statement, from the order config lists the"
            " concepts in. An array rather than object keys because JSON keys carry no order."
        )
    )
    unit: str | None = None
    value: float | None = None
    confidence: str | None = Field(
        default=None,
        description="Paired with its value structurally, rather than by a naming convention.",
    )


class StatementRow(Period):
    ticker: str
    company_name: str | None = None
    period_days: int | None = Field(
        default=None,
        description=(
            "Actual length of the period, so a 52 or 53 week fiscal year is visible rather"
            " than assumed to be 365 days."
        ),
    )
    fiscal_year_end: date | None = Field(
        default=None,
        description="The fiscal year own end date, so a quarter still says when the books close.",
    )
    is_year_end: bool | None = Field(
        default=None, description="Whether this period ends the fiscal year."
    )
    basis: str | None = None
    statement_accession: str | None = Field(
        default=None,
        description="The SEC accession number of the filing this statement was read from.",
    )
    statement_form: str | None = None
    statement_filed_date: date | None = None
    statement_covers_whole: bool | None = Field(
        default=None,
        description=(
            "Whether one filing carried every line. Most statements are assembled from two"
            " or more, because a later filing restates one line and not another."
        ),
    )
    incoherent_lines: int | None = Field(
        default=None,
        description="How many lines disagree with the figure in the chosen filing.",
    )
    lines: list[StatementLine] = Field(
        description="The statement's lines, in the order config lists them."
    )


class ConfidenceRow(Period):
    ticker: str
    statement: str
    lines_present: int = Field(description="How many of the statement's lines have a value.")
    lines_expected: int = Field(description="How many that statement should have.")
    is_complete: bool | None = None
    high_lines: int | None = None
    medium_lines: int | None = None
    low_lines: int | None = None
    derived_lines: int | None = Field(
        default=None, description="How many lines were computed rather than reported."
    )
    ambiguous_lines: int | None = Field(
        default=None, description="How many lines had candidate tags that disagreed."
    )
    restated_lines: int | None = None
    incoherent_lines: int | None = None
    confirmed_lines: int | None = Field(
        default=None, description="How many lines the filing's own arithmetic supports."
    )
    contradicted_lines: int | None = None
    identity_gap: float | None = Field(
        default=None,
        description=(
            "The accounting identity's residual, so assets minus liabilities minus equity"
            " for a balance sheet. Zero is what should happen."
        ),
    )
    identity_holds: bool | None = Field(
        default=None, description="Whether that gap is within tolerance. Null when unchecked."
    )
    trust: str = Field(
        description=(
            "A one word summary derived from the counts above. A documented judgement rather"
            " than a fact, which is why the counts travel with it. `check` is the one worth"
            " a human look."
        )
    )


class CoverageRow(BaseModel):
    ticker: str
    fiscal_year: int = Field(
        description="This data is keyed by fiscal year alone, so a year range means fiscal."
    )
    fiscal_year_end: date | None = None
    concept: str
    statement: str
    status: str = Field(description="Why the concept is or is not present.")
    value: float | None = None
    confidence: str | None = None
    source_tag: str | None = None
    basis: str | None = None
    period_end: date | None = None


class CompanyRow(BaseModel):
    cik: str = Field(description="The SEC's own identifier for the company.")
    ticker: str
    company_name: str | None = None
    basis: str | None = None
    fiscal_year_end_month: int | None = Field(
        default=None,
        description=(
            "The month this company closes its books. What a reader needs to interpret the"
            " year labels, and the reason year_basis exists."
        ),
    )
    first_period_end: date | None = None
    last_period_end: date | None = None
    fiscal_years: int = Field(description="How many distinct fiscal years are covered.")
    values: int = Field(description="How many reconciled values exist for this company.")


class ConceptRow(BaseModel):
    concept: str
    statement: str
    position: int = Field(description="Where it sits on its statement, from the order in config.")
    unit: str
    is_additive: bool = Field(
        description=(
            "Whether its periods can be added or subtracted. False for a ratio or an"
            " average, which is why a fourth quarter cannot be derived for one."
        )
    )
    is_optional: bool = Field(
        description=(
            "Whether a company may legitimately have none of it. What separates a real gap"
            " from an absence in the coverage report."
        )
    )


class VocabularyRow(BaseModel):
    vocabulary: str = Field(description="Which closed set this value belongs to.")
    vocabulary_description: str
    value: str
    description: str = Field(
        description="What this value means. Declared in config, not written here."
    )
    position: int


class MartSummary(BaseModel):
    name: str
    rows: int
    bytes: int


class Index(BaseModel):
    name: str
    description: str
    as_of: str | None = Field(description="When the pipeline last published.")
    companies: int
    concepts: int
    fiscal_years: dict[str, int | None]
    marts: list[MartSummary]
    docs: str
    redoc: str
    parquet_note: str = Field(
        description="How to read the whole dataset directly, which beats paging through JSON."
    )


class Health(BaseModel):
    status: str
    as_of: str | None


class Error(BaseModel):
    error: str
    field: str | None = None
    value: str | None = None
    reason: str | None = None
    valid: list[str] | None = Field(
        default=None,
        description=(
            "What would have worked. Returned because an empty result is indistinguishable"
            " from a typo, and a caller who misspelled something should be told the choices."
        ),
    )
