# tests/test_gci_transformer.py
from gci_phenopacket.transformer import sanitize_label, mondo_id_to_colon, build_iso8601_age


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
    with caplog.at_level(logging.WARNING, logger="gci_phenopacket.transformer"):
        build_iso8601_age(5, "Decades")
    assert "Unrecognized ageUnit" in caplog.text

def test_build_iso8601_age_none_unit_returns_none():
    assert build_iso8601_age(5, None) is None


from gci_phenopacket.transformer import collect_individuals

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


from gci_phenopacket.transformer import passes_filter

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
from gci_phenopacket.transformer import build_subject

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

def test_build_subject_vital_status_not_set_when_not_death():
    ind = {"sex": "Male", "ageType": "Onset", "ageUnit": "Years", "ageValue": 14}
    subj = build_subject("1", "X", ind)
    assert not subj.HasField("vital_status")

def test_build_subject_age_at_last_encounter():
    ind = {"sex": "Male", "ageType": "Onset", "ageUnit": "Years", "ageValue": 41}
    subj = build_subject("1", "X", ind)
    assert subj.time_at_last_encounter.age.iso8601duration == "P41Y"

def test_build_subject_missing_age_omits_field():
    ind = {"sex": "Male", "ageType": None, "ageUnit": None, "ageValue": None}
    subj = build_subject("1", "X", ind)
    assert not subj.HasField("time_at_last_encounter")

def test_build_subject_gestational_age():
    ind = {"sex": "Male", "ageType": "Onset", "ageUnit": "Weeks gestation", "ageValue": 38.5}
    subj = build_subject("1", "X", ind)
    assert subj.time_at_last_encounter.gestational_age.weeks == 38
    assert subj.time_at_last_encounter.gestational_age.days == 4


from unittest.mock import MagicMock
from gci_phenopacket.transformer import build_phenotypic_features

def _make_om():
    """Mock OntologyManager — returns predictable HPO labels."""
    om = MagicMock()
    om.hpo_to_labeled_phenotype.side_effect = lambda hpo_id: {
        "id": hpo_id, "label": f"Label for {hpo_id}"
    }
    return om

def test_phenotypic_features_diagnosis_not_excluded():
    ind = {"hpoIdInDiagnosis": ["HP:0001942"], "hpoIdInElimination": []}
    features = build_phenotypic_features(ind, "12345", "Article title", _make_om())
    assert len(features) == 1
    assert features[0].type.id == "HP:0001942"
    assert features[0].excluded is False

def test_phenotypic_features_elimination_excluded():
    ind = {"hpoIdInDiagnosis": [], "hpoIdInElimination": ["HP:0001903"]}
    features = build_phenotypic_features(ind, "12345", "Title", _make_om())
    assert len(features) == 1
    assert features[0].excluded is True

def test_phenotypic_features_combined():
    ind = {"hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": ["HP:0002"]}
    features = build_phenotypic_features(ind, "12345", "Title", _make_om())
    assert len(features) == 2
    excluded_flags = {f.type.id: f.excluded for f in features}
    assert excluded_flags["HP:0001"] is False
    assert excluded_flags["HP:0002"] is True

def test_phenotypic_features_evidence_populated():
    ind = {"hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": []}
    features = build_phenotypic_features(ind, "99999", "My Article", _make_om())
    ev = features[0].evidence[0]
    assert ev.reference.id == "PMID:99999"
    assert ev.reference.description == "My Article"
    assert ev.evidence_code.id == "ECO:0000304"


from gci_phenopacket.transformer import build_genomic_interpretations

def _make_geno_om():
    om = MagicMock()
    om.geno_lookup = {
        "homozygous":            "GENO:0000136",
        "heterozygous":          "GENO:0000135",
        "compound heterozygous": "GENO:0000402",
        "hemizygous":            "GENO:0000134",
        "unspecified zygosity":  "GENO:0000137",
    }
    return om

def test_variant_uses_carid_when_available():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "CA123", "clinvarVariantId": "456", "clinvarVariantTitle": "NM_001.1(GENE):c.1A>T"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "Patient1", "GENE", "HGNC:1", _make_geno_om())
    assert interps[0].variant_interpretation.variation_descriptor.id == "caid:CA123"

def test_variant_falls_back_to_clinvar_id():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "", "clinvarVariantId": "789", "clinvarVariantTitle": "Some variant"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "Patient1", "GENE", "HGNC:1", _make_geno_om())
    assert interps[0].variant_interpretation.variation_descriptor.id == "clinvar:789"

def test_variant_gene_context_set_when_gene_in_title():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "CA1", "clinvarVariantId": "", "clinvarVariantTitle": "NM_001(DSG2):c.1A>T"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "DSG2", "HGNC:3049", _make_geno_om())
    vd = interps[0].variant_interpretation.variation_descriptor
    assert vd.gene_context.value_id == "HGNC:3049"
    assert vd.gene_context.symbol == "DSG2"

def test_variant_gene_context_omitted_when_gene_not_in_title():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "CA1", "clinvarVariantId": "", "clinvarVariantTitle": "NM_001(OTHER):c.1A>T"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "DSG2", "HGNC:3049", _make_geno_om())
    vd = interps[0].variant_interpretation.variation_descriptor
    assert not vd.HasField("gene_context")

def test_variant_allelic_state_set_when_zygosity_present():
    ind = {
        "recessiveZygosity": "Homozygous",
        "variants": [{"carId": "CA1", "clinvarVariantId": "", "clinvarVariantTitle": "X"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "G", "HGNC:1", _make_geno_om())
    vd = interps[0].variant_interpretation.variation_descriptor
    assert vd.allelic_state.id == "GENO:0000136"

def test_variant_no_variants_returns_empty():
    ind = {"recessiveZygosity": None, "variants": []}
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "G", "HGNC:1", _make_geno_om())
    assert interps == []


from gci_phenopacket.transformer import build_phenopacket

def _make_om_with_mondo():
    om = MagicMock()
    om.hpo_to_labeled_phenotype.side_effect = lambda h: {"id": h, "label": f"L:{h}"}
    om.mondo_lookup = {"MONDO:0016587": "arrhythmogenic right ventricular cardiomyopathy"}
    om.geno_lookup = {
        "homozygous":            "GENO:0000136",
        "heterozygous":          "GENO:0000135",
        "compound heterozygous": "GENO:0000402",
        "hemizygous":            "GENO:0000134",
        "unspecified zygosity":  "GENO:0000137",
    }
    return om

def _base_individual():
    return {
        "label": "Test Patient",
        "uuid": "uuid-123",
        "sex": "Male",
        "is_proband": "Yes",
        "ageType": "Onset", "ageUnit": "Years", "ageValue": 30,
        "recessiveZygosity": None,
        "hpoIdInDiagnosis": ["HP:0001942"],
        "hpoIdInElimination": [],
        "diagnosis": [{"diseaseId": "MONDO_0016587"}],
        "variants": [],
    }

def test_build_phenopacket_id_format():
    # Input uses MONDO_0016587; ID should contain the underscore form
    pp = build_phenopacket(0, 1, "DSG2", "HGNC:3049", "12345", "Title", _base_individual(), "i", _make_om_with_mondo())
    assert pp.id == "0_1_DSG2_MONDO_0016587_12345_Test_Patient_i"

def test_build_phenopacket_diagnosis_uses_colon_form():
    # Diagnosis disease.id must use colon format even though ID uses underscore
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "12345", "Title", _base_individual(), "i", _make_om_with_mondo())
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0016587"

def test_build_phenopacket_subject_id():
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", _base_individual(), "f", _make_om_with_mondo())
    assert pp.subject.id == "PMID_99:Test Patient"

def test_build_phenopacket_freetext_disease_defaults_to_fallback():
    ind = _base_individual()
    ind["diagnosis"] = [{"diseaseId": "FREETEXT_abc"}]
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", ind, "i", _make_om_with_mondo())
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0700096"
    assert pp.interpretations[0].diagnosis.disease.label == "human disease"

def test_build_phenopacket_empty_diagnosis_defaults_to_fallback():
    ind = _base_individual()
    ind["diagnosis"] = []
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", ind, "i", _make_om_with_mondo())
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0700096"

def test_build_phenopacket_interpretation_id():
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", _base_individual(), "i", _make_om_with_mondo())
    assert pp.interpretations[0].id == "99_Test_Patient_uuid-123"

def test_build_phenopacket_metadata_schema_version():
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", _base_individual(), "i", _make_om_with_mondo())
    assert pp.meta_data.phenopacket_schema_version == "2.0"

def test_build_phenopacket_metadata_resources_count():
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", _base_individual(), "i", _make_om_with_mondo())
    assert len(pp.meta_data.resources) == 4
    resource_ids = {r.id for r in pp.meta_data.resources}
    assert resource_ids == {"hp", "mondo", "geno", "eco"}
