import requests
import logging

logger = logging.getLogger("GenegraphTransform")

def get_pubmed_article_info(proband_id, source_url):
    """Fetches PMID metadata from NCBI."""
    if not (source_url and "pubmed.ncbi.nlm.nih.gov" in source_url):
        return None, None
    pmid = source_url.strip('/').split('/')[-1]
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json"
    try:
        data = requests.get(url, timeout=10).json()
        res = data.get("result", {}).get(pmid, {})
        return res.get('title'), res.get("sortfirstauthor")
    except Exception as e:
        logger.error(f"PubMed error for {pmid}: {e}")
        return None, None