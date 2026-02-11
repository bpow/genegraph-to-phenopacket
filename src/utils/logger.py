import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_logger(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = logging.getLogger("GenegraphTransform")
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_dir / f"run_{timestamp}.log")
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))

    logger.addHandler(file_handler);
    logger.addHandler(console_handler)
    return logger