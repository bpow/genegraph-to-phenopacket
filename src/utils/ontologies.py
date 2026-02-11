import pyhpo
import pronto


class OntologyManager:
    def __init__(self, logger):
        # We assign the logger passed from main.py to an internal variable
        self.logger = logger

        # Now we use self.logger to track the progress
        self.logger.info("Initializing HPO Ontology (Local)...")
        pyhpo.Ontology()

        self.logger.info("Fetching Mondo and Geno via Pronto (Remote OWL)...")
        # These calls use the Internet and may take a moment
        self.mondo = pronto.Ontology("http://purl.obolibrary.org/obo/mondo.owl")
        self.geno = pronto.Ontology("http://purl.obolibrary.org/obo/geno.owl")

        # Creating lookups for fast access during transformation
        self.geno_lookup = {term.name: term.id for term in self.geno.terms()}
        self.mondo_lookup = {term.id: term.name for term in self.mondo.terms()}

        self.logger.info("Ontologies successfully loaded and indexed.")

    def hpo_to_labeled_phenotype(self, hpo_id):
        """Maps HPO ID to a clean label using pyhpo."""
        try:
            term = pyhpo.Ontology.get_hpo_object(hpo_id.replace('obo:HP_', 'HP:'))
            return {'id': term.id, 'label': term.name}
        except Exception as e:
            # We log the specific HPO ID that failed
            self.logger.warning(f"Could not resolve HPO label for {hpo_id}: {e}")
            return {'id': hpo_id, 'label': 'Unknown Phenotype'}