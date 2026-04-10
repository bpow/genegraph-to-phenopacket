import json
from pathlib import Path

import click
from google.protobuf.json_format import MessageToJson

from gci_phenopacket.utils.logger import setup_logger
from gci_phenopacket.utils.ontologies import OntologyManager
from gci_phenopacket.transformer import collect_individuals, passes_filter, build_phenopacket


@click.command()
@click.option(
    "--input", "-i", "input_path",
    prompt="Path to input JSONL file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to input JSONL file",
)
@click.option(
    "--output", "-o", "output_path",
    type=click.Path(path_type=Path),
    default=lambda: Path.cwd() / "gci_phenopackets",
    show_default="./gci_phenopackets",
    help="Directory for output Phenopacket JSON files",
)
@click.option(
    "--record", "-r",
    type=int,
    default=None,
    help="0-based line index to process a single record (for testing)",
)
def main(input_path, output_path, record):
    """Transform a ClinGen GCI snapshot (JSONL) into GA4GH Phenopacket v2 JSON files."""
    logger = setup_logger()

    output_path.mkdir(parents=True, exist_ok=True)

    try:
        om = OntologyManager(logger)
    except Exception as e:
        logger.error(f"Failed to initialize ontologies: {e}")
        raise SystemExit(1)

    total_written = 0
    skipped_no_hpo = 0

    with open(input_path, encoding="utf-8") as f:
        for file_index, line in enumerate(f):
            if record is not None and file_index != record:
                continue

            line = line.strip()
            if not line:
                continue

            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Line {file_index}: JSON parse error — {e}")
                continue

            gdm = rec.get("resourceParent", {}).get("gdm", {})
            gene_symbol = gdm.get("gene", {}).get("symbol", "UNKNOWN")
            hgnc_id = gdm.get("gene", {}).get("hgncId", "")

            for annotation_index, annotation in enumerate(gdm.get("annotations") or []):
                pmid = annotation.get("article", {}).get("pmid", "UNKNOWN")
                title = annotation.get("article", {}).get("title", "")

                for individual, tag in collect_individuals(annotation):
                    if not passes_filter(individual):
                        skipped_no_hpo += 1
                        logger.debug(f"Skipped (no HPO): {individual.get('label')} — PMID {pmid}")
                        continue

                    try:
                        pp = build_phenopacket(
                            file_index, annotation_index,
                            gene_symbol, hgnc_id,
                            pmid, title, individual, tag, om,
                        )
                        out_path = output_path / f"{pp.id}.json"
                        with open(out_path, "w", encoding="utf-8") as out_f:
                            out_f.write(MessageToJson(pp, indent=2))
                        total_written += 1
                        logger.info(f"Saved: {out_path.name}")
                    except Exception as e:
                        logger.error(
                            f"Line {file_index}, annotation {annotation_index}, "
                            f"individual '{individual.get('label')}': {e}"
                        )

    logger.info(
        f"Done. Written: {total_written} | "
        f"Skipped (no HPO): {skipped_no_hpo}"
    )


if __name__ == "__main__":
    main()
