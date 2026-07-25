"""Mappings and expected values for Manchester NH budget extraction."""
EXPECTED = {
    "FY2025": {"gf_total": 185_760_157, "gf_revenue": 64_074_762,
               "msd_total": 227_982_610, "msd_property_tax": 120_439_237},
    "FY2026": {"gf_total": 196_511_261, "gf_revenue": 66_487_051,
               "msd_total": 237_999_925, "msd_property_tax": 117_531_711},
}
TRANSIT_OBJECT = "0909"  # excluded from GF totals per the book's own footnote
