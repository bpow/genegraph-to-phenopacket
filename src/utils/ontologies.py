import pronto
from utils.paths import ONTOLOGY_DIR


class OntologyManager:
    def __init__(self, logger, custom_paths=None):
        self.logger = logger
        self.custom_paths = custom_paths or {}

        urls = {
            "hp":    "http://purl.obolibrary.org/obo/hp.owl",
            "mondo": "http://purl.obolibrary.org/obo/mondo.owl",
            "geno":  "http://purl.obolibrary.org/obo/geno.owl",
        }

        self.logger.info("Initializing Ontologies (Checking Cache/Remote)...")

        self.hpo   = self._load_ontology("hp",    urls["hp"])
        self.mondo = self._load_ontology("mondo",  urls["mondo"])
        self.geno  = self._load_ontology("geno",   urls["geno"])

        self.geno_lookup  = {term.name: term.id for term in self.geno.terms()}
        self.mondo_lookup = {term.id: term.name  for term in self.mondo.terms()}

        self.logger.info("Ontologies successfully loaded and indexed.")

    def _load_ontology(self, name, url):
        """Load ontology: custom path → cache → remote download."""
        if name in self.custom_paths:
            return pronto.Ontology(str(self.custom_paths[name]))

        cache_path = ONTOLOGY_DIR / f"{name}.obo"
        if cache_path.exists():
            self.logger.info(f"Loading {name} from cache: {cache_path}")
            return pronto.Ontology(str(cache_path))

        self.logger.info(f"Downloading {name} from remote...")
        onto = pronto.Ontology(url)
        self.logger.info(f"Saving {name} to cache...")
        with open(cache_path, "wb") as f:
            onto.dump(f, format="obo")
        return onto

    def hpo_to_labeled_phenotype(self, hpo_id):
        """Map HPO ID (e.g. 'obo:HP_0001250' or 'HP:0001250') to {id, label}."""
        normalized = hpo_id.replace("obo:HP_", "HP:").replace("obo:HP:", "HP:")
        try:
            term = self.hpo[normalized]
            return {"id": term.id, "label": term.name}
        except Exception as e:
            self.logger.warning(f"Could not resolve HPO label for {hpo_id}: {e}")
            return {"id": normalized, "label": "Unknown Phenotype"}