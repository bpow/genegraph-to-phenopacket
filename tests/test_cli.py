import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner
from gci_phenopacket.cli import main


MINIMAL_RECORD = json.dumps({
    "resourceParent": {
        "gdm": {
            "gene": {"symbol": "BRCA1", "hgncId": "hgnc:1100"},
            "annotations": [{
                "article": {"pmid": "12345", "title": "Test Article"},
                "individuals": [{
                    "label": "Proband1",
                    "is_proband": "Yes",
                    "hpoIdInDiagnosis": ["HP:0001250"],
                    "uuid": "test-uuid",
                }]
            }]
        }
    }
})


@pytest.fixture
def input_file(tmp_path):
    f = tmp_path / "snapshot.jsonl"
    f.write_text(MINIMAL_RECORD + "\n")
    return f


def mock_om():
    om = MagicMock()
    om.hpo_to_labeled_phenotype.return_value = {"id": "HP:0001250", "label": "Seizure"}
    om.mondo_to_label.return_value = None
    return om


def test_cli_default_output_is_gci_phenopackets_in_cwd(input_file, tmp_path, monkeypatch):
    """--output defaults to ./gci_phenopackets in the current working directory."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    with patch("gci_phenopacket.cli.OntologyManager", return_value=mock_om()):
        result = runner.invoke(main, ["--input", str(input_file)])
    assert result.exit_code == 0
    assert (tmp_path / "gci_phenopackets").is_dir()


def test_cli_prompts_for_input_when_not_provided(input_file, tmp_path, monkeypatch):
    """When --input is omitted, CLI prompts the user interactively."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    with patch("gci_phenopacket.cli.OntologyManager", return_value=mock_om()):
        result = runner.invoke(main, input=str(input_file) + "\n")
    assert "Path to input JSONL file" in result.output


def test_cli_record_flag_processes_only_that_line(tmp_path, monkeypatch):
    """--record N skips all lines except line N."""
    monkeypatch.chdir(tmp_path)
    two_records = tmp_path / "two.jsonl"
    two_records.write_text(MINIMAL_RECORD + "\n" + MINIMAL_RECORD + "\n")

    runner = CliRunner()
    with patch("gci_phenopacket.cli.OntologyManager", return_value=mock_om()):
        result = runner.invoke(main, ["--input", str(two_records), "--record", "0"])

    assert result.exit_code == 0
    written = list((tmp_path / "gci_phenopackets").glob("*.json"))
    assert len(written) == 1


def test_cli_exits_with_error_on_missing_input_file(tmp_path, monkeypatch):
    """Passing a non-existent input file results in a non-zero exit and error message."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--input", str(tmp_path / "nonexistent.jsonl")])
    assert result.exit_code != 0
    assert "nonexistent.jsonl" in result.output or "does not exist" in result.output.lower() or "invalid" in result.output.lower()
