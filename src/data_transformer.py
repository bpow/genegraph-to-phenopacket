import re
import json
import pyld
import requests
import phenopackets.schema.v2 as pps2
from google.protobuf.timestamp_pb2 import Timestamp

from src.config import RESOURCE_METADATA, FALLBACK_DISEASE_ID, FALLBACK_DISEASE_LABEL
from src.utils.pubmed_downloader import get_pubmed_title

# JSON-LD keys used in the data
_SKOS_PREF_LABEL = "http://www.w3.org/2004/02/skos/core#prefLabel"
_CAR_REFERENCE   = "https://terms.ga4gh.org/CanonicalReference"

# Zygosity: cg: term → GENO term name used for geno_lookup
_CG_ZYGOSITY_MAP = {
    "heterozygous":         "heterozygous",
    "homozygous":           "homozygous",
    "hemizygous":           "hemizygous",
    "compoundheterozygous": "compound heterozygous",
}

SEX_MAP = {
    "male":   pps2.Sex.MALE,
    "female": pps2.Sex.FEMALE,
}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _build_index(graph):
    """Build {id_string: node} index from a flat graph list."""
    return {n["id"]: n for n in graph if "id" in n}


def _resolve(index, ref):
    """Dereference {'id': '...'} to the full node, or return None."""
    if isinstance(ref, dict):
        return index.get(ref.get("id"))
    return None


def _sanitize(label):
    """Replace non-alphanumeric characters with underscores for safe filenames."""
    return re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")


def _extract_gene_from_label(var_label):
    """Extract gene symbol from a variant label like 'NM_001111.4(ACVR1):c.617G>A'.
    Returns the symbol string or None if not found.
    """
    match = re.search(r"\(([A-Za-z][A-Za-z0-9]+)\)", var_label)
    return match.group(1) if match else None


def _extract_pmid(source_url):
    """Extract PMID string from a PubMed URL."""
    if source_url:
        return source_url.strip("/").split("/")[-1]
    return "NA"


def _extract_car_id(allele_node):
    """Extract bare CAR ID (e.g. 'CA128036') from CanonicalReference."""
    if not allele_node:
        return None
    ref = allele_node.get(_CAR_REFERENCE)
    if isinstance(ref, dict):
        raw = ref.get("id", "")
        return raw.rstrip("/").split("/")[-1] if raw else None
    return None


def _fetch_allele_label(car_id, logger):
    """Hit ClinGen Allele Registry to get a variant label when skos label is absent."""
    url = f"http://reg.genome.network/allele/{car_id}"
    try:
        data = requests.get(url, timeout=10).json()
        hgvs_list = data.get("genomicAlleles", [{}])[0].get(
            "hgvsMatchingTranscriptVariant", []
        )
        return hgvs_list[0] if hgvs_list else None
    except Exception as e:
        logger.warning(f"Allele registry fetch failed for {car_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# Transformer
# ---------------------------------------------------------------------------

class PhenopacketTransformer:
    def __init__(self, ontology_manager, logger):
        self.om = ontology_manager
        self.logger = logger

    def transform_file(self, path):
        """
        Process a single JSON-LD file.
        Returns (results, stats) where:
          results — list of (gene_symbol, pmid, raw_label, phenopacket) tuples
          stats   — dict with keys: total_probands, skipped_no_hpo, phenopackets_created
        Only probands with at least one phenotype are converted.
        """
        empty = ([], {"total_probands": 0, "skipped_no_hpo": 0, "phenopackets_created": 0})

        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to read {path.name}: {e}")
            return empty

        ctx = doc.get("@context", {})

        try:
            flattened = pyld.jsonld.flatten(doc, ctx)
        except Exception as e:
            self.logger.error(f"Failed to flatten {path.name}: {e}")
            return empty

        graph = flattened.get("@graph", [])
        if not graph:
            self.logger.warning(f"Empty graph after flatten: {path.name}")
            return empty

        index = _build_index(graph)

        # Gene symbol from GeneValidityProposition
        proposition = next(
            (n for n in graph if n.get("type") == "GeneValidityProposition"), None
        )
        gene_symbol = "UNKNOWN"
        hgnc_id = ""
        if proposition:
            hgnc_id = proposition.get("gene", "")
            gene_symbol = self.om.hgnc_to_symbol(hgnc_id)

        results = []
        skipped_no_hpo = 0
        total_probands = 0

        for node in graph:
            if node.get("type") != "Proband":
                continue

            total_probands += 1
            phenotypes = node.get("phenotypes", [])
            if not phenotypes:
                skipped_no_hpo += 1
                self.logger.debug(
                    f"Skipped proband '{node.get('rdfs:label', '?')}' in "
                    f"{path.name} — no phenotypes"
                )
                continue

            pmid = _extract_pmid(node.get("dc:source", ""))
            raw_label = node.get("rdfs:label", "UNKNOWN")
            title = get_pubmed_title(pmid, self.logger)

            try:
                pp = self._build_phenopacket(
                    node, index, gene_symbol, hgnc_id, pmid, title
                )
                results.append((gene_symbol, pmid, raw_label, pp))
            except Exception as e:
                self.logger.error(
                    f"Failed to build phenopacket for '{raw_label}' "
                    f"in {path.name}: {e}"
                )

        stats = {
            "total_probands": total_probands,
            "skipped_no_hpo": skipped_no_hpo,
            "phenopackets_created": len(results),
        }
        return results, stats

    # ------------------------------------------------------------------

    def _build_phenopacket(self, proband, index, gene_symbol, hgnc_id, pmid, title=""):
        raw_label = proband.get("rdfs:label", "UNKNOWN")
        subj_id = f"PMID_{pmid}:{raw_label}"

        subject = pps2.Individual(
            id=subj_id,
            sex=SEX_MAP.get((proband.get("sex") or "").lower(), pps2.Sex.UNKNOWN_SEX)
        )

        phenotypic_features = self._build_phenotypic_features(
            proband.get("phenotypes", []), pmid, title
        )

        genomic_interps = self._build_genomic_interpretations(
            proband, index, subj_id, gene_symbol, hgnc_id
        )

        interpretation = pps2.Interpretation(
            id=proband.get("id", subj_id),
            progress_status=pps2.Interpretation.ProgressStatus.UNKNOWN_PROGRESS,
            diagnosis=pps2.Diagnosis(
                disease=pps2.OntologyClass(
                    id=FALLBACK_DISEASE_ID,
                    label=FALLBACK_DISEASE_LABEL
                ),
                genomic_interpretations=genomic_interps
            )
        )

        ts = Timestamp()
        ts.GetCurrentTime()
        meta_data = pps2.MetaData(
            created=ts,
            created_by="Automated import from ClinGen GCI data",
            resources=[pps2.Resource(**r) for r in RESOURCE_METADATA],
            phenopacket_schema_version="2.0"
        )

        return pps2.Phenopacket(
            id=subj_id,
            subject=subject,
            phenotypic_features=phenotypic_features,
            interpretations=[interpretation],
            meta_data=meta_data
        )

    def _build_phenotypic_features(self, phenotype_ids, pmid, title=""):
        evidence = [pps2.Evidence(
            reference=pps2.ExternalReference(
                id=f"PMID:{pmid}",
                description=title
            ),
            evidence_code=pps2.OntologyClass(
                id="ECO:0000304",
                label="author statement supported by traceable reference used in manual assertion"
            )
        )]
        features = []
        ids = phenotype_ids if isinstance(phenotype_ids, list) else [phenotype_ids]
        for hpo_id in ids:
            mapped = self.om.hpo_to_labeled_phenotype(hpo_id)
            features.append(pps2.PhenotypicFeature(
                type=pps2.OntologyClass(id=mapped["id"], label=mapped["label"]),
                evidence=evidence
            ))
        return features

    def _build_genomic_interpretations(self, proband, index, subj_id, gene_symbol, hgnc_id):
        interps = []

        variant_ref = proband.get("variant")
        if not variant_ref:
            return interps

        refs = variant_ref if isinstance(variant_ref, list) else [variant_ref]

        for vref in refs:
            var_obs = _resolve(index, vref)
            if not var_obs:
                continue

            # Zygosity
            zyg_raw = var_obs.get("zygosity", {}).get("id", "")
            zyg_term = zyg_raw.replace("cg:", "").lower()
            geno_name = _CG_ZYGOSITY_MAP.get(zyg_term, "unspecified zygosity")
            geno_id = self.om.geno_lookup.get(geno_name, "GENO:0000137")

            # Allele
            allele_node = _resolve(index, var_obs.get("allele"))
            car_id = _extract_car_id(allele_node)
            skos_label = (allele_node or {}).get(_SKOS_PREF_LABEL, "")

            if not car_id and not skos_label:
                self.logger.warning(
                    f"Skipping variant for {subj_id} — no CAR ID or skos label found"
                )
                continue
            else:
                var_id = f"caid:{car_id}" if car_id else ""
                var_label = skos_label
                if car_id and not skos_label:
                    var_label = _fetch_allele_label(car_id, self.logger) or ""

            # Gene context: use gene from variant label if present,
            # falling back to the subject gene from the file.
            variant_gene = _extract_gene_from_label(var_label)
            if variant_gene:
                if variant_gene == gene_symbol:
                    # Variant gene matches subject gene — use hgnc_id from file
                    gene_context_id = hgnc_id
                else:
                    # Different gene in variant — look up its HGNC ID
                    gene_context_id = self.om.symbol_to_hgnc(variant_gene) or ""
                gene_context_symbol = variant_gene
            else:
                gene_context_id = hgnc_id
                gene_context_symbol = gene_symbol

            vd_kwargs = dict(
                id=var_id,
                label=var_label,
                molecule_context=pps2.MoleculeContext.unspecified_molecule_context,
                allelic_state=pps2.OntologyClass(id=geno_id, label=geno_name)
            )
            if gene_context_symbol and gene_context_symbol != "UNKNOWN":
                vd_kwargs["gene_context"] = pps2.GeneDescriptor(
                    value_id=gene_context_id,
                    symbol=gene_context_symbol
                )

            interps.append(pps2.GenomicInterpretation(
                subject_or_biosample_id=subj_id,
                interpretation_status=pps2.GenomicInterpretation.InterpretationStatus.UNKNOWN_STATUS,
                variant_interpretation=pps2.VariantInterpretation(
                    acmg_pathogenicity_classification=pps2.AcmgPathogenicityClassification.NOT_PROVIDED,
                    therapeutic_actionability=pps2.TherapeuticActionability.UNKNOWN_ACTIONABILITY,
                    variation_descriptor=pps2.VariationDescriptor(**vd_kwargs)
                )
            ))

        return interps