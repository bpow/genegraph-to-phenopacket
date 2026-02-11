import pyld
import json
import phenopackets.schema.v2 as pps2
from google.protobuf.timestamp_pb2 import Timestamp
from config import PROBAND_FRAME, RESOURCE_METADATA
from utils.external_data import get_pubmed_article_info


def ensure_list(v):
    return v if isinstance(v, list) else [v]


class PhenopacketTransformer:
    def __init__(self, ontology_manager, logger):
        self.om = ontology_manager
        self.logger = logger

    def transform_file(self, path):
        with open(path) as f: doc = json.load(f)
        framed = pyld.jsonld.frame(doc, PROBAND_FRAME)  #
        proband = framed.get('@graph', [{}])[0]
        return self.build_phenopacket(proband) if proband else None

    def build_phenopacket(self, proband):
        pid, src = proband.get('id'), proband.get('dc:source', '')
        pmid = src.strip('/').split('/')[-1] if src else "NA"
        subj_id = f"PMID_{pmid}:{proband.get('rdfs:label', 'UNKNOWN')}"

        title, _ = get_pubmed_article_info(pid, src)
        evidence = [pps2.Evidence(
            reference=pps2.ExternalReference(id=f"PMID:{pmid}", reference=src, description=title or ""),
            evidence_code=pps2.OntologyClass(id="ECO:0006017", label="author statement...")
        )] if title else []

        phenotypes = [
            pps2.PhenotypicFeature(type=pps2.OntologyClass(**self.om.hpo_to_labeled_phenotype(h)), evidence=evidence)
            for h in ensure_list(proband.get('phenotypes', []))
        ]

        interpretations = []
        for var in ensure_list(proband.get('variant', [])):
            zyg = var.get("zygosity", {}).get("id", "").replace("cg:", "").lower()
            geno_id = self.om.geno_lookup.get(zyg, "GENO:0000137")
            for allele in ensure_list(var.get("allele", [])):
                desc = pps2.VariationDescriptor(
                    id=allele.get("http://www.w3.org/2004/02/skos/core#prefLabel", "UNK"),
                    allelic_state=pps2.OntologyClass(id=geno_id, label=zyg)
                )
                interpretations.append(pps2.GenomicInterpretation(
                    subject_or_biosample_id=subj_id,
                    variant_interpretation=pps2.VariantInterpretation(variation_descriptor=desc)
                ))

        return pps2.Phenopacket(
            id=pid,
            subject=pps2.Individual(id=subj_id, sex=pps2.Sex.Value(proband.get('sex', 'UNKNOWN').upper())),
            phenotypic_features=phenotypes,
            meta_data=pps2.MetaData(
                resources=[pps2.Resource(**r) for r in RESOURCE_METADATA],
                phenopacket_schema_version="2.0"
            ),
            interpretations=[pps2.Interpretation(id=pid, diagnosis=pps2.Diagnosis(
                disease=pps2.OntologyClass(id='MONDO:0700096', label='human disease'),
                genomic_interpretations=interpretations
            ))]
        )