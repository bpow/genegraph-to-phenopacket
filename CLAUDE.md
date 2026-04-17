# CLAUDE.md — GCI to Phenopacket Pipeline

## Project Overview

This pipeline reads a ClinGen GCI snapshot (JSONL format) and produces GA4GH Phenopacket v2 JSON files — one per qualifying individual with HPO terms.

**Active branch:** `gci-to-phenopacket-2026-03-cc`
**Remote:** `github.com/bpow/genegraph-to-phenopacket`

## Key Files

| File | Purpose |
|---|---|
| `src/gci_phenopacket/cli.py` | Click CLI entry point, JSONL loop, output writing |
| `src/gci_phenopacket/transformer.py` | All GCI → Phenopacket field mapping logic |
| `src/gci_phenopacket/utils/ontologies.py` | OntologyManager: HPO + Mondo via pronto, disk cache (GENO hardcoded) |
| `src/gci_phenopacket/utils/paths.py` | `CACHE_DIR` via platformdirs |
| `tests/test_gci_transformer.py` | Unit tests (over 60 tests across 4 test files) |
| `conftest.py` | Adds `src/` to sys.path for tests |
| `pyproject.toml` | Package metadata and `gci-transform` entry point |
| `data/gci/` | Input JSONL snapshots |

## Running the Pipeline

```bash
# Full run (prompts for --input if omitted)
pixi run gci_transform

# With explicit input (output defaults to ./gci_phenopackets/ in cwd)
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl

# Custom output directory
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --output /path/to/output/

# Single record (0-based line index)
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --record 0

# Pipe logs to a file
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl > run.log

# Once installed as a package (from any directory)
pip install .
gci-transform --input /path/to/snapshot.jsonl
```

## Running Tests

```bash
pixi run test
```

## Design Docs

- **Spec:** `docs/superpowers/specs/2026-03-25-gci-to-phenopacket-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-25-gci-to-phenopacket.md`

## Key Design Decisions

- Any individual with at least one HPO term is converted — `is_proband` status is not checked
- GCI stores HPO terms as `"Label (HP:XXXXXXX)"` — `extract_hpo_id()` strips the label before lookup
- `FREETEXT_` or missing disease IDs fall back to `MONDO:0700096` ("human disease")
- Vital status is only set when `ageType == "Death"` — omitted otherwise
- Evidence code: `ECO:0000304` ("author statement supported by traceable reference used in manual assertion")
- Variant IDs are prefixed: `caid:CA123` or `clinvar:789`
- Phenopacket ID format: `{record_uuid}_{annotation_uuid}_{gene_symbol}_{mondo_id}_{pmid}_{label_sanitized}_{tag}`
- Tag values: `individual` (direct), `family`, `group` — reflects nesting in the GCI annotation
- GENO zygosity terms are hardcoded in `GCI_TO_GENO` (4 terms + fallback `GENO:0000137`); unknown values log a warning
- `iter_individuals(annotation)` yields `(individual_dict, tag)` for all nesting levels
- `resolve_disease(disease_id)` converts `MONDO_XXXXXXX` → `MONDO:XXXXXXX`; falls back for FREETEXT/empty
- Ontologies (HP, Mondo only) are cached on first download to the platform cache dir (e.g. `~/Library/Caches/gci-phenopacket/ontologies/` on macOS)
- `--record N` jumps directly to line N via `itertools.islice` — does not scan the whole file

## Environment

- Package manager: [Pixi](https://pixi.sh)
- Python: 3.12
- Key dependencies: `phenopackets>=2.0.2.post5`, `pronto`, `click`, `platformdirs`, `pytest`

## Conventions

- Do not auto-commit — always ask before committing
- Run all tests before committing any change
- Use `pixi run test` not bare `pytest`
