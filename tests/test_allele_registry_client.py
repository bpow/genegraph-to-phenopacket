import json
from pathlib import Path
from unittest.mock import patch
import pytest
from gci_phenopacket.allele_registry_client import AlleleRegistryClient


MOCK_API_RESPONSE = {
    "genomicAlleles": [
        {
            "referenceGenome": "GRCh38",
            "chromosome": "11",
            "hgvs": ["NC_000011.10:g.68032291C>T"],
            "coordinates": [{"start": 68032290, "referenceAllele": "C", "allele": "T"}],
        },
        {
            "referenceGenome": "GRCh37",
            "chromosome": "11",
            "hgvs": ["NC_000011.9:g.67799758C>T"],
            "coordinates": [{"start": 67799757, "referenceAllele": "C", "allele": "T"}],
        },
        {
            "referenceGenome": "NCBI36",
            "chromosome": "11",
            "hgvs": ["NC_000011.8:g.67556334C>T"],
            "coordinates": [{"start": 67556333, "referenceAllele": "C", "allele": "T"}],
        },
    ],
    "transcriptAlleles": [
        {
            "geneSymbol": "NDUFS8",
            "hgvs": ["NM_002496.4:c.64C>T"],
            "proteinEffect": {"hgvs": "NP_002487.1:p.Pro22Ser"},
            "MANE": {"maneStatus": "MANE Select"},
        },
        {
            "geneSymbol": "NDUFS8",
            "hgvs": ["NM_001127713.3:c.64C>T"],
        },
    ],
    "externalRecords": {
        "dbSNP": [{"rs": 369602258}],
        "ClinVarAlleles": [{"alleleId": 211565}],
        "gnomAD_4": [{"id": "11-68032291-C-T"}],
    },
}


def _client_with_no_cache(tmp_path) -> AlleleRegistryClient:
    return AlleleRegistryClient(tmp_path / "allele_registry_cache.json")


def test_parse_vcf_record_grch38(tmp_path):
    client = _client_with_no_cache(tmp_path)
    result = client._parse(MOCK_API_RESPONSE)
    assert result["vcf_record"] == {
        "genome_assembly": "GRCh38",
        "chrom": "11",
        "pos": 68032291,
        "ref": "C",
        "alt": "T",
    }


def test_parse_vcf_record_from_gnomad_indel(tmp_path):
    # gnomAD ids are normalized with an anchor base — ref/alt are never empty for indels
    client = _client_with_no_cache(tmp_path)
    response = {"externalRecords": {"gnomAD_4": [{"id": "1-12345-CAG-C"}]}}
    result = client._parse(response)
    assert result["vcf_record"] == {
        "genome_assembly": "GRCh38",
        "chrom": "1",
        "pos": 12345,
        "ref": "CAG",
        "alt": "C",
    }


def test_parse_vcf_record_none_without_gnomad(tmp_path):
    # No gnomAD_4 record → no VCF record, even when genomicAlleles/coordinates exist
    client = _client_with_no_cache(tmp_path)
    response = {
        "genomicAlleles": MOCK_API_RESPONSE["genomicAlleles"],
        "externalRecords": {"dbSNP": [{"rs": 1}]},
    }
    result = client._parse(response)
    assert result["vcf_record"] is None


def test_parse_vcf_record_malformed_gnomad_id(tmp_path):
    client = _client_with_no_cache(tmp_path)
    response = {"externalRecords": {"gnomAD_4": [{"id": "not-valid"}]}}
    result = client._parse(response)
    assert result["vcf_record"] is None


def test_parse_genomic_expressions_grch38_and_grch37_only(tmp_path):
    client = _client_with_no_cache(tmp_path)
    result = client._parse(MOCK_API_RESPONSE)
    genomic = [e for e in result["expressions"] if e["syntax"] == "hgvs.g"]
    assemblies = {e["assembly"] for e in genomic}
    assert assemblies == {"GRCh38", "GRCh37"}  # NCBI36 excluded


def test_parse_genomic_expression_values(tmp_path):
    client = _client_with_no_cache(tmp_path)
    result = client._parse(MOCK_API_RESPONSE)
    values = {e["value"] for e in result["expressions"] if e["syntax"] == "hgvs.g"}
    assert "NC_000011.10:g.68032291C>T" in values
    assert "NC_000011.9:g.67799758C>T" in values


def test_parse_prefers_mane_for_transcript_expression(tmp_path):
    client = _client_with_no_cache(tmp_path)
    result = client._parse(MOCK_API_RESPONSE)
    coding = [e for e in result["expressions"] if e["syntax"] == "hgvs.c"]
    # MANE Select transcript is NM_002496.4; non-MANE NM_001127713.3 should be excluded
    assert len(coding) == 1
    assert "NM_002496.4" in coding[0]["value"]


def test_parse_protein_expression(tmp_path):
    client = _client_with_no_cache(tmp_path)
    result = client._parse(MOCK_API_RESPONSE)
    protein = [e for e in result["expressions"] if e["syntax"] == "hgvs.p"]
    assert len(protein) == 1
    assert "Pro22Ser" in protein[0]["value"]


def test_parse_gene_symbols(tmp_path):
    client = _client_with_no_cache(tmp_path)
    result = client._parse(MOCK_API_RESPONSE)
    assert "NDUFS8" in result["gene_symbols"]


def test_parse_gene_symbols_deduplicated(tmp_path):
    client = _client_with_no_cache(tmp_path)
    result = client._parse(MOCK_API_RESPONSE)
    assert result["gene_symbols"].count("NDUFS8") == 1


def test_parse_xrefs_dbsnp(tmp_path):
    client = _client_with_no_cache(tmp_path)
    result = client._parse(MOCK_API_RESPONSE)
    assert "dbSNP:rs369602258" in result["xrefs"]


def test_parse_xrefs_clinvar(tmp_path):
    client = _client_with_no_cache(tmp_path)
    result = client._parse(MOCK_API_RESPONSE)
    assert "ClinVar:211565" in result["xrefs"]


def test_parse_no_mane_falls_back_to_first_transcript(tmp_path):
    response = {
        "genomicAlleles": [],
        "transcriptAlleles": [
            {"geneSymbol": "GENE1", "hgvs": ["NM_001.1:c.1A>T"]},
            {"geneSymbol": "GENE1", "hgvs": ["NM_002.1:c.1A>T"]},
        ],
        "externalRecords": {},
    }
    client = _client_with_no_cache(tmp_path)
    result = client._parse(response)
    coding = [e for e in result["expressions"] if e["syntax"] == "hgvs.c"]
    assert len(coding) == 1
    assert "NM_001.1" in coding[0]["value"]


def test_parse_empty_response(tmp_path):
    client = _client_with_no_cache(tmp_path)
    result = client._parse({})
    assert result["expressions"] == []
    assert result["vcf_record"] is None
    assert result["xrefs"] == []
    assert result["gene_symbols"] == []


def test_get_by_clinvar_id_cache_hit(tmp_path):
    cache_file = tmp_path / "allele_registry_cache.json"
    cached = {"clinvar:2597": {"expressions": [], "vcf_record": None, "xrefs": [], "gene_symbols": ["ETFA"]}}
    cache_file.write_text(json.dumps(cached))
    client = AlleleRegistryClient(cache_file)
    with patch.object(client, "_fetch_by_clinvar_id") as mock_fetch:
        result = client.get_by_clinvar_id("2597")
        mock_fetch.assert_not_called()
    assert result["gene_symbols"] == ["ETFA"]


def test_get_by_clinvar_id_cache_miss_calls_api(tmp_path):
    client = _client_with_no_cache(tmp_path)
    mock_result = {"expressions": [], "vcf_record": None, "xrefs": [], "gene_symbols": ["ETFA"]}
    with patch.object(client, "_fetch_by_clinvar_id", return_value=mock_result):
        result = client.get_by_clinvar_id("2597")
    assert result == mock_result
    assert "clinvar:2597" in client._cache


def test_get_by_clinvar_id_uses_prefixed_cache_key(tmp_path):
    client = _client_with_no_cache(tmp_path)
    mock_result = {"expressions": [], "vcf_record": None, "xrefs": [], "gene_symbols": []}
    with patch.object(client, "_fetch_by_clinvar_id", return_value=mock_result):
        client.get_by_clinvar_id("999")
    assert "clinvar:999" in client._cache
    assert "999" not in client._cache  # no collision with CAID keys


def test_get_by_clinvar_id_empty_response_returns_none(tmp_path):
    client = _client_with_no_cache(tmp_path)
    with patch.object(client, "_fetch_by_clinvar_id", return_value=None):
        result = client.get_by_clinvar_id("9999")
    assert result is None
    assert "clinvar:9999" not in client._cache


def test_cache_hit_skips_api(tmp_path):
    cache_file = tmp_path / "allele_registry_cache.json"
    cached = {"CA321211": {"expressions": [], "vcf_record": None, "xrefs": [], "gene_symbols": ["NDUFS8"]}}
    cache_file.write_text(json.dumps(cached))
    client = AlleleRegistryClient(cache_file)
    with patch.object(client, "_fetch") as mock_fetch:
        result = client.get("CA321211")
        mock_fetch.assert_not_called()
    assert result["gene_symbols"] == ["NDUFS8"]


def test_cache_miss_calls_api_and_stores_result(tmp_path):
    client = _client_with_no_cache(tmp_path)
    mock_result = {"expressions": [], "vcf_record": None, "xrefs": [], "gene_symbols": ["TEST"]}
    with patch.object(client, "_fetch", return_value=mock_result):
        result = client.get("CA999")
    assert result == mock_result
    assert "CA999" in client._cache


def test_api_error_returns_none(tmp_path):
    client = _client_with_no_cache(tmp_path)
    with patch.object(client, "_fetch", return_value=None):
        result = client.get("CA_BAD")
    assert result is None
    assert "CA_BAD" not in client._cache


def test_save_and_reload(tmp_path):
    cache_file = tmp_path / "allele_registry_cache.json"
    client = AlleleRegistryClient(cache_file)
    client._cache["CA1"] = {"expressions": [], "vcf_record": None, "xrefs": ["dbSNP:rs1"], "gene_symbols": ["G1"]}
    client.save()
    client2 = AlleleRegistryClient(cache_file)
    assert "CA1" in client2._cache
    assert client2._cache["CA1"]["xrefs"] == ["dbSNP:rs1"]


def test_save_creates_parent_dirs(tmp_path):
    cache_file = tmp_path / "nested" / "dir" / "cache.json"
    client = AlleleRegistryClient(cache_file)
    client._cache["CA1"] = {"expressions": [], "vcf_record": None, "xrefs": [], "gene_symbols": []}
    client.save()
    assert cache_file.exists()
