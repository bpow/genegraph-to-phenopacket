from pathlib import Path


def _find_project_root() -> Path:
    """Walk up from this file until we find pixi.toml — that's the project root."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pixi.toml").exists():
            return parent
    raise FileNotFoundError("Could not find project root: no pixi.toml found in any parent directory")


PROJECT_ROOT = _find_project_root()

# Define the paths
PATHS = {
    "INPUT":   PROJECT_ROOT / "data" / "input",
    "OUTPUT":  PROJECT_ROOT / "data" / "output",
    "ONTOLOGY": PROJECT_ROOT / "data" / "ontologies",
    "PUBMED":  PROJECT_ROOT / "data" / "pubmed_cache",
    "LOGS":    PROJECT_ROOT / "logs"
}

# 3. Create folders once on import
for path in PATHS.values():
    path.mkdir(parents=True, exist_ok=True)

# 4. Export constants
INPUT_DIR = PATHS["INPUT"]
OUTPUT_DIR = PATHS["OUTPUT"]
ONTOLOGY_DIR = PATHS["ONTOLOGY"]
PUBMED_CACHE_DIR = PATHS["PUBMED"]
LOG_DIR = PATHS["LOGS"]
