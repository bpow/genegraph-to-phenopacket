# src/gci_transformer.py
import math
import logging
import phenopackets.schema.v2 as pps2

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FALLBACK_DISEASE_ID = "MONDO:0700096"
FALLBACK_DISEASE_LABEL = "human disease"

GENO_LOOKUP = {
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


def mondo_id_to_colon(disease_id: str) -> str:
    """Convert 'MONDO_0016587' -> 'MONDO:0016587'. Returns fallback for FREETEXT_ or empty."""
    if not disease_id or disease_id.startswith("FREETEXT_"):
        return FALLBACK_DISEASE_ID
    parts = disease_id.split("_", 1)
    if len(parts) == 2:
        return f"{parts[0]}:{parts[1]}"
    return FALLBACK_DISEASE_ID


def build_iso8601_age(age_value, age_unit: str):
    """
    Convert ageValue + ageUnit to an ISO 8601 duration string.
    Returns:
      ("age", "P41Y")               for standard units
      ("gestational", (weeks, days)) for "Weeks gestation"
      None                           for missing/unknown input (logs a warning)
    """
    if age_value is None:
        return None
    if age_unit is None:
        return None
    if age_unit == "Weeks gestation":
        weeks = math.floor(age_value)
        days = round((age_value - weeks) * 7)
        return ("gestational", (weeks, days))
    template = AGE_UNIT_MAP.get(age_unit)
    if template is None:
        logging.getLogger(__name__).warning(f"Unrecognized ageUnit '{age_unit}' — omitting time_at_last_encounter")
        return None
    return ("age", template.replace("{n}", str(int(age_value))))


def collect_individuals(annotation: dict):
    """
    Yield (individual_dict, tag) for all individuals in an annotation.
    tag is "i" (direct), "f" (family), or "g" (group/group-family).
    """
    for ind in annotation.get("individuals", []):
        yield ind, "i"

    for family in annotation.get("families", []):
        for ind in family.get("individualIncluded", []):
            yield ind, "f"

    for group in annotation.get("groups", []):
        for ind in group.get("individualIncluded", []):
            yield ind, "g"
        for family in group.get("familyIncluded", []):
            for ind in family.get("individualIncluded", []):
                yield ind, "g"


def passes_filter(individual: dict) -> bool:
    """Return True only if individual is a proband with at least one HPO term."""
    if individual.get("is_proband") != "Yes":
        return False
    has_hpo = bool(individual.get("hpoIdInDiagnosis")) or bool(individual.get("hpoIdInElimination"))
    return has_hpo


def build_subject(pmid: str, label: str, individual: dict) -> pps2.Individual:
    """Build pps2.Individual from individual dict fields."""
    sex = SEX_MAP.get((individual.get("sex") or "").lower(), pps2.Sex.UNKNOWN_SEX)
    age_type = individual.get("ageType")
    age_unit = individual.get("ageUnit")
    age_value = individual.get("ageValue")

    vital_status = pps2.VitalStatus(
        status=pps2.VitalStatus.Status.DECEASED if age_type == "Death"
               else pps2.VitalStatus.Status.ALIVE
    )

    kwargs = dict(
        id=f"PMID_{pmid}:{label}",
        sex=sex,
        vital_status=vital_status,
    )

    age_result = build_iso8601_age(age_value, age_unit) if age_unit else None
    if age_result:
        kind, value = age_result
        if kind == "age":
            kwargs["time_at_last_encounter"] = pps2.TimeElement(
                age=pps2.Age(iso8601duration=value)
            )
        elif kind == "gestational":
            weeks, days = value
            kwargs["time_at_last_encounter"] = pps2.TimeElement(
                gestational_age=pps2.GestationalAge(weeks=weeks, days=days)
            )

    return pps2.Individual(**kwargs)


def build_phenotypic_features(individual: dict, pmid: str, article_title: str, om) -> list:
    """Build PhenotypicFeature list from hpoIdInDiagnosis and hpoIdInElimination."""
    evidence = [pps2.Evidence(
        reference=pps2.ExternalReference(
            id=f"PMID:{pmid}",
            description=article_title or "",
        ),
        evidence_code=pps2.OntologyClass(
            id="ECO:0006017",
            label="author statement from published clinical study used in manual assertion",
        ),
    )]

    features = []
    for hpo_id in individual.get("hpoIdInDiagnosis", []):
        mapped = om.hpo_to_labeled_phenotype(hpo_id)
        features.append(pps2.PhenotypicFeature(
            type=pps2.OntologyClass(id=mapped["id"], label=mapped["label"]),
            excluded=False,
            evidence=evidence,
        ))
    for hpo_id in individual.get("hpoIdInElimination", []):
        mapped = om.hpo_to_labeled_phenotype(hpo_id)
        features.append(pps2.PhenotypicFeature(
            type=pps2.OntologyClass(id=mapped["id"], label=mapped["label"]),
            excluded=True,
            evidence=evidence,
        ))
    return features
