"""Shared vocabulary: the codes and labels every stage agrees on, and the parsed shapes."""
from dataclasses import dataclass, field
from typing import NamedTuple

GENERAL_FUND = "0101"  # the tax-supported fund; every other fund code is an enterprise fund
TRANSIT_OBJECT = "0909"  # excluded from GF totals per the book's own footnote

# Organization label the parser stamps on a detail section whose printed total was split
# across lines, leaving it without one. Shared because the parser emits it, the Public Works
# split has to recognize it, and the site labels it.
UNATTRIBUTED = "(unattributed)"

SCHOOL_CATEGORY = "Education (MSD)"  # a constant, not parsed: the school district prints its own book
MIXED_CATEGORY = "Mixed (see line items)"  # departments split across several categories
ENTERPRISE_CATEGORY = "Enterprise Funds"

EXPENSE, REVENUE = "expense", "revenue"
KINDS = (EXPENSE, REVENUE)

# Every comparison against a printed figure allows one dollar: the books round cents to whole
# dollars line by line, so a total can differ from the sum of its rounded lines by that much.
TOLERANCE = 1


def agrees(got, expected):
    """True when a computed figure matches a printed one to within `TOLERANCE`."""
    return abs(got - expected) <= TOLERANCE


class ItemKey(NamedTuple):
    """A line item's identity within a bucket. A plain tuple underneath, so `(code, desc)`
    literals still index a bucket and still unpack."""
    code: str
    desc: str


@dataclass
class Agency:
    """One department as the book prints it, with each side of its ledger as {ItemKey: amount}.

    `org_expenses` is the organization-level breakdown of the same expense money, keyed by
    organization name; `printed_totals` is every total printed on its pages, keyed by
    (kind, label), kept for diagnostics.
    """
    name: str
    fund_code: str
    expenses: dict = field(default_factory=dict)
    revenues: dict = field(default_factory=dict)
    org_expenses: dict = field(default_factory=dict)
    printed_totals: dict = field(default_factory=dict)

    @property
    def in_general_fund(self):
        return self.fund_code == GENERAL_FUND

    def bucket(self, kind):
        """The expense or revenue side of the ledger."""
        return self.expenses if kind == EXPENSE else self.revenues


@dataclass
class Book:
    """One parsed budget book.

    `printed` holds each agency's own printed grand total, keyed by (agency, kind) -- the
    anchor its bucket is cross-checked against. `dropped_lines` is every (page, line) the
    parser skipped although it carried money, so the report can show them.
    """
    agencies: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    printed: dict = field(default_factory=dict)
    dropped_lines: list = field(default_factory=list)

    def general_fund(self):
        return [a for a in self.agencies.values() if a.in_general_fund]
