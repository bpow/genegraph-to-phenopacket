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
| `src/gci_phenopacket/ontologies.py` | OntologyManager: HPO + Mondo via oaklib sqlite adapter (auto-cached by oaklib) |
| `tests/test_gci_transformer.py` | Unit tests (over 60 tests across 4 test files) |
| `conftest.py` | Adds `src/` to sys.path for tests |
| `pyproject.toml` | Package metadata and `gci-transform` entry point |
| `data/gci/` | Input JSONL snapshots |
| `scripts/combine_yaml.sh` | Concatenate all output JSON phenopackets into a single YAML stream (requires `yq` on PATH) |

## Running the Pipeline

```bash
# Full run (prompts for --input if omitted)
pixi run gci_transform

# With explicit input (output written to ./gci_phenopackets/{gene_symbol}/ subdirs)
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl

# Custom output directory
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --output /path/to/output/

# Single record (0-based line index)
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --record 0

# Control log verbosity (DEBUG, INFO, WARNING, ERROR)
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --log-level DEBUG

# Preserve freetext disease terms instead of falling back to MONDO:0700096
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --preserve-freetext

# Write all files flat into the output dir (no per-gene subdirectories)
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --no-subdirs

# Pipe logs to a file
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl > run.log

# Pipe JSONL from stdin (reads /dev/stdin, log level fixed at WARNING)
zcat gene_validity_raw.jsonl.gz | pixi run stdin
grep '"gene":"BRCA1"' data/gci/snapshot.jsonl | pixi run stdin

# Once installed as a package (from any directory)
pip install .
gci-transform --input /path/to/snapshot.jsonl
```

## Combining Output into YAML

`pixi run combine_yaml` concatenates every `*.json` under `gci_phenopackets/` into a
single multi-document YAML stream. It requires [`yq`](https://github.com/mikefarah/yq)
to be installed and on `PATH` (not managed by Pixi — install separately, e.g.
`brew install yq`).

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
- Phenopacket ID format: `{gene_symbol}_{mondo_id}_{pmid}_{label_sanitized}_{individual_uuid}_{record_uuid}_{gdm_uuid}_{annotation_uuid}`
- `metadata.external_references` always contains `PMID:{pmid}` (with article title as description); when a provenance ID is present it is appended as a second entry (`gdm:...`)
- Output files are written to `{output_dir}/{gene_symbol}/{phenopacket_id}.json` by default; `--no-subdirs` / `-S` writes them flat into `{output_dir}/`
- Tag values: `individual` (direct), `family`, `group` — reflects nesting in the GCI annotation
- GENO zygosity terms are hardcoded in `GCI_TO_GENO` (4 terms + fallback `GENO:0000137`); unknown values log a warning
- `iter_individuals(annotation)` yields `GCIIndividualContext` (fields: `individual`, `individual_id`, `group_id`, `family_id`) for all nesting levels
- `resolve_disease(disease_id)` converts `MONDO_XXXXXXX` → `MONDO:XXXXXXX`; falls back for FREETEXT/empty
- Ontologies (HP, Mondo only) are loaded via oaklib's sqlite adapter (`sqlite:obo:hp`, `sqlite:obo:mondo`); oaklib manages download and caching automatically
- `OntologyManager.mondo_label(disease_id)` returns the Mondo label string or `None` if not found
- `--record N` jumps directly to line N via `itertools.islice` — does not scan the whole file

## Environment

- Package manager: [Pixi](https://pixi.sh)
- Python: 3.12
- Key dependencies: `phenopackets>=2.0.2.post5`, `oaklib`, `click`, `pytest`

## Conventions

- Do not auto-commit — always ask before committing
- Run all tests before committing any change
- Use `pixi run test` not bare `pytest`
- Update CLAUDE.md (Key Files table, Key Design Decisions) whenever files are moved, renamed, deleted, or their responsibilities change
