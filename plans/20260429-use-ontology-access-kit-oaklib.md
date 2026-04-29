# Plan: Replace pronto with ontology-access-kit (oaklib) sqlite adapter

## Context

The current `OntologyManager` in `ontologies.py` uses `pronto` to load and parse HPO and MONDO ontologies from OWL/OBO files, with a hand-rolled disk cache managed via `platformdirs`. Switching to `ontology-access-kit` (oaklib) with its sqlite adapter eliminates all of that manual caching logic — oaklib downloads and caches ontologies as sqlite databases automatically using `get_adapter("sqlite:obo:hp")`. This simplifies the code and leverages an actively maintained, OBO-ecosystem-native library.

---

## Files to Change

| File | Change |
|---|---|
| `src/gci_phenopacket/ontologies.py` | Full rewrite: pronto → oaklib, drop manual cache |
| `src/gci_phenopacket/transformer.py` | Replace `om.mondo.get()` + `.name` with `om.mondo_label()` |
| `tests/test_ontologies.py` | Rewrite to mock oaklib `get_adapter` |
| `pyproject.toml` | Remove `pronto`, `platformdirs`; add `ontology-access-kit` |
| `pixi.toml` | Remove `pronto` from `[dependencies]`; remove `platformdirs` from `[pypi-dependencies]`; add `ontology-access-kit` to `[pypi-dependencies]` |
| `CLAUDE.md` | Update key dependencies and design decisions |

---

## Implementation

### 1. `src/gci_phenopacket/ontologies.py` — rewrite

```python
import logging
from oaklib import get_adapter

logger = logging.getLogger(__name__)


class OntologyManager:
    def __init__(self, hp_selector="sqlite:obo:hp", mondo_selector="sqlite:obo:mondo"):
        logger.info("Initializing Ontologies (Checking Cache/Remote)...")
        self._hpo = get_adapter(hp_selector)
        self._mondo = get_adapter(mondo_selector)
        logger.info("Ontologies successfully loaded and indexed.")

    def hpo_to_labeled_phenotype(self, hpo_id):
        """Map HPO ID (e.g. 'obo:HP_0001250' or 'HP:0001250') to {id, label}."""
        normalized = hpo_id.replace("obo:HP_", "HP:").replace("obo:HP:", "HP:")
        label = self._hpo.label(normalized)
        if label is None:
            logger.warning(f"Could not resolve HPO label for {hpo_id}")
            return {"id": normalized, "label": "Unknown Phenotype"}
        return {"id": normalized, "label": label}

    def mondo_label(self, disease_id):
        """Return the Mondo label for a CURIE, or None if not found."""
        return self._mondo.label(disease_id)
```

Key changes:
- `get_adapter("sqlite:obo:hp")` / `"sqlite:obo:mondo"` — oaklib downloads and caches sqlite db automatically
- `selector` params replace `custom_paths`: tests pass e.g. `hp_selector="sqlite:/path/to/hp.db"` or mock `get_adapter`
- `hpo_to_labeled_phenotype()` uses `adapter.label(curie)` → `Optional[str]`
- New `mondo_label()` method encapsulates MONDO lookups (replaces direct `om.mondo.get()` in transformer)
- `CACHE_DIR`, `platformdirs`, `pronto`, `os` imports all removed

### 2. `src/gci_phenopacket/transformer.py` — replace mondo access (~lines 268–277)

Current:
```python
mondo = om.mondo.get(disease_id)
if not mondo and raw_disease_label:
    ...
    disease_label = raw_disease_label
else:
    disease_label = mondo.name
    if disease_label != raw_disease_label:
        ...
```

Replace with:
```python
disease_label = om.mondo_label(disease_id)
if disease_label is None and raw_disease_label:
    LOGGER.warning(
        f"MONDO ID '{disease_id}' not found in ontology — falling back to label '{raw_disease_label}'"
    )
    disease_label = raw_disease_label
elif disease_label is None:
    disease_label = raw_disease_label or FALLBACK_DISEASE_LABEL
else:
    if disease_label != raw_disease_label:
        LOGGER.warning(
            f"MONDO ID '{disease_id}' label '{disease_label}' does not match annotation label '{raw_disease_label}', using current Mondo label"
        )
```

### 3. `tests/test_ontologies.py` — rewrite

Remove the three pronto/cache tests (caching is oaklib's responsibility). Replace with tests that mock `get_adapter`:

```python
from unittest.mock import MagicMock, patch
import pytest
from gci_phenopacket.ontologies import OntologyManager


def _make_adapter(label_map=None):
    adapter = MagicMock()
    adapter.label.side_effect = lambda curie: (label_map or {}).get(curie)
    return adapter


def test_hpo_to_labeled_phenotype_normalizes_obo_prefix():
    hp_adapter = _make_adapter({"HP:0001250": "Seizure"})
    with patch("gci_phenopacket.ontologies.get_adapter", side_effect=[hp_adapter, MagicMock()]):
        om = OntologyManager()
    result = om.hpo_to_labeled_phenotype("obo:HP_0001250")
    hp_adapter.label.assert_called_with("HP:0001250")
    assert result == {"id": "HP:0001250", "label": "Seizure"}


def test_hpo_to_labeled_phenotype_returns_fallback_on_unknown_id():
    hp_adapter = _make_adapter({})
    with patch("gci_phenopacket.ontologies.get_adapter", side_effect=[hp_adapter, MagicMock()]):
        om = OntologyManager()
    result = om.hpo_to_labeled_phenotype("HP:9999999")
    assert result == {"id": "HP:9999999", "label": "Unknown Phenotype"}


def test_mondo_label_returns_label_when_found():
    mondo_adapter = _make_adapter({"MONDO:0007947": "Marfan syndrome"})
    with patch("gci_phenopacket.ontologies.get_adapter", side_effect=[MagicMock(), mondo_adapter]):
        om = OntologyManager()
    assert om.mondo_label("MONDO:0007947") == "Marfan syndrome"


def test_mondo_label_returns_none_when_not_found():
    mondo_adapter = _make_adapter({})
    with patch("gci_phenopacket.ontologies.get_adapter", side_effect=[MagicMock(), mondo_adapter]):
        om = OntologyManager()
    assert om.mondo_label("MONDO:9999999") is None
```

Also update `tests/test_gci_transformer.py` mock: `_make_om_with_mondo()` currently uses `om.mondo.get(disease_id).name` — update to `om.mondo_label.return_value = "Marfan syndrome"` etc. (check exact mock shape after reading the full function).

### 4. `pyproject.toml`

```toml
dependencies = [
    "click>=8.0",
    "phenopackets>=2.0.2.post5",
    "ontology-access-kit>=0.3",
    "requests>=2.32",
]
```
(Remove `pronto>=2.7` and `platformdirs>=4.0`.)

### 5. `pixi.toml`

In `[dependencies]`: remove `pronto = ">=2.7.3,<3"`
In `[pypi-dependencies]`: remove `platformdirs = ">=4.0"`, add `ontology-access-kit = ">=0.3"`

---

## Verification

```bash
# Install updated deps
pixi install

# Run full test suite
pixi run test

# Smoke test with a real record (hits the oaklib cache on first run)
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --record 0
```

On first run oaklib will download and cache `hp.db` and `mondo.db` via semsimian/sqlite. Subsequent runs will be fast. Verify that phenopacket output contains correct HPO labels and MONDO disease labels.
