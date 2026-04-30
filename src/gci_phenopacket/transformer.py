# src/gci_phenopacket/transformer.py
import math
import re
import logging
from dataclasses import dataclass, asdict
from typing import Iterator
import phenopackets.schema.v2 as pps2
from google.protobuf.timestamp_pb2 import Timestamp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOGGER = logging.getLogger(__name__)

FALLBACK_DISEASE_ID = "MONDO:0700096"
FALLBACK_DISEASE_LABEL = "human disease"

GCI_TO_GENO = {
    "homozygous":   ("GENO:0000136", "homozygous"),
    "heterozygous": ("GENO:0000135", "heterozygous"),
    "twotrans":     ("GENO:0000402", "compound heterozygous"),
    "hemizygous":   ("GENO:0000134", "hemizygous"),
}
GENO_FALLBACK = ("GENO:0000137", "unspecified zygosity")

RESOURCE_METADATA = [
    pps2.Resource(id="hp",    name="Human Phenotype Ontology",        namespace_prefix="HP",    url="http://purl.obolibrary.org/obo/hp.owl"),
    pps2.Resource(id="mondo", name="Mondo Disease Ontology",          namespace_prefix="MONDO", url="http://purl.obolibrary.org/obo/mondo.owl"),
    pps2.Resource(id="geno",  name="Genotype Ontology",               namespace_prefix="GENO",  url="http://purl.obolibrary.org/obo/geno.owl"),
    pps2.Resource(id="eco",   name="Evidence and Conclusion Ontology",namespace_prefix="ECO",   url="https://evidenceontology.org/repo/ECO.owl", iri_prefix="http://purl.obolibrary.org/obo/ECO_"),
]

SEX_MAP = {
    "male":   pps2.Sex.MALE,
    "female": pps2.Sex.FEMALE,
}

AGE_UNIT_MAP = {
    "Years":  "P{n}Y",
    "Months": "P{n}M",
    "Weeks":  "P{n}W",
    "Days":   "P{n}D",
    "Hours":  "PT{n}H",
}

@dataclass
class GCIRecordContext:
    record_id: str
    gdm_id: str
    gene_symbol: str
    hgnc_id: str


@dataclass
class GCIAnnotationContext:
    annotation_id: str
    pmid: str
    title: str


@dataclass
class GCIIndividualContext:
    individual: dict
    individual_id: str
    group_id: str | None
    family_id: str | None


@dataclass
class GCITransformerStats:
    """Class to track statistics during transformation."""

    total_records: int = 0
    total_individuals: int = 0
    individuals_with_hpo: int = 0
    phenopackets_created: int = 0
    skipped_no_hpo: int = 0

    def asdict(self):
        return asdict(self)

class GCITransformer:
    """Class to encapsulate transformation logic from GCI records to Phenopackets."""
    def __init__(self, ontology_manager, preserve_freetext: bool = False):
        self.om = ontology_manager
        self.stats = GCITransformerStats()
        self.preserve_freetext = preserve_freetext

    def phenopackets_from_gci_record(self, record: dict) -> Iterator[pps2.Phenopacket]:
        """Extract phenopackets from a single GCI record dict. Returns list of phenopackets."""
        self.stats.total_records += 1
        gdm = record.get("resourceParent", {}).get("gdm", {})
        ctx = GCIRecordContext(
            record_id=_gci_id(record),
            gdm_id=_gci_id(gdm),
            gene_symbol=gdm.get("gene", {}).get("symbol", "UNKNOWN"),
            hgnc_id=gdm.get("gene", {}).get("hgncId", ""),
        )

        for annotation in gdm.get("annotations") or []:
            ann_ctx = GCIAnnotationContext(
                annotation_id=_gci_id(annotation),
                pmid=annotation.get("article", {}).get("pmid", "UNKNOWN"),
                title=annotation.get("article", {}).get("title", ""),
            )

            for ind_ctx in iter_individuals(annotation):
                self.stats.total_individuals += 1
                if not passes_filter(ind_ctx.individual):
                    self.stats.skipped_no_hpo += 1
                    LOGGER.debug(f"Skipped (no HPO): {ind_ctx.individual.get('label')} — PMID {ann_ctx.pmid}")
                    continue
                self.stats.individuals_with_hpo += 1

                try:
                    prov_id = build_gci_provenance_id(
                        ctx.gdm_id, ind_ctx.individual_id,
                        ind_ctx.group_id, ind_ctx.family_id,
                    )
                    pp = self.build_phenopacket(ctx, ann_ctx, ind_ctx.individual, provenance_id=prov_id)
                    self.stats.phenopackets_created += 1
                    yield pp
                except Exception as e:
                    LOGGER.error(
                        f"Record {ctx.record_id}, annotation {ann_ctx.annotation_id}, "
                        f"individual '{ind_ctx.individual.get('label')}': {e}"
                    )

    def build_phenotypic_features(self, individual: dict, pmid: str, article_title: str) -> list:
        """Build PhenotypicFeature list from hpoIdInDiagnosis and hpoIdInElimination."""
        features = []
        for hpo_id in individual.get("hpoIdInDiagnosis", []):
            mapped = self.om.hpo_to_labeled_phenotype(extract_hpo_id(hpo_id))
            features.append(pps2.PhenotypicFeature(
                type=pps2.OntologyClass(id=mapped["id"], label=mapped["label"]),
                excluded=False,
                evidence=[_make_evidence(pmid, article_title)],
            ))
        for hpo_id in individual.get("hpoIdInElimination", []):
            mapped = self.om.hpo_to_labeled_phenotype(extract_hpo_id(hpo_id))
            features.append(pps2.PhenotypicFeature(
                type=pps2.OntologyClass(id=mapped["id"], label=mapped["label"]),
                excluded=True,
                evidence=[_make_evidence(pmid, article_title)],
            ))
        return features

    def process_diagnosis(self, diagnosis: dict) -> tuple[str, str]:
        raw_disease_id = diagnosis.get("diseaseId") or diagnosis.get("PK") or FALLBACK_DISEASE_ID
        raw_disease_label = diagnosis.get("term")
        if raw_disease_id.startswith("MONDO_"):
            disease_id = raw_disease_id.replace("_", ":", 1)
            disease_label = self.om.mondo_label(disease_id)
            if disease_label is None:
                disease_label = raw_disease_label or FALLBACK_DISEASE_LABEL
                LOGGER.warning(
                    f"MONDO ID '{disease_id}' not found in ontology — falling back to label '{disease_label}'"
                )
                return disease_id, disease_label
            elif disease_label != raw_disease_label:
                LOGGER.warning(
                    f"MONDO ID '{disease_id}' label '{disease_label}' does not match annotation label '{raw_disease_label}', using current Mondo label"
                )
                return disease_id, disease_label
        elif self.preserve_freetext:
            LOGGER.warning(
                f"Unrecognized disease ID format '{raw_disease_id}' — falling back to label '{raw_disease_label or FALLBACK_DISEASE_LABEL}'"
            )
            return raw_disease_id, raw_disease_label or FALLBACK_DISEASE_LABEL
        else:
            LOGGER.warning(
                f"Unrecognized disease ID format '{raw_disease_id}' — falling back to {FALLBACK_DISEASE_ID} with label '{FALLBACK_DISEASE_LABEL}'"
            )
            return FALLBACK_DISEASE_ID, FALLBACK_DISEASE_LABEL

    def build_phenopacket(self, ctx: GCIRecordContext, ann_ctx: GCIAnnotationContext,
                          individual: dict, provenance_id: str | None = None) -> pps2.Phenopacket:
        """Assemble a complete Phenopacket from all parts."""
        label = individual.get('label') or f'Individual: {provenance_id}'
        label_s = sanitize_label(label)

        # Disease
        diag_list = individual.get("diagnosis") or []
        diag = diag_list[0] if diag_list else {}
        disease_id, disease_label = self.process_diagnosis(diag)

        # Phenopacket ID
        prov_s = sanitize_label(provenance_id or "")
        pp_id = f"{ctx.gene_symbol}_{disease_id.replace(':', '_')}_{ann_ctx.pmid}_{label_s}_{ctx.record_id}_{ctx.gdm_id}_{ann_ctx.annotation_id}_{prov_s}"

        # MetaData
        ts = Timestamp()
        ts.GetCurrentTime()
        metadata_kwargs = dict(
            created=ts,
            resources=list(RESOURCE_METADATA),
            phenopacket_schema_version="2.0",
        )
        if provenance_id:
            metadata_kwargs["external_references"] = [pps2.ExternalReference(id=provenance_id)]
        meta_data = pps2.MetaData(**metadata_kwargs)

        # Build parts
        subject = build_subject(ann_ctx.pmid, label, individual)
        phenotypic_features = self.build_phenotypic_features(individual, ann_ctx.pmid, ann_ctx.title)
        genomic_interps = build_genomic_interpretations(individual, ann_ctx.pmid, label, ctx.gene_symbol, ctx.hgnc_id)

        interpretation = pps2.Interpretation(
            id=f"{ann_ctx.pmid}_{label_s}_{prov_s}",
            progress_status=pps2.Interpretation.ProgressStatus.UNKNOWN_PROGRESS,
            diagnosis=pps2.Diagnosis(
                disease=pps2.OntologyClass(id=disease_id, label=disease_label),
                genomic_interpretations=genomic_interps,
            ),
        )

        return pps2.Phenopacket(
            id=pp_id,
            subject=subject,
            phenotypic_features=phenotypic_features,
            interpretations=[interpretation],
            meta_data=meta_data,
        )

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def sanitize_label(label: str) -> str:
    """Replace spaces with _ and colons with - for safe use in IDs/filenames."""
    return label.replace(" ", "_").replace(":", "-")


def extract_hpo_id(raw: str) -> str:
    """Extract bare HP:XXXXXXX from strings like 'Seizures (HP:0001250)' or plain 'HP:0001250'."""
    match = re.search(r'HP:\d+', raw)
    return match.group(0) if match else raw


def resolve_disease(disease_id: str) -> str:
    """Convert 'MONDO_0016587' -> 'MONDO:0016587'. Returns fallback for FREETEXT_ or empty."""
    if not disease_id or disease_id.startswith("FREETEXT_"):
        return FALLBACK_DISEASE_ID
    parts = disease_id.split("_", 1)
    if len(parts) == 2:
        return f"{parts[0]}:{parts[1]}"
    return FALLBACK_DISEASE_ID


def build_time_element(age_value, age_unit: str):
    """Convert ageValue + ageUnit to a phenopacket TimeElement."""
    if age_value is None:
        return None
    if age_unit is None:
        return None
    if age_unit == "Weeks gestation":
        weeks = math.floor(age_value)
        days = round((age_value - weeks) * 7)
        return pps2.TimeElement(gestational_age=pps2.GestationalAge(weeks=weeks, days=days))
    
    template = AGE_UNIT_MAP.get(age_unit)
    if template is None:
        LOGGER.warning(f"Unrecognized ageUnit '{age_unit}' — omitting time_at_last_encounter")
        return None
    return pps2.TimeElement(age=pps2.Age(iso8601duration=template.replace("{n}", str(int(age_value)))))


def _gci_id(obj: dict) -> str:
    return obj.get("uuid") or obj.get("PK") or "no_uuid"


def build_gci_provenance_id(gdm_uuid: str, individual_uuid: str,
                            group_uuid=None, family_uuid=None) -> str:
    parts = [f"gdm:{gdm_uuid}"]
    if group_uuid:
        parts.append(f"group:{group_uuid}")
    if family_uuid:
        parts.append(f"family:{family_uuid}")
    parts.append(f"individual:{individual_uuid}")
    return "-".join(parts)


def iter_individuals(annotation: dict):
    """
    Yield GCIIndividualContext for all individuals in an annotation.
    group_id/family_id are None when the individual is not nested in that structure.
    """
    for ind in annotation.get("individuals") or []:
        yield GCIIndividualContext(individual=ind, individual_id=_gci_id(ind), group_id=None, family_id=None)

    for family in annotation.get("families") or []:
        fam_uuid = _gci_id(family)
        for ind in family.get("individualIncluded") or []:
            yield GCIIndividualContext(individual=ind, individual_id=_gci_id(ind), group_id=None, family_id=fam_uuid)

    for group in annotation.get("groups") or []:
        grp_uuid = _gci_id(group)
        for ind in group.get("individualIncluded") or []:
            yield GCIIndividualContext(individual=ind, individual_id=_gci_id(ind), group_id=grp_uuid, family_id=None)
        for family in group.get("familyIncluded") or []:
            fam_uuid = _gci_id(family)
            for ind in family.get("individualIncluded") or []:
                yield GCIIndividualContext(individual=ind, individual_id=_gci_id(ind), group_id=grp_uuid, family_id=fam_uuid)


def passes_filter(individual: dict) -> bool:
    """Return True only if an individual has at least one HPO term."""
    return bool(individual.get("hpoIdInDiagnosis")) or bool(individual.get("hpoIdInElimination"))


def build_subject(pmid: str, label: str, individual: dict) -> pps2.Individual:
    """Build pps2.Individual from individual dict fields."""
    sex = SEX_MAP.get((individual.get("sex") or "").lower(), pps2.Sex.UNKNOWN_SEX)
    age_type = individual.get("ageType")
    age_unit = individual.get("ageUnit")
    age_value = individual.get("ageValue")

    kwargs = dict(
        id=f"PMID_{pmid}:{label}",
        sex=sex,
    )

    if age_type == "Death":
        kwargs["vital_status"] = pps2.VitalStatus(status=pps2.VitalStatus.Status.DECEASED)

    age_result = build_time_element(age_value, age_unit) if age_unit else None
    if age_result:
        kwargs["time_at_last_encounter"] = age_result

    return pps2.Individual(**kwargs)


def _make_evidence(pmid: str, article_title: str) -> pps2.Evidence:
    return pps2.Evidence(
        reference=pps2.ExternalReference(
            id=f"PMID:{pmid}",
            description=article_title or "",
        ),
        evidence_code=pps2.OntologyClass(
            id="ECO:0000304",
            label="author statement supported by traceable reference used in manual assertion",
        ),
    )


def build_genomic_interpretations(individual: dict, pmid: str, label: str,
                                   gene_symbol: str, hgnc_id: str) -> list:
    """Build one GenomicInterpretation per variant in the individual."""
    subject_id = f"PMID_{pmid}:{label}"
    zyg = individual.get("recessiveZygosity")
    if zyg:
        if zyg.lower() not in GCI_TO_GENO:
            LOGGER.warning(
                f"Unrecognized recessiveZygosity '{zyg}' — falling back to unspecified zygosity"
            )
        geno_id, geno_label = GCI_TO_GENO.get(zyg.lower(), GENO_FALLBACK)
    else:
        geno_id, geno_label = None, None

    variants = individual.get("variants") or []
    if not variants:
        variants = [
            vs["variantScored"]
            for vs in (individual.get("variantScores") or [])
            if vs.get("variantScored")
        ]

    results = []
    for variant in variants:
        car_id = variant.get("carId")
        clinvar_id = variant.get("clinvarVariantId", "")
        if car_id:
            var_id = f"caid:{car_id}"
        elif clinvar_id:
            var_id = f"clinvar:{clinvar_id}"
        else:
            var_id = ""
        var_title = variant.get("clinvarVariantTitle", "")

        vd_kwargs = dict(
            id=var_id,
            label=var_title,
            molecule_context=pps2.MoleculeContext.unspecified_molecule_context,
        )

        if gene_symbol and gene_symbol in var_title:
            vd_kwargs["gene_context"] = pps2.GeneDescriptor(
                value_id=hgnc_id,
                symbol=gene_symbol,
            )

        if geno_id:
            vd_kwargs["allelic_state"] = pps2.OntologyClass(id=geno_id, label=geno_label)

        vd = pps2.VariationDescriptor(**vd_kwargs)
        vi = pps2.VariantInterpretation(
            acmg_pathogenicity_classification=pps2.AcmgPathogenicityClassification.NOT_PROVIDED,
            therapeutic_actionability=pps2.TherapeuticActionability.UNKNOWN_ACTIONABILITY,
            variation_descriptor=vd,
        )
        results.append(pps2.GenomicInterpretation(
            subject_or_biosample_id=subject_id,
            interpretation_status=pps2.GenomicInterpretation.InterpretationStatus.UNKNOWN_STATUS,
            variant_interpretation=vi,
        ))
    return results


