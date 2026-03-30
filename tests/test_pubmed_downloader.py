"""Tests for src/utils/pubmed_downloader.py"""
import json
import pytest
from unittest.mock import patch, MagicMock


def _make_ncbi_response(pmid, title):
    return {"result": {pmid: {"title": title}}}


def test_returns_empty_for_na_pmid():
    import src.utils.pubmed_downloader as mod
    logger = MagicMock()
    assert mod.get_pubmed_title("NA", logger) == ""


def test_returns_empty_for_none_pmid():
    import src.utils.pubmed_downloader as mod
    logger = MagicMock()
    assert mod.get_pubmed_title(None, logger) == ""


def test_returns_cached_title_without_hitting_api(tmp_path, monkeypatch):
    import src.utils.pubmed_downloader as mod

    # Pre-populate the in-memory cache
    monkeypatch.setitem(mod._cache, "12345", "Cached Title")
    logger = MagicMock()

    with patch("src.utils.pubmed_downloader.requests.get") as mock_get:
        result = mod.get_pubmed_title("12345", logger)

    assert result == "Cached Title"
    mock_get.assert_not_called()


def test_fetches_from_api_on_cache_miss(monkeypatch):
    import src.utils.pubmed_downloader as mod

    # Ensure pmid not in cache
    monkeypatch.setattr(mod, "_cache", {})
    logger = MagicMock()

    mock_resp = MagicMock()
    mock_resp.json.return_value = _make_ncbi_response("99999", "Fetched Title")

    with patch("src.utils.pubmed_downloader.requests.get", return_value=mock_resp) as mock_get:
        with patch("src.utils.pubmed_downloader._save_cache"):
            result = mod.get_pubmed_title("99999", logger)

    assert result == "Fetched Title"
    mock_get.assert_called_once()


def test_saves_fetched_title_to_cache(monkeypatch):
    import src.utils.pubmed_downloader as mod

    cache = {}
    monkeypatch.setattr(mod, "_cache", cache)
    logger = MagicMock()

    mock_resp = MagicMock()
    mock_resp.json.return_value = _make_ncbi_response("11111", "New Title")

    with patch("src.utils.pubmed_downloader.requests.get", return_value=mock_resp):
        with patch("src.utils.pubmed_downloader._save_cache") as mock_save:
            mod.get_pubmed_title("11111", logger)

    assert cache["11111"] == "New Title"
    mock_save.assert_called_once()


def test_returns_empty_string_on_api_error(monkeypatch):
    import src.utils.pubmed_downloader as mod

    monkeypatch.setattr(mod, "_cache", {})
    logger = MagicMock()

    with patch("src.utils.pubmed_downloader.requests.get", side_effect=Exception("timeout")):
        result = mod.get_pubmed_title("77777", logger)

    assert result == ""
    logger.warning.assert_called()
