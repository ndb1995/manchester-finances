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
SOURCES_DIR = (ROOT / "sources").resolve()
DATA_JS = ROOT / "data.js"

_TOP_KEYS = {"label", "period", "source", "as_of", "anchors", "categories", "_comment"}
_ANCHOR_KEYS = {"gf_total", "gf_revenue", "msd_total", "msd_property_tax"}
# An extracted year has to reproduce its revenue total and split the school district's
# property tax out for the flow diagram; a hand-entered year only draws category bars.
_EXTRACTED_ANCHORS = _ANCHOR_KEYS


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


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
        return (ROOT / self.source).resolve() if self.source is not None else None

    @property
    def citywide(self):
        return self.gf_total + self.msd_total


def _year_from_json(path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BudgetError(f"{path.name}: not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise BudgetError(f"{path.name}: top-level JSON value must be an object")
    anchors = raw.get("anchors", {})
    categories = raw.get("categories")
    if not isinstance(anchors, dict):
        raise BudgetError(f"{path.name}: 'anchors' must be an object")
    if categories is not None and not isinstance(categories, dict):
        raise BudgetError(f"{path.name}: 'categories' must be an object")
    unknown = set(raw) - _TOP_KEYS
    unknown |= {f"anchors.{k}" for k in set(anchors) - _ANCHOR_KEYS}
    if unknown:  # a typo'd key would otherwise be ignored and its anchor never checked
        raise BudgetError(f"{path.name}: unknown keys {sorted(unknown)}")
    source = raw.get("source")
    if source is not None and (not isinstance(source, str) or not source.strip()):
        raise BudgetError(f"{path.name}: 'source' must be a non-empty string or null")
    required = {"label", "period", "categories"} - set(raw)
    required |= {f"anchors.{k}" for k in ({"gf_total", "msd_total"} - set(anchors))}
    if source is not None:
        required |= {f"anchors.{k}" for k in _EXTRACTED_ANCHORS - set(anchors)}
    if required:
        raise BudgetError(f"{path.name}: missing {sorted(required)}")
    if not isinstance(raw["label"], str) or not isinstance(raw["period"], str) or not raw["period"].strip():
        raise BudgetError(f"{path.name}: 'label' and 'period' must be non-empty strings")
    as_of = raw.get("as_of")
    if as_of is not None and (not isinstance(as_of, str) or not as_of.strip()):
        raise BudgetError(f"{path.name}: 'as_of' must be a non-empty string or null")
    if raw["label"] != path.stem:
        raise BudgetError(f"{path.name}: label {raw['label']!r} does not match the file name")
    bad_ints = [f"anchors.{k}" for k, v in anchors.items() if not _is_int(v)]
    bad_ints += [f"categories.{k}" for k, v in categories.items() if not isinstance(k, str) or not _is_int(v)]
    if bad_ints:
        raise BudgetError(f"{path.name}: expected integer amounts for {sorted(bad_ints)}")
    return YearConfig(label=raw["label"], period=raw["period"], source=source,
                      as_of=as_of, categories=dict(categories), **anchors)


def _check_year(year):
    """A year file has to be internally consistent before any book is compared against it."""
    total = sum(year.categories.values())
    if not agrees(total, year.gf_total):
        raise BudgetError(f"{year.label}: categories sum to {total:,}, "
                          f"not the General Fund total {year.gf_total:,}")
    if year.extracted:
        if not year.source_path.is_relative_to(SOURCES_DIR):
            raise BudgetError(f"{year.label}: source must be inside sources/: {year.source}")
        if not year.source_path.is_file():
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
