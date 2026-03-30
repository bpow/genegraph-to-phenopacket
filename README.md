# ClinGen Genegraph to Phenopacket Data Transformer

Transforms individual ClinGen GCI JSON-LD files (one per gene-disease curation) into
**GA4GH Phenopackets v2**. Only probands with at least one HPO phenotype are converted.

## Project Structure

```
src/
  main.py                  — CLI entry point and execution loop
  data_transformer.py      — Core JSON-LD → Phenopacket logic
  config.py                — Resource metadata and disease fallback constants
  utils/
    paths.py               — Project root discovery (anchored to pixi.toml) and path constants
    ontologies.py          — Loads and caches HPO, Mondo, Geno (pronto) and HGNC (TSV)
    pubmed_downloader.py   — Fetches and caches PubMed article titles (NCBI esummary API)
    data_downloader.py     — Downloads and extracts input data from a .tar.gz URL
    logger.py              — Structured file + console logging
data/
  input/                   — Input JSON-LD files (one per gene-disease curation)
  output/                  — Generated Phenopacket JSON files
  ontologies/              — Cached ontology files (hp.obo, mondo.obo, geno.obo, hgnc.tsv)
  pubmed_cache/            — Cached PubMed titles (pmid_titles.json)
tests/                     — pytest test suite
plan/                      — Design and implementation planning documents
```

## Output Filename Convention

```
{file_stem}_{gene_symbol}_MONDO_0700096_{pmid}_{proband_label}.json
```

Example: `gg_3e60939f_ACVR1_MONDO_0700096_16642017_A_II_I.json`

## Requirements

- [Pixi](https://pixi.sh) for environment management

## Getting Started

```bash
# Install dependencies
pixi install

# Run on a directory of JSON-LD files (default: data/input/)
pixi run data_transform

# Run on a single file (useful for testing)
pixi run data_transform --file data/input/<filename>.json

# Download input data from a URL first, then transform
pixi run data_transform --url <url_to_tar_gz>

# Run tests
pixi run test
```

## CLI Options

| Flag | Description |
|------|-------------|
| `--input` / `-i` | Directory containing JSON-LD input files (default: `data/input/`) |
| `--output` / `-o` | Directory for output Phenopacket files (default: `data/output/`) |
| `--file` / `-f` | Process a single JSON-LD file |
| `--url` / `-u` | Download and extract input data from a `.tar.gz` URL |
| `--hp-path` | Custom local path to HPO `.obo`/`.owl` file |
| `--mondo-path` | Custom local path to Mondo `.obo`/`.owl` file |
| `--geno-path` | Custom local path to Geno `.obo`/`.owl` file |
| `--hgnc-path` | Custom local path to HGNC `.tsv` file |

## Ontology & Reference Data Caching

On first run, the pipeline downloads and caches:
- **HPO, Mondo, Geno** — saved as `.obo` files in `data/ontologies/`
- **HGNC gene symbols** — saved as `data/ontologies/hgnc.tsv`
- **PubMed titles** — saved as `data/pubmed_cache/pmid_titles.json`

Subsequent runs use the cached versions. Custom paths via CLI flags bypass the cache.

## Phenopacket Details

- **Disease** — always `MONDO:0700096 / human disease`
- **Variant ID** — `caid:{CAR_ID}` from ClinGen Allele Registry; falls back to allele registry API if label is missing
- **Gene context** — gene symbol extracted from variant HGVS label; HGNC ID resolved from cached TSV
- **Evidence** — `ECO:0000304` with PMID reference and article title
- **Proband filter** — probands with no HPO terms are skipped and counted in the summary log