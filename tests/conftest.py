"""Shared fixtures. Each book is parsed once per session, however many tests read it.

Any test that takes an `fy` argument runs once per extracted year in `years/`, so a new
year's book is held to every year-generic check without touching the tests.
"""
import pytest

from budget.config import load_years
from budget.parse import parse_book
from budget.payload import build_budget_data


def pytest_generate_tests(metafunc):
    if "fy" in metafunc.fixturenames:
        metafunc.parametrize("fy", [y.label for y in load_years() if y.extracted])


@pytest.fixture(scope="session")
def years():
    return load_years()


@pytest.fixture(scope="session")
def year(years):
    """{label: YearConfig}"""
    return {y.label: y for y in years}


@pytest.fixture(scope="session")
def books(years):
    """{label: Book} for every extracted year."""
    return {y.label: parse_book(y.source_path) for y in years if y.extracted}


@pytest.fixture(scope="session")
def payload(years, books):
    return build_budget_data(years, books)
