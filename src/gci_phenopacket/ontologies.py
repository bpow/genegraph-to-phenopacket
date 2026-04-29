import logging
from oaklib import get_adapter

logger = logging.getLogger(__name__)


class OntologyManager:
    def __init__(self, hp_selector="sqlite:obo:hp", mondo_selector="sqlite:obo:mondo"):
        logger.info("Initializing Ontologies (Checking Cache/Remote)...")
        self._hpo = get_adapter(hp_selector)
        self._mondo = get_adapter(mondo_selector)
        logger.info("Ontologies successfully loaded and indexed.")

    def hpo_to_labeled_phenotype(self, hpo_id):
        """Map HPO ID (e.g. 'obo:HP_0001250' or 'HP:0001250') to {id, label}."""
        normalized = hpo_id.replace("obo:HP_", "HP:").replace("obo:HP:", "HP:")
        label = self._hpo.label(normalized)
        if label is None:
            logger.warning(f"Could not resolve HPO label for {hpo_id}")
            return {"id": normalized, "label": "Unknown Phenotype"}
        return {"id": normalized, "label": label}

    def mondo_label(self, disease_id):
        """Return the Mondo label for a CURIE, or None if not found."""
        return self._mondo.label(disease_id)
