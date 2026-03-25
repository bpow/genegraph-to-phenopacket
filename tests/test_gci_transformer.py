# tests/test_gci_transformer.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gci_transformer import sanitize_label, mondo_id_to_colon, build_iso8601_age


def test_sanitize_label_spaces():
    assert sanitize_label("Patient 3") == "Patient_3"

def test_sanitize_label_colons():
    assert sanitize_label("II:9") == "II-9"

def test_sanitize_label_mixed():
    assert sanitize_label("Proband C:1 test") == "Proband_C-1_test"

def test_mondo_id_to_colon_standard():
    assert mondo_id_to_colon("MONDO_0016587") == "MONDO:0016587"

def test_mondo_id_to_colon_preserves_numeric_part():
    assert mondo_id_to_colon("MONDO_0700096") == "MONDO:0700096"

def test_mondo_id_to_colon_freetext_returns_default():
    assert mondo_id_to_colon("FREETEXT_abc123") == "MONDO:0700096"

def test_mondo_id_to_colon_empty_returns_default():
    assert mondo_id_to_colon("") == "MONDO:0700096"

def test_build_iso8601_age_years():
    assert build_iso8601_age(41, "Years") == ("age", "P41Y")

def test_build_iso8601_age_months():
    assert build_iso8601_age(6, "Months") == ("age", "P6M")

def test_build_iso8601_age_days():
    assert build_iso8601_age(5, "Days") == ("age", "P5D")

def test_build_iso8601_age_weeks():
    assert build_iso8601_age(3, "Weeks") == ("age", "P3W")

def test_build_iso8601_age_hours():
    assert build_iso8601_age(12, "Hours") == ("age", "PT12H")

def test_build_iso8601_age_weeks_gestation_whole():
    assert build_iso8601_age(38, "Weeks gestation") == ("gestational", (38, 0))

def test_build_iso8601_age_weeks_gestation_fractional():
    assert build_iso8601_age(38.5, "Weeks gestation") == ("gestational", (38, 4))

def test_build_iso8601_age_unknown_unit_returns_none():
    assert build_iso8601_age(5, "Decades") is None

def test_build_iso8601_age_none_value_returns_none():
    assert build_iso8601_age(None, "Years") is None

def test_build_iso8601_age_float_truncated():
    assert build_iso8601_age(41.7, "Years") == ("age", "P41Y")