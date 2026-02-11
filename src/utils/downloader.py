import requests
import tarfile
import io
from pathlib import Path


def fetch_and_extract_data(url: str, extract_to: Path, logger):
    """Downloads a .tar.gz from a URL and extracts it to data/raw."""
    try:
        logger.info(f"Downloading data from: {url}")
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        # Used io.BytesIO to directly read the tar file downloaded from the memory , otherwise it will save the file on disk and reads it
        with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
            logger.info(f"Extracting files to {extract_to}...")
            tar.extractall(path=extract_to)

        logger.info("Data extraction successful.")
        return True
    except Exception as e:
        logger.error(f"Failed to download or extract data: {e}")
        return False