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
