from unittest.mock import MagicMock, patch
import pytest
from gci_phenopacket.transformer import GCITransformer


def _make_adapter(label_map=None):
    adapter = MagicMock()
    adapter.label.side_effect = lambda curie: (label_map or {}).get(curie)
    return adapter


def _make_transformer(hp_labels=None, mondo_labels=None):
    hp_adapter = _make_adapter(hp_labels)
    mondo_adapter = _make_adapter(mondo_labels)
    with patch("gci_phenopacket.transformer.get_adapter", side_effect=[hp_adapter, mondo_adapter]):
        t = GCITransformer()
    return t, hp_adapter


def test_hpo_to_labeled_phenotype_normalizes_obo_prefix():
    """'obo:HP_0001250' is normalized to 'HP:0001250' before lookup."""
    t, hp_adapter = _make_transformer(hp_labels={"HP:0001250": "Seizure"})
    result = t.hpo_to_labeled_phenotype("obo:HP_0001250")
    hp_adapter.label.assert_called_with("HP:0001250")
    assert result == {"id": "HP:0001250", "label": "Seizure"}


def test_hpo_to_labeled_phenotype_returns_fallback_on_unknown_id():
    """Unknown HPO ID returns normalized id with 'Unknown Phenotype' label."""
    t, _ = _make_transformer(hp_labels={})
    result = t.hpo_to_labeled_phenotype("HP:9999999")
    assert result == {"id": "HP:9999999", "label": "Unknown Phenotype"}
