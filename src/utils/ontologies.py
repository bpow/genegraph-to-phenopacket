import pronto
from src.utils.paths import ONTOLOGY_DIR


class OntologyManager:
    def __init__(self, logger, custom_paths=None):
        self.logger = logger
        self.custom_paths = custom_paths or {}

        # Default URLs
        urls = {
            "hp": "http://purl.obolibrary.org/obo/hp.owl",
            "mondo": "http://purl.obolibrary.org/obo/mondo.owl",
            "geno": "http://purl.obolibrary.org/obo/geno.owl"
        }

        self.logger.info("Initializing Ontologies (Checking Cache/Remote)...")

        # 1. Load HPO
        self.hpo = self._load_resource("hp", urls["hp"])

        # 2. Load Mondo
        self.mondo = self._load_resource("mondo", urls["mondo"])

        # 3. Load Geno & Create Lookup
        self.geno = self._load_resource("geno", urls["geno"])
        self.geno_lookup = {term.name: term.id for term in self.geno.terms()}

        self.logger.info("Ontologies successfully loaded and indexed.")

    def _load_resource(self, name, url):
        """Helper to handle the 'User Path -> Cache -> Download' logic."""
        if name in self.custom_paths:
            return pronto.Ontology(str(self.custom_paths[name]))

        # Changed extension to .obo for better compatibility
        cache_path = ONTOLOGY_DIR / f"{name}.obo"

        if cache_path.exists():
            self.logger.info(f"Loading {name} from cache: {cache_path}")
            return pronto.Ontology(str(cache_path))

        self.logger.info(f"Downloading {name} from remote...")
        onto = pronto.Ontology(url)

        self.logger.info(f"Saving {name} to cache in OBO format...")
        with open(cache_path, "wb") as f:
            onto.dump(f, format="obo")

        return onto

    def hpo_to_labeled_phenotype(self, hpo_id):
        try:
            # Normalize the ID for pronto lookup
            term = self.hpo[hpo_id.replace('obo:HP_', 'HP:')]
            return {'id': term.id, 'label': term.name}
        except Exception as e:
            self.logger.warning(f"Could not resolve HPO label for {hpo_id}: {e}")
            return {'id': hpo_id, 'label': 'Unknown Phenotype'}
