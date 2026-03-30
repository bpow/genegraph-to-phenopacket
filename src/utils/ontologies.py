import csv
import io
from pathlib import Path
import requests
import pronto
from src.utils.paths import ONTOLOGY_DIR


HGNC_TSV_URL = (
    "https://www.genenames.org/cgi-bin/download/custom?"
    "col=gd_hgnc_id&col=gd_app_sym&status=Approved"
    "&hgnc_dbtag=on&order_by=gd_app_sym_sort&format=text&submit=submit"
)


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

        self.hgnc_lookup = self._load_hgnc()
        # Reverse lookup: symbol → "hgnc:{numeric_id}"
        self.hgnc_symbol_lookup = {v: f"hgnc:{k}" for k, v in self.hgnc_lookup.items()}

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

    def _load_hgnc(self):
        """Load HGNC gene symbol lookup: custom path → cache → remote download.
        Returns dict mapping numeric HGNC ID (str) → gene symbol (str).
        """
        if "hgnc" in self.custom_paths:
            path = self.custom_paths["hgnc"]
            self.logger.info(f"Loading HGNC from custom path: {path}")
            return self._parse_hgnc_tsv(Path(path).read_text(encoding="utf-8"))

        cache_path = ONTOLOGY_DIR / "hgnc.tsv"

        if cache_path.exists():
            self.logger.info(f"Loading HGNC from cache: {cache_path}")
            return self._parse_hgnc_tsv(cache_path.read_text(encoding="utf-8"))

        self.logger.info("Downloading HGNC gene symbols from remote...")
        try:
            response = requests.get(HGNC_TSV_URL, timeout=60)
            response.raise_for_status()
            cache_path.write_text(response.text, encoding="utf-8")
            self.logger.info(f"HGNC saved to cache: {cache_path}")
            return self._parse_hgnc_tsv(response.text)
        except Exception as e:
            self.logger.error(f"Failed to download HGNC data: {e}")
            return {}

    def _parse_hgnc_tsv(self, text):
        """Parse HGNC TSV into {numeric_id: symbol} dict.
        HGNC IDs in the file look like 'HGNC:171' — we store just '171'.
        """
        lookup = {}
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        for row in reader:
            raw_id = row.get("HGNC ID", "").strip()
            symbol = row.get("Approved symbol", "").strip()
            if raw_id and symbol:
                numeric = raw_id.replace("HGNC:", "")
                lookup[numeric] = symbol
        return lookup

    def hpo_to_labeled_phenotype(self, hpo_id):
        """Map HPO ID (e.g. 'obo:HP_0001250' or 'HP:0001250') to {id, label}."""
        normalized = hpo_id.replace("obo:HP_", "HP:").replace("obo:HP:", "HP:")
        try:
            term = self.hpo[normalized]
            return {"id": term.id, "label": term.name}
        except Exception as e:
            self.logger.warning(f"Could not resolve HPO label for {hpo_id}: {e}")
            return {"id": normalized, "label": "Unknown Phenotype"}

    def hgnc_to_symbol(self, hgnc_id):
        """Map 'hgnc:171' or '171' to gene symbol (e.g. 'ACVR1')."""
        numeric = str(hgnc_id).replace("hgnc:", "").strip()
        symbol = self.hgnc_lookup.get(numeric)
        if not symbol:
            self.logger.warning(f"Could not resolve gene symbol for HGNC ID: {hgnc_id}")
            return "UNKNOWN"
        return symbol

    def symbol_to_hgnc(self, symbol):
        """Map gene symbol (e.g. 'ACVR1') to 'hgnc:171'. Returns None if not found."""
        hgnc_id = self.hgnc_symbol_lookup.get(symbol)
        if not hgnc_id:
            self.logger.warning(f"Could not resolve HGNC ID for symbol: {symbol}")
        return hgnc_id