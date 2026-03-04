import pyld
import json
import time
import phenopackets.schema.v2 as pps2
from google.protobuf.timestamp_pb2 import Timestamp
from src.config import PROBAND_FRAME, RESOURCE_METADATA
from src.utils.pubmed_downloader import get_pubmed_article_info


def ensure_list(v):
    return v if isinstance(v, list) else [v]


class PhenopacketTransformer:
    def __init__(self, ontology_manager, logger):
        self.om = ontology_manager
        self.logger = logger

    def transform_file(self, path):
        """Processes a JSON-LD file and returns a list of (label, phenopacket) tuples."""
        with open(path) as f:
            doc = json.load(f)

        # Framing the data to extract all probands
        framed = pyld.jsonld.frame(doc, PROBAND_FRAME)
        graph = framed.get('@graph', [])

        if not graph:
            self.logger.warning(f"No proband data found in {path.name}")
            return []

        results = []
        for proband in graph:
            # Create a clean label for the filename (e.g., "Patient_123")
            # We replace spaces and slashes to avoid file path errors
            raw_label = proband.get('rdfs:label', 'UNKNOWN')
            clean_label = "".join(c if c.isalnum() else "_" for c in raw_label)

            try:
                pp = self.build_phenopacket(proband)
                results.append((clean_label, pp))
            except Exception as e:
                self.logger.error(f"Failed to build phenopacket for {clean_label}: {e}")

        return results

    def build_phenopacket(self, proband):
        # 1. Identity & Reference Prep
        pid = proband.get('id', 'no_id')
        src = proband.get('dc:source', '')
        pmid = src.strip('/').split('/')[-1] if src else "NA"

        # Consistent Subject ID format as per your original requirement
        label = proband.get('rdfs:label', 'UNKNOWN')
        subj_id = f"PMID_{pmid}:{label}"

        if src and pmid != "NA":
            self.logger.info(f"Pausing for PubMed rate limit (PMID: {pmid})...")
            time.sleep(1.0)

        # 2. Fetch External Metadata (RESTORED)
        title, _ = get_pubmed_article_info(pid, src)

        # 3. Evidence Construction (RESTORED ECO Code)
        evidence = []
        if title or src:
            evidence = [pps2.Evidence(
                reference=pps2.ExternalReference(
                    id=f"PMID:{pmid}",
                    reference=src,
                    description=title or ""
                ),
                evidence_code=pps2.OntologyClass(
                    id="ECO:0000304",
                    label="author statement supported by traceable reference used in manual assertion"
                )
            )]

        # 4. Phenotypic Features (Using evidence for each feature)
        phenotypes = [
            pps2.PhenotypicFeature(
                type=pps2.OntologyClass(**self.om.hpo_to_labeled_phenotype(h)),
                evidence=evidence
            ) for h in ensure_list(proband.get('phenotypes', []))
        ]

        # 5. Interpretations (Restored logic from our previous step)
        genomic_interpretations = []
        for variant in ensure_list(proband.get('variant', [])):
            zyg_id = variant.get("zygosity", {}).get("id", "").strip('cg:').lower()
            geno_id = self.om.geno_lookup.get(zyg_id, "GENO:0000137")

            for allele in ensure_list(variant.get("allele", [])):
                variation_descriptor = pps2.VariationDescriptor(
                    id=allele.get("http://www.w3.org/2004/02/skos/core#prefLabel", "UNK"),
                    molecule_context=pps2.MoleculeContext.unspecified_molecule_context,
                    allelic_state=pps2.OntologyClass(id=geno_id, label=zyg_id)
                )

                genomic_interpretations.append(pps2.GenomicInterpretation(
                    subject_or_biosample_id=subj_id,
                    interpretation_status=pps2.GenomicInterpretation.InterpretationStatus.UNKNOWN_STATUS,
                    variant_interpretation=pps2.VariantInterpretation(
                        acmg_pathogenicity_classification=pps2.AcmgPathogenicityClassification.NOT_PROVIDED,
                        therapeutic_actionability=pps2.TherapeuticActionability.UNKNOWN_ACTIONABILITY,
                        variation_descriptor=variation_descriptor
                    )
                ))

        # 6. Final Assembly
        diagnosis = pps2.Diagnosis(
            disease=pps2.OntologyClass(id='MONDO:0700096', label='human disease'),
            genomic_interpretations=genomic_interpretations
        )

        interpretation = pps2.Interpretation(
            id=pid,
            progress_status=pps2.Interpretation.ProgressStatus.UNKNOWN_PROGRESS,
            diagnosis=diagnosis
        )

        return pps2.Phenopacket(
            id=pid,
            subject=pps2.Individual(
                id=subj_id,
                sex=pps2.Sex.Value(proband.get('sex', 'UNKNOWN').upper())
            ),
            phenotypic_features=phenotypes,
            meta_data=pps2.MetaData(
                resources=[pps2.Resource(**r) for r in RESOURCE_METADATA],
                phenopacket_schema_version="2.0",
                created=Timestamp().GetCurrentTime(),
                created_by="Automated import from ClinGen GCI data",
            ),
            interpretations=[interpretation]
        )
