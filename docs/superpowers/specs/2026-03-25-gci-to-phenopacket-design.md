# GCI Snapshot → Phenopacket v2 Pipeline Design

**Date:** 2026-03-25
**Branch:** `gci-to-phenopacket-2026-03-cc`
**Status:** Approved

---

## Overview

A standalone pipeline that reads a GCI snapshot JSONL file (one GDM record per line) and produces GA4GH Phenopacket v2 JSON files — one per qualifying proband individual. This pipeline runs independently of the existing Genegraph JSON-LD pipeline; no existing code is modified.

---

## Input Format

**File:** `gci_snapshot_YYYY-MM-DD.jsonl`
**Format:** Newline-delimited JSON (JSONL). Each line is one GDM record.

**Key paths per GDM record:**
```
resourceParent.gdm.gene.symbol          → gene symbol (e.g. "DSG2")
resourceParent.gdm.gene.hgncId          → HGNC ID (e.g. "HGNC:3049")
resourceParent.gdm.annotations[]        → list of evidence annotations
  .article.pmid                         → PubMed ID
  .article.title                        → article title
  .individuals[]                        → direct individuals (tag: "i")
  .families[].individualIncluded[]      → family individuals (tag: "f")
  .groups[].individualIncluded[]        → group individuals (tag: "g")
  .groups[].familyIncluded[]
      .individualIncluded[]             → group-family individuals (tag: "g")
```

**Per-individual key fields:**
```
label                    → display name / identifier
sex                      → "Male", "Female", or other
is_proband               → string "Yes" or "No" (not boolean)
hpoIdInDiagnosis[]       → HP term IDs (included phenotypes)
hpoIdInElimination[]     → HP term IDs (excluded phenotypes)
ageType                  → "Onset", "Death", "Diagnosis", "Report"
ageUnit                  → "Years", "Months", "Days", "Weeks", "Weeks gestation", "Hours"
ageValue                 → numeric
recessiveZygosity        → string or null (e.g. "Homozygous", "TwoTrans")
diagnosis[]              → list of disease objects (use first entry)
  .diseaseId             → "MONDO_XXXXXXX" or "FREETEXT_..." format
uuid                     → individual's unique identifier
variants[]
  .carId                 → ClinGen Allele Registry ID (preferred)
  .clinvarVariantId      → ClinVar ID (fallback)
  .clinvarVariantTitle   → variant label string
```

---

## Individual Filtering Rules

An individual is processed **only if both conditions are met:**
1. `is_proband == "Yes"` (string comparison, not boolean)
2. At least one of `hpoIdInDiagnosis` or `hpoIdInElimination` is non-empty

All others are silently skipped with a debug log message.

---

## New Files

| File | Purpose |
|---|---|
| `src/gci_main.py` | Entry point: CLI args, JSONL reader loop, output writer |
| `src/gci_transformer.py` | All GCI → Phenopacket field mapping and building logic |

**Reused (unchanged):**
- `src/utils/ontologies.py` — `OntologyManager` for HPO + Mondo label lookups
- `src/utils/logger.py`
- `src/utils/paths.py`

---

## CLI Interface

```bash
# Process full JSONL file
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --output data/output/

# Process single record by 0-based line index (for testing)
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --output data/output/ --record 5
```

A new `gci_transform` run target is added to `pixi.toml`.

---

## Processing Flow

```
for file_index, line in enumerate(jsonl_file):
    gdm = line["resourceParent"]["gdm"]
    gene_symbol = gdm["gene"]["symbol"]
    hgnc_id = gdm["gene"]["hgncId"]

    for annotation_index, annotation in enumerate(gdm["annotations"]):
        pmid = annotation["article"]["pmid"]
        title = annotation["article"]["title"]

        individuals = collect_individuals(annotation)
        # yields (individual_dict, tag) where tag in {"i", "f", "g"}

        for individual, tag in individuals:
            if not passes_filter(individual):
                continue
            # build_phenopacket returns None if individual has FREETEXT_ disease ID
            phenopacket = build_phenopacket(file_index, annotation_index,
                                            gene_symbol, hgnc_id,
                                            pmid, title, individual, tag)
            if phenopacket:
                write_output(phenopacket)
```

---

## Complete Field Mapping

### Phenopacket (top level)

| Field | Value |
|---|---|
| `id` | `{gene_symbol}_{mondo_id}_{pmid}_{individual_label_sanitized}_{record_uuid}_{gdm_uuid}_{annotation_uuid}_{individual_uuid}` |
| `meta_data.resources` | HPO, Mondo, GENO, and ECO resource entries (see below) |
| `meta_data.phenopacket_schema_version` | `"2.0"` |
| `meta_data.created` | current UTC timestamp: `ts = Timestamp(); ts.GetCurrentTime()` |

**ID construction notes:**
- `individual_label_sanitized`: spaces replaced with `_`, colons with `-`
- `mondo_id` is taken from `individual.diagnosis[0].diseaseId` with `:` replaced by `_` (e.g. `MONDO_0016587`)
- UUIDs (`record_uuid`, `gdm_uuid`, `annotation_uuid`, `individual_uuid`) come from the GCI `uuid`/`PK` fields; fall back to `"no-uuid"` when absent
- The output filename is `{phenopacket_id}.json` using the same sanitized ID

### Subject (Individual)

| Field | Source / Value |
|---|---|
| `id` | `PMID_{pmid}:{individual_label}` |
| `sex` | mapped: `"Male"` → `Sex.MALE`, `"Female"` → `Sex.FEMALE`, else `Sex.UNKNOWN_SEX` |
| `time_at_last_encounter` | `TimeElement(age=Age(iso8601duration=...))` built from `ageValue` + `ageUnit` → ISO 8601 (e.g. `P41Y`, `P6M`, `P5D`) |
| `vital_status` | `VitalStatus(status=VitalStatus.Status.DECEASED)` if `ageType == "Death"`, else `ALIVE` |

### PhenotypicFeature (one per HP term)

| Field | Source / Value |
|---|---|
| `type.id` | HP ID from `hpoIdInDiagnosis[]` or `hpoIdInElimination[]` |
| `type.label` | looked up via `OntologyManager.hpo_to_labeled_phenotype()` |
| `excluded` | `False` for diagnosis terms; `True` for elimination terms |
| `evidence[0].reference.id` | `PMID:{pmid}` |
| `evidence[0].reference.description` | `article.title` |
| `evidence[0].evidence_code` | `OntologyClass(id="ECO:0006017", label="author statement from published clinical study used in manual assertion")` |

### Interpretation

Create **exactly one `Interpretation` per individual**. All `GenomicInterpretation` objects for that individual's variants are collected into `Interpretation.diagnosis.genomic_interpretations`.

| Field | Source / Value |
|---|---|
| `id` | `{pmid}_{individual_label_sanitized}_{individual_uuid}` |
| `progress_status` | `Interpretation.ProgressStatus.UNKNOWN_PROGRESS` |

### Diagnosis

| Field | Source / Value |
|---|---|
| `disease.id` | `individual.diagnosis[0].diseaseId` → replace first `_` with `:` → `MONDO:XXXXXXX` |
| `disease.label` | looked up via `OntologyManager` (Mondo) |

**Edge cases:**
- If `individual.diagnosis` is empty, `diagnosis[0]` has no `diseaseId` key, or `diseaseId` starts with `FREETEXT_` → default to `MONDO:0700096` (label: `"human disease"`), log a warning
- Use only the first entry in `diagnosis[]` if multiple exist

**Mondo label lookup:** Use `ontology_manager.mondo_lookup.get(mondo_id, "")` where `mondo_id` is in colon format (e.g. `"MONDO:0016587"`). If the label is empty string (term not found), use `""` as the label and log a warning.

### GenomicInterpretation (one per variant)

| Field | Source / Value |
|---|---|
| `subject_or_biosample_id` | `PMID_{pmid}:{individual_label}` |
| `interpretation_status` | `GenomicInterpretation.InterpretationStatus.UNKNOWN_STATUS` |

### VariantInterpretation

| Field | Source / Value |
|---|---|
| `acmg_pathogenicity_classification` | `AcmgPathogenicityClassification.NOT_PROVIDED` |
| `therapeutic_actionability` | `TherapeuticActionability.UNKNOWN_ACTIONABILITY` |

### VariationDescriptor

| Field | Source / Value |
|---|---|
| `id` | `variant.carId` if non-empty, else `variant.clinvarVariantId` |
| `label` | `variant.clinvarVariantTitle` |
| `gene_context.value_id` | `gene.hgncId` — only if `gene_symbol` appears in `clinvarVariantTitle` |
| `gene_context.symbol` | `gene.symbol` — only if matched above; otherwise `gene_context` is omitted |
| `molecule_context` | `pps2.MoleculeContext.unspecified_molecule_context` |
| `allelic_state` | built from `individual.recessiveZygosity` via `geno_lookup` if non-null; omitted if null |

---

## Enum & Literal Mapping Notes

All protobuf enum values must use their exact Python SDK form. A dedicated mapping layer in `gci_transformer.py` handles all conversions:

| Concept | Exact value |
|---|---|
| Sex fallback | `pps2.Sex.UNKNOWN_SEX` |
| Vital status alive | `pps2.VitalStatus.Status.ALIVE` |
| Vital status deceased | `pps2.VitalStatus.Status.DECEASED` |
| Molecule context | `pps2.MoleculeContext.unspecified_molecule_context` |
| Progress status | `pps2.Interpretation.ProgressStatus.UNKNOWN_PROGRESS` |
| Interpretation status | `pps2.GenomicInterpretation.InterpretationStatus.UNKNOWN_STATUS` |
| ACMG classification | `pps2.AcmgPathogenicityClassification.NOT_PROVIDED` |
| Therapeutic actionability | `pps2.TherapeuticActionability.UNKNOWN_ACTIONABILITY` |

**Age ISO 8601 conversion:**
- `"Years"` → `P{n}Y`
- `"Months"` → `P{n}M`
- `"Weeks"` → `P{n}W`
- `"Days"` → `P{n}D`
- `"Hours"` → `PT{n}H`
- `"Weeks gestation"` → use `TimeElement(gestational_age=GestationalAge(weeks=int(ageValue), days=0))`; if `ageValue` is fractional, take `floor(ageValue)` as weeks and `round(frac * 7)` as days, log a warning
- Missing or unrecognized `ageUnit`, or missing `ageValue` → omit `time_at_last_encounter`, log a warning

**MONDO ID conversion:**
- `"MONDO_0016587"` → `"MONDO:0016587"` (replace first `_` after `MONDO` with `:`)
- `"FREETEXT_..."` → skip individual, log warning

**Zygosity (`geno_lookup`) key normalization:**
- Lowercase the `recessiveZygosity` value before lookup (e.g. `"Homozygous"` → `"homozygous"`)
- Static lookup table defined in `gci_transformer.py` mapping to `(id, label)` tuples:
  ```python
  GENO_LOOKUP = {
      "homozygous":   ("GENO:0000136", "homozygous"),
      "heterozygous": ("GENO:0000135", "heterozygous"),
      "twotrans":     ("GENO:0000402", "compound heterozygous"),
      "hemizygous":   ("GENO:0000134", "hemizygous"),
  }
  ```
- Use as: `geno_id, geno_label = GENO_LOOKUP.get(zyg.lower(), ("GENO:0000137", "unspecified zygosity"))`
- If lowercased value not in table → use fallback `("GENO:0000137", "unspecified zygosity")`, log a warning

**Interpretation `id` field:**
- Use `individual.uuid` as the resource identifier component: `{pmid}_{individual_label_sanitized}_{individual_uuid}`

**`meta_data.resources` — four entries required:**
```python
[
  {"id": "hp",   "name": "Human Phenotype Ontology",       "namespace_prefix": "HP",    "url": "http://purl.obolibrary.org/obo/hp.owl"},
  {"id": "mondo","name": "Mondo Disease Ontology",         "namespace_prefix": "MONDO", "url": "http://purl.obolibrary.org/obo/mondo.owl"},
  {"id": "geno", "name": "Genotype Ontology",              "namespace_prefix": "GENO",  "url": "http://purl.obolibrary.org/obo/geno.owl"},
  {"id": "eco",  "name": "Evidence and Conclusion Ontology","namespace_prefix": "ECO",  "url": "https://evidenceontology.org/repo/ECO.owl",
   "iri_prefix": "http://purl.obolibrary.org/obo/ECO_"},
]
```

---

## Output

- One `.json` file per qualifying individual
- Filename: `{phenopacket_id}.json` (same as `Phenopacket.id` field)
- Written to `--output` directory
- Format: `MessageToJson(phenopacket, indent=2)` via `google.protobuf.json_format`

---

## What Is Not Changed

- `src/main.py` — untouched
- `src/data_transformer.py` — untouched
- `src/config.py` — untouched
- All existing input/output data — untouched
- No PubMed API calls in the new pipeline