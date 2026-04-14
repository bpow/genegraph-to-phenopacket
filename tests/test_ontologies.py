import logging
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
from gci_phenopacket.utils.ontologies import OntologyManager


def make_logger():
    logger = logging.getLogger("test-ontologies")
    logger.addHandler(logging.NullHandler())
    return logger


def make_mock_onto():
    onto = MagicMock()
    onto.terms.return_value = []
    return onto


def test_load_ontology_uses_custom_path(tmp_path):
    """custom_paths bypasses both cache and remote download."""
    fake = tmp_path / "hp.obo"
    fake.touch()
    mock_onto = make_mock_onto()

    with patch("gci_phenopacket.utils.ontologies.pronto.Ontology", return_value=mock_onto):
        om = OntologyManager(
            make_logger(),
            custom_paths={"hp": fake, "mondo": fake},
        )
        # Both loaded via custom path — no URL strings passed
        import gci_phenopacket.utils.ontologies as mod
        from unittest.mock import patch as p2
        with p2.object(mod.pronto, "Ontology", return_value=mock_onto) as mock_pronto:
            om2 = OntologyManager(
                make_logger(),
                custom_paths={"hp": fake, "mondo": fake},
            )
            for c in mock_pronto.call_args_list:
                assert c == call(str(fake))


def test_load_ontology_loads_from_cache_when_exists(tmp_path):
    """Cache hit: loads .obo file, does not download from URL."""
    cache_file = tmp_path / "hp.obo"
    cache_file.write_text("fake obo content")
    mock_onto = make_mock_onto()

    with patch("gci_phenopacket.utils.ontologies.CACHE_DIR", tmp_path), \
         patch("gci_phenopacket.utils.ontologies.pronto.Ontology", return_value=mock_onto) as mock_pronto:
        om = OntologyManager(make_logger(), custom_paths={"mondo": tmp_path / "mondo.obo"})

    # hp.obo existed — should have been loaded from path, not URL
    hp_calls = [c for c in mock_pronto.call_args_list if "hp.obo" in str(c)]
    assert len(hp_calls) == 1
    assert str(tmp_path / "hp.obo") in str(hp_calls[0])


def test_load_ontology_downloads_and_caches_when_no_cache(tmp_path):
    """Cache miss: downloads from URL and saves .obo to cache dir."""
    mock_onto = make_mock_onto()

    with patch("gci_phenopacket.utils.ontologies.CACHE_DIR", tmp_path), \
         patch("gci_phenopacket.utils.ontologies.pronto.Ontology", return_value=mock_onto):
        OntologyManager(make_logger())

    # Cache files should now exist
    assert (tmp_path / "hp.obo").exists()
    assert (tmp_path / "mondo.obo").exists()


def test_hpo_to_labeled_phenotype_passes_bare_hpo_id_to_ontology():
    """hpo_to_labeled_phenotype passes the bare HP:XXXXXXX ID directly to the ontology.
    Normalization of obo: prefixes happens upstream in extract_hpo_id()."""
    mock_term = MagicMock()
    mock_term.id = "HP:0001250"
    mock_term.name = "Seizure"

    mock_onto = make_mock_onto()
    mock_onto.__getitem__ = MagicMock(return_value=mock_term)

    with patch("gci_phenopacket.utils.ontologies.CACHE_DIR", Path("/tmp")), \
         patch("gci_phenopacket.utils.ontologies.pronto.Ontology", return_value=mock_onto):
        om = OntologyManager(make_logger())

    result = om.hpo_to_labeled_phenotype("HP:0001250")
    mock_onto.__getitem__.assert_called_with("HP:0001250")
    assert result == {"id": "HP:0001250", "label": "Seizure"}


def test_hpo_to_labeled_phenotype_returns_fallback_on_unknown_id():
    """Unknown HPO ID returns normalized id with 'Unknown Phenotype' label."""
    mock_onto = make_mock_onto()
    mock_onto.__getitem__ = MagicMock(side_effect=KeyError("not found"))

    with patch("gci_phenopacket.utils.ontologies.CACHE_DIR", Path("/tmp")), \
         patch("gci_phenopacket.utils.ontologies.pronto.Ontology", return_value=mock_onto):
        om = OntologyManager(make_logger())

    result = om.hpo_to_labeled_phenotype("HP:9999999")
    assert result == {"id": "HP:9999999", "label": "Unknown Phenotype"}
