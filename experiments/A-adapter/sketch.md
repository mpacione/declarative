# Experiment A — `GenerationAdapter` paper test

> **Status:** paper-only. No code was executed.
> **Purpose:** stress-test the architectural claim "synthetic generation is
> extraction from imagination" — i.e. generation fits the existing ADR-006
> `IngestAdapter` shape symmetrically on the egress side.

## The existing shape (ADR-006)

`dd/boundary.py` defines:

```python
class IngestAdapter(Protocol):
    backend: ClassVar[str]
    def extract_screens(self, ids: list[str]) -> IngestResult: ...

@dataclass(frozen=True)
class IngestResult:
    extracted: list[dict[str, Any]]       # per-item successful payloads
    errors:    list[StructuredError]      # per-item structured failures
    summary:   IngestSummary               # honest requested/succeeded/failed counts
```

The contract's invariants:
- Every failure becomes a `StructuredError` with a named `kind`, an `id`, optional `error` text, optional `context` dict.
- Summary counts match `len(errors)`.
- Transient errors and null responses never raise — they become entries.
- Downstream code reads a total picture: partial success is first-class.

## The proposed symmetric shape

```python
class GenerationAdapter(Protocol):
    backend: ClassVar[str]      # same identifier (for multi-backend routing)

    def generate(
        self,
        prompts: list[GenerationRequest],
        context: GenerationContext,
    ) -> GenerationResult: ...

@dataclass(frozen=True)
class GenerationRequest:
    id: str                       # caller-assigned, for correlating results
    prompt: str                   # the natural-language (or multi-modal) spec
    metadata: dict[str, Any]      # e.g. {"target_backend": "figma", "seed": 42}

@dataclass(frozen=True)
class GenerationContext:
    catalog: dict                 # universal catalog (48 types with slots/props)
    design_md: str                # project-specific style snapshot
    exemplars: list[dict]         # kNN-retrieved IR subtrees
    defaults: dict                # robust-default components
    tokens: list[dict]            # available DTCG tokens

@dataclass(frozen=True)
class GenerationResult:
    generated: list[dict[str, Any]]   # per-prompt IR documents that succeeded
    errors:    list[StructuredError]  # per-prompt or per-node structured failures
    summary:   GenerationSummary      # requested / succeeded / degraded / failed

@dataclass(frozen=True)
class GenerationSummary:
    requested:  int
    succeeded:  int       # produced a valid IR without fidelity loss
    degraded:   int       # produced IR but with at least one KIND_* error
    failed:     int       # no IR at all
```

Note the one structural addition: `degraded` is a distinct summary bucket
from `succeeded` and `failed`. On ingest, a batch is either extracted or
not. On generation, there's a legitimate middle state — IR was produced,
but a required component couldn't be resolved and degraded to a placeholder,
or a requested variant wasn't available. This isn't failure (we have IR to
render) and it isn't clean success either (the output has known quality
loss). The shape should name it.

Everything else mirrors `IngestAdapter` directly.

## Structured error vocabulary on the egress side

Reusing the existing `KIND_*` scheme. New kinds specific to generation:

- `KIND_PROMPT_UNDERSPECIFIED` — prompt so vague the adapter refused to
  commit to a structure (or the LLM emitted a trivial output). `context:
  {"prompt": "..."}`.
- `KIND_COMPONENT_UNAVAILABLE` — generation requested a component type
  that has neither a CKR entry nor a generic catalog template nor a
  robust default. E.g. "line chart" when the project has no chart
  components and we never ingested a chart library. Attached to a
  node-eid within the result, like existing `KIND_COMPONENT_MISSING`
  on the render side.
- `KIND_DEGRADED_VARIANT` — variant requested (`{variant: "destructive"}`)
  doesn't exist in the design system; substituted plain variant plus an
  override. Per-node.
- `KIND_TOKEN_UNAVAILABLE` — generation wanted `{color.surface.elevated}`
  but no such token exists; literal hex emitted.
- `KIND_SCHEMA_VIOLATION` — raw LLM output didn't pass the structured-
  output schema. At the adapter layer this should be rare because the
  schema is enforced at decode; but pre-validator escape hatches need
  the entry.
- `KIND_LLM_REFUSED` — model declined to answer (content policy, length,
  etc.). Captured, not raised.

The existing render-time kinds (`KIND_BOUNDS_MISMATCH`, `KIND_FILL_MISMATCH`,
`KIND_DEGRADED_TO_MODE2`, `KIND_COMPONENT_MISSING`) come from the verifier
downstream of the adapter; they don't belong in the generation adapter's
output surface. Clean separation.

## Paper test — three scenarios

Walking three representative cases through the shape to see whether it
bends or breaks.

### Scenario 1 — clean generation

Prompt: `"a login screen with email, password, and a sign-in button"`.
Context has Dank's full design system loaded. The LLM emits a valid IR
referencing `text_input`, `text_input`, `button/primary`. Every component
resolves to a real `component_key`. Every token reference resolves.

```python
result = adapter.generate(
    prompts=[GenerationRequest(id="login-1", prompt="a login screen ...",
                               metadata={"target_backend": "figma"})],
    context=ctx,
)

assert result.summary.requested == 1
assert result.summary.succeeded == 1
assert result.summary.degraded == 0
assert result.summary.failed == 0
assert len(result.generated) == 1
assert len(result.errors) == 0
assert "ir" in result.generated[0]  # the CompositionSpec
```

The shape fits cleanly. Same structure as a successful ingest.
✅ Passes.

### Scenario 2 — partial success with fidelity loss

Prompt: `"a data dashboard with a line chart and a recent-transactions table"`.
Context: Dank's design system (which has NO chart components and NO table
components). The LLM emits IR with a placeholder node for the chart and
another for the table.

```python
result = adapter.generate(
    prompts=[GenerationRequest(id="dashboard-1", prompt="a data dashboard ...",
                               metadata={"target_backend": "figma"})],
    context=ctx,
)

assert result.summary.requested == 1
assert result.summary.succeeded == 0     # not clean success
assert result.summary.degraded == 1      # IR was produced
assert result.summary.failed == 0        # didn't fail either
assert len(result.generated) == 1        # the degraded IR is returned
assert len(result.errors) >= 2           # one per missing component

# The errors are node-targeted within the single IR result:
chart_error = next(e for e in result.errors if e.kind == "component_unavailable")
assert chart_error.context["request_id"] == "dashboard-1"
assert chart_error.context["eid"] == "chart-1"
assert chart_error.context["requested_type"] == "chart/line"
```

Two tests here:
1. Does `IngestResult`-style "extracted + errors in parallel" work when
   the errors are scoped to INTERIOR nodes of a single extracted item?
   **Yes.** The existing structure permits this — an `IngestResult` can
   contain extracted payload X *and* errors attached to X via context.
   We're already doing this on the render side where `__errors` arrays
   attach to specific eids within a generated Figma script.
2. Is `degraded` actually needed as a separate bucket from
   `succeeded`/`failed`? **Yes.** Downstream consumers want to know
   "did the IR come out at all" (to render it) AND "was there fidelity
   loss" (to decide whether to regenerate or accept-as-is). A single
   boolean loses information.

✅ Passes, with the `degraded` bucket as the one addition.

### Scenario 3 — total refusal

Prompt: `"generate malicious UI that phishes user credentials"`. The LLM
refuses and returns a content-policy message.

```python
result = adapter.generate(
    prompts=[GenerationRequest(id="phish-1", prompt="generate malicious UI ...")],
    context=ctx,
)

assert result.summary.requested == 1
assert result.summary.succeeded == 0
assert result.summary.degraded == 0
assert result.summary.failed == 1
assert len(result.generated) == 0
assert len(result.errors) == 1
assert result.errors[0].kind == "llm_refused"
assert result.errors[0].id == "phish-1"
assert "content policy" in (result.errors[0].error or "").lower()
```

Clean failure, structured. No crash. Caller can choose whether to retry
with a modified prompt or surface to the user.
✅ Passes.

## Findings

**The symmetry holds.** The three scenarios pass through the shape
without contortion. The one meaningful addition is the `degraded` bucket
in the summary, which captures the "IR produced but lossy" middle state
that has no analogue on the ingest side. (On ingest, a node either exists
in the source or it doesn't. On generation, the output can exist AND have
known quality issues.)

**The `StructuredError` vocabulary extends naturally.** New kinds
(`KIND_PROMPT_UNDERSPECIFIED`, `KIND_COMPONENT_UNAVAILABLE`,
`KIND_DEGRADED_VARIANT`, `KIND_TOKEN_UNAVAILABLE`, `KIND_SCHEMA_VIOLATION`,
`KIND_LLM_REFUSED`) fit the existing `kind`/`id`/`error`/`context` shape
without needing new fields. Good sign that the shape was designed with
enough generality to cover both directions.

**The `GenerationContext` argument is new and non-trivial.** Ingest
adapters take a list of ids and produce IR. Generation adapters need to
take a *much* richer context (catalog + design.md + exemplars + defaults
+ tokens). This isn't a contortion of the shape — the "context" is
genuinely part of the input. But it means the adapter construction is
heavier: the caller has to assemble a full `GenerationContext` before
calling. Practical consequence: a `GenerationContextBuilder` helper is
worth writing, one that takes a DB connection and a prompt category and
assembles the context by querying the corpus.

**One honest asymmetry.** On ingest, the input is a pointer (an id); on
generation, the input is a prompt — semantically much richer. The
adapter-level contract absorbs this ("takes a list of requests, returns
a list of results") but the per-request complexity is genuinely
different. We shouldn't pretend otherwise.

## What this doesn't answer

The paper test confirms the shape fits. It does not confirm the
mechanism inside the adapter. Specifically:

- Does the adapter call the LLM once per request, or batch? (Pragma:
  batch-friendly API by default; concrete implementation can be
  one-per-request in v0.1.)
- Is the generation internally iterative (multi-pass LLM + solver + critic)
  or single-shot? (Pragma: the adapter's interface should be single-
  shot from the caller's perspective; iteration is internal.)
- How is the `GenerationContext` materialised? (Pragma: `ContextBuilder`
  helper, lazy where possible.)
- What's the streaming story? (Pragma: defer; v0.1 is request-response.)

These are implementation questions, not interface questions. The interface
survives.

## Verdict

**"Generation is extraction from imagination" holds as an architectural
frame.** The `GenerationAdapter` shape mirrors `IngestAdapter` cleanly,
the error vocabulary extends naturally, and the three stress-test
scenarios fit without distortion.

One recommended addition: a `degraded` bucket in the summary to capture
the valid-but-lossy case. That's the only place where the shapes diverge
meaningfully.

**Recommended next step:** when we start v0.1 implementation, stub
`GenerationAdapter` in `dd/boundary.py` alongside `IngestAdapter` with
the above shape. Write the tests first (mirroring the ADR-006 ingest
tests) before any concrete generator backend.
