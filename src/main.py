import argparse
from pathlib import Path
from google.protobuf.json_format import MessageToJson

# Centralized path and project constants
from src.utils.paths import INPUT_DIR, OUTPUT_DIR, LOG_DIR
from src.utils.logger import setup_logger
from src.utils.data_downloader import fetch_and_extract_data
from src.utils.ontologies import OntologyManager
from src.data_transformer import PhenopacketTransformer, _sanitize
from src.config import FALLBACK_DISEASE_ID


def parse_args():
    """Defines CLI arguments with defaults pointing to the project structure."""
    parser = argparse.ArgumentParser(description="Genegraph to Phenopacket Transformer")

    # Path Arguments
    parser.add_argument("--input", "-i", type=Path, default=INPUT_DIR,
                        help="Directory containing JSON-LD files")
    parser.add_argument("--output", "-o", type=Path, default=OUTPUT_DIR,
                        help="Directory to save Phenopackets")

    # Debugging/Testing Argument
    parser.add_argument("--file", "-f", type=Path, default=None,
                        help="Path to a single JSON-LD file for targeted testing")

    # Download Argument
    parser.add_argument("--url", "-u", type=str, default=None,
                        help="URL to the genegraph .tar.gz data")

    # Custom Ontology Path Arguments
    parser.add_argument("--hp-path", type=Path, help="Local path to HPO .owl/.obo file")
    parser.add_argument("--mondo-path", type=Path, help="Local path to Mondo .owl/.obo file")
    parser.add_argument("--geno-path", type=Path, help="Local path to Geno .owl/.obo file")
    parser.add_argument("--hgnc-path", type=Path, help="Local path to HGNC .tsv file")

    return parser.parse_args()


def main():
    # 1. Setup
    args = parse_args()
    logger = setup_logger(LOG_DIR)
    logger.info("Starting Genegraph to Phenopacket Pipeline")

    # 2. Handle Data Acquisition
    if args.url:
        logger.info(f"Downloading data from: {args.url}")
        success = fetch_and_extract_data(args.url, args.input, logger)
        if not success:
            logger.error("Data acquisition failed. Exiting.")
            return

    # 3. Initialize Domain Resources
    try:
        # Collect custom ontology paths into a dictionary for the Manager
        custom_ontos = {}
        if args.hp_path: custom_ontos["hp"] = args.hp_path
        if args.mondo_path: custom_ontos["mondo"] = args.mondo_path
        if args.geno_path: custom_ontos["geno"] = args.geno_path
        if args.hgnc_path: custom_ontos["hgnc"] = args.hgnc_path

        # OntologyManager handles user paths, caching, and downloading internally
        om = OntologyManager(logger, custom_paths=custom_ontos)
        transformer = PhenopacketTransformer(om, logger)
    except Exception as e:
        logger.error(f"Resource Initialization Error: {e}")
        return

    # 4. Determine File Queue
    if args.file:
        if not args.file.exists():
            logger.error(f"Specified test file not found: {args.file}")
            return
        files_to_process = [args.file]
        logger.info(f"DEBUG MODE: Processing single file: {args.file.name}")
    else:
        files_to_process = list(args.input.glob("*.json"))
        if not files_to_process:
            logger.warning(f"No .json files found in {args.input}.")
            return
        logger.info(f"BATCH MODE: Found {len(files_to_process)} files in {args.input}")

    # 5. Execution Loop
    disease_segment = FALLBACK_DISEASE_ID.replace(":", "_")
    total_files_processed = 0
    total_probands = 0
    total_skipped_no_hpo = 0
    total_phenopackets_created = 0

    for file_path in files_to_process:
        try:
            results, stats = transformer.transform_file(file_path)

            total_probands += stats["total_probands"]
            total_skipped_no_hpo += stats["skipped_no_hpo"]

            if not results:
                logger.warning(f"No phenopackets generated from {file_path.name}")
                continue

            for gene_symbol, pmid, raw_label, pp in results:
                output_filename = (
                    f"{file_path.stem}_{gene_symbol}_{disease_segment}"
                    f"_{pmid}_{_sanitize(raw_label)}.json"
                )
                output_path = args.output / output_filename

                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(MessageToJson(pp, indent=2))

                total_phenopackets_created += 1

            total_files_processed += 1

        except Exception as e:
            logger.error(f"Failed to transform {file_path.name}: {str(e)}")

    logger.info("=" * 50)
    logger.info("Pipeline complete. Summary:")
    logger.info(f"  Files processed        : {total_files_processed} / {len(files_to_process)}")
    logger.info(f"  Potential probands     : {total_probands}")
    logger.info(f"  Skipped (no phenotypes): {total_skipped_no_hpo}")
    logger.info(f"  Phenopackets created   : {total_phenopackets_created}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
