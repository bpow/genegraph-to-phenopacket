# CLAUDE.md — GCI to Phenopacket Pipeline

## Project Overview

This pipeline reads a ClinGen GCI snapshot (JSONL format) and produces GA4GH Phenopacket v2 JSON files — one per qualifying proband individual.

**Active branch:** `gci-to-phenopacket-2026-03-cc`
**Remote:** `github.com/bpow/genegraph-to-phenopacket`

## Key Files

| File | Purpose |
|---|---|
| `src/gci_main.py` | CLI entry point, JSONL loop, output writing |
| `src/gci_transformer.py` | All GCI → Phenopacket field mapping logic |
| `src/utils/ontologies.py` | OntologyManager: HPO (pyhpo) + Mondo (pronto) lookups |
| `src/utils/logger.py` | Logging setup |
| `src/utils/paths.py` | `get_project_root()` only |
| `tests/test_gci_transformer.py` | Unit tests (56 tests) |
| `conftest.py` | Adds `src/` to sys.path for tests |
| `data/gci/` | Input JSONL snapshots |
| `data/output/gci_phenopackets/` | Generated Phenopacket JSON files |

## Running the Pipeline

```bash
# Full run
pixi run gci_transform

# Single record (0-based line index)
pixi run gci_transform --record 0

# Custom paths
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --output data/output/gci_phenopackets/
```

## Running Tests

```bash
pixi run python -m pytest tests/ -v
```

## Design Docs

- **Spec:** `docs/superpowers/specs/2026-03-25-gci-to-phenopacket-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-25-gci-to-phenopacket.md`

## Key Design Decisions

- Only probands with at least one HPO term are converted (`is_proband == "Yes"` + non-empty `hpoIdInDiagnosis` or `hpoIdInElimination`)
- GCI stores HPO terms as `"Label (HP:XXXXXXX)"` — `extract_hpo_id()` strips the code before lookup
- FREETEXT_ or missing disease IDs fall back to `MONDO:0700096` ("human disease")
- Vital status is only set when `ageType == "Death"` — omitted otherwise
- Evidence code: `ECO:0000304` ("author statement supported by traceable reference used in manual assertion")
- Variant IDs are prefixed: `caid:CA123` or `clinvar:789`
- Phenopacket ID format: `{file_index}_{annotation_index}_{gene_symbol}_{mondo_id}_{pmid}_{label_sanitized}_{tag}`

## Environment

- Package manager: [Pixi](https://pixi.sh)
- Python: 3.12
- Key dependencies: `phenopackets>=2.0.2.post5`, `pyhpo`, `pronto`, `pytest`

## Conventions

- Do not auto-commit — always ask before committing
- Run all tests before committing any change
- Use `pixi run python -m pytest` not bare `pytest`