# Code Review: genegraph-to-phenopacket

## Context
Constructive criticism of the current codebase — no feature additions, just identifying where the code could be more robust, readable, or maintainable. Items are ordered from most to least impactful.

---

## Issue 1 — Subject ID computed in two places (DRY violation)

**Files:** `transformer.py:124`, `transformer.py:183`

`f"PMID_{pmid}:{label}"` is constructed independently in `build_subject` and `build_genomic_interpretations`. If the format ever changes, one site will silently diverge. Extract into a single helper:

```python
def _subject_id(pmid: str, label: str) -> str:
    return f"PMID_{pmid}:{label}"
```

---

## Issue 2 — Non-reproducible phenopacket output (timestamp in MetaData)

**File:** `transformer.py:260–261`

`ts.GetCurrentTime()` stamps each phenopacket with the wall-clock time of generation. Two identical runs produce different output, which breaks diffing, reproducibility tests, and version control comparisons. Consider:
- Accepting a `created_ts` parameter with a default of `None` (use `GetCurrentTime()` only when `None`)
- Passing a fixed timestamp in tests (the tests currently don't assert on `created`)

---

## Issue 3 — `build_phenopacket` signature is too wide (9 parameters)

**File:** `transformer.py:235–238`

Nine positional parameters, with `record_uuid`/`annotation_uuid`/`gene_symbol`/`hgnc_id` representing GDM-level data and `pmid`/`article_title` representing annotation-level data. A dataclass or namedtuple for each level would make call sites readable and catch argument-order mistakes at the type checker:

```python
@dataclass
class AnnotationContext:
    record_uuid: str
    annotation_uuid: str
    gene_symbol: str
    hgnc_id: str
    pmid: str
    article_title: str
```

Then `build_phenopacket(ctx, individual, tag, om)`.

---

## Issue 4 — `om` parameter has no type contract

**Files:** `transformer.py:160`, `transformer.py:235`, `cli.py:82–86`

`om` is typed as bare (no annotation at all), making it invisible to IDEs and type checkers. Define a `Protocol` or `ABC`:

```python
class OntologyManagerProtocol(Protocol):
    def hpo_to_labeled_phenotype(self, hpo_id: str) -> dict[str, str]: ...
    def mondo_to_label(self, mondo_id: str) -> str | None: ...
```

This makes mock construction in tests self-documenting and catches interface drift.

---

## Issue 5 — Gene-in-title check is fragile for short gene symbols

**File:** `transformer.py:212`

```python
if gene_symbol and gene_symbol in var_title:
```

For short symbols like `"A"`, `"AR"`, or `"F5"`, this substring test will match spuriously. Use word-boundary matching:

```python
import re
if gene_symbol and re.search(rf'\b{re.escape(gene_symbol)}\b', var_title):
```

---

## Issue 6 — HPO normalization in `hpo_to_labeled_phenotype` is dead code for the current call path

**File:** `ontologies.py:53`

```python
normalized = hpo_id.replace("obo:HP_", "HP:").replace("obo:HP:", "HP:")
```

All callers go through `extract_hpo_id()` first, which already returns bare `HP:XXXXXXX`. The `obo:` normalization never triggers in practice. Either:
- Remove it (and add a test asserting `extract_hpo_id` always strips the prefix), or
- Move it into `extract_hpo_id` where it belongs

---

## Issue 7 — `sanitize_label` leaves filesystem-unsafe characters in phenopacket filenames

**File:** `transformer.py:47–49`, `cli.py:87`

Only spaces and colons are replaced. On macOS the filename is written as `{pp_id}.json`, and `pp_id` is built from `label_s` which still permits `/`, `*`, `?`, `<`, `>`, `|`, and other characters that are unsafe on various OSes and shells. At minimum add `/`:

```python
return re.sub(r'[ :/\\*?"<>|]', '_', label)
```

---

## Issue 8 — Ontology URLs use plain HTTP

**File:** `ontologies.py:13–14`

Both OBO URLs use `http://`. `pronto` uses requests under the hood; plain HTTP is susceptible to MITM if ontologies are downloaded over untrusted networks. The OBO Foundry serves HTTPS — change to `https://purl.obolibrary.org/obo/...`.

---

## Issue 9 — `resolve_disease` will inadvertently convert non-MONDO IDs

**File:** `transformer.py:58–65`

The function splits on `_` and joins with `:`, so `"OMIM_615346"` → `"OMIM:615346"` or `"HP_0001250"` → `"HP:0001250"`. The name and docstring say "MONDO" but the logic is prefix-agnostic. If the GCI data only ever contains MONDO IDs this is fine — but the silent behavior is surprising. Add an assertion or guard:

```python
if parts[0] != "MONDO":
    logging.getLogger(__name__).warning(f"Unexpected disease prefix: {parts[0]!r} — using fallback")
    return FALLBACK_DISEASE_ID
```

---

## Issue 10 — Test file organization

**File:** `tests/test_gci_transformer.py`

351 lines with `import` statements scattered mid-file (lines 2, 66, 124, 147, 193, 234, 286). This is valid Python but makes the test file hard to navigate. Consider grouping into classes by tested function, or splitting into `test_helpers.py`, `test_builders.py`, `test_integration.py`. Move all imports to the top.

---

## Execution Steps

1. **Create a new git branch** — `refactor/code-review-fixes`
2. **Save this plan** as `plans/2026-04-14-code-review-fixes.md` and include it in the first commit
3. **Implement changes** — each issue above is a self-contained edit
4. **Update `CLAUDE.md`** to reflect architectural changes
5. **Run tests** after all changes: `pixi run test`

## Verification

Existing `pixi run test` suite covers most affected functions. For Issue 5 (gene symbol check), verify against a real snapshot record where the gene symbol is 2–3 characters.
