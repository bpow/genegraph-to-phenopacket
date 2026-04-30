# tests/test_gci_transformer.py
import phenopackets.schema.v2 as pps2
from gci_phenopacket.transformer import sanitize_label, resolve_disease, build_time_element


def test_sanitize_label_spaces():
    assert sanitize_label("Patient 3") == "Patient_3"

def test_sanitize_label_colons():
    assert sanitize_label("II:9") == "II-9"

def test_sanitize_label_mixed():
    assert sanitize_label("Proband C:1 test") == "Proband_C-1_test"

def test_resolve_disease_standard():
    assert resolve_disease("MONDO_0016587") == "MONDO:0016587"

def test_resolve_disease_preserves_numeric_part():
    assert resolve_disease("MONDO_0700096") == "MONDO:0700096"

def test_resolve_disease_freetext_returns_default():
    assert resolve_disease("FREETEXT_abc123") == "MONDO:0700096"

def test_resolve_disease_empty_returns_default():
    assert resolve_disease("") == "MONDO:0700096"

def test_build_time_element_years():
    te = build_time_element(41, "Years")
    assert te == pps2.TimeElement(age=pps2.Age(iso8601duration="P41Y"))

def test_build_time_element_months():
    te = build_time_element(6, "Months")
    assert te == pps2.TimeElement(age=pps2.Age(iso8601duration="P6M"))

def test_build_time_element_days():
    te = build_time_element(5, "Days")
    assert te == pps2.TimeElement(age=pps2.Age(iso8601duration="P5D"))

def test_build_time_element_weeks():
    te = build_time_element(3, "Weeks")
    assert te == pps2.TimeElement(age=pps2.Age(iso8601duration="P3W"))

def test_build_time_element_hours():
    te = build_time_element(12, "Hours")
    assert te == pps2.TimeElement(age=pps2.Age(iso8601duration="PT12H"))

def test_build_time_element_weeks_gestation_whole():
    te = build_time_element(38, "Weeks gestation")
    assert te == pps2.TimeElement(gestational_age=pps2.GestationalAge(weeks=38, days=0))

def test_build_time_element_weeks_gestation_fractional():
    te = build_time_element(38.5, "Weeks gestation")
    assert te == pps2.TimeElement(gestational_age=pps2.GestationalAge(weeks=38, days=4))

def test_build_time_element_unknown_unit_returns_none():
    assert build_time_element(5, "Decades") is None

def test_build_time_element_none_value_returns_none():
    assert build_time_element(None, "Years") is None

def test_build_time_element_float_truncated():
    te = build_time_element(41.7, "Years")
    assert te == pps2.TimeElement(age=pps2.Age(iso8601duration="P41Y"))

def test_build_time_element_unknown_unit_logs_warning(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="gci_phenopacket.transformer"):
        build_time_element(5, "Decades")
    assert "Unrecognized ageUnit" in caplog.text

def test_build_time_element_none_unit_returns_none():
    assert build_time_element(5, None) is None


from gci_phenopacket.transformer import iter_individuals

def _make_individual(label):
    return {"label": label, "is_proband": "Yes"}

def test_collect_direct_individuals():
    annotation = {
        "individuals": [_make_individual("A"), _make_individual("B")],
        "families": [],
        "groups": [],
    }
    results = list(iter_individuals(annotation))
    assert len(results) == 2
    assert [ind["label"] for ind, *_ in results] == ["A", "B"]
    assert all(grp is None and fam is None for _, grp, fam in results)

def test_collect_family_individuals():
    annotation = {
        "individuals": [],
        "families": [{"uuid": "fam-1", "individualIncluded": [_make_individual("C")]}],
        "groups": [],
    }
    results = list(iter_individuals(annotation))
    assert len(results) == 1
    _, grp_uuid, fam_uuid = results[0]
    assert grp_uuid is None
    assert fam_uuid == "fam-1"

def test_collect_family_individuals_pk_fallback():
    annotation = {
        "individuals": [],
        "families": [{"PK": "fam-pk", "individualIncluded": [_make_individual("C2")]}],
        "groups": [],
    }
    _, _, fam_uuid = list(iter_individuals(annotation))[0]
    assert fam_uuid == "fam-pk"

def test_collect_group_direct_individuals():
    annotation = {
        "individuals": [],
        "families": [],
        "groups": [{"uuid": "grp-1", "individualIncluded": [_make_individual("D")], "familyIncluded": []}],
    }
    results = list(iter_individuals(annotation))
    assert len(results) == 1
    _, grp_uuid, fam_uuid = results[0]
    assert grp_uuid == "grp-1"
    assert fam_uuid is None

def test_collect_group_family_individuals():
    annotation = {
        "individuals": [],
        "families": [],
        "groups": [{
            "uuid": "grp-2",
            "individualIncluded": [],
            "familyIncluded": [{"uuid": "fam-2", "individualIncluded": [_make_individual("E")]}],
        }],
    }
    results = list(iter_individuals(annotation))
    assert len(results) == 1
    _, grp_uuid, fam_uuid = results[0]
    assert grp_uuid == "grp-2"
    assert fam_uuid == "fam-2"

def test_collect_empty_annotation():
    annotation = {"individuals": [], "families": [], "groups": []}
    assert list(iter_individuals(annotation)) == []

def test_collect_annotation_with_absent_keys():
    # Annotation dict with no keys at all should yield nothing, not raise
    assert list(iter_individuals({})) == []


from gci_phenopacket.transformer import build_gci_provenance_id

def test_provenance_id_direct_individual():
    assert build_gci_provenance_id("gdm-1", "ind-1") == "gdm:gdm-1-individual:ind-1"

def test_provenance_id_family_individual():
    assert build_gci_provenance_id("gdm-1", "ind-1", family_uuid="fam-1") == "gdm:gdm-1-family:fam-1-individual:ind-1"

def test_provenance_id_group_individual():
    assert build_gci_provenance_id("gdm-1", "ind-1", group_uuid="grp-1") == "gdm:gdm-1-group:grp-1-individual:ind-1"

def test_provenance_id_group_family_individual():
    assert build_gci_provenance_id("gdm-1", "ind-1", group_uuid="grp-1", family_uuid="fam-1") == "gdm:gdm-1-group:grp-1-family:fam-1-individual:ind-1"


from gci_phenopacket.transformer import passes_filter

def test_passes_filter_proband_with_hpo():
    ind = {"is_proband": "Yes", "hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": []}
    assert passes_filter(ind) is True

def test_passes_filter_proband_with_elimination_only():
    ind = {"is_proband": "Yes", "hpoIdInDiagnosis": [], "hpoIdInElimination": ["HP:0001"]}
    assert passes_filter(ind) is True

def test_passes_filter_non_proband_with_hpo():
    ind = {"is_proband": "No", "hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": []}
    assert passes_filter(ind) is True

def test_passes_filter_no_hpo():
    ind = {"hpoIdInDiagnosis": [], "hpoIdInElimination": []}
    assert passes_filter(ind) is False

def test_passes_filter_missing_is_proband_with_hpo():
    ind = {"hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": []}
    assert passes_filter(ind) is True


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

def test_variant_uses_carid_when_available():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "CA123", "clinvarVariantId": "456", "clinvarVariantTitle": "NM_001.1(GENE):c.1A>T"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "Patient1", "GENE", "HGNC:1")
    assert interps[0].variant_interpretation.variation_descriptor.id == "caid:CA123"

def test_variant_falls_back_to_clinvar_id():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "", "clinvarVariantId": "789", "clinvarVariantTitle": "Some variant"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "Patient1", "GENE", "HGNC:1")
    assert interps[0].variant_interpretation.variation_descriptor.id == "clinvar:789"

def test_variant_gene_context_set_when_gene_in_title():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "CA1", "clinvarVariantId": "", "clinvarVariantTitle": "NM_001(DSG2):c.1A>T"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "DSG2", "HGNC:3049")
    vd = interps[0].variant_interpretation.variation_descriptor
    assert vd.gene_context.value_id == "HGNC:3049"
    assert vd.gene_context.symbol == "DSG2"

def test_variant_gene_context_omitted_when_gene_not_in_title():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "CA1", "clinvarVariantId": "", "clinvarVariantTitle": "NM_001(OTHER):c.1A>T"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "DSG2", "HGNC:3049")
    vd = interps[0].variant_interpretation.variation_descriptor
    assert not vd.HasField("gene_context")

def test_variant_allelic_state_set_when_zygosity_present():
    ind = {
        "recessiveZygosity": "Homozygous",
        "variants": [{"carId": "CA1", "clinvarVariantId": "", "clinvarVariantTitle": "X"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "G", "HGNC:1")
    vd = interps[0].variant_interpretation.variation_descriptor
    assert vd.allelic_state.id == "GENO:0000136"

def test_variant_no_variants_returns_empty():
    ind = {"recessiveZygosity": None, "variants": []}
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "G", "HGNC:1")
    assert interps == []

def test_variant_falls_back_to_variant_scores_when_no_variants():
    ind = {
        "recessiveZygosity": None,
        "variants": [],
        "variantScores": [
            {"variantScored": {"carId": "CA999", "clinvarVariantId": "111", "clinvarVariantTitle": "NM_001(GENE):c.2T>A"}},
        ],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "GENE", "HGNC:1")
    assert len(interps) == 1
    assert interps[0].variant_interpretation.variation_descriptor.id == "caid:CA999"

def test_variant_scores_skips_entries_without_variant_scored():
    ind = {
        "recessiveZygosity": None,
        "variants": [],
        "variantScores": [
            {"variantScored": {"carId": "CA1", "clinvarVariantId": "", "clinvarVariantTitle": "X"}},
            {"score": 0.5},  # no variantScored key
        ],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "GENE", "HGNC:1")
    assert len(interps) == 1

def test_variant_prefers_variants_over_variant_scores():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "CA_DIRECT", "clinvarVariantId": "", "clinvarVariantTitle": "X"}],
        "variantScores": [
            {"variantScored": {"carId": "CA_SCORE", "clinvarVariantId": "", "clinvarVariantTitle": "Y"}},
        ],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "GENE", "HGNC:1")
    assert len(interps) == 1
    assert interps[0].variant_interpretation.variation_descriptor.id == "caid:CA_DIRECT"


from gci_phenopacket.transformer import build_phenopacket, GCIRecordContext

def _make_om_with_mondo():
    om = MagicMock()
    om.hpo_to_labeled_phenotype.side_effect = lambda h: {"id": h, "label": f"L:{h}"}
    _mondo_data = {
        "MONDO:0016587": "arrhythmogenic right ventricular cardiomyopathy",
    }
    om.mondo_label.side_effect = _mondo_data.get
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

REC_UUID = "aaaa-1111"
ANN_UUID = "bbbb-2222"
CTX = GCIRecordContext(record_id=REC_UUID, gdm_id="no-uuid", gene_symbol="DSG2", hgnc_id="HGNC:3049")

def test_build_phenopacket_id_format():
    # ID should use record and annotation UUIDs instead of positional indices
    pp = build_phenopacket(CTX, ANN_UUID, "12345", "Title", _base_individual(), _make_om_with_mondo())
    assert pp.id == "aaaa-1111_bbbb-2222_DSG2_MONDO_0016587_12345_Test_Patient"

def test_build_phenopacket_diagnosis_uses_colon_form():
    # Diagnosis disease.id must use colon format even though ID uses underscore
    pp = build_phenopacket(CTX, ANN_UUID, "12345", "Title", _base_individual(), _make_om_with_mondo())
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0016587"

def test_build_phenopacket_subject_id():
    pp = build_phenopacket(CTX, ANN_UUID, "99", "T", _base_individual(), _make_om_with_mondo())
    assert pp.subject.id == "PMID_99:Test Patient"

def test_build_phenopacket_freetext_disease_defaults_to_fallback():
    ind = _base_individual()
    ind["diagnosis"] = [{"diseaseId": "FREETEXT_abc"}]
    pp = build_phenopacket(CTX, ANN_UUID, "99", "T", ind, _make_om_with_mondo())
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0700096"
    assert pp.interpretations[0].diagnosis.disease.label == "human disease"

def test_build_phenopacket_empty_diagnosis_defaults_to_fallback():
    ind = _base_individual()
    ind["diagnosis"] = []
    pp = build_phenopacket(CTX, ANN_UUID, "99", "T", ind, _make_om_with_mondo())
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0700096"

def test_build_phenopacket_diagnosis_uses_pk_when_no_disease_id():
    ind = _base_individual()
    ind["diagnosis"] = [{"PK": "MONDO_0016587"}]
    pp = build_phenopacket(CTX, ANN_UUID, "99", "T", ind, _make_om_with_mondo())
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0016587"

def test_build_phenopacket_diagnosis_prefers_disease_id_over_pk():
    ind = _base_individual()
    ind["diagnosis"] = [{"diseaseId": "MONDO_0016587", "PK": "MONDO_0054748"}]
    pp = build_phenopacket(CTX, ANN_UUID, "99", "T", ind, _make_om_with_mondo())
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0016587"

def test_build_phenopacket_interpretation_id():
    pp = build_phenopacket(CTX, ANN_UUID, "99", "T", _base_individual(), _make_om_with_mondo())
    assert pp.interpretations[0].id == "99_Test_Patient_uuid-123"

def test_build_phenopacket_metadata_schema_version():
    pp = build_phenopacket(CTX, ANN_UUID, "99", "T", _base_individual(), _make_om_with_mondo())
    assert pp.meta_data.phenopacket_schema_version == "2.0"

def test_build_phenopacket_metadata_resources_count():
    pp = build_phenopacket(CTX, ANN_UUID, "99", "T", _base_individual(), _make_om_with_mondo())
    assert len(pp.meta_data.resources) == 4
    resource_ids = {r.id for r in pp.meta_data.resources}
    assert resource_ids == {"hp", "mondo", "geno", "eco"}

def test_build_phenopacket_provenance_direct_individual():
    ctx = GCIRecordContext(record_id=REC_UUID, gdm_id="gdm-abc", gene_symbol="DSG2", hgnc_id="HGNC:3049")
    pp = build_phenopacket(ctx, ANN_UUID, "99", "T", _base_individual(), _make_om_with_mondo())
    assert len(pp.meta_data.external_references) == 1
    assert pp.meta_data.external_references[0].id == "gdm:gdm-abc-individual:uuid-123"

def test_build_phenopacket_provenance_group_family():
    ctx = GCIRecordContext(record_id=REC_UUID, gdm_id="gdm-abc", gene_symbol="DSG2", hgnc_id="HGNC:3049")
    pp = build_phenopacket(ctx, ANN_UUID, "99", "T", _base_individual(), _make_om_with_mondo(),
                           group_uuid="grp-1", family_uuid="fam-1")
    assert pp.meta_data.external_references[0].id == "gdm:gdm-abc-group:grp-1-family:fam-1-individual:uuid-123"
