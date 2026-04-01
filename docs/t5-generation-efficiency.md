# T5 Research: Efficient AI Design Generation

Research compiled 2026-03-31. Focused on practical numbers and real-world performance
for multi-pass AI design generation with critique loops.

---

## 1. Token-Efficient Design Representations

### Raw Numbers: How Big Is a Screen?

| Representation | Tokens (typical screen) | Source |
|---|---|---|
| Raw HTML (full webpage) | ~31,000 median (Design2Code benchmark, 484 pages) | Design2Code, NAACL 2025 |
| Raw DOM (web app page) | 100,000+ | DOM Downsampling research |
| Figma REST API JSON (complex file) | 48MB+ for full file; single screen varies widely | Figma Developer API docs |
| Accessibility tree (Playwright MCP) | 14,500-19,400 per page | Accessibility tree token cost comparison |
| Accessibility tree (optimized/WebClaw) | 3,000-7,800 per page (51-79% smaller) | Same source |
| Mind2Web UI representation (raw) | ~52,000 tokens | UIFormer paper |
| Mind2Web UI representation (UIFormer optimized) | ~6,100 tokens (88% reduction) | Same source |
| Android screen (raw) | 2,750-3,450 tokens | Same source |
| Android screen (UIFormer optimized) | 596-1,484 tokens (49-54% reduction) | Same source |

**Key insight**: UI representations account for 80-99% of total tokens in generation
requests. This is THE optimization target.

### Representation Format Comparison

| Format | Token Efficiency | LLM Comprehension | Practical Notes |
|---|---|---|---|
| Full node-tree JSON | Worst (verbose keys, deep nesting) | Good (explicit structure) | Figma API output is enormous |
| TOON (tabular format) | 60% fewer tokens than JSON for same data | Good | Replaces repetitive JSON syntax with compact tabular layout |
| Markdown | ~50% fewer tokens than equivalent HTML | Excellent (trained on it) | Best for text-heavy content |
| HTML (vs JSON for actions) | 11% fewer tokens than JSON, 3.9% better success | Good | Skyvern production findings |
| Custom DSL | Best possible (domain-specific compression) | Requires training/examples | UIFormer DSL achieved 49-88% reduction |
| SiFR schema | 10-50x smaller than raw HTML on complex pages | Good (structured JSON) | Semantic information for representation |
| Declarative spec (structured schema) | Compact (only meaningful properties) | Excellent (constrained output space) | What v0/Bolt effectively do |

### Compression Techniques for UI Trees

1. **UIFormer DSL approach** -- Merge parent-child nodes, strip non-actionable
   elements, keep only semantic hierarchy. Achieved 76.9% reduction in production
   at WeChat with no accuracy loss. Also reduced latency by 26.1% and increased
   throughput by 35.2%.

2. **DOM downsampling (D2Snap)** -- Downsample DOM based on UI features rather than
   extracting individual elements. Hierarchy is the strongest feature for LLM
   performance -- throwing it away hurts more than token savings help.

3. **Interactive-only filtering** -- Only label interactive elements (buttons, inputs,
   links) instead of every DOM node. Reduced refs from 789 to 245 on a GitHub page.

4. **Declarative output schemas** -- Instead of generating arbitrary HTML/CSS, have
   the model output a constrained JSON/DSL describing UI elements. This is what
   Declarative Build should do: define a compact schema that maps directly to Figma
   nodes.

### Recommendation for Declarative Build

For the use case of generating Figma designs from descriptions, the optimal
representation is a **custom declarative schema** that:

- Uses short property names (e.g., `w` not `width`, `bg` not `backgroundColor`)
- Omits default values (only specify what differs from defaults)
- Uses references for repeated patterns (e.g., `$heading` style ref)
- Flattens where possible (avoid deep nesting)
- Estimated token cost: **500-2,000 tokens per screen** for a compact declarative spec
  vs. 15,000-50,000 for equivalent raw JSON

---

## 2. Cascade / Progressive Validation

### The Validation Pyramid

| Level | Cost | Catches | Examples |
|---|---|---|---|
| **Schema validation** | ~0 tokens (code) | 30-40% of issues | Missing required fields, invalid types, out-of-range values |
| **Rule-based structural** | ~0 tokens (code) | 20-30% of issues | Overlapping elements, text outside bounds, contrast failures, spacing violations |
| **LLM structural critique** | 500-2,000 tokens | 15-25% of issues | Layout logic errors, semantic grouping problems, flow issues |
| **Vision critique** | 1,000-5,000 tokens + image | 10-15% of issues | Visual balance, aesthetic judgment, subtle alignment |

**Total issue coverage**: Rule-based catches ~60-70% without any LLM cost. Adding
a cheap LLM pass catches another 15-25%. Vision is only needed for the remaining
10-15%.

### Visual Critic Without Rendering (ViCR)

Research from Widget2Code and UI-to-Code Visual Critic shows that predicting visual
discrepancy from code alone (without rendering) can achieve comparable performance
to actual screenshot comparison, at much lower cost.

This means: you can potentially skip the expensive render+screenshot+vision step
entirely for most screens, using a code-level critic instead.

### Recommended Cascade

```
Pass 1: Schema validation (free, instant)
  |-- 60-70% of issues caught
  v
Pass 2: Rule engine (free, <100ms)
  |-- Spacing, overlap, contrast, hierarchy depth
  |-- Additional 15-20% caught
  v
Pass 3: Haiku structural check (cheap, ~500 tokens)
  |-- "Does this layout make sense for a login form?"
  |-- Additional 10-15% caught
  v
Pass 4: Vision critique (expensive, only if needed)
  |-- Only for final review or when confidence is low
  |-- Catches remaining 5-10%
```

**Expected result**: 85-90% of generations never need the vision pass.

---

## 3. Model Selection for Cost Efficiency

### Current Claude Pricing (March 2026)

| Model | Input $/MTok | Output $/MTok | Cache Hit $/MTok | Relative Cost |
|---|---|---|---|---|
| Haiku 4.5 | $1.00 | $5.00 | $0.10 | 1x (baseline) |
| Sonnet 4.6 | $3.00 | $15.00 | $0.30 | 3x |
| Opus 4.6 | $5.00 | $25.00 | $0.50 | 5x |
| Opus 4.6 (batch) | $2.50 | $12.50 | -- | 2.5x |
| Sonnet 4.6 (batch) | $1.50 | $7.50 | -- | 1.5x |
| Haiku 4.5 (batch) | $0.50 | $2.50 | -- | 0.5x |

### Task-to-Model Routing Strategy

| Task | Recommended Model | Why |
|---|---|---|
| Schema validation | None (code) | Zero cost |
| Rule-based checks | None (code) | Zero cost |
| Design token lookup | Haiku 4.5 | Simple retrieval |
| Layout structure generation | Sonnet 4.6 | Needs spatial reasoning |
| Component selection | Haiku 4.5 | Pattern matching |
| Full screen composition | Sonnet 4.6 | Complex but not frontier-level |
| Visual critique (screenshot) | Sonnet 4.6 | Vision capability, good enough |
| Novel/creative layout | Opus 4.6 | Only for genuinely hard problems |
| Error recovery/debugging | Sonnet 4.6 | Needs reasoning about what went wrong |

### Cascade Routing Economics

Research shows typical cascade distributions:

- 60-70% of requests handled by cheapest model (Haiku)
- 25-30% escalated to mid-tier (Sonnet)
- 3-5% escalated to top-tier (Opus)

This produces **50-60% cost reduction** vs. using Sonnet for everything, and
**80-87% reduction** vs. using Opus for everything.

### Flash/Screening Models

For high-throughput screening (e.g., batch-validating 100 generated screens), Haiku
in batch mode at $0.50/MTok input is the clear choice. At ~1,500 tokens per screen
spec, validating 100 screens costs approximately $0.075 input + output.

---

## 4. Caching and Reuse

### Prompt Caching

Anthropic's prompt caching delivers the single highest ROI optimization:

| Operation | Cost Multiplier | Savings vs Base |
|---|---|---|
| Cache write (5 min) | 1.25x base input | Pays off after 1 reuse |
| Cache write (1 hour) | 2x base input | Pays off after 2 reuses |
| Cache hit/read | 0.1x base input | **90% savings** |

**For design generation, cache these (they rarely change)**:
- System prompt with design system rules (~2,000-5,000 tokens)
- Design token definitions (~1,000-3,000 tokens)
- Component library reference (~2,000-10,000 tokens)
- Style guide constraints (~1,000-2,000 tokens)

Total cacheable prefix: ~6,000-20,000 tokens. At Sonnet pricing, caching this saves
$0.016-$0.054 per request after the first. Over 100 screens, that is $1.60-$5.40
saved on input alone.

### Pattern Caching (Application Level)

No standard approach exists yet, but the following strategies are used in practice:

1. **Template library** -- Store successful generation outputs as templates. When a
   new request matches a known pattern (e.g., "login form", "settings page"), start
   from the template rather than generating from scratch. Reduces output tokens by
   50-80%.

2. **Critique result caching** -- If a structural critique identifies "buttons should
   be 48px minimum touch target", store that as a rule. Future generations include it
   as a constraint, avoiding the critique pass entirely.

3. **Component-level caching** -- Generate individual components once, then compose
   screens from cached components. A "primary button" generated once can be reused
   across all screens.

### How Existing Tools Handle This

- **v0 (Vercel)**: Uses shadcn/ui as a component library, effectively caching known
  component patterns. Generates React with constrained output space. Runs inputs at
  $1.50/MTok, outputs at $7.50/MTok.
- **Bolt.new**: Includes full filesystem context in every request (expensive). Error
  loops multiply token cost -- a single auth bug fix can consume 3-5M tokens across
  3 attempts.
- **Emergent**: Uses design rules for validation (button states, form validations),
  avoiding LLM calls for structural checks.

---

## 5. Benchmarks and Real Numbers

### Self-Refine Convergence Formula

Using the mathematical model from Yang et al. (2025):

```
Acc_t = Upp - alpha^t * (Upp - Acc_0)
```

Where Upp = CS / (1 - CL + CS) is the theoretical accuracy ceiling and alpha = CL - CS
is the convergence rate (CL = confidence level, CS = critique score).

With typical parameters (CL=0.9, CS=0.4, alpha=0.5, Upp=0.80):

| Round | Improvement Share | Cumulative |
|---|---|---|
| 1 | 50% | 50% |
| 2 | 25% | 75% |
| 3 | 12.5% | 87.5% |
| 4 | 6.25% | 93.75% |
| 5 | 3.125% | 96.875% |

**Key takeaway**: Rounds 1 and 2 account for 75% of the total improvement the loop
will ever achieve. Stop at 2-3 iterations. Hard cap at 5.

Self-Refine (Madaan et al.) achieves 5-40% improvement across tasks (average ~20%
absolute improvement), typically within 2-4 iterations.

### Tokens Per Screen Generation

| Scenario | Input Tokens | Output Tokens | Total | Source |
|---|---|---|---|---|
| Design2Code median webpage | ~5,000 (prompt + image) | ~31,000 (full HTML) | ~36,000 | Design2Code benchmark |
| Compact declarative spec (estimated) | ~3,000 (prompt + constraints) | ~1,500 (structured output) | ~4,500 | Estimated from UIFormer data |
| Bolt.new simple page | Unknown exact | Unknown exact | Est. 50,000-100,000 | Inferred from error loop costs |
| v0 component generation | ~1,500 (prompt) | ~2,000-5,000 (React component) | ~3,500-6,500 | Inferred from pricing |

### Cost Per Screen (Single Pass, No Critique)

| Model | Input Cost | Output Cost | Total | Notes |
|---|---|---|---|---|
| Haiku 4.5 (compact spec) | $0.003 | $0.0075 | **$0.01** | Structural generation only |
| Sonnet 4.6 (compact spec) | $0.009 | $0.0225 | **$0.03** | Good layout reasoning |
| Opus 4.6 (compact spec) | $0.015 | $0.0375 | **$0.05** | Overkill for most screens |
| Sonnet 4.6 (full HTML) | $0.015 | $0.465 | **$0.48** | Design2Code-style generation |
| Sonnet 4.6 (cached prefix) | $0.003 | $0.0225 | **$0.025** | With 6K cached tokens |

### Cost Per Screen (With Critique Loop)

| Strategy | Iterations | Cost per Screen | Time | Notes |
|---|---|---|---|---|
| Single-pass Sonnet | 1 | $0.03 | ~3s | No quality assurance |
| Cascade validation (no vision) | 1 + rules | $0.03 | ~3s | Catches 85% of issues for free |
| Sonnet generate + Haiku critique x2 | 3 | $0.08 | ~8s | Good quality/cost balance |
| Sonnet generate + Sonnet critique x2 | 3 | $0.12 | ~10s | Higher quality critique |
| Sonnet generate + vision critique x1 | 2 | $0.08 | ~6s | Vision adds ~$0.02 for screenshot |
| Full loop: Sonnet + 3 critiques + vision | 5 | $0.20 | ~15s | Diminishing returns after iteration 3 |
| Bolt.new error recovery (worst case) | 3-5 | $3-8 | Minutes | Full context per request |

### Time Per Generation

| Phase | Estimated Time | Notes |
|---|---|---|
| Schema validation | <10ms | Local code |
| Rule engine | <100ms | Local code |
| Haiku generation (1.5K output) | 1-2s | Fastest model |
| Sonnet generation (1.5K output) | 2-4s | Good balance |
| Sonnet vision critique | 3-5s | Image processing adds latency |
| Figma API write | 0.5-2s | Depends on node count |
| **Total (optimal pipeline)** | **3-8s** | Single pass with rule validation |
| **Total (with 1 critique loop)** | **6-12s** | Most practical approach |

### Agent Loop Token Economics

General finding: agents make 3-10x more LLM calls than simple chatbots. A single
user request can trigger planning, tool selection, execution, verification, and
response generation, easily consuming 5x the token budget of a direct completion.
An unconstrained agent solving a software engineering task can cost $5-8 per task.

---

## 6. Practical Recommendations

### Architecture for Declarative Build

```
User prompt
  |
  v
[Haiku] Intent classification + component selection (~500 tokens)
  |
  v
[Cached prefix] Design system rules + tokens + component library
  |
  v
[Sonnet] Generate declarative spec (~1,500 tokens output)
  |
  v
[Code] Schema validation (free)
  |
  v
[Code] Rule engine: spacing, contrast, overlap, hierarchy (free)
  |
  v
  |-- 85% pass --> Write to Figma
  |
  |-- 15% fail --> [Haiku] Structural fix suggestions (~500 tokens)
  |                  |
  |                  v
  |                [Sonnet] Regenerate specific section (~800 tokens)
  |                  |
  |                  v
  |                Write to Figma
  |
  v
[Optional] [Sonnet+vision] Final visual QA (only on user request)
```

### Expected Cost Per Screen

- **Best case** (single pass, rules pass): **$0.025-0.03**
- **Typical case** (1 fix iteration): **$0.05-0.08**
- **Worst case** (3 iterations + vision): **$0.15-0.20**
- **At scale** (100 screens with batch API): **$2.50-5.00 total**

### Key Optimizations Ranked by Impact

1. **Compact declarative schema** -- 10-20x fewer output tokens vs raw HTML/CSS.
   Single biggest win.
2. **Prompt caching** -- 90% savings on the ~6-20K token design system prefix.
   Second biggest win.
3. **Rule-based validation first** -- Eliminates 85% of critique LLM calls.
   Third biggest win.
4. **Model routing** -- Haiku for simple tasks, Sonnet for generation.
   50-60% cost reduction.
5. **Batch API** -- 50% discount for non-interactive generation.
   Good for bulk operations.
6. **Template/pattern reuse** -- Start from known-good patterns, not blank canvas.
   Reduces output by 50-80%.
7. **Stop at 2-3 iterations** -- 75-87.5% of improvement captured.
   Diminishing returns after that.

---

## Sources

### Academic Papers
- [Design2Code benchmark (NAACL 2025)](https://aclanthology.org/2025.naacl-long.199/)
- [UIFormer: UI representation optimization](https://arxiv.org/abs/2512.13438)
- [Self-Refine: Iterative refinement with self-feedback](https://arxiv.org/abs/2303.17651)
- [UI-to-Code Visual Critic without rendering](https://arxiv.org/abs/2305.14637)
- [Widget2Code](https://arxiv.org/pdf/2512.19918)
- [DOM Downsampling for LLM web agents](https://arxiv.org/html/2508.04412v1)
- [Model cascading for code](https://arxiv.org/html/2405.15842)

### Engineering & Industry
- [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Anthropic prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Claude model selection guide](https://www.sitepoint.com/claude-model-selection-framework/)
- [v0 vs Bolt comparison](https://www.index.dev/blog/v0-vs-bolt-ai-app-builder-review)
- [Skyvern: HTML vs JSON for LLM actions](https://www.skyvern.com/blog/how-we-cut-token-count-by-11-and-boosted-success-rate-by-3-9-by-using-html-instead-of-json-in-our-llm-calls/)
- [Accessibility tree token costs](https://dev.to/kuroko1t/how-accessibility-tree-formatting-affects-token-cost-in-browser-mcps-n2a)
- [TOON format for token efficiency](https://betterstack.com/community/guides/ai/toon-explained/)
- [SiFR schema for UI representation](https://dev.to/alexey_sokolov_10deecd763/-runtime-snapshots-7-inside-sifr-the-schema-that-makes-llms-see-web-uis-acg)
- [Self-correction convergence formula](https://dev.to/yannick555/iterative-review-fix-loops-remove-llm-hallucinations-and-there-is-a-formula-for-it-4ee8)
- [AI agent cost optimization](https://zylos.ai/research/2026-02-19-ai-agent-cost-optimization-token-economics)
- [LLM token optimization guide](https://redis.io/blog/llm-token-optimization-speed-up-apps/)
