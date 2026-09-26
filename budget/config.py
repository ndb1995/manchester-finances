"""Per-year configuration: which book to parse, and the published figures it must reproduce.

Each fiscal year is one JSON file in `years/`. Adding a year is adding a file -- no code
changes -- and every figure the site draws for a year traces back either to its budget book
(an *extracted* year, one with a `source`) or to the literals in its file (a hand-entered
year, one without).
"""
import json
from dataclasses import dataclass
from pathlib import Path

from .errors import BudgetError
from .model import agrees

ROOT = Path(__file__).resolve().parent.parent
YEARS_DIR = ROOT / "years"
DATA_JS = ROOT / "data.js"

_TOP_KEYS = {"label", "period", "source", "as_of", "anchors", "categories", "_comment"}
_ANCHOR_KEYS = {"gf_total", "gf_revenue", "msd_total", "msd_property_tax"}
# An extracted year has to reproduce its revenue total and split the school district's
# property tax out for the flow diagram; a hand-entered year only draws category bars.
_EXTRACTED_ANCHORS = _ANCHOR_KEYS


@dataclass(frozen=True)
class YearConfig:
    label: str  # 'FY2026'
    period: str  # 'Jul 2025 – Jun 2026'
    gf_total: int  # the book's General Fund total, transit subsidy excluded as it directs
    msd_total: int  # the school district budget, a constant: the district prints its own book
    categories: dict  # General Fund category -> published total; anchors for an extracted year
    source: str | None = None  # budget book PDF relative to the repo root; None = hand-entered
    as_of: str | None = None  # when the figures were published, for the page footer
    gf_revenue: int | None = None
    msd_property_tax: int | None = None

    @property
    def extracted(self):
        return self.source is not None

    @property
    def source_path(self):
        return ROOT / self.source

    @property
    def citywide(self):
        return self.gf_total + self.msd_total


def _year_from_json(path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BudgetError(f"{path.name}: not valid JSON: {exc}") from exc
    unknown = set(raw) - _TOP_KEYS
    anchors = raw.get("anchors", {})
    unknown |= {f"anchors.{k}" for k in set(anchors) - _ANCHOR_KEYS}
    if unknown:  # a typo'd key would otherwise be ignored and its anchor never checked
        raise BudgetError(f"{path.name}: unknown keys {sorted(unknown)}")
    required = {"label", "period", "categories"} - set(raw)
    required |= {f"anchors.{k}" for k in ({"gf_total", "msd_total"} - set(anchors))}
    if raw.get("source"):
        required |= {f"anchors.{k}" for k in _EXTRACTED_ANCHORS - set(anchors)}
    if required:
        raise BudgetError(f"{path.name}: missing {sorted(required)}")
    if raw["label"] != path.stem:
        raise BudgetError(f"{path.name}: label {raw['label']!r} does not match the file name")
    return YearConfig(label=raw["label"], period=raw["period"], source=raw.get("source"),
                      as_of=raw.get("as_of"), categories=dict(raw["categories"]), **anchors)


def _check_year(year):
    """A year file has to be internally consistent before any book is compared against it."""
    total = sum(year.categories.values())
    if not agrees(total, year.gf_total):
        raise BudgetError(f"{year.label}: categories sum to {total:,}, "
                          f"not the General Fund total {year.gf_total:,}")
    if year.extracted and not year.source_path.is_file():
        raise BudgetError(f"{year.label}: budget book not found: {year.source}")


def load_years(years_dir=YEARS_DIR):
    """Every configured year, oldest first."""
    years = sorted((_year_from_json(p) for p in Path(years_dir).glob("FY*.json")),
                   key=lambda y: y.label)
    if not years:
        raise BudgetError(f"no year files in {years_dir}")
    for year in years:
        _check_year(year)
    return years
