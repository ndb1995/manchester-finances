"""The one exception the pipeline raises on purpose."""


class BudgetError(Exception):
    """A book or configuration the pipeline cannot turn into trustworthy numbers.

    Raised instead of guessing: an unmapped department, an unrecognized organization or a
    malformed year file would otherwise reach the site as a silently wrong figure. The CLI
    turns it into a nonzero exit; library callers and tests can catch it like any exception.
    """
