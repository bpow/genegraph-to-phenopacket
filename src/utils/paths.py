from pathlib import Path


def _find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pixi.toml").exists():
            return parent
    raise FileNotFoundError("Could not find project root: no pixi.toml found in any parent directory")


PROJECT_ROOT = _find_project_root()

PATHS = {
    "INPUT":    PROJECT_ROOT / "data" / "gci",
    "OUTPUT":   PROJECT_ROOT / "data" / "output",
    "ONTOLOGY": PROJECT_ROOT / "data" / "ontologies",
    "LOGS":     PROJECT_ROOT / "logs",
}

for path in PATHS.values():
    path.mkdir(parents=True, exist_ok=True)

INPUT_DIR    = PATHS["INPUT"]
OUTPUT_DIR   = PATHS["OUTPUT"]
ONTOLOGY_DIR = PATHS["ONTOLOGY"]
LOG_DIR      = PATHS["LOGS"]