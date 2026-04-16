# Experiment 02 — Structural match ablation

**Question (OQ2 from the planning doc):** does v0.1 need embedding-based
matching, or does canonical-type equality suffice when lowering synthesised
IR to real CKR components?

**Setup:** 50 held-out INSTANCE nodes stratified across 7 canonical types
that exist in Dank (icon=25, button=10, system_chrome=7, button_group=4,
image=2, header=1, tabs=1). Ground truth is the `component_key` column
from `nodes`. Three matchers ran against the 129-entry CKR.

Queries simulate what a synthetic LLM might emit: the canonical type, a
deterministically paraphrased semantic intent (`icon/chevron-right` →
"chevron right icon"), size-derived variant hints, and the immediate
children signature. The literal CKR name is never used in the query.

## The numbers

| matcher | @1   | @3  | canonical @1 | n  |
|---------|------|-----|--------------|----|
| A (type + instance count) | **0.42** | 0.60 | 1.00 | 50 |
| B (type + variant filter) | **0.44** | 0.60 | 1.00 | 50 |
| C (type-scoped embedding kNN, MiniLM-L6)   | **0.86** | 1.00 | 1.00 | 50 |

All three matchers hit 100 % canonical-type accuracy — meaning every pick
was at least in the right class. No matcher is broken at the sanity check.

### Per-type breakdown (top-1, %)

| canonical_type | n  | A   | B   | C   |
|----------------|----|-----|-----|-----|
| icon           | 25 | 24  | 24  | **92** |
| button         | 10 | 90  | **100** | 80  |
| system_chrome  | 7  | 14  | 14  | **57** |
| button_group   | 4  | 25  | 25  | **100** |
| image          | 2  | 100 | 100 | 100 |
| header         | 1  | 100 | 100 | 100 |
| tabs           | 1  | 100 | 100 | 100 |

## A → C gap: 42 % → 86 %

The 44-point gap is driven almost entirely by **icons** (91 of 129 CKR
entries, 25 of 50 holdout rows). Matcher A's `icon` pick is always whichever
icon has the highest instance count — it ignores intent entirely because
canonical-type alone is a 91-way ambiguity. B's size-bucket prop filter
doesn't help icons either: virtually all Dank icons live in a 20×20 or
24×24 frame, so the filter collapses to the same A-style ranking. Matcher
C embeds the paraphrased intent ("back arrow icon") and the CKR glyph
names share a semantic space where MiniLM-L6 can find the nearest neighbor
with 92 % top-1 accuracy.

The `button_group` and `system_chrome` buckets show the same pattern at
smaller n: tiny ambiguous spaces where A picks by popularity and is usually
wrong; C picks by semantic fingerprint and is usually right.

The one bucket where A/B **beat** C is `button`: 7 CKR entries, driven by
size (small=40×40, large=48×52) and style (solid/translucent/white). B's
size-filter matcher B gets 100 % there because width is a near-perfect
discriminator. C loses one button to children-signature noise — the
CKR-representative button/small happens to share the word "Cancel" with
the held-out button/large instance, and the embedder over-weights that.

## Failure patterns

Of C's 7 top-1 misses, all 7 are top-3 correct. Three of them are cases
where the CKR has **two distinct component_keys sharing an identical
name** (Dank has 2× "Home Indicator", 2× "icon/edit", 2× ".?123"). The
matcher picks the right name but the wrong key — there is literally no
disambiguating signal in the query. This is an information-theoretic
ceiling, not a matcher defect. A v0.1 policy should reconcile these at
dedup time (or declare them interchangeable).

Two more misses are `button/large/translucent` predicted as
`button/small/translucent` because the children-signature dominated the
size hint. Tweaking the canonical string to weight `variant_segments`
more heavily would likely recover both.

## Verdict on "embeddings in v0.1?"

**Yes — for icon-like vocabularies, embeddings are load-bearing.**

If Dank's vocabulary looked like its buttons (small set, size-distinguished),
matcher B would be enough and `all-MiniLM-L6` would be over-engineering.
But any real project's CKR will have a long-tail icon vocabulary — that's
what icon sets look like. **A loses 68 percentage points** on that long
tail in this corpus. That loss is the whole reason to want intent-aware
retrieval.

The caveat: matcher C's edge **requires a plausible semantic intent
string in the query**. With no intent (raw structural fingerprint only),
C performed worse than A in an early run because it latched onto spurious
children-signature similarities. The lesson is that embeddings are only
useful in v0.1 if the IR carries a free-text intent field. That's cheap to
require: our existing prompt-driven IR already does.

## Implementation cost for C in v0.1

Rough estimate — **2 engineer-days** for first landing, plus small
incremental overhead:

- sentence-transformers dep (~500 MB install, but weights cache-able): 0.25 d
- embed CKR on extraction (129 rows × MiniLM batch = 4 s): 0.25 d
- CKR embedding table in SQLite (BLOB column on CKR + hash for freshness): 0.5 d
- matcher wiring in lowering pipeline (canonical filter + kNN rank): 0.5 d
- re-embedding on CKR change: hook into the existing supplement-extraction
  pass, 0.25 d
- tests (golden set of ~20 queries): 0.25 d

No ongoing infra — embeddings are tiny, deterministic, and project-local.
If we reach for `all-mpnet-base-v2` later (768-dim, higher quality) the
shape of the code doesn't change.

## Caveats

- `instance_count = 1` CKR edge case: the single such entry in Dank is an
  icon; stratified sampling didn't pick it. Noted but not exercised.
- The 7-type canonical distribution in Dank is narrow. A richer DS would
  have navigation, input, card, text-input etc. — and those would mostly
  land in A-territory (small option set, structural discriminators) rather
  than C-territory (long-tail vocabulary).
- MiniLM-L6's semantic space is English-leaning. A Dank-like English
  vocabulary sits in its sweet spot. Non-English labels would need retest.
