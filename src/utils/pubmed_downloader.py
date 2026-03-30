import json
import time
import requests
from src.utils.paths import PUBMED_CACHE_DIR

# NCBI allows 3 requests/sec without an API key — 0.4s keeps safely under that limit
_NCBI_RATE_LIMIT_SLEEP = 0.4

NCBI_ESUMMARY_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    "?db=pubmed&id={pmid}&retmode=json"
)
_CACHE_FILE = PUBMED_CACHE_DIR / "pmid_titles.json"

# In-memory cache loaded once at import time
_cache: dict = json.loads(_CACHE_FILE.read_text(encoding="utf-8")) if _CACHE_FILE.exists() else {}


def _save_cache():
    with open(_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(_cache, f, indent=2)


def get_pubmed_title(pmid: str, logger) -> str:
    """Return the article title for a PMID.
    Checks in-memory cache first; hits NCBI API only on a cache miss.
    Returns empty string if the title cannot be resolved.
    """
    if not pmid or pmid == "NA":
        return ""

    if pmid in _cache:
        logger.debug(f"PMID {pmid} title loaded from cache")
        return _cache[pmid]

    logger.info(f"Fetching PubMed title for PMID: {pmid}")
    time.sleep(_NCBI_RATE_LIMIT_SLEEP)
    try:
        response = requests.get(
            NCBI_ESUMMARY_URL.format(pmid=pmid), timeout=10
        )
        response.raise_for_status()
        data = response.json()
        title = data.get("result", {}).get(pmid, {}).get("title", "")
    except Exception as e:
        logger.warning(f"PubMed fetch failed for PMID {pmid}: {e}")
        return ""

    _cache[pmid] = title
    _save_cache()
    return title