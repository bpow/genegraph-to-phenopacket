import logging
import os
from pathlib import Path
import pronto
from platformdirs import user_cache_dir

CACHE_DIR = Path(user_cache_dir("gci-phenopacket")) / "ontologies"

logger = logging.getLogger(__name__)


class OntologyManager:
    def __init__(self, custom_paths=None):
        self.custom_paths = custom_paths or {}

        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        urls = {
            "hp":    "https://purl.obolibrary.org/obo/hp.owl",
            "mondo": "https://purl.obolibrary.org/obo/mondo.owl",
        }

        logger.info("Initializing Ontologies (Checking Cache/Remote)...")

        self.hpo   = self._load_ontology("hp",     urls["hp"])
        self.mondo = self._load_ontology("mondo",  urls["mondo"])

        logger.info("Ontologies successfully loaded and indexed.")

    def _load_ontology(self, name, url):
        """Load ontology: custom path → cache → remote download."""
        if name in self.custom_paths:
            return pronto.Ontology(str(self.custom_paths[name]))

        cache_path = CACHE_DIR / f"{name}.obo"
        if cache_path.exists():
            logger.info(f"Loading {name} from cache: {cache_path}")
            return pronto.Ontology(str(cache_path))

        logger.info(f"Downloading {name} from remote...")
        onto = pronto.Ontology(url)
        logger.info(f"Saving {name} to cache...")
        tmp_path = cache_path.with_suffix(".obo.tmp")
        with open(tmp_path, "wb") as f:
            onto.dump(f, format="obo")
        os.replace(tmp_path, cache_path)
        return onto

    def hpo_to_labeled_phenotype(self, hpo_id):
        """Map HPO ID (e.g. 'obo:HP_0001250' or 'HP:0001250') to {id, label}."""
        normalized = hpo_id.replace("obo:HP_", "HP:").replace("obo:HP:", "HP:")
        try:
            term = self.hpo[normalized]
            return {"id": term.id, "label": term.name}
        except Exception as e:
            logger.warning(f"Could not resolve HPO label for {hpo_id}: {e}")
            return {"id": normalized, "label": "Unknown Phenotype"}
