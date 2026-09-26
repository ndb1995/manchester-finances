"""Manchester NH budget books -> data.js.

Pipeline, one module per stage: `config` (which years, which anchors) -> `parse` (PDF text
into agencies) -> `categorize` (agencies into the site's categories) -> `checks` (the anchors)
-> `payload` (the site's data) -> `report`. Run it with `python -m budget`.
"""
