import json
from google.protobuf.json_format import MessageToJson
from utils.paths import parse_args, get_project_root
from utils.logger import setup_logger
from utils.downloader import fetch_and_extract_data
from utils.ontologies import OntologyManager
from data_transformer import PhenopacketTransformer

def main():
    args = parse_args()
    root = get_project_root()
    logger = setup_logger(root / "logs")

    # 1. Handle Data Download if URL is provided
    if args.url:
        logger.info("Download URL detected.")
        success = fetch_and_extract_data(args.url, args.input, logger)
        if not success:
            logger.error("Stopping: Data download failed.")
            return

    # 2. Initialize Ontologies (Now using Pronto for Mondo & Geno)
    try:
        om = OntologyManager(logger)
        transformer = PhenopacketTransformer(om, logger)
    except Exception as e:
        logger.error(f"Failed to initialize ontologies: {e}")
        return

    # 3. Process the Files
    input_files = list(args.input.glob("*.json"))
    if not input_files:
        logger.warning(f"No .json files found in {args.input}. Check your download/path.")
        return

    logger.info(f"Starting transformation of {len(input_files)} files...")
    for file_path in input_files:
        try:
            phenopacket = transformer.transform_file(file_path)
            if phenopacket:
                output_path = args.output / f"{file_path.stem}_pp.json"
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(MessageToJson(phenopacket, indent=2))
                logger.info(f"Saved: {output_path.name}")
        except Exception as e:
            logger.error(f"Error in {file_path.name}: {e}")

    logger.info("Transformation pipeline complete.")

if __name__ == "__main__":
    main()