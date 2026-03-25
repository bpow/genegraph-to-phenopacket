# tests/test_gci_transformer.py
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

def test_build_iso8601_age_unknown_unit_logs_warning(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="gci_transformer"):
        build_iso8601_age(5, "Decades")
    assert "Unrecognized ageUnit" in caplog.text

def test_build_iso8601_age_none_unit_returns_none():
    assert build_iso8601_age(5, None) is None


from gci_transformer import collect_individuals

def _make_individual(label):
    return {"label": label, "is_proband": "Yes"}

def test_collect_direct_individuals():
    annotation = {
        "individuals": [_make_individual("A"), _make_individual("B")],
        "families": [],
        "groups": [],
    }
    results = list(collect_individuals(annotation))
    assert len(results) == 2
    assert all(tag == "i" for _, tag in results)
    assert [ind["label"] for ind, _ in results] == ["A", "B"]

def test_collect_family_individuals():
    annotation = {
        "individuals": [],
        "families": [{"individualIncluded": [_make_individual("C")]}],
        "groups": [],
    }
    results = list(collect_individuals(annotation))
    assert len(results) == 1
    assert results[0][1] == "f"

def test_collect_group_direct_individuals():
    annotation = {
        "individuals": [],
        "families": [],
        "groups": [{"individualIncluded": [_make_individual("D")], "familyIncluded": []}],
    }
    results = list(collect_individuals(annotation))
    assert len(results) == 1
    assert results[0][1] == "g"

def test_collect_group_family_individuals():
    annotation = {
        "individuals": [],
        "families": [],
        "groups": [{
            "individualIncluded": [],
            "familyIncluded": [{"individualIncluded": [_make_individual("E")]}],
        }],
    }
    results = list(collect_individuals(annotation))
    assert len(results) == 1
    assert results[0][1] == "g"

def test_collect_empty_annotation():
    annotation = {"individuals": [], "families": [], "groups": []}
    assert list(collect_individuals(annotation)) == []

def test_collect_annotation_with_absent_keys():
    # Annotation dict with no keys at all should yield nothing, not raise
    assert list(collect_individuals({})) == []


from gci_transformer import passes_filter

def test_passes_filter_proband_with_hpo():
    ind = {"is_proband": "Yes", "hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": []}
    assert passes_filter(ind) is True

def test_passes_filter_proband_with_elimination_only():
    ind = {"is_proband": "Yes", "hpoIdInDiagnosis": [], "hpoIdInElimination": ["HP:0001"]}
    assert passes_filter(ind) is True

def test_passes_filter_not_proband():
    ind = {"is_proband": "No", "hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": []}
    assert passes_filter(ind) is False

def test_passes_filter_proband_no_hpo():
    ind = {"is_proband": "Yes", "hpoIdInDiagnosis": [], "hpoIdInElimination": []}
    assert passes_filter(ind) is False

def test_passes_filter_missing_is_proband():
    ind = {"hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": []}
    assert passes_filter(ind) is False


import phenopackets.schema.v2 as pps2
from gci_transformer import build_subject

def test_build_subject_male():
    ind = {"sex": "Male", "ageType": "Onset", "ageUnit": "Years", "ageValue": 41}
    subj = build_subject("12345", "Proband A", ind)
    assert subj.id == "PMID_12345:Proband A"
    assert subj.sex == pps2.Sex.MALE

def test_build_subject_female():
    ind = {"sex": "Female", "ageType": "Onset", "ageUnit": "Years", "ageValue": 5}
    subj = build_subject("99", "Jane", ind)
    assert subj.sex == pps2.Sex.FEMALE

def test_build_subject_unknown_sex():
    ind = {"sex": "Other", "ageType": "Onset", "ageUnit": "Years", "ageValue": 10}
    subj = build_subject("1", "X", ind)
    assert subj.sex == pps2.Sex.UNKNOWN_SEX

def test_build_subject_vital_status_deceased():
    ind = {"sex": "Male", "ageType": "Death", "ageUnit": "Years", "ageValue": 14}
    subj = build_subject("1", "X", ind)
    assert subj.vital_status.status == pps2.VitalStatus.Status.DECEASED

def test_build_subject_vital_status_alive():
    ind = {"sex": "Male", "ageType": "Onset", "ageUnit": "Years", "ageValue": 14}
    subj = build_subject("1", "X", ind)
    assert subj.vital_status.status == pps2.VitalStatus.Status.ALIVE

def test_build_subject_age_at_last_encounter():
    ind = {"sex": "Male", "ageType": "Onset", "ageUnit": "Years", "ageValue": 41}
    subj = build_subject("1", "X", ind)
    assert subj.time_at_last_encounter.age.iso8601duration == "P41Y"

def test_build_subject_missing_age_omits_field():
    ind = {"sex": "Male", "ageType": None, "ageUnit": None, "ageValue": None}
    subj = build_subject("1", "X", ind)
    assert not subj.HasField("time_at_last_encounter")
