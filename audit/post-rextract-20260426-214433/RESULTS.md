# Re-extract sweep — cumulative impact + newly-revealed bugs

**Run**: 2026-04-26 ~14:48 PT
**DB**: `/tmp/nouns-postrextract.db` (full `dd extract` against
Nouns Experimental, then `dd extract-plugin` for plugin enrichment)
**Bridge**: WebSocket port 9225
**Commits applied**:
- `0efbf38` fix(pipeline): plug 3-layer drop on non-SOLID strokes +
  effect token refs
- `16be167` feat(cluster): wire VLM image_provider end-to-end via
  bridge thumbnails
- `8247066` fix(extract): mirror sgt enrichment in unified plugin
  walker (caught mid-flight; 0efbf38 added sgt to extract_supplement
  but extract_plugin's JS walker also needed it)

## Headline data wins

| Metric                                | Pre  | Post     | Δ              |
|---------------------------------------|------|----------|----------------|
| `component_figma_id` populated        | 0    | **1342** | new column     |
| **CKR `figma_node_id` coverage**      | 1/179 (0.6%) | **179/179 (100%)** | **+99.4 pp** |
| Stroke gradientTransform on Ellipse 58 (screen 68) | absent | populated | gradient now emits |
| **Screen 68 missing_asset DRIFT**     | DRIFT | **PARITY** ✅ | targeted fix landed |

## Sweep delta vs prev (postE3+ on pre-rextract DB)

| Metric                        | postE3+ (prev) | post-rextract | Δ        |
|-------------------------------|---------------:|--------------:|---------:|
| `is_parity_true` (clean)      | 46             | 32            | -14      |
| `is_parity_false`             | 21             | 35            | +14      |
| `is_structural_parity_true`   | 66             | 50            | -16      |
| `walk_failed`                 | 0              | 0             | 0        |
| `walk_timed_out_count`        | 0              | 0             | 0        |
| screens with runtime errors   | 20             | 20            | 0        |
| total runtime errors          | 37             | 37            | 0        |
| `error_kinds`                 | {missing_asset: 1} | {fill_mismatch: 23, stroke_mismatch: 7} | new classes |
| `elapsed_s`                   | 396.7          | 259.6         | -137     |

## Why the apparent regression is actually progress

The 17 newly-DRIFT screens were **also broken before** — they just
appeared CLEAN because the verifier was looking at the wrong nodes.

### Mechanism

Pre-rextract, CKR coverage was 0.6% (1/179). The renderer's Mode-1
instance dispatch (recreate node from master in the live Figma file)
needs the master's `figma_node_id` to find it via
`getNodeByIdAsync`. Without that, Mode-1 silently fell through to a
Mode-2 fallback path (or a frame placeholder) that didn't trigger
the verifier's fill/stroke comparison checks.

Post-rextract, CKR is 100%. Mode-1 fires. The renderer creates the
master via `figma.getNodeByIdAsync(masterId).clone()`, then applies
override prop writes. **And those override writes don't actually
land** on certain node classes — bool_op fills + iPhone-instance
strokes — so the rendered result has the master's defaults, not
the IR's overrides. Verifier sees the drift; flags `fill_mismatch`
or `stroke_mismatch`.

Codex 2026-04-26 (gpt-5.5 high reasoning) reviewed this analysis:
"Mostly A: re-extract activated Mode-1 dispatch via 100% CKR
coverage, exposing pre-existing renderer gaps. Don't roll back.
Document, then file two focused follow-ons."

## Two follow-on bugs (filed; not fixed in this session)

### Follow-on 1: deferred bool-op visual prop emission (MUST FIX)

**10 screens, 23 `fill_mismatch` errors.** All on `boolean_operation-N`
nodes; rendered as `#D9D9D9` (Figma's default placeholder grey)
where IR has the real color (`#FFD74B`, `#000000`, etc).

**Mechanism** (per Codex review of the actual code path):
`dd/render_figma_ast.py:939` — `if etype == "boolean_operation": continue`
prevents the normal `_emit_visual` (fills/strokes/effects) emission
for bool_ops. After `figma.union(children, parent)`, the materialization
path at `dd/render_figma_ast.py:1896` only sets `name`, `M[...]`,
and z-order. Visual props are never replayed.

**Fix shape**: After the figma.union/subtract/intersect/exclude
materialization call, replay `_emit_visual` for the resulting
bool_op node so fills/strokes/effects from the IR get applied.

### Follow-on 2: Mode-1 descendant override targeting (MUST FIX)

**7 screens, 7 `stroke_mismatch` errors.** All iPhone 15-sized
screens (50, 51, 52, 53, 54, 55, 57). Pattern:
`stroke[0] color: IR=#222529, rendered=#FFFFFF` on `instance-N`
nodes. The instance is created via Mode-1 (master clone), but the
descendant stroke override isn't being applied to the right node
in the override tree.

**Investigation pointer**: `dd/renderers/figma.py:1344` (Mode-1
instance recreation). Override resolver / override-tree targeting
likely picks the wrong node when the master has a similarly-named
child.

## Other bug surfaced

- **Screen 24, instance-5**: `solid fill count: IR=0, rendered=1`
  — default-fill artifact. The instance has no fills in IR but
  Figma added a default solid fill on creation. Codex previously
  flagged this class in `feedback_figma_default_visibility.md` —
  factory defaults need explicit clearing.

## Residuals (unchanged from prev sweep)

- 20 PARITY+ screens with `text_op_failed (20)` + `font_health (17)`
  runtime errors — same set as postE3+, font-license blocker
  (GT Walsheim Trial / GT America Mono / GT Flexa Mono not
  installed). Not addressed in this work.

## Snapshot trail (rollback safety)

```
archive/db-snapshots/
├─ dank-pre-rextract-20260426-213038.db   (canonical Dank, untouched)
└─ nouns-pre-rextract-20260426-213038.db  (Nouns pre-Phase-E3+)
```

Re-extract output: `/tmp/nouns-postrextract.db`.

## Commands

```bash
# Snapshot
mkdir -p archive/db-snapshots
TS=$(date -u +%Y%m%d-%H%M%S)
cp Dank-EXP-02.declarative.db archive/db-snapshots/dank-pre-rextract-$TS.db
cp /tmp/nouns-postE3plus.db archive/db-snapshots/nouns-pre-rextract-$TS.db

# Re-extract
.venv/bin/python -m dd extract B512WwrY9M0Pu4nacnMIPe \
  --db /tmp/nouns-postrextract.db
.venv/bin/python -m dd extract-plugin \
  --db /tmp/nouns-postrextract.db --port 9225

# Sweep
.venv/bin/python -m render_batch.sweep \
  --db /tmp/nouns-postrextract.db --port 9225 \
  --grid --grid-cols 6 \
  --out-dir audit/post-rextract-20260426-214433
```
