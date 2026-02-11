# ClinGen Genegraph to Phenopacket Data Transformer

This pipeline automates the transformation of Genegraph JSON-LD data into standardized **GA4GH Phenopackets (v2)**.

## Project Structure
- `src/main.py`: Entry point for the transformation loop.
- `src/data_transformer.py`: Core logic for mapping JSON-LD to Phenopacket schema.
- `src/utils/ontologies.py`: Manages HPO, Mondo, and Geno ontologies via `pronto` and `pyhpo`.
- `src/utils/external_data.py`: Fetches publication metadata from NCBI PubMed API.
- `data/`: Local storage for input JSON-LD and output Phenopackets.

## Requirements
- [Pixi](https://pixi.sh) for environment management.

## Getting Started
1. Install dependencies: `pixi install`
2. Run the transformation: `pixi run data_transform`