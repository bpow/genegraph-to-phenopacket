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
