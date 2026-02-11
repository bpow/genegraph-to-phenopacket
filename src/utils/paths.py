import argparse
from pathlib import Path

# To get the root path for the user
def get_project_root() -> Path:
    return Path(__file__).parent.parent.parent.absolute()


def parse_args():
    root = get_project_root()
    parser = argparse.ArgumentParser(description="Genegraph to Phenopacket Transformer")

    # Path Arguments
    parser.add_argument("--input", "-i", type=Path, default=root / "data" / "input")
    parser.add_argument("--output", "-o", type=Path, default=root / "data" / "output")

    # Download Argument
    parser.add_argument(
        "--url", "-u",
        type=str,
        default=None,
        help="URL to the genegraph .tar.gz data"
    )

    return parser.parse_args()