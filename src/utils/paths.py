from pathlib import Path

# Define the root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Define the paths
PATHS = {
    "INPUT": PROJECT_ROOT / "data" / "input",
    "OUTPUT": PROJECT_ROOT / "data" / "output",
    "ONTOLOGY": PROJECT_ROOT / "data" / "ontologies",
    "LOGS": PROJECT_ROOT / "logs"
}

# 3. Create folders once on import
for path in PATHS.values():
    path.mkdir(parents=True, exist_ok=True)

# 4. Export constants
INPUT_DIR = PATHS["INPUT"]
OUTPUT_DIR = PATHS["OUTPUT"]
ONTOLOGY_DIR = PATHS["ONTOLOGY"]
LOG_DIR = PATHS["LOGS"]
