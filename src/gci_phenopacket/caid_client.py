import json
import logging
import urllib.request
import urllib.error
from pathlib import Path

LOGGER = logging.getLogger(__name__)
CAID_API_BASE = "https://reg.clinicalgenome.org/allele"


class CaidClient:
    """Fetches variant info from the ClinGen Allele Registry with a persistent JSON cache."""

    def __init__(self, cache_path: Path):
        self._cache_path = cache_path
        self._cache: dict = {}
        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    self._cache = json.load(f)
                LOGGER.info(f"Loaded CAID cache: {len(self._cache)} entries from {cache_path}")
            except Exception as e:
                LOGGER.warning(f"Could not load CAID cache from {cache_path}: {e}")

    def get(self, car_id: str) -> dict | None:
        """Return enriched variant info for car_id. Uses cache first, then API."""
        if car_id in self._cache:
            return self._cache[car_id]
        data = self._fetch(car_id)
        if data is not None:
            self._cache[car_id] = data
        return data

    def save(self):
        """Write in-memory cache to disk."""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._cache_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, indent=2)
        LOGGER.info(f"Saved CAID cache: {len(self._cache)} entries to {self._cache_path}")

    def _fetch(self, car_id: str) -> dict | None:
        url = f"{CAID_API_BASE}/{car_id}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            LOGGER.debug(f"CAID API: fetched {car_id}")
            return self._parse(raw)
        except urllib.error.HTTPError as e:
            LOGGER.warning(f"CAID API HTTP {e.code} for {car_id} — skipping")
        except Exception as e:
            LOGGER.warning(f"CAID API error for {car_id}: {e} — skipping")
        return None

    def _parse(self, data: dict) -> dict:
        expressions = []
        vcf_record = None
        xrefs = []
        gene_symbols = []

        # Genomic alleles → GRCh38/GRCh37 HGVS expressions; GRCh38 VCF record
        for ga in data.get("genomicAlleles") or []:
            ref_genome = ga.get("referenceGenome", "")
            if ref_genome not in ("GRCh38", "GRCh37"):
                continue
            chrom = ga.get("chromosome", "")
            for hgvs_str in ga.get("hgvs") or []:
                expressions.append({"syntax": "hgvs.g", "value": hgvs_str, "assembly": ref_genome})
            if ref_genome == "GRCh38":
                coords = ga.get("coordinates") or []
                if coords:
                    c = coords[0]
                    vcf_record = {
                        "genome_assembly": "GRCh38",
                        "chrom": chrom,
                        # API uses 0-based interbase coordinates; VCF is 1-based
                        "pos": c["start"] + 1,
                        "ref": c.get("referenceAllele", ""),
                        "alt": c.get("allele", ""),
                    }

        # Transcript alleles → gene symbols; MANE Select (or first) hgvs.c/hgvs.p
        all_tas = data.get("transcriptAlleles") or []
        for ta in all_tas:
            sym = ta.get("geneSymbol")
            if sym and sym not in gene_symbols:
                gene_symbols.append(sym)

        mane_tas = [ta for ta in all_tas if ta.get("MANE")]
        candidate_tas = mane_tas if mane_tas else all_tas[:1]
        for ta in candidate_tas:
            for hgvs_str in ta.get("hgvs") or []:
                expressions.append({"syntax": "hgvs.c", "value": hgvs_str})
            pe = ta.get("proteinEffect") or {}
            if pe.get("hgvs"):
                expressions.append({"syntax": "hgvs.p", "value": pe["hgvs"]})

        # External records → xrefs
        ext = data.get("externalRecords") or {}
        for dbsnp in ext.get("dbSNP") or []:
            rs = dbsnp.get("rs")
            if rs:
                xrefs.append(f"dbSNP:rs{rs}")
        for cv in ext.get("ClinVarAlleles") or []:
            allele_id = cv.get("alleleId")
            if allele_id:
                xrefs.append(f"ClinVar:{allele_id}")

        return {
            "expressions": expressions,
            "vcf_record": vcf_record,
            "xrefs": xrefs,
            "gene_symbols": gene_symbols,
        }
