from pathlib import Path


def get_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pixi.toml").exists():
            return parent
    raise FileNotFoundError("Could not find project root: no pixi.toml found in any parent directory")
