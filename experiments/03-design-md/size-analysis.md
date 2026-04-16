# design.md size analysis

- Source file: `design.md`
- Tokenizer: cl100k_base (tiktoken)
- Total characters: 36,191
- **Total tokens: 11,551**
- Verdict: **prompt-cache** (< 50K tokens)

## Section breakdown (largest first)

| Section | Chars | Tokens | % of total |
| --- | --- | --- | --- |
| Component inventory | 20,552 | 6,013 | 52.1% |
| Token palette | 3,255 | 1,271 | 11.0% |
| Adjacencies | 3,675 | 1,229 | 10.6% |
| Screen archetypes | 2,608 | 950 | 8.2% |
| Missing / gaps | 2,704 | 784 | 6.8% |
| Spacing rhythm | 1,224 | 572 | 5.0% |
| Typography scale | 1,310 | 498 | 4.3% |
| design.md — Dank (Experimental) | 484 | 149 | 1.3% |
| Designer-authored sections (TODO) | 362 | 84 | 0.7% |

## Recommendation

With a design.md under **50K tokens**, the entire artefact fits comfortably inside a single Claude / GPT prompt cache entry and we should treat it as a **static prefix** — prompt-cached once per file, invalidated only when the designer edits the TODO sections or when a fresh extraction materially changes the CKR / token palette.

Retrieval-chunking is not warranted at this size; the retrieval index should instead point at individual *subtree exemplars* from the IR, not at substrings of this file.

If a **new project** had substantially more CKR entries (say, a design system like Carbon or Primer with ~500 shared components), the Component-inventory section would dominate and could push the total toward the 50K–200K band. In that regime the natural split is section-level: cache the tokens / typography / spacing / adjacency sections as a stable prefix, and retrieve the component-inventory rows relevant to each prompt.

### Sanity numbers for extrapolation

- Average component-inventory row: 46.6 tokens (129 CKR entries in this file).
- At 500 CKR entries (a mid-sized public design system) the inventory alone would land near 23,306 tokens, pushing total into the retrieval band.
- At 2,000 CKR entries (Material Design class) it would exceed 93,224 tokens — retrieval-chunked is the only tractable option.

### Concrete wiring recommendation

- Store the full design.md under a **stable cache key** derived from `(file_key, extraction_run_id, design_md_revision)`.
- Put the designer-authored TODO sections at the *end* so their edits don't bust the prefix cache for the deterministic sections.
- Expose the section map (from `size-analysis.json`) so the generator prompt can cheaply reason about how much of the budget each section will consume.
