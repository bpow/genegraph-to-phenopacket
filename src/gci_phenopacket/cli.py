import json
import itertools
import logging
import sys
from pathlib import Path

import click
from google.protobuf.json_format import MessageToJson

from gci_phenopacket.ontologies import OntologyManager
from gci_phenopacket.transformer import GCITransformer

logger = logging.getLogger(__name__)


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
@click.option(
    "--log-level", "-l",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    show_default=True,
    help="Logging verbosity level",
)
@click.option(
    "--preserve-freetext", '-f',
    is_flag=True,
    default=False,
    help="Preserve freetext phenotypes instead of replacing with fallback 'human disease'",
)
@click.option(
    "--subdirs/--no-subdirs", "-s/-S",
    default=True,
    show_default=True,
    help="Create per-gene subdirectories under the output directory",
)
def main(input_path, output_path, record, log_level, preserve_freetext, subdirs):
    """Transform a ClinGen GCI snapshot (JSONL) into GA4GH Phenopacket v2 JSON files."""
    logging.basicConfig(
        level=log_level.upper(),
        stream=sys.stdout,
        format="%(levelname)s: %(message)s",
    )

    try:
        om = OntologyManager()
    except Exception as e:
        logging.error(f"Failed to initialize ontologies: {e}")
        raise SystemExit(1)
    
    transformer = GCITransformer(om, preserve_freetext=preserve_freetext)

    with open(input_path, encoding="utf-8") as f:
        if record is not None:
            file_iter = enumerate(itertools.islice(f, record, record + 1), start=record)
        else:
            file_iter = enumerate(f)

        for file_index, line in file_iter:
            line = line.strip()
            if not line:
                continue

            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Line {file_index}: JSON parse error — {e}")
                continue

            for pp in transformer.phenopackets_from_gci_record(rec):
                out_dir = output_path / pp.id.split('_', 1)[0] if subdirs else output_path
                out_dir.mkdir(parents=True, exist_ok=True)

                out_path = out_dir / f"{pp.id}.json"
                with open(out_path, "w", encoding="utf-8") as out_f:
                    out_f.write(MessageToJson(pp, indent=2))
                logger.info(f"Saved: {out_path.name}")
        
    logger.info(
        f"Done. Written: {transformer.stats.phenopackets_created} | "
        f"Skipped (no HPO): {transformer.stats.skipped_no_hpo}"
    )


if __name__ == "__main__":
    main()
