"""Tests for pure/cheap methods in src/utils/ontologies.py — no ontology downloads."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# We test _parse_hgnc_tsv and the lookup methods directly
# by constructing an OntologyManager with all heavy I/O mocked.

SAMPLE_HGNC_TSV = (
    "HGNC ID\tApproved symbol\n"
    "HGNC:171\tACVR1\n"
    "HGNC:3049\tDSG2\n"
    "HGNC:9673\tPTPRJ\n"
)


def _make_manager():
    """Return an OntologyManager with all ontology loading mocked out."""
    from src.utils.ontologies import OntologyManager

    logger = MagicMock()
    dummy_onto = MagicMock()
    dummy_onto.terms.return_value = []

    with patch.object(OntologyManager, "_load_ontology", return_value=dummy_onto), \
         patch.object(OntologyManager, "_load_hgnc", return_value={}):
        om = OntologyManager(logger)

    # Inject a real parsed HGNC lookup for testing
    om.hgnc_lookup = om._parse_hgnc_tsv(SAMPLE_HGNC_TSV)
    om.hgnc_symbol_lookup = {v: f"hgnc:{k}" for k, v in om.hgnc_lookup.items()}
    return om


# ---------------------------------------------------------------------------
# _parse_hgnc_tsv
# ---------------------------------------------------------------------------

def test_parse_hgnc_tsv_maps_numeric_id_to_symbol():
    from src.utils.ontologies import OntologyManager
    om = _make_manager()
    result = om._parse_hgnc_tsv(SAMPLE_HGNC_TSV)
    assert result["171"] == "ACVR1"
    assert result["3049"] == "DSG2"


def test_parse_hgnc_tsv_strips_hgnc_prefix():
    from src.utils.ontologies import OntologyManager
    om = _make_manager()
    result = om._parse_hgnc_tsv(SAMPLE_HGNC_TSV)
    assert "HGNC:171" not in result
    assert "171" in result


def test_parse_hgnc_tsv_empty_input():
    om = _make_manager()
    result = om._parse_hgnc_tsv("HGNC ID\tApproved symbol\n")
    assert result == {}


# ---------------------------------------------------------------------------
# hgnc_to_symbol
# ---------------------------------------------------------------------------

def test_hgnc_to_symbol_with_prefix():
    om = _make_manager()
    assert om.hgnc_to_symbol("hgnc:171") == "ACVR1"


def test_hgnc_to_symbol_numeric_only():
    om = _make_manager()
    assert om.hgnc_to_symbol("171") == "ACVR1"


def test_hgnc_to_symbol_unknown_returns_unknown():
    om = _make_manager()
    result = om.hgnc_to_symbol("hgnc:99999999")
    assert result == "UNKNOWN"
    om.logger.warning.assert_called()


# ---------------------------------------------------------------------------
# symbol_to_hgnc
# ---------------------------------------------------------------------------

def test_symbol_to_hgnc_known_symbol():
    om = _make_manager()
    assert om.symbol_to_hgnc("ACVR1") == "hgnc:171"


def test_symbol_to_hgnc_another_symbol():
    om = _make_manager()
    assert om.symbol_to_hgnc("DSG2") == "hgnc:3049"


def test_symbol_to_hgnc_unknown_returns_none():
    om = _make_manager()
    result = om.symbol_to_hgnc("NOSUCHGENE")
    assert result is None
    om.logger.warning.assert_called()


# ---------------------------------------------------------------------------
# hpo_to_labeled_phenotype (mocked pronto)
# ---------------------------------------------------------------------------

def test_hpo_normalizes_obo_prefix():
    om = _make_manager()
    mock_term = MagicMock()
    mock_term.id = "HP:0001250"
    mock_term.name = "Seizure"
    om.hpo = {"HP:0001250": mock_term}

    result = om.hpo_to_labeled_phenotype("obo:HP_0001250")
    assert result == {"id": "HP:0001250", "label": "Seizure"}


def test_hpo_returns_fallback_on_missing_term():
    om = _make_manager()
    om.hpo = {}  # empty — will raise KeyError

    result = om.hpo_to_labeled_phenotype("obo:HP_9999999")
    assert result["id"] == "HP:9999999"
    assert result["label"] == "Unknown Phenotype"
    om.logger.warning.assert_called()
