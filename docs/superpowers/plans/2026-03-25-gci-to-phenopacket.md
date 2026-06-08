# GCI to Phenopacket Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone pipeline that reads a GCI snapshot JSONL file and produces one GA4GH Phenopacket v2 JSON file per qualifying proband individual.

**Architecture:** Two new files — `src/gci_transformer.py` (all field mapping logic) and `src/gci_main.py` (CLI entry point + JSONL loop). Reuses `OntologyManager`, `setup_logger`, and `get_project_root` from existing utils. No existing files are modified except `pixi.toml`.

**Tech Stack:** Python 3.12, `phenopackets>=2.0.2.post5` (protobuf SDK), `pyhpo`, `pronto`, `google-protobuf`, `pytest` (tests), `unittest.mock` (mock OntologyManager in tests)

**Spec:** `docs/superpowers/specs/2026-03-25-gci-to-phenopacket-design.md`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/gci_transformer.py` | All GCI → Phenopacket field mapping and assembly |
| Create | `src/gci_main.py` | CLI args, JSONL reader loop, file output |
| Create | `tests/test_gci_transformer.py` | Unit tests for transformer logic |
| Modify | `pixi.toml` | Add `gci_transform` run target |

---

## Task 1: Pure Helper Functions

**Files:**
- Create: `src/gci_transformer.py`
- Create: `tests/test_gci_transformer.py`

These are pure functions with no dependencies — test and implement them first.

- [ ] **Step 1.1: Create `tests/test_gci_transformer.py` with failing tests for helpers**

```python
# tests/test_gci_transformer.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gci_transformer import sanitize_label, mondo_id_to_colon, build_iso8601_age


def test_sanitize_label_spaces():
    assert sanitize_label("Patient 3") == "Patient_3"

def test_sanitize_label_colons():
    assert sanitize_label("II:9") == "II-9"

def test_sanitize_label_mixed():
    assert sanitize_label("Proband C:1 test") == "Proband_C-1_test"

def test_mondo_id_to_colon_standard():
    assert mondo_id_to_colon("MONDO_0016587") == "MONDO:0016587"

def test_mondo_id_to_colon_preserves_numeric_part():
    # Ensure only the first separator is converted, not numbers
    assert mondo_id_to_colon("MONDO_0700096") == "MONDO:0700096"

def test_mondo_id_to_colon_freetext_returns_default():
    assert mondo_id_to_colon("FREETEXT_abc123") == "MONDO:0700096"

def test_mondo_id_to_colon_empty_returns_default():
    assert mondo_id_to_colon("") == "MONDO:0700096"

def test_build_iso8601_age_float_truncated():
    # Float ageValues are truncated to int for non-gestational units
    assert build_iso8601_age(41.7, "Years") == ("age", "P41Y")

def test_build_iso8601_age_years():
    assert build_iso8601_age(41, "Years") == ("age", "P41Y")

def test_build_iso8601_age_months():
    assert build_iso8601_age(6, "Months") == ("age", "P6M")

def test_build_iso8601_age_days():
    assert build_iso8601_age(5, "Days") == ("age", "P5D")

def test_build_iso8601_age_weeks():
    assert build_iso8601_age(3, "Weeks") == ("age", "P3W")

def test_build_iso8601_age_hours():
    assert build_iso8601_age(12, "Hours") == ("age", "PT12H")

def test_build_iso8601_age_weeks_gestation_whole():
    assert build_iso8601_age(38, "Weeks gestation") == ("gestational", (38, 0))

def test_build_iso8601_age_weeks_gestation_fractional():
    assert build_iso8601_age(38.5, "Weeks gestation") == ("gestational", (38, 4))

def test_build_iso8601_age_unknown_unit_returns_none():
    assert build_iso8601_age(5, "Decades") is None

def test_build_iso8601_age_none_value_returns_none():
    assert build_iso8601_age(None, "Years") is None
```

- [ ] **Step 1.2: Run tests to confirm they all fail**

```bash
cd /Users/vibhor/Documents/genegraph-to-phenopacket
pixi run python -m pytest tests/test_gci_transformer.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError: No module named 'gci_transformer'`

- [ ] **Step 1.3: Create `src/gci_transformer.py` with helpers only**

```python
# src/gci_transformer.py
import math
from google.protobuf.timestamp_pb2 import Timestamp
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
    """Convert 'MONDO_0016587' → 'MONDO:0016587'. Returns fallback for FREETEXT_ or empty."""
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
    if age_unit == "Weeks gestation":
        weeks = math.floor(age_value)
        days = round((age_value - weeks) * 7)
        return ("gestational", (weeks, days))
    template = AGE_UNIT_MAP.get(age_unit)
    if template is None:
        logging.getLogger(__name__).warning(f"Unrecognized ageUnit '{age_unit}' — omitting time_at_last_encounter")
        return None
    return ("age", template.replace("{n}", str(int(age_value))))
```

- [ ] **Step 1.4: Run tests — all helper tests should pass**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v 2>&1 | head -40
```
Expected: 14 tests PASSED (0 failed)

- [ ] **Step 1.5: Commit**

```bash
git add src/gci_transformer.py tests/test_gci_transformer.py
git commit -m "feat: add gci_transformer helpers and constants"
```

---

## Task 2: Individual Traversal (`collect_individuals`)

**Files:**
- Modify: `src/gci_transformer.py`
- Modify: `tests/test_gci_transformer.py`

`collect_individuals(annotation)` yields `(individual_dict, tag)` tuples for all three sources.

- [ ] **Step 2.1: Add failing tests for `collect_individuals`**

Append to `tests/test_gci_transformer.py`:

```python
from gci_transformer import collect_individuals

def _make_individual(label):
    return {"label": label, "is_proband": "Yes"}

def test_collect_direct_individuals():
    annotation = {
        "individuals": [_make_individual("A"), _make_individual("B")],
        "families": [],
        "groups": [],
    }
    results = list(collect_individuals(annotation))
    assert len(results) == 2
    assert all(tag == "i" for _, tag in results)
    assert [ind["label"] for ind, _ in results] == ["A", "B"]

def test_collect_family_individuals():
    annotation = {
        "individuals": [],
        "families": [{"individualIncluded": [_make_individual("C")]}],
        "groups": [],
    }
    results = list(collect_individuals(annotation))
    assert len(results) == 1
    assert results[0][1] == "f"

def test_collect_group_direct_individuals():
    annotation = {
        "individuals": [],
        "families": [],
        "groups": [{"individualIncluded": [_make_individual("D")], "familyIncluded": []}],
    }
    results = list(collect_individuals(annotation))
    assert len(results) == 1
    assert results[0][1] == "g"

def test_collect_group_family_individuals():
    annotation = {
        "individuals": [],
        "families": [],
        "groups": [{
            "individualIncluded": [],
            "familyIncluded": [{"individualIncluded": [_make_individual("E")]}],
        }],
    }
    results = list(collect_individuals(annotation))
    assert len(results) == 1
    assert results[0][1] == "g"

def test_collect_empty_annotation():
    annotation = {"individuals": [], "families": [], "groups": []}
    assert list(collect_individuals(annotation)) == []

def test_collect_annotation_with_absent_keys():
    # Annotation dict with no keys at all should yield nothing, not raise
    assert list(collect_individuals({})) == []
```

- [ ] **Step 2.2: Run tests to confirm they fail**

```bash
pixi run python -m pytest tests/test_gci_transformer.py::test_collect_direct_individuals -v
```
Expected: FAIL — `ImportError` or `AttributeError`

- [ ] **Step 2.3: Implement `collect_individuals` in `src/gci_transformer.py`**

Add after the helper functions:

```python
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
```

- [ ] **Step 2.4: Run traversal tests — all should pass**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v -k "collect" 2>&1
```
Expected: 6 tests PASSED

- [ ] **Step 2.5: Commit**

```bash
git add src/gci_transformer.py tests/test_gci_transformer.py
git commit -m "feat: add collect_individuals traversal"
```

---

## Task 3: Individual Filter (`passes_filter`)

**Files:**
- Modify: `src/gci_transformer.py`
- Modify: `tests/test_gci_transformer.py`

- [ ] **Step 3.1: Add failing tests**

Append to `tests/test_gci_transformer.py`:

```python
from gci_transformer import passes_filter

def test_passes_filter_proband_with_hpo():
    ind = {"is_proband": "Yes", "hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": []}
    assert passes_filter(ind) is True

def test_passes_filter_proband_with_elimination_only():
    ind = {"is_proband": "Yes", "hpoIdInDiagnosis": [], "hpoIdInElimination": ["HP:0001"]}
    assert passes_filter(ind) is True

def test_passes_filter_not_proband():
    ind = {"is_proband": "No", "hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": []}
    assert passes_filter(ind) is False

def test_passes_filter_proband_no_hpo():
    ind = {"is_proband": "Yes", "hpoIdInDiagnosis": [], "hpoIdInElimination": []}
    assert passes_filter(ind) is False

def test_passes_filter_missing_is_proband():
    ind = {"hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": []}
    assert passes_filter(ind) is False
```

- [ ] **Step 3.2: Run to confirm failure**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v -k "passes_filter"
```
Expected: FAIL — ImportError

- [ ] **Step 3.3: Implement `passes_filter`**

Add to `src/gci_transformer.py`:

```python
def passes_filter(individual: dict) -> bool:
    """Return True only if individual is a proband with at least one HPO term."""
    if individual.get("is_proband") != "Yes":
        return False
    has_hpo = bool(individual.get("hpoIdInDiagnosis")) or bool(individual.get("hpoIdInElimination"))
    return has_hpo
```

- [ ] **Step 3.4: Run filter tests — all pass**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v -k "passes_filter"
```
Expected: 5 tests PASSED

- [ ] **Step 3.5: Commit**

```bash
git add src/gci_transformer.py tests/test_gci_transformer.py
git commit -m "feat: add passes_filter for proband selection"
```

---

## Task 4: Subject Builder

**Files:**
- Modify: `src/gci_transformer.py`
- Modify: `tests/test_gci_transformer.py`

Builds the `pps2.Individual` (subject) from an individual dict. No OntologyManager needed.

- [ ] **Step 4.1: Add failing tests**

Append to `tests/test_gci_transformer.py`:

```python
import phenopackets.schema.v2 as pps2
from gci_transformer import build_subject

def test_build_subject_male():
    ind = {"sex": "Male", "ageType": "Onset", "ageUnit": "Years", "ageValue": 41}
    subj = build_subject("12345", "Proband A", ind)
    assert subj.id == "PMID_12345:Proband A"
    assert subj.sex == pps2.Sex.MALE

def test_build_subject_female():
    ind = {"sex": "Female", "ageType": "Onset", "ageUnit": "Years", "ageValue": 5}
    subj = build_subject("99", "Jane", ind)
    assert subj.sex == pps2.Sex.FEMALE

def test_build_subject_unknown_sex():
    ind = {"sex": "Other", "ageType": "Onset", "ageUnit": "Years", "ageValue": 10}
    subj = build_subject("1", "X", ind)
    assert subj.sex == pps2.Sex.UNKNOWN_SEX

def test_build_subject_vital_status_deceased():
    ind = {"sex": "Male", "ageType": "Death", "ageUnit": "Years", "ageValue": 14}
    subj = build_subject("1", "X", ind)
    assert subj.vital_status.status == pps2.VitalStatus.Status.DECEASED

def test_build_subject_vital_status_alive():
    ind = {"sex": "Male", "ageType": "Onset", "ageUnit": "Years", "ageValue": 14}
    subj = build_subject("1", "X", ind)
    assert subj.vital_status.status == pps2.VitalStatus.Status.ALIVE

def test_build_subject_age_at_last_encounter():
    ind = {"sex": "Male", "ageType": "Onset", "ageUnit": "Years", "ageValue": 41}
    subj = build_subject("1", "X", ind)
    assert subj.time_at_last_encounter.age.iso8601duration == "P41Y"

def test_build_subject_missing_age_omits_field():
    ind = {"sex": "Male", "ageType": None, "ageUnit": None, "ageValue": None}
    subj = build_subject("1", "X", ind)
    # time_at_last_encounter should not be set
    assert not subj.HasField("time_at_last_encounter")
```

- [ ] **Step 4.2: Run to confirm failure**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v -k "build_subject"
```
Expected: FAIL — ImportError

- [ ] **Step 4.3: Implement `build_subject`**

Add to `src/gci_transformer.py`:

```python
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
```

- [ ] **Step 4.4: Run subject tests — all pass**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v -k "build_subject"
```
Expected: 7 tests PASSED

- [ ] **Step 4.5: Commit**

```bash
git add src/gci_transformer.py tests/test_gci_transformer.py
git commit -m "feat: add build_subject with age and vital status"
```

---

## Task 5: Phenotypic Features Builder

**Files:**
- Modify: `src/gci_transformer.py`
- Modify: `tests/test_gci_transformer.py`

Builds `pps2.PhenotypicFeature` list. Uses a mocked `OntologyManager`.

- [ ] **Step 5.1: Add failing tests**

Append to `tests/test_gci_transformer.py`:

```python
from unittest.mock import MagicMock
from gci_transformer import build_phenotypic_features

def _make_om():
    """Mock OntologyManager — returns predictable HPO labels."""
    om = MagicMock()
    om.hpo_to_labeled_phenotype.side_effect = lambda hpo_id: {
        "id": hpo_id, "label": f"Label for {hpo_id}"
    }
    return om

def test_phenotypic_features_diagnosis_not_excluded():
    ind = {"hpoIdInDiagnosis": ["HP:0001942"], "hpoIdInElimination": []}
    features = build_phenotypic_features(ind, "12345", "Article title", _make_om())
    assert len(features) == 1
    assert features[0].type.id == "HP:0001942"
    assert features[0].excluded is False

def test_phenotypic_features_elimination_excluded():
    ind = {"hpoIdInDiagnosis": [], "hpoIdInElimination": ["HP:0001903"]}
    features = build_phenotypic_features(ind, "12345", "Title", _make_om())
    assert len(features) == 1
    assert features[0].excluded is True

def test_phenotypic_features_combined():
    ind = {"hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": ["HP:0002"]}
    features = build_phenotypic_features(ind, "12345", "Title", _make_om())
    assert len(features) == 2
    excluded_flags = {f.type.id: f.excluded for f in features}
    assert excluded_flags["HP:0001"] is False
    assert excluded_flags["HP:0002"] is True

def test_phenotypic_features_evidence_populated():
    ind = {"hpoIdInDiagnosis": ["HP:0001"], "hpoIdInElimination": []}
    features = build_phenotypic_features(ind, "99999", "My Article", _make_om())
    ev = features[0].evidence[0]
    assert ev.reference.id == "PMID:99999"
    assert ev.reference.description == "My Article"
    assert ev.evidence_code.id == "ECO:0006017"
```

- [ ] **Step 5.2: Run to confirm failure**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v -k "phenotypic"
```
Expected: FAIL — ImportError

- [ ] **Step 5.3: Implement `build_phenotypic_features`**

Add to `src/gci_transformer.py`:

```python
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
```

- [ ] **Step 5.4: Run phenotypic feature tests — all pass**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v -k "phenotypic"
```
Expected: 4 tests PASSED

- [ ] **Step 5.5: Commit**

```bash
git add src/gci_transformer.py tests/test_gci_transformer.py
git commit -m "feat: add build_phenotypic_features with evidence"
```

---

## Task 6: Variant and Genomic Interpretation Builder

**Files:**
- Modify: `src/gci_transformer.py`
- Modify: `tests/test_gci_transformer.py`

Builds `pps2.GenomicInterpretation` (one per variant) containing `VariantInterpretation` → `VariationDescriptor`.

- [ ] **Step 6.1: Add failing tests**

Append to `tests/test_gci_transformer.py`:

```python
from gci_transformer import build_genomic_interpretations

def test_variant_uses_carid_when_available():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "CA123", "clinvarVariantId": "456", "clinvarVariantTitle": "NM_001.1(GENE):c.1A>T"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "Patient1", "GENE", "HGNC:1")
    assert interps[0].variant_interpretation.variation_descriptor.id == "CA123"

def test_variant_falls_back_to_clinvar_id():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "", "clinvarVariantId": "789", "clinvarVariantTitle": "Some variant"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "Patient1", "GENE", "HGNC:1")
    assert interps[0].variant_interpretation.variation_descriptor.id == "789"

def test_variant_gene_context_set_when_gene_in_title():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "CA1", "clinvarVariantId": "", "clinvarVariantTitle": "NM_001(DSG2):c.1A>T"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "DSG2", "HGNC:3049")
    vd = interps[0].variant_interpretation.variation_descriptor
    assert vd.gene_context.value_id == "HGNC:3049"
    assert vd.gene_context.symbol == "DSG2"

def test_variant_gene_context_omitted_when_gene_not_in_title():
    ind = {
        "recessiveZygosity": None,
        "variants": [{"carId": "CA1", "clinvarVariantId": "", "clinvarVariantTitle": "NM_001(OTHER):c.1A>T"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "DSG2", "HGNC:3049")
    vd = interps[0].variant_interpretation.variation_descriptor
    assert vd.gene_context.value_id == ""  # not set

def test_variant_allelic_state_set_when_zygosity_present():
    ind = {
        "recessiveZygosity": "Homozygous",
        "variants": [{"carId": "CA1", "clinvarVariantId": "", "clinvarVariantTitle": "X"}],
    }
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "G", "HGNC:1")
    vd = interps[0].variant_interpretation.variation_descriptor
    assert vd.allelic_state.id == "GENO:0000136"

def test_variant_no_variants_returns_empty():
    ind = {"recessiveZygosity": None, "variants": []}
    interps = build_genomic_interpretations(ind, "pmid1", "P1", "G", "HGNC:1")
    assert interps == []
```

- [ ] **Step 6.2: Run to confirm failure**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v -k "variant"
```
Expected: FAIL — ImportError

- [ ] **Step 6.3: Implement `build_genomic_interpretations`**

Add to `src/gci_transformer.py`:

```python
def build_genomic_interpretations(individual: dict, pmid: str, label: str,
                                   gene_symbol: str, hgnc_id: str) -> list:
    """Build one GenomicInterpretation per variant in the individual."""
    subject_id = f"PMID_{pmid}:{label}"
    zyg = individual.get("recessiveZygosity")
    geno_id, geno_label = GENO_LOOKUP.get(zyg.lower(), GENO_FALLBACK) if zyg else (None, None)

    results = []
    for variant in individual.get("variants", []):
        var_id = variant.get("carId") or variant.get("clinvarVariantId", "")
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
```

- [ ] **Step 6.4: Run variant tests — all pass**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v -k "variant"
```
Expected: 6 tests PASSED

- [ ] **Step 6.5: Commit**

```bash
git add src/gci_transformer.py tests/test_gci_transformer.py
git commit -m "feat: add build_genomic_interpretations for variant mapping"
```

---

## Task 7: Full `build_phenopacket` Assembler

**Files:**
- Modify: `src/gci_transformer.py`
- Modify: `tests/test_gci_transformer.py`

Assembles all parts into a `pps2.Phenopacket`. Uses a mocked `OntologyManager`.

- [ ] **Step 7.1: Add failing tests**

Append to `tests/test_gci_transformer.py`:

```python
from gci_transformer import build_phenopacket

def _make_om_with_mondo():
    om = MagicMock()
    om.hpo_to_labeled_phenotype.side_effect = lambda h: {"id": h, "label": f"L:{h}"}
    om.mondo_lookup = {"MONDO:0016587": "arrhythmogenic right ventricular cardiomyopathy"}
    return om

def _base_individual():
    return {
        "label": "Test Patient",
        "uuid": "uuid-123",
        "sex": "Male",
        "is_proband": "Yes",
        "ageType": "Onset", "ageUnit": "Years", "ageValue": 30,
        "recessiveZygosity": None,
        "hpoIdInDiagnosis": ["HP:0001942"],
        "hpoIdInElimination": [],
        "diagnosis": [{"diseaseId": "MONDO_0016587"}],
        "variants": [],
    }

def test_build_phenopacket_id_format():
    # Input uses MONDO_0016587; ID should contain the underscore form
    pp = build_phenopacket(0, 1, "DSG2", "HGNC:3049", "12345", "Title", _base_individual(), "i", _make_om_with_mondo())
    assert pp.id == "0_1_DSG2_MONDO_0016587_12345_Test_Patient_i"

def test_build_phenopacket_diagnosis_uses_colon_form():
    # Diagnosis disease.id must use colon format even though ID uses underscore
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "12345", "Title", _base_individual(), "i", _make_om_with_mondo())
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0016587"

def test_build_phenopacket_subject_id():
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", _base_individual(), "f", _make_om_with_mondo())
    assert pp.subject.id == "PMID_99:Test Patient"

def test_build_phenopacket_freetext_disease_defaults_to_fallback():
    ind = _base_individual()
    ind["diagnosis"] = [{"diseaseId": "FREETEXT_abc"}]
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", ind, "i", _make_om_with_mondo())
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0700096"
    assert pp.interpretations[0].diagnosis.disease.label == "human disease"

def test_build_phenopacket_empty_diagnosis_defaults_to_fallback():
    ind = _base_individual()
    ind["diagnosis"] = []
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", ind, "i", _make_om_with_mondo())
    assert pp.interpretations[0].diagnosis.disease.id == "MONDO:0700096"

def test_build_phenopacket_interpretation_id():
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", _base_individual(), "i", _make_om_with_mondo())
    assert pp.interpretations[0].id == "99_Test_Patient_uuid-123"

def test_build_phenopacket_metadata_schema_version():
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", _base_individual(), "i", _make_om_with_mondo())
    assert pp.meta_data.phenopacket_schema_version == "2.0"

def test_build_phenopacket_metadata_resources_count():
    pp = build_phenopacket(0, 0, "DSG2", "HGNC:3049", "99", "T", _base_individual(), "i", _make_om_with_mondo())
    assert len(pp.meta_data.resources) == 4
    resource_ids = {r.id for r in pp.meta_data.resources}
    assert resource_ids == {"hp", "mondo", "geno", "eco"}
```

- [ ] **Step 7.2: Run to confirm failure**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v -k "build_phenopacket"
```
Expected: FAIL — ImportError

- [ ] **Step 7.3: Implement `build_phenopacket`**

Add to `src/gci_transformer.py`:

```python
def build_phenopacket(file_index: int, annotation_index: int,
                      gene_symbol: str, hgnc_id: str,
                      pmid: str, article_title: str,
                      individual: dict, tag: str, om) -> pps2.Phenopacket:
    """Assemble a complete Phenopacket from all parts."""
    label = individual.get("label", "Unknown")
    label_s = sanitize_label(label)
    uuid = individual.get("uuid", "no-uuid")

    # Disease
    diag_list = individual.get("diagnosis") or []
    if diag_list and diag_list[0].get("diseaseId"):
        raw_disease_id = diag_list[0]["diseaseId"]
    else:
        raw_disease_id = ""
    mondo_id = mondo_id_to_colon(raw_disease_id)
    # mondo_id for the Phenopacket ID uses underscore form
    mondo_id_for_pp_id = mondo_id.replace(":", "_")

    disease_label = om.mondo_lookup.get(mondo_id, FALLBACK_DISEASE_LABEL)

    # Phenopacket ID
    pp_id = f"{file_index}_{annotation_index}_{gene_symbol}_{mondo_id_for_pp_id}_{pmid}_{label_s}_{tag}"

    # MetaData
    ts = Timestamp()
    ts.GetCurrentTime()
    meta_data = pps2.MetaData(
        created=ts,
        resources=RESOURCE_METADATA,
        phenopacket_schema_version="2.0",
    )

    # Build parts
    subject = build_subject(pmid, label, individual)
    phenotypic_features = build_phenotypic_features(individual, pmid, article_title, om)
    genomic_interps = build_genomic_interpretations(individual, pmid, label, gene_symbol, hgnc_id)

    interpretation = pps2.Interpretation(
        id=f"{pmid}_{label_s}_{uuid}",
        progress_status=pps2.Interpretation.ProgressStatus.UNKNOWN_PROGRESS,
        diagnosis=pps2.Diagnosis(
            disease=pps2.OntologyClass(id=mondo_id, label=disease_label),
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
```

- [ ] **Step 7.4: Run all tests — all pass**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v
```
Expected: All tests PASSED (no failures). Should be ~35+ tests at this point.

- [ ] **Step 7.5: Commit**

```bash
git add src/gci_transformer.py tests/test_gci_transformer.py
git commit -m "feat: add build_phenopacket assembler"
```

---

## Task 8: Entry Point `gci_main.py`

**Files:**
- Create: `src/gci_main.py`

CLI args, JSONL reader loop, output writing. No unit tests needed here — covered by the smoke test in Task 9.

- [ ] **Step 8.1: Create `src/gci_main.py`**

```python
# src/gci_main.py
import json
import argparse
from pathlib import Path
from google.protobuf.json_format import MessageToJson

from utils.paths import get_project_root
from utils.logger import setup_logger
from utils.ontologies import OntologyManager
from gci_transformer import collect_individuals, passes_filter, build_phenopacket


def parse_args():
    root = get_project_root()
    parser = argparse.ArgumentParser(description="GCI Snapshot to Phenopacket Transformer")
    parser.add_argument("--input", "-i", type=Path,
                        default=root / "data" / "gci" / "gci_snapshot_2026-03-11.jsonl",
                        help="Path to input JSONL file")
    parser.add_argument("--output", "-o", type=Path,
                        default=root / "data" / "output",
                        help="Directory for output Phenopacket JSON files")
    parser.add_argument("--record", "-r", type=int, default=None,
                        help="0-based line index to process only one record (for testing)")
    return parser.parse_args()


def main():
    args = parse_args()
    root = get_project_root()
    logger = setup_logger(root / "logs")

    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        return

    args.output.mkdir(parents=True, exist_ok=True)

    try:
        om = OntologyManager(logger)
    except Exception as e:
        logger.error(f"Failed to initialize ontologies: {e}")
        return

    total_written = 0
    total_skipped = 0

    with open(args.input, encoding="utf-8") as f:
        for file_index, line in enumerate(f):
            if args.record is not None and file_index != args.record:
                continue

            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Line {file_index}: JSON parse error — {e}")
                continue

            gdm = record.get("resourceParent", {}).get("gdm", {})
            gene_symbol = gdm.get("gene", {}).get("symbol", "UNKNOWN")
            hgnc_id = gdm.get("gene", {}).get("hgncId", "")

            for annotation_index, annotation in enumerate(gdm.get("annotations", [])):
                pmid = annotation.get("article", {}).get("pmid", "UNKNOWN")
                title = annotation.get("article", {}).get("title", "")

                for individual, tag in collect_individuals(annotation):
                    if not passes_filter(individual):
                        total_skipped += 1
                        logger.debug(f"Skipped: {individual.get('label')} (is_proband={individual.get('is_proband')}, hpo={bool(individual.get('hpoIdInDiagnosis'))})")
                        continue

                    try:
                        pp = build_phenopacket(
                            file_index, annotation_index,
                            gene_symbol, hgnc_id,
                            pmid, title, individual, tag, om
                        )
                        # build_phenopacket always returns a Phenopacket
                        # (FREETEXT/missing disease falls back to MONDO:0700096)
                        out_path = args.output / f"{pp.id}.json"
                        with open(out_path, "w", encoding="utf-8") as out_f:
                            out_f.write(MessageToJson(pp, indent=2))
                        total_written += 1
                        logger.info(f"Saved: {out_path.name}")
                    except Exception as e:
                        logger.error(f"Line {file_index}, annotation {annotation_index}, individual '{individual.get('label')}': {e}")

    logger.info(f"Done. Written: {total_written}, Skipped: {total_skipped}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 8.2: Verify the file parses without errors**

```bash
pixi run python -c "import sys; sys.path.insert(0,'src'); import gci_main; print('OK')"
```
Expected: `OK`

- [ ] **Step 8.3: Commit**

```bash
git add src/gci_main.py
git commit -m "feat: add gci_main entry point with JSONL loop and CLI"
```

---

## Task 9: Pixi Config + End-to-End Smoke Test

**Files:**
- Modify: `pixi.toml`

- [ ] **Step 9.1: Add `gci_transform` task and `pytest` dependency to `pixi.toml`**

In `pixi.toml`, add `pytest` to `[pypi-dependencies]` and a new task:

```toml
[tasks]
data_transform = "python src/main.py"
gci_transform = "python src/gci_main.py"

[pypi-dependencies]
phenopackets = ">=2.0.2.post5, <3"
hpo3 = "*"
pytest = "*"
```

**Note on imports:** `pixi run python src/gci_main.py` runs from the project root, and Python automatically adds `src/` to `sys.path` when executing a script in that directory — so `from utils.paths import ...` resolves correctly with no extra configuration needed. This matches the existing `data_transform` task behaviour.

- [ ] **Step 9.2: Run smoke test — single record**

```bash
pixi run gci_transform --record 0 --output data/output/
```
Expected: Logger output showing ontologies loading, then at least one `Saved:` line (or a `Done. Written: N` line). No unhandled exceptions.

- [ ] **Step 9.3: Verify output file is valid JSON with expected structure**

```bash
ls data/output/*.json | head -3
python3 -c "
import json, glob
files = glob.glob('data/output/*.json')[:1]
if files:
    d = json.load(open(files[0]))
    print('id:', d.get('id'))
    print('subject:', d.get('subject', {}).get('id'))
    print('phenotypicFeatures:', len(d.get('phenotypicFeatures', [])))
    print('interpretations:', len(d.get('interpretations', [])))
"
```
Expected: `id`, `subject.id`, non-zero `phenotypicFeatures`, one `interpretations` entry.

- [ ] **Step 9.4: Run full test suite to confirm nothing is broken**

```bash
pixi run python -m pytest tests/test_gci_transformer.py -v
```
Expected: All tests PASSED

- [ ] **Step 9.5: Commit**

```bash
git add pixi.toml
git commit -m "feat: add gci_transform pixi run target"
```

---

## Future Work

### ClinVar API enrichment for `acmg_pathogenicity_classification`

**Do not implement now.**

For variants that have a `clinvarVariantId` but no `carId`, the ClinVar API
(`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=clinvar&id={clinvarVariantId}`)
returns the clinical significance (Pathogenic / Likely Pathogenic / VUS / etc.) and review status.

This could populate `VariantInterpretation.acmg_pathogenicity_classification`, which is currently
hardcoded to `NOT_PROVIDED`. A persistent JSON cache (same pattern as `data/cache/caid_cache.json`)
should be used to avoid redundant API calls across pipeline runs.

---

## Final Checklist

- [ ] All unit tests pass: `pixi run python -m pytest tests/ -v`
- [ ] Single-record smoke test runs without error: `pixi run gci_transform --record 0`
- [ ] Output JSON files have `id`, `subject`, `phenotypicFeatures`, `interpretations`, `metaData`
- [ ] Existing pipeline unaffected: `src/main.py`, `src/data_transformer.py`, `src/config.py` untouched