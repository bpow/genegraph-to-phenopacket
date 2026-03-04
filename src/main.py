import argparse
from pathlib import Path
from google.protobuf.json_format import MessageToJson

# Centralized path and project constants
from src.utils.paths import INPUT_DIR, OUTPUT_DIR, LOG_DIR
from src.utils.logger import setup_logger
from src.utils.data_downloader import fetch_and_extract_data
from src.utils.ontologies import OntologyManager
from src.data_transformer import PhenopacketTransformer


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
    file_processed_count = 0
    total_phenopackets_created = 0

    for file_path in files_to_process:
        try:
            # transform_file now returns a list of (patient_label, phenopacket_object)
            phenopackets = transformer.transform_file(file_path)

            if not phenopackets:
                logger.warning(f"No phenopackets generated from {file_path.name}")
                continue

            for patient_label, pp in phenopackets:
                # Naming convention: filename_patientlabel_pp.json
                output_filename = f"{file_path.stem}_{patient_label}_pp.json"
                output_path = args.output / output_filename

                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(MessageToJson(pp, indent=2))

                total_phenopackets_created += 1

            logger.info(f"Success: Processed {file_path.name} ({len(phenopackets)} phenopackets)")
            file_processed_count += 1

        except Exception as e:
            logger.error(f"Failed to transform {file_path.name}: {str(e)}")

    logger.info(f"Pipeline complete.")
    logger.info(f"Files processed: {file_processed_count}")
    logger.info(f"Total Phenopackets created: {total_phenopackets_created}")


if __name__ == "__main__":
    main()
