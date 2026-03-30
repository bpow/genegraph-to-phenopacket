"""Tests for pure helper functions and transformer logic in src/data_transformer.py"""
import pytest
from unittest.mock import MagicMock
import phenopackets.schema.v2 as pps2

from src.data_transformer import (
    _build_index,
    _resolve,
    _sanitize,
    _extract_gene_from_label,
    _extract_pmid,
    _extract_car_id,
    PhenopacketTransformer,
)

# ---------------------------------------------------------------------------
# _build_index
# ---------------------------------------------------------------------------

def test_build_index_maps_id_to_node():
    graph = [{"id": "abc", "type": "Proband"}, {"id": "xyz", "type": "VariantObservation"}]
    index = _build_index(graph)
    assert index["abc"]["type"] == "Proband"
    assert index["xyz"]["type"] == "VariantObservation"

def test_build_index_skips_nodes_without_id():
    graph = [{"type": "Proband"}, {"id": "xyz", "type": "VariantObservation"}]
    index = _build_index(graph)
    assert len(index) == 1
    assert "xyz" in index

def test_build_index_empty_graph():
    assert _build_index([]) == {}


# ---------------------------------------------------------------------------
# _resolve
# ---------------------------------------------------------------------------

def test_resolve_returns_full_node():
    index = {"abc": {"id": "abc", "type": "Proband"}}
    node = _resolve(index, {"id": "abc"})
    assert node["type"] == "Proband"

def test_resolve_returns_none_for_missing_id():
    index = {"abc": {"id": "abc"}}
    assert _resolve(index, {"id": "does-not-exist"}) is None

def test_resolve_returns_none_for_non_dict_ref():
    index = {"abc": {"id": "abc"}}
    assert _resolve(index, "abc") is None

def test_resolve_returns_none_for_none_ref():
    assert _resolve({}, None) is None


# ---------------------------------------------------------------------------
# _sanitize
# ---------------------------------------------------------------------------

def test_sanitize_replaces_spaces():
    assert _sanitize("Patient 3") == "Patient_3"

def test_sanitize_replaces_colons():
    assert _sanitize("II:9") == "II_9"

def test_sanitize_collapses_consecutive_separators():
    assert _sanitize("A, B") == "A_B"

def test_sanitize_strips_leading_trailing_underscores():
    assert _sanitize(".Patient.") == "Patient"

def test_sanitize_handles_dots_and_slashes():
    assert _sanitize("A.II.I") == "A_II_I"


# ---------------------------------------------------------------------------
# _extract_gene_from_label
# ---------------------------------------------------------------------------

def test_extract_gene_from_standard_hgvs_label():
    assert _extract_gene_from_label("NM_001111067.4(ACVR1):c.617G>A (p.Arg206His)") == "ACVR1"

def test_extract_gene_from_label_returns_none_when_no_parentheses():
    assert _extract_gene_from_label("NM_001111067.4:c.617G>A") is None

def test_extract_gene_from_label_ignores_numeric_only_parentheses():
    # Gene symbols must start with a letter — reject pure numbers
    assert _extract_gene_from_label("NM_001(123):c.617G>A") is None

def test_extract_gene_returns_first_match():
    assert _extract_gene_from_label("NM_001(DSG2):c.1A>T (p.Met1Val)") == "DSG2"

def test_extract_gene_from_empty_string():
    assert _extract_gene_from_label("") is None


# ---------------------------------------------------------------------------
# _extract_pmid
# ---------------------------------------------------------------------------

def test_extract_pmid_from_pubmed_url():
    assert _extract_pmid("https://pubmed.ncbi.nlm.nih.gov/16642017") == "16642017"

def test_extract_pmid_from_url_with_trailing_slash():
    assert _extract_pmid("https://pubmed.ncbi.nlm.nih.gov/16642017/") == "16642017"

def test_extract_pmid_returns_na_for_none():
    assert _extract_pmid(None) == "NA"

def test_extract_pmid_returns_na_for_empty():
    assert _extract_pmid("") == "NA"


# ---------------------------------------------------------------------------
# _extract_car_id
# ---------------------------------------------------------------------------

_CAR_REFERENCE = "https://terms.ga4gh.org/CanonicalReference"

def test_extract_car_id_strips_to_bare_id():
    node = {_CAR_REFERENCE: {"id": "http://reg.genome.network/allele/CA128036"}}
    assert _extract_car_id(node) == "CA128036"

def test_extract_car_id_with_trailing_slash():
    node = {_CAR_REFERENCE: {"id": "http://reg.genome.network/allele/CA128036/"}}
    assert _extract_car_id(node) == "CA128036"

def test_extract_car_id_returns_none_when_no_reference():
    assert _extract_car_id({"type": "VariationDescriptor"}) is None

def test_extract_car_id_returns_none_for_none_node():
    assert _extract_car_id(None) is None

def test_extract_car_id_returns_none_when_id_empty():
    node = {_CAR_REFERENCE: {"id": ""}}
    assert _extract_car_id(node) is None


# ---------------------------------------------------------------------------
# PhenopacketTransformer helpers (with mocked OntologyManager)
# ---------------------------------------------------------------------------

def _make_om(gene_symbol="ACVR1", hgnc_id="hgnc:171"):
    om = MagicMock()
    om.hpo_to_labeled_phenotype.side_effect = lambda hpo_id: {
        "id": hpo_id.replace("obo:HP_", "HP:"),
        "label": f"Label for {hpo_id}"
    }
    om.geno_lookup = {
        "heterozygous":         "GENO:0000135",
        "homozygous":           "GENO:0000136",
        "hemizygous":           "GENO:0000134",
        "compound heterozygous": "GENO:0000402",
        "unspecified zygosity": "GENO:0000137",
    }
    om.hgnc_to_symbol.return_value = gene_symbol
    om.symbol_to_hgnc.return_value = hgnc_id
    return om


def _make_transformer(gene_symbol="ACVR1"):
    logger = MagicMock()
    om = _make_om(gene_symbol)
    return PhenopacketTransformer(om, logger)


# --- _build_phenotypic_features ---

def test_phenotypic_features_count_matches_input():
    t = _make_transformer()
    features = t._build_phenotypic_features(
        ["obo:HP_0001250", "obo:HP_0001942"], pmid="12345"
    )
    assert len(features) == 2

def test_phenotypic_features_hpo_id_normalised():
    t = _make_transformer()
    features = t._build_phenotypic_features(["obo:HP_0001250"], pmid="12345")
    assert features[0].type.id == "HP:0001250"

def test_phenotypic_features_evidence_pmid():
    t = _make_transformer()
    features = t._build_phenotypic_features(["obo:HP_0001250"], pmid="99999")
    ev = features[0].evidence[0]
    assert ev.reference.id == "PMID:99999"

def test_phenotypic_features_evidence_eco_code():
    t = _make_transformer()
    features = t._build_phenotypic_features(["obo:HP_0001250"], pmid="1")
    assert features[0].evidence[0].evidence_code.id == "ECO:0000304"

def test_phenotypic_features_title_in_description():
    t = _make_transformer()
    features = t._build_phenotypic_features(
        ["obo:HP_0001250"], pmid="1", title="My Article"
    )
    assert features[0].evidence[0].reference.description == "My Article"

def test_phenotypic_features_single_string_input():
    t = _make_transformer()
    features = t._build_phenotypic_features("obo:HP_0001250", pmid="1")
    assert len(features) == 1


# --- _build_genomic_interpretations ---

_SKOS_PREF_LABEL = "http://www.w3.org/2004/02/skos/core#prefLabel"

def _make_flat_graph(zygosity="cg:Heterozygous", car_id="CA128036", skos_label="NM_001(ACVR1):c.1A>T"):
    allele_id = "https://example.org/allele/1"
    var_obs_id = "https://example.org/var_obs/1"

    allele_node = {
        "id": allele_id,
        "type": "https://terms.ga4gh.org/VariationDescriptor",
        _SKOS_PREF_LABEL: skos_label,
        "https://terms.ga4gh.org/CanonicalReference": {
            "id": f"http://reg.genome.network/allele/{car_id}"
        }
    }
    if not car_id:
        allele_node.pop("https://terms.ga4gh.org/CanonicalReference", None)
    if not skos_label:
        allele_node.pop(_SKOS_PREF_LABEL, None)

    var_obs = {
        "id": var_obs_id,
        "type": "VariantObservation",
        "zygosity": {"id": zygosity},
        "allele": {"id": allele_id},
    }
    proband = {
        "id": "https://example.org/proband/1",
        "type": "Proband",
        "rdfs:label": "Patient A",
        "sex": "Female",
        "phenotypes": ["obo:HP_0001250"],
        "dc:source": "https://pubmed.ncbi.nlm.nih.gov/12345",
        "variant": {"id": var_obs_id},
    }
    return proband, _build_index([allele_node, var_obs, proband])


def test_genomic_interp_zygosity_heterozygous():
    t = _make_transformer()
    proband, index = _make_flat_graph(zygosity="cg:Heterozygous")
    interps = t._build_genomic_interpretations(proband, index, "PMID_1:P", "ACVR1", "hgnc:171")
    assert interps[0].variant_interpretation.variation_descriptor.allelic_state.id == "GENO:0000135"

def test_genomic_interp_zygosity_homozygous():
    t = _make_transformer()
    proband, index = _make_flat_graph(zygosity="cg:Homozygous")
    interps = t._build_genomic_interpretations(proband, index, "PMID_1:P", "ACVR1", "hgnc:171")
    assert interps[0].variant_interpretation.variation_descriptor.allelic_state.id == "GENO:0000136"

def test_genomic_interp_variant_id_uses_caid():
    t = _make_transformer()
    proband, index = _make_flat_graph(car_id="CA999")
    interps = t._build_genomic_interpretations(proband, index, "PMID_1:P", "ACVR1", "hgnc:171")
    assert interps[0].variant_interpretation.variation_descriptor.id == "caid:CA999"

def test_genomic_interp_label_from_skos():
    t = _make_transformer()
    proband, index = _make_flat_graph(skos_label="NM_001(ACVR1):c.617G>A")
    interps = t._build_genomic_interpretations(proband, index, "PMID_1:P", "ACVR1", "hgnc:171")
    assert interps[0].variant_interpretation.variation_descriptor.label == "NM_001(ACVR1):c.617G>A"

def test_genomic_interp_gene_context_matching_gene():
    t = _make_transformer()
    proband, index = _make_flat_graph(skos_label="NM_001(ACVR1):c.617G>A")
    interps = t._build_genomic_interpretations(proband, index, "PMID_1:P", "ACVR1", "hgnc:171")
    gc = interps[0].variant_interpretation.variation_descriptor.gene_context
    assert gc.symbol == "ACVR1"
    assert gc.value_id == "hgnc:171"

def test_genomic_interp_gene_context_different_gene_uses_reverse_lookup():
    t = _make_transformer()
    # Variant contains DSG2, but subject gene is ACVR1
    proband, index = _make_flat_graph(skos_label="NM_001(DSG2):c.1A>T")
    interps = t._build_genomic_interpretations(proband, index, "PMID_1:P", "ACVR1", "hgnc:171")
    gc = interps[0].variant_interpretation.variation_descriptor.gene_context
    assert gc.symbol == "DSG2"
    # symbol_to_hgnc mock returns "hgnc:171" for any input
    t.om.symbol_to_hgnc.assert_called_once_with("DSG2")

def test_genomic_interp_skips_variant_when_no_car_id_and_no_label():
    t = _make_transformer()
    proband, index = _make_flat_graph(car_id="", skos_label="")
    interps = t._build_genomic_interpretations(proband, index, "PMID_1:P", "ACVR1", "hgnc:171")
    assert interps == []
    t.logger.warning.assert_called()

def test_genomic_interp_empty_when_no_variant():
    t = _make_transformer()
    proband = {"type": "Proband", "rdfs:label": "P"}
    interps = t._build_genomic_interpretations(proband, {}, "PMID_1:P", "ACVR1", "hgnc:171")
    assert interps == []


# --- transform_file (integration-level with real fixture JSON-LD) ---

import json
import tempfile
from pathlib import Path


def _make_jsonld_fixture(include_phenotypes=True, include_variant=True):
    """Minimal JSON-LD document matching the structure of real GCI files."""
    allele_id = "https://example.org/allele/1"
    var_obs_id = "https://example.org/var_obs/1"
    proband_id = "https://example.org/proband/1"

    doc = {
        "@context": {
            "@vocab": "https://genegraph.clinicalgenome.org/terms/",
            "id": "@id",
            "type": "@type",
            "obo": "http://purl.obolibrary.org/obo/",
            "dc": "http://purl.org/dc/terms/",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        },
        "id": "https://example.org/assertion/1",
        "type": "EvidenceStrengthAssertion",
        "subject": {
            "id": "https://example.org/prop/1",
            "type": "GeneValidityProposition",
            "gene": "hgnc:171",
            "disease": "obo:MONDO_0007606",
            "modeOfInheritance": "obo:HP_0000006"
        },
        "evidence": [
            {
                "id": var_obs_id,
                "type": "VariantObservation",
                "dc:source": "https://pubmed.ncbi.nlm.nih.gov/16642017",
                "allele": {
                    "id": allele_id,
                    "type": "https://terms.ga4gh.org/VariationDescriptor",
                    "http://www.w3.org/2004/02/skos/core#prefLabel": "NM_001111.4(ACVR1):c.617G>A",
                    "https://terms.ga4gh.org/CanonicalReference": {
                        "id": "http://reg.genome.network/allele/CA128036"
                    }
                },
                "zygosity": {"id": "cg:Heterozygous"},
                "member": {
                    "id": proband_id,
                    "type": "Proband",
                    "dc:source": "https://pubmed.ncbi.nlm.nih.gov/16642017",
                    "rdfs:label": "Patient A",
                    "sex": "Female",
                    "phenotypes": ["obo:HP_0001250", "obo:HP_0001822"] if include_phenotypes else [],
                    "variant": {"id": var_obs_id} if include_variant else None
                }
            }
        ]
    }
    return doc


def _make_transformer_no_pubmed():
    """Transformer with mocked OntologyManager and PubMed disabled."""
    logger = MagicMock()
    om = _make_om()
    t = PhenopacketTransformer(om, logger)
    return t


def test_transform_file_returns_one_result_for_proband_with_phenotypes(tmp_path, monkeypatch):
    monkeypatch.setattr("src.data_transformer.get_pubmed_title", lambda pmid, logger: "Test Title")
    doc = _make_jsonld_fixture(include_phenotypes=True)
    f = tmp_path / "test.json"
    f.write_text(json.dumps(doc))

    t = _make_transformer_no_pubmed()
    results, stats = t.transform_file(f)
    assert len(results) == 1
    assert stats["total_probands"] == 1
    assert stats["skipped_no_hpo"] == 0
    assert stats["phenopackets_created"] == 1


def test_transform_file_skips_proband_with_no_phenotypes(tmp_path, monkeypatch):
    monkeypatch.setattr("src.data_transformer.get_pubmed_title", lambda pmid, logger: "")
    doc = _make_jsonld_fixture(include_phenotypes=False)
    f = tmp_path / "test.json"
    f.write_text(json.dumps(doc))

    t = _make_transformer_no_pubmed()
    results, stats = t.transform_file(f)
    assert results == []
    assert stats["total_probands"] == 1
    assert stats["skipped_no_hpo"] == 1
    assert stats["phenopackets_created"] == 0


def test_transform_file_result_tuple_structure(tmp_path, monkeypatch):
    monkeypatch.setattr("src.data_transformer.get_pubmed_title", lambda pmid, logger: "My Title")
    doc = _make_jsonld_fixture()
    f = tmp_path / "test.json"
    f.write_text(json.dumps(doc))

    t = _make_transformer_no_pubmed()
    results, _ = t.transform_file(f)
    gene_symbol, pmid, raw_label, pp = results[0]
    assert gene_symbol == "ACVR1"
    assert pmid == "16642017"
    assert raw_label == "Patient A"
    assert isinstance(pp, pps2.Phenopacket)


def test_transform_file_phenopacket_subject_id(tmp_path, monkeypatch):
    monkeypatch.setattr("src.data_transformer.get_pubmed_title", lambda pmid, logger: "")
    doc = _make_jsonld_fixture()
    f = tmp_path / "test.json"
    f.write_text(json.dumps(doc))

    t = _make_transformer_no_pubmed()
    results, _ = t.transform_file(f)
    _, _, _, pp = results[0]
    assert pp.subject.id == "PMID_16642017:Patient A"


def test_transform_file_disease_always_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("src.data_transformer.get_pubmed_title", lambda pmid, logger: "")
    doc = _make_jsonld_fixture()
    f = tmp_path / "test.json"
    f.write_text(json.dumps(doc))

    t = _make_transformer_no_pubmed()
    results, _ = t.transform_file(f)
    _, _, _, pp = results[0]
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0700096"
    assert pp.interpretations[0].diagnosis.disease.label == "human disease"


def test_transform_file_returns_empty_for_invalid_json(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not json at all")
    t = _make_transformer_no_pubmed()
    results, stats = t.transform_file(f)
    assert results == []
    assert stats["total_probands"] == 0
    t.logger.error.assert_called()
