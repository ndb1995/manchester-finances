# tests/test_config.py -- the per-year files in years/
import json

import pytest

from budget.config import load_years
from budget.errors import BudgetError

MANUAL = {"label": "FY2023", "period": "Jul 2022 – Jun 2023",
          "anchors": {"gf_total": 30, "msd_total": 100},
          "categories": {"Public Safety": 20, "Other": 10}}


def _write(tmp_path, **overrides):
    raw = {**MANUAL, **overrides}
    (tmp_path / f"{raw['label']}.json").write_text(json.dumps(raw), encoding="utf-8")
    return tmp_path


def test_repository_years_load_oldest_first(years):
    labels = [y.label for y in years]
    assert labels == sorted(labels) and {"FY2025", "FY2026"} <= set(labels)
    assert all(y.source_path.is_file() for y in years if y.extracted)


def test_a_hand_entered_year_needs_no_book(tmp_path):
    (year,) = load_years(_write(tmp_path))
    assert not year.extracted and year.citywide == 130


def test_categories_must_add_up_to_the_general_fund_total(tmp_path):
    with pytest.raises(BudgetError, match="categories sum to 35"):
        load_years(_write(tmp_path, categories={"Public Safety": 25, "Other": 10}))


def test_a_misspelled_key_is_rejected_rather_than_ignored(tmp_path):
    with pytest.raises(BudgetError, match="gf_totl"):
        load_years(_write(tmp_path, anchors={"gf_totl": 30, "gf_total": 30, "msd_total": 100}))


def test_an_extracted_year_needs_its_revenue_anchors(tmp_path):
    with pytest.raises(BudgetError, match="gf_revenue"):
        load_years(_write(tmp_path, source="sources/Budget_Book_2026.pdf"))


def test_an_extracted_year_needs_its_book(tmp_path):
    anchors = {"gf_total": 30, "gf_revenue": 5, "msd_total": 100, "msd_property_tax": 50}
    with pytest.raises(BudgetError, match="not found"):
        load_years(_write(tmp_path, source="sources/nope.pdf", anchors=anchors))


def test_the_label_must_match_the_file_name(tmp_path):
    (tmp_path / "FY2024.json").write_text(json.dumps(MANUAL), encoding="utf-8")
    with pytest.raises(BudgetError, match="does not match"):
        load_years(tmp_path)
