from unittest.mock import MagicMock, patch
import pytest
from gci_phenopacket.ontologies import OntologyManager


def _make_adapter(label_map=None):
    adapter = MagicMock()
    adapter.label.side_effect = lambda curie: (label_map or {}).get(curie)
    return adapter


def test_hpo_to_labeled_phenotype_normalizes_obo_prefix():
    """'obo:HP_0001250' is normalized to 'HP:0001250' before lookup."""
    hp_adapter = _make_adapter({"HP:0001250": "Seizure"})
    with patch("gci_phenopacket.ontologies.get_adapter", side_effect=[hp_adapter, MagicMock()]):
        om = OntologyManager()
    result = om.hpo_to_labeled_phenotype("obo:HP_0001250")
    hp_adapter.label.assert_called_with("HP:0001250")
    assert result == {"id": "HP:0001250", "label": "Seizure"}


def test_hpo_to_labeled_phenotype_returns_fallback_on_unknown_id():
    """Unknown HPO ID returns normalized id with 'Unknown Phenotype' label."""
    hp_adapter = _make_adapter({})
    with patch("gci_phenopacket.ontologies.get_adapter", side_effect=[hp_adapter, MagicMock()]):
        om = OntologyManager()
    result = om.hpo_to_labeled_phenotype("HP:9999999")
    assert result == {"id": "HP:9999999", "label": "Unknown Phenotype"}


def test_mondo_label_returns_label_when_found():
    """mondo_label returns the ontology label string for a known CURIE."""
    mondo_adapter = _make_adapter({"MONDO:0007947": "Marfan syndrome"})
    with patch("gci_phenopacket.ontologies.get_adapter", side_effect=[MagicMock(), mondo_adapter]):
        om = OntologyManager()
    assert om.mondo_label("MONDO:0007947") == "Marfan syndrome"


def test_mondo_label_returns_none_when_not_found():
    """mondo_label returns None for an unknown CURIE."""
    mondo_adapter = _make_adapter({})
    with patch("gci_phenopacket.ontologies.get_adapter", side_effect=[MagicMock(), mondo_adapter]):
        om = OntologyManager()
    assert om.mondo_label("MONDO:9999999") is None
