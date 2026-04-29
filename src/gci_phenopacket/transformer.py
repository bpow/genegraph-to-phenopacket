# src/gci_phenopacket/transformer.py
import math
import re
import logging
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
    Yield (individual_dict, tag, group_uuid, family_uuid) for all individuals in an annotation.
    tag is "individual" (direct), "family", or "group". group_uuid/family_uuid are None when
    the individual is not nested in that structure.
    """
    for ind in annotation.get("individuals") or []:
        yield ind, "individual", None, None

    for family in annotation.get("families") or []:
        fam_uuid = _gci_id(family)
        for ind in family.get("individualIncluded") or []:
            yield ind, "family", None, fam_uuid

    for group in annotation.get("groups") or []:
        grp_uuid = _gci_id(group)
        for ind in group.get("individualIncluded") or []:
            yield ind, "group", grp_uuid, None
        for family in group.get("familyIncluded") or []:
            fam_uuid = _gci_id(family)
            for ind in family.get("individualIncluded") or []:
                yield ind, "group", grp_uuid, fam_uuid


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


def _make_evidence(pmid: str, article_title: str) -> list:
    return [pps2.Evidence(
        reference=pps2.ExternalReference(
            id=f"PMID:{pmid}",
            description=article_title or "",
        ),
        evidence_code=pps2.OntologyClass(
            id="ECO:0000304",
            label="author statement supported by traceable reference used in manual assertion",
        ),
    )]


def build_phenotypic_features(individual: dict, pmid: str, article_title: str, om) -> list:
    """Build PhenotypicFeature list from hpoIdInDiagnosis and hpoIdInElimination."""
    features = []
    for hpo_id in individual.get("hpoIdInDiagnosis", []):
        mapped = om.hpo_to_labeled_phenotype(extract_hpo_id(hpo_id))
        features.append(pps2.PhenotypicFeature(
            type=pps2.OntologyClass(id=mapped["id"], label=mapped["label"]),
            excluded=False,
            evidence=_make_evidence(pmid, article_title),
        ))
    for hpo_id in individual.get("hpoIdInElimination", []):
        mapped = om.hpo_to_labeled_phenotype(extract_hpo_id(hpo_id))
        features.append(pps2.PhenotypicFeature(
            type=pps2.OntologyClass(id=mapped["id"], label=mapped["label"]),
            excluded=True,
            evidence=_make_evidence(pmid, article_title),
        ))
    return features


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


def build_phenopacket(record_uuid: str, annotation_uuid: str,
                      gene_symbol: str, hgnc_id: str,
                      pmid: str, article_title: str,
                      individual: dict, tag: str, om,
                      gdm_uuid: str = "no-uuid",
                      group_uuid: str | None = None,
                      family_uuid: str | None = None,
                      preserve_freetext: bool = False) -> pps2.Phenopacket:
    """Assemble a complete Phenopacket from all parts."""
    label = individual.get("label", "Unknown")
    label_s = sanitize_label(label)
    uuid = individual.get("uuid", "no-uuid")

    # Disease
    diag_list = individual.get("diagnosis") or []
    diag = diag_list[0] if diag_list else {}
    raw_disease_id = diag.get("diseaseId") or diag.get("PK") or FALLBACK_DISEASE_ID
    raw_disease_label = diag.get("term")
    if raw_disease_id.startswith("MONDO_"):
        disease_id = raw_disease_id.replace("_", ":", 1)
        disease_label = om.mondo_label(disease_id)
        if disease_label is None and raw_disease_label:
            LOGGER.warning(
                f"MONDO ID '{disease_id}' not found in ontology — falling back to label '{raw_disease_label}'"
            )
            disease_label = raw_disease_label
        elif disease_label is None:
            disease_label = raw_disease_label or FALLBACK_DISEASE_LABEL
        elif disease_label != raw_disease_label:
            LOGGER.warning(
                f"MONDO ID '{disease_id}' label '{disease_label}' does not match annotation label '{raw_disease_label}', using current Mondo label"
            )
    elif preserve_freetext:
        LOGGER.warning(
            f"Unrecognized disease ID format '{raw_disease_id}' — falling back to label '{raw_disease_label or FALLBACK_DISEASE_LABEL}'"
        )
        disease_id = raw_disease_id
        disease_label = raw_disease_label or FALLBACK_DISEASE_LABEL
    else:
        LOGGER.warning(
            f"Unrecognized disease ID format '{raw_disease_id}' — falling back to {FALLBACK_DISEASE_ID} with label '{FALLBACK_DISEASE_LABEL}'"
        )
        disease_id = FALLBACK_DISEASE_ID
        disease_label = FALLBACK_DISEASE_LABEL

    # Phenopacket ID
    pp_id = f"{record_uuid}_{annotation_uuid}_{gene_symbol}_{disease_id.replace(':', '_')}_{pmid}_{label_s}_{tag}"

    # MetaData
    ts = Timestamp()
    ts.GetCurrentTime()
    provenance_id = build_gci_provenance_id(gdm_uuid, uuid, group_uuid, family_uuid)
    meta_data = pps2.MetaData(
        created=ts,
        resources=list(RESOURCE_METADATA),
        phenopacket_schema_version="2.0",
        external_references=[pps2.ExternalReference(id=provenance_id)],
    )

    # Build parts
    subject = build_subject(pmid, label, individual)
    phenotypic_features = build_phenotypic_features(individual, pmid, article_title, om)
    genomic_interps = build_genomic_interpretations(individual, pmid, label, gene_symbol, hgnc_id)

    interpretation = pps2.Interpretation(
        id=f"{pmid}_{label_s}_{uuid}",
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
