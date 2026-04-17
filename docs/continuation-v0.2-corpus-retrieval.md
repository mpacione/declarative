# Continuation — v0.2 corpus retrieval

> Supersedes `docs/continuation-v0.2-post-breadth.md` for the active
> work. That doc's deferred-fix priority list (#3/#4/#5/meme-feed) is
> now subsumed by the corpus-retrieval architecture below; fall through
> to it only for prompts with no corpus match.

## Why corpus retrieval

The v0.1.5 5-round patch arc (R1 merge-extract, R2 shadow-allowlist,
R3 strip-container-fill, H7-reverted, Fix#1 leaf-parent gate) + 3
deferred defects (#3/#4/#5) were all landing in the compose/render
boundary. Each tried to close the density gap between hand-authored
catalog templates (~27 types, token refs + slot grammar) and real
extracted IR (~20K round-trip-clean fragments per 204-screen corpus).
Template enrichment is asymptotic at ~0.75 render-fid. Corpus retrieval
ISN'T, because it IS the real extracted IR.

Research-arc load-bearing insight: prompt-fidelity held at 0.83 through
all 5 rounds; render-fid moved 0.25 → 0.75 entirely from
compose/render plumbing fixes. The LLM was structurally fine; the
catalog was thin.

## Architecture

```
prompt
  → LLM components (unchanged — archetype classifier + CKR vocab stay)
  → compose_screen(components, registry=R)
     → _try_corpus_splice(comp)                   NEW
        - registry.resolve(type, variant, ctx)
        - If template.corpus_subtree is not None:
          _splice_subtree(subtree, llm_props, elements, allocate_id)
          returns spliced-root eid; skip synthesis
     → else (no corpus match):
        _apply_template_to_parent(comp_type, variant, element)  (v0.1.5)
        _mode3_synthesise_children(...)                          (v0.1.5)
  → build_template_visuals(spec, conn)
  → generate_figma_script(spec, db_visuals)
```

Registry cascade (top → bottom):
1. `CorpusRetrievalProvider` (priority 150) — behind
   `DD_ENABLE_CORPUS_RETRIEVAL=1`
2. `ProjectCKRProvider` (priority 100)
3. `UniversalCatalogProvider` (priority 10)

Fragment unit = a subtree rooted at any SCI-classified node (canonical
type in `component_type_catalog`). Retrieval key (PoC): canonical_type
+ deterministic MIN(node_id) selection. v0.3 adds structural-match
ranking against the LLM's child-type set.

## Foundation landed (2026-04-17)

- `dd classify` run over 338 screens → 42,938 nodes labelled, 338
  skeletons (1.5 s). Writes to `screen_component_instances` +
  `screen_skeletons`.
- `dd/composition/protocol.py` — `PresentationTemplate.corpus_subtree:
  dict[str, Any] | None = None` (backward compat).
- `dd/composition/providers/corpus_retrieval.py` — 150-priority
  provider, recursive CTE subtree extraction, DB visuals + layout +
  props per element.
- `dd/compose.py::compose_screen(registry=…)` — optional registry
  kwarg. `_try_corpus_splice` + `_splice_subtree` helpers.
- 1,947 unit tests green (+15: 12 provider, 3 integration).
- 204/204 round-trip parity preserved.

## Remaining for the PoC A/B

### 1. Wire retrieval registry into `prompt_to_figma`

In `dd/prompt_parser.py::prompt_to_figma` (has `conn`), build:

```python
from dd.composition.providers.corpus_retrieval import CorpusRetrievalProvider
from dd.composition.providers.universal import UniversalCatalogProvider
from dd.composition.registry import ProviderRegistry

registry = ProviderRegistry(providers=[
    CorpusRetrievalProvider(conn=conn),
    UniversalCatalogProvider(),
])
```

Thread it into `_generate_from_prompt` → `compose_screen`.

### 2. Renderer visual integration for spliced elements

`dd/compose.py::build_template_visuals` assigns synthetic NEGATIVE
node_ids + template lookup per element. For spliced elements, need the
**source DB node_id** so the renderer's `db_visuals` picks up real DB
fills/strokes/effects/radius/etc. Options:

- **(a)** Extend the provider to stamp `element["_corpus_node_id"]`
  per element; `build_template_visuals` detects it, uses the real
  node_id as the key, pulls real visuals from DB.
- **(b)** Pre-populate `spec["_node_id_map"]` from splice time
  (eid → real node_id); `build_template_visuals` preserves existing
  entries instead of overwriting.

(b) is cleaner — smaller blast radius in `build_template_visuals`.

### 3. Run 00g + 00i A/B

```bash
cd /Users/mattpacione/declarative-build
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)

# A: current (flag off)
unset DD_ENABLE_CORPUS_RETRIEVAL
PYTHONPATH=$(pwd) python3 experiments/00g-mode3-v4/run_parse_compose.py  # or equivalent
PYTHONPATH=$(pwd) python3 experiments/_lib/score_experiment.py experiments/00g-mode3-v4

# B: retrieval (flag on)
export DD_ENABLE_CORPUS_RETRIEVAL=1
# (ideally point to a different artefact dir, e.g. 00j-corpus-retrieval/)
# ...
```

Expected: render-fid 0.72 → ≥0.85 on prompts with corpus match.
Prompt-fid unchanged (we didn't touch the LLM path).

## Guardrails (unchanged from v0.1.5)

- 204/204 parity is load-bearing
- Unit tests ≥ 1,947 green; new behavior = new tests
- Round-trip is the fidelity oracle — cross-reference spliced IR
  against a real round-trip walk for the same source screen
- Rollback: `DD_ENABLE_CORPUS_RETRIEVAL=0` (default) OR
  `DD_DISABLE_PROVIDER=corpus:retrieval`

## Known scope boundaries

- No structural-match ranking yet: MIN(node_id) pick is deterministic
  but not aware of the LLM's child-type set. Defer to v0.3.
- Text substitution: first N LLM text props → first N TEXT leaves in
  tree order. Good enough for PoC; slot-aware substitution deferred.
- Variant is ignored in `supports()`. Variant-aware retrieval (ranking
  by variant axis match) defers to v0.3.
- Second-project portability: retrieval needs corpus. First run on a
  new Figma file uses catalog; extract + classify populates SCI;
  subsequent runs use retrieval.

## References

- Architectural pivot memo: `memory/project_corpus_retrieval_v0_2.md`
- Why classify was dormant: `memory/feedback_classify_chain_was_dormant.md`
- Why sweep timeouts are transient: `memory/feedback_sweep_transient_timeouts.md`
- v0.1.5 research arc: `docs/research/mode3-forensic-analysis.md`,
  `docs/research/iteration-journal.md`
- Superseded doc: `docs/continuation-v0.2-post-breadth.md`
