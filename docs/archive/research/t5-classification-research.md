# T5 Classification Research — Plugins, Fine-Tuned Models, and Approaches

Compiled 2026-03-31 from 5 research agents covering: structural classification from view hierarchies, bidirectional UI models, vision-based classification, Figma layer labeling plugins, and fine-tuned UI vision models. This document synthesizes ALL findings relevant to the compositional analysis layer's classification problem.

---

## The Classification Problem

Given a subtree of Figma nodes with properties (type, layout direction, sizing, child count, text content, dimensions, component_key), determine:
1. **What canonical component type this subtree represents** (one of ~60 types from component.gallery)
2. **What its internal slot structure is** (image-top, title, subtitle, action-row, etc.)
3. **What its role is in the screen-level skeleton** (header zone, content zone, navigation zone)

This is the foundational capability for the compositional analysis layer described in `docs/t5-compositional-analysis.md`.

---

## 1. Figma Layer Labeling Plugins — Prior Art

### 1.1 What Exists

10+ AI-powered layer naming/classification plugins exist in the Figma Community:

**Screenshot-based classification:**
- **Figma Autoname** (Hugo-Dz) — TensorFlow.js with Google Teachable Machine image classification model. Renders each layer as an image, classifies into ~10 coarse categories (buttons, frames, text, etc.). Open source (MIT), model is swappable (users can train their own via Teachable Machine and provide model.json URL). Skips components and instances intentionally.
  - GitHub: https://github.com/Hugo-Dz/figma_autoname_client_app
  - Figma: https://www.figma.com/community/plugin/1160642826057169962/figma-autoname

**LLM-based naming:**
- **Smart Layer Renamer** — Google Gemini 2.5 Flash. Analyzes layers and produces semantic names.
- **Rename Layers AI Magic (Token Mode)** — Bring-your-own-key (OpenAI, DeepSeek, Perplexity, OpenRouter). Up to 120 layers at once. Design token naming convention support.
- **RenameGPT** — ChatGPT-based.
- **LayerSense** — Free/zero-cost AI renamer. Model undisclosed.
- **AI Auto Naming** — Generates semantic names. Model undisclosed.
- **AI Layer Organizer** — Names layers based on "visual role and content." Goes beyond renaming to organize structure.

**Figma's built-in:**
- **Rename Layers with AI** (native, paid plans) — Uses layer contents, location, and relationship to other selected layers. Structural data analysis, not screenshot-based. Only renames default-named layers ("Frame 42"). Hidden/locked layers skipped. Individual vector shapes NOT renamed. Model undisclosed (likely Anthropic partnership given Config 2024 timing).

### 1.2 Design-to-Code Tools That Classify

**Codia AI VisualStruct:**
- Multi-stage CV pipeline: U-Net segmentation → ResNet/Inception classification → OCR
- Classifies into: buttons, text fields, images, navigation, icons, checkboxes, interactive elements, containers, list views, inputs
- **Outputs structured JSON** with full component hierarchy including parent-child relationships
- Claims 95%+ accuracy (self-reported, community feedback mixed on complex layouts)
- Works from **screenshots only**, not Figma structural data
- https://codia.ai/visual-struct

**Builder.io Visual Copilot:**
- Custom LLM trained on 2+ million design-to-code data points from scratch
- Recognizes design patterns (buttons, navigation, cards) and maps to semantic HTML
- Multi-pass: AI classification → Mitosis compiler → final LLM cleanup
- Uses **Figma structural data** (reads Figma file API), not screenshots
- Component mapping feature lets users map Figma components to code components

**Locofy Lightning:**
- Proprietary "Large Design Model" (LDM) trained on millions of designs and websites
- Distinct from LLMs — focuses on visual/structural patterns
- Auto-detects interactive components, groups layers, applies auto-layout
- "Auto-Components" feature scans designs and suggests reusable components with props
- Uses **Figma structural data** primarily

**Anima:**
- **Automatic Component Detection** — identifies potential components even if not defined as Figma components
- Uses "Visual Analysis" to intelligently analyze designs regardless of structure, naming, or component usage
- Presents detected components in a Components Panel for accept/reject
- Generates semantic HTML (avoids unnecessary div wrappers)
- The closest to our informal pattern recognition problem

### 1.3 Accessibility Plugins

All require manual annotation — none automatically classify elements by role:
- **Include** (eBay, open source) — manual landmarks, headings, reading order
- **Stark** — manual landmarks + focus order, AI-powered alt text suggestions
- **Accessibility Assistant** — manual annotations for interactive elements, headings, images

### 1.4 The Gap

**No existing plugin produces a standardized, machine-readable component taxonomy.**

All produce human-readable names ("hero_section", "nav_bar"), not machine-readable classifications ("this is a Card with slots: image-top, title, subtitle, action-row").

The design-to-code tools (Anima, Locofy, Builder.io) come closest to true classification but:
- Their taxonomies are tied to code generation output, not exposed as standalone APIs
- They classify for HTML/React output, not for compositional analysis
- Codia's VisualStruct is the closest to a pure classification service but works from screenshots only

**What we need that doesn't exist:** Classify Figma node subtrees into the 60 canonical component types WITH internal slot decomposition, using Figma's rich structural data as primary input, and store the result as compositional analysis data. This is genuinely novel.

---

## 2. Structural Classification from View Hierarchies

### 2.1 CLAY (Google, CHI 2022) — The Strongest Evidence

Built a pipeline classifying raw view hierarchy nodes into ~24 semantic UI types (BUTTON, IMAGE, CHECKBOX, TEXT, etc.). Two architectures evaluated:
- **GNN-based model** — preserves tree structure, nodes exchange messages with neighbors
- **Transformer-based model** — self-attention aggregates information from all nodes

**Result: Transformer achieves F1 of 85.9% for type recognition from structured features.**

Key: structured features from view hierarchy ALONE are informative. A heuristic baseline (rule-based mapping from Android class names) is significantly outperformed.

Dataset: 59,555 human-annotated screen layouts.
- Paper: https://arxiv.org/abs/2201.04100
- Dataset: https://github.com/google-research-datasets/clay

### 2.2 Screen Parsing (CMU, UIST 2021) — Container Classification

Three-stage pipeline:
1. Element detection (Faster-RCNN)
2. Hierarchy prediction — stack-based transition parser using bi-LSTM. Outputs: Arc (parent-child edge), Emit (intermediate container), Pop (finish children). Reconstructs UI tree from flat element list.
3. **Container classification** — Deep Averaging Network classifies groups into 7 types (collections, tables, tab bars, etc.)

Outperforms baselines by up to 23%. Directly addresses "determine that a subtree constitutes a Card, TabBar, etc."
- Paper: https://arxiv.org/abs/2109.08763

### 2.3 Design System Grammars — Formal Rules

Formal context-free grammars for component composition:
```
Layout → Navigation? Main Footer?
Content → Card*
Card → Image? Title Description Action*
```

Could serve as basis for rule-based recognition system — match subtrees against grammar productions.
- Nolan Phillips: https://blog.nolanphillips.com/design-system-grammar
- Daniel Eden: https://daneden.me/blog/2017/a-design-system-grammar

### 2.4 Position and Size Heuristics (Alibaba/imgcook)

Semi-automatic labeling where position heuristics automatically classify:
- **Statusbar**: fixed position at screen top, consistent height → near-perfect accuracy
- **Navbar**: fixed position below status bar → near-perfect accuracy
- **Tabbar**: fixed position at screen bottom → near-perfect accuracy
- Other components require detection. Overall ~75% mAP across 10 types.

### 2.5 Magic Layouts (CVPR 2021)

Learns a structural prior over mobile UI layouts encoding common spatial co-occurrence relationships between component types. "A search bar commonly appears at the top with a list below it." Extends object detectors with this learned prior.

### 2.6 UI Grammar (Lu & Tong, 2023-2024)

Context-free production rules for parent-child relationships in UI screen hierarchies. `A → B` where A is parent type, B is sequence of child types.

**Bidirectional**: Same grammar works for generation (constrain output to valid trees) AND analysis (parse existing tree into derivation). This is the key insight — the grammar IS the shared compositional model.

- Paper: https://arxiv.org/abs/2310.15455

### 2.7 ComUICoder (2025)

Hybrid Semantic-aware Block Segmentation (HSBS) partitions pages into meaningful blocks. Visual-aware Graph-based Block Merge (VGBM) clusters structurally similar blocks into reusable component groups. Closest to automated structural zone detection.

### 2.8 LLM-Based Classification

**Tree-of-Lens (ToL) Agent** (EMNLP 2024): Constructs Hierarchical Layout Tree with fixed 3-layer depth: whole screen → global regions (header, content, nav) → interactive elements. Trained on ASHL dataset (50K bounding boxes). Uses chain-of-lenses reasoning.

**DesignCoder** (2025): "UI Grouping Chains" for hierarchical divide-and-conquer decomposition. 30%+ improvement in tree structure similarity metrics.

**Zero-Shot GUI Generation** (2024): LLMs can reason about UI structure from textual descriptions without training. RAGG approach uses retrieval from GUI repository.

---

## 3. Vision-Based Classification

### 3.1 Best Available Models

| Model | Architecture | Speed | Key Capability | Available |
|-------|-------------|-------|----------------|-----------|
| **OmniParser v2** (Microsoft) | YOLOv8 + Florence-2 | 0.6s/frame (A100) | Detection + icon captioning. GPT-4V icon labeling: 70.5% → 93.8% | HuggingFace (MIT) |
| **UI-DETR-1** (Racine AI) | RF-DETR-M | Fast | 98 UI element types. 70.8% WebClick accuracy | HuggingFace (MIT) |
| **ScreenAI** (Google) | PaLI (ViT + T5) 5B | Moderate | Screen Annotation: (type, bbox, description) per element. SOTA on UI benchmarks | Research only |
| **Ferret-UI** (Apple) | Multimodal LLM | Moderate | Surpasses GPT-4V on ALL elementary UI tasks. Cross-platform (v2) | GitHub (CC-BY-NC) |
| **Ferret-UI Lite** | 3B | On-device | 91.6% ScreenSpot-V2. Chain-of-thought + visual tool-use | GitHub |
| **ShowUI** (CVPR 2025) | Qwen-2-VL 2B | Fast | Rivals 10x larger models. 75.1% zero-shot grounding | HuggingFace |
| **CogAgent** (Tsinghua) | 18B (11V+7L) | Slow | 1120x1120 resolution, bilingual | HuggingFace (academic) |

### 3.2 When Vision Adds Value vs. Structure-Only

**Vision helps with:**
- Missing or incorrect structural metadata
- Icon and image classification (structure says "image", vision says "search icon")
- Visual similarity to known patterns (unusual markup but LOOKS like a Card)
- Cross-platform consistency (same component, different structural representations)
- Custom/non-standard components
- Rendered state (checked vs. unchecked, open vs. closed)

**Structure is sufficient for:**
- Standard widgets with proper accessibility labels
- Components with clear type info in tree (Figma component instances with names)
- Text-based classification (button text, label text)
- Layout relationships (parent-child, sibling order)

### 3.3 Hybrid Approaches

**UIBert** (Google, 2021): Joint image-text model. Structured + visual features are "self-aligned." **+5-9% accuracy** over single modality.

**Screen2AX** (July 2025): Reconstructs accessibility tree FROM screenshots with 77-79% F1. 2.2x improvement over native accessibility trees. Proves vision can augment/validate structural analysis.

**UIED**: Combines old-fashioned CV (edge detection, contours) with CNN classifier. Neither alone is best — the combination handles GUI-specific challenges.

### 3.4 Vision-Only Accuracy Ceiling

**70-80% for fine-grained component classification** from screenshots alone. Hybrid vision+structure gets +5-9%. Structure-only with good metadata (Figma provides this) is likely already above vision-only for standard components.

### 3.5 Error Modes

1. Non-text elements (icons/widgets) — all models struggle
2. Touch target vs. visual element mismatch — vision finds the visible element but misses padding
3. Tiny targets — ScreenSpot-Pro average target is 0.07% of screen area
4. Nested/overlapping components — vision detects inner elements but misses outer container
5. Custom styled components — heavily styled button doesn't look "standard"
6. State-dependent appearance — same component looks different when hovered/focused/disabled

---

## 4. Fine-Tuned Models Available Now

### 4.1 For Component TYPE Classification

| Model | Size | CPU? | Does type classification? | Where |
|-------|------|------|--------------------------|-------|
| **Roboflow YOLO (UIed)** | YOLOv8 | Yes | **Yes — 61 element classes** | Roboflow Universe |
| **GUIClip** | CLIP B/32 | Yes | Via embedding similarity (zero-shot) | HuggingFace (academic) |
| **Florence-2** | 0.23B | Marginal | Via captioning (free-text → map to type) | HuggingFace |
| **OmniParser v2** | YOLO+Florence | Single 4090 | Detection + captioning | HuggingFace (MIT) |
| **web-form-ui-field-detection** | YOLOv8 | Yes | Form field types | HuggingFace |

**Key finding: most specialized GUI models focus on grounding/locating (WHERE to click), not classifying (WHAT TYPE).** The YOLO-based detectors and CLAY-based approaches are the best for actual type classification.

### 4.2 For Embedding-Based Zero-Shot Classification

**GUIClip** — CLIP fine-tuned on 303K app screenshots. Available on HuggingFace. Academic license. Runs on CPU. Could enable similarity-based classification:
1. Create reference set of canonical component type renderings
2. Embed unknown elements
3. Classify by nearest neighbor in embedding space

### 4.3 For Fine-Tuning a Custom Classifier

**Best candidate: Florence-2 at 0.23B** — small, fast to fine-tune, well-documented pipeline. CLAY dataset provides 59K screens with semantic type labels for training data. Roboflow provides tooling for fine-tuning Florence-2, PaliGemma, and Qwen2-VL on custom datasets.

**Smol2Operator** (HuggingFace, 2025): Fully open 2.2B VLM pipeline. Two-phase SFT transforms a model with zero grounding capability into a capable GUI agent (+41% on ScreenSpot-v2). All training code, data processing, datasets, and checkpoints released. Could serve as a reference architecture for building our own classifier.

### 4.4 Training Datasets

| Dataset | Size | Content | Best for |
|---------|------|---------|----------|
| **CLAY** | 59K layouts | Denoised RICO, semantic type labels | Training classifiers |
| **RICO** | 66K UIs | Screenshots + view hierarchies | General UI understanding |
| **MobileViews** | 600K+ pairs | Modern Android, screenshot-VH pairs | Large-scale training |
| **MUD** | 18K UIs | Noise-filtered modern Android | Clean training data |
| **WebUI** | 400K pages | Web screenshots + accessibility trees | Web component detection |
| **OS-Atlas** | 13M+ elements | Cross-platform GUI elements | Large-scale grounding |

**No Figma-specific dataset exists.** A recent EICS 2025 paper introduces a pipeline converting HTML UIs to Figma-compatible JSON, but no large-scale public Figma-native dataset is available. This is a gap.

### 4.5 Edge/Local Deployment

- **YOLO models**: ONNX, TensorRT, CoreML, TFLite export. YOLOv8 Nano runs sub-second on consumer hardware.
- **GUIClip** (CLIP B/32): ~150M params, runs easily on CPU
- **Florence-2** (0.23B): Small enough for CPU inference
- **Apple Silicon / MLX**: Qwen3-VL, SmolVLM2 convertible to MLX format

---

## 5. Bidirectional UI Models — The Shared Compositional Model

### 5.1 Catalog-Constrained Generation (Dominant 2025-2026 Pattern)

**A2UI** (Google, Dec 2025): Client maintains a catalog of trusted, pre-approved components. Agent can only request from that catalog. Declarative data, not executable code.

**json-render** (Vercel, Jan 2026, 13K+ stars): Developers define permitted components using **Zod schemas**. LLM generates JSON constrained to that catalog. Framework renders progressively. **The Zod schema serves as both generation constraint AND validation/analysis schema.** Ships with 36 pre-built shadcn/ui components.

**Open-JSON-UI** (OpenAI): Similar catalog-constrained approach.

**Relevance:** The catalog-constrained pattern maps directly to our architecture. The DB's token vocabulary + component vocabulary IS the catalog. Generation is constrained to it. Analysis decomposes against it. Same schema, both directions.

### 5.2 UI Grammar (Context-Free Production Rules)

Grammar rules like `Screen → Header Content Footer` and `Card → Image? Title Description Action*` enable:
- **Generation**: Produce valid trees by following rules
- **Analysis**: Parse existing trees into derivations
- **Validation**: Check tree conformance

This is the formal backbone of the Pattern Language's compositional model.

### 5.3 SpecifyUI — SPEC as Shared Semantic Layer

SPEC Embedding = vision-centered IR making design intent explicit. Same representation used to (a) extract specifications from existing designs and (b) guide generation of new designs. Closest academic work to a shared analysis+generation representation.

### 5.4 UISearch — Structural Similarity via Graph Embeddings

Converts UI screenshots into attributed graphs encoding hierarchical + spatial relationships. Contrastive graph autoencoder learns embeddings. **0.92 Top-5 accuracy** on 20K screens, 47.5ms latency.

**Key finding: structural embeddings achieve better discriminative power than vision encoders.** Component tree structure is more useful for finding similar UIs than pixel similarity.

### 5.5 Slot-Filling as Unifying Primitive

The slot model appears everywhere:
- Web Components: `<slot name="...">`
- React: children, named props, render props
- Radix UI: asChild/Slot delegation (most rigorous practical model)
- Figma: component properties (BOOLEAN → visibility slot, TEXT → content slot, INSTANCE_SWAP → component slot, VARIANT → configuration slot)
- SDUI: sections within screen layouts
- A2UI/json-render: component props defined by schemas

**A bidirectional model should represent all composition as slot-filling:** analysis decomposes UI into components with filled slots; generation fills empty slots with content.

### 5.6 No Formal Round-Trip Guarantees Exist

Lens theory from PL research provides the theoretical framework (GetPut/PutGet laws). No one has instantiated it for UI transformations. Practical systems (Figma MCP, UXPin Merge) achieve approximate bidirectionality through engineering, not formal guarantees.

---

## 6. The Recommended Classification Cascade for Declarative Design

Based on ALL research, the recommended approach for classifying Figma node subtrees into canonical component types:

```
Step 1: Formal component matching (free, exact)
  → Nodes with component_key → lookup against canonical types + aliases
  → Figma gives us this for free on component instances
  → Coverage: 60-80% in well-structured files

Step 2: Structural heuristics + text content (free, ~85-90%)
  → Position/size rules: top fixed-height = Header, bottom fixed = Nav
    (CLAY proved 85.9% F1 from structure alone)
  → Text content: "Submit"/"Save" = Button, date patterns = Datepicker
  → Auto-layout analysis: direction + children types → pattern match
  → Design grammar matching: Card → Image? Title Subtitle Action*
  → Figma data is RICHER than any benchmark dataset used:
    component keys, auto-layout, semantic layer names, full properties

Step 3: LLM classification (cheap, Haiku, ~$0.01-0.02/screen)
  → Compact subtree description → Haiku → canonical type
  → Only for unclassified or low-confidence nodes from Steps 1-2
  → ~500-1,000 tokens per classification
  → Run once, cache permanently

Step 4: Vision fallback (optional, for ambiguous/custom components)
  → Option A: GUIClip embedding similarity to reference components (CPU, fast)
  → Option B: Florence-2 captioning → map free-text to canonical type
  → Option C: OmniParser v2 detection + captioning (GPU required)
  → Only for the ~5-10% that structural analysis can't resolve
  → Vision tops out at 70-80% alone; its value is the long tail

Step 5: Manual review / user accept-reject (for novel components)
  → Components that don't match any canonical type
  → User can create new types or confirm classification
  → Feeds back into the classification system over time
```

### Why This Works Better for Figma Than for Android/Web

Figma gives us structural data that's RICHER than any benchmark:
- **component_key**: Exact component identity (when present)
- **Auto-layout direction/sizing/alignment**: Direct layout intent, not inferred
- **Layer names**: Often semantically meaningful (designers name things)
- **Full property data**: Fills, strokes, typography, effects — complete visual description
- **Instance overrides**: What the designer changed from the default component
- **No rendering noise**: Unlike Android view hierarchies or web DOM, Figma's tree represents design intent, not implementation artifacts

CLAY achieved 85.9% F1 on noisy Android view hierarchies. We should exceed that baseline before adding any vision or LLM classification.

---

## 7. The Custom Classifier Question

Building a custom classifier for our 60 canonical component types is potentially necessary because:

1. **No existing model classifies into our specific taxonomy** — YOLO models use their own 21-98 element types, CLAY uses ~24 types, none map to component.gallery's 60 canonical types
2. **Figma structural data is a unique input format** — no existing model is trained on Figma node trees
3. **Our requirements are specific** — we need BOTH type classification AND slot decomposition, not just bounding boxes

### Options for Building a Custom Classifier

**Option A: Rule-based + LLM hybrid (no training required)**
- Design grammar rules for the 60 canonical types
- Use LLM (Haiku) for ambiguous cases with the 60 types as the classification vocabulary
- Advantage: No training data needed, no model training infrastructure
- Disadvantage: Accuracy ceiling limited by rule quality and LLM's zero-shot capability

**Option B: Fine-tune Florence-2 (0.23B) on synthetic Figma data**
- Generate synthetic training data: programmatically create Figma designs with known component types
- Fine-tune Florence-2 to classify Figma subtree descriptions into the 60 types
- Advantage: Proven fine-tuning pipeline, lightweight model, well-documented
- Disadvantage: Need to create training data, maintain fine-tuned model

**Option C: GUIClip embedding + nearest-neighbor**
- Create a reference embedding database: render canonical examples of each of the 60 types
- For unknown components, crop screenshot → embed → find nearest reference
- Advantage: Zero-shot, no training, extensible (add new types by adding reference images)
- Disadvantage: Academic license, accuracy limited by embedding quality for UI

**Option D: Hybrid approach (recommended)**
- Steps 1-2 (formal matching + heuristics) handle 80-90%
- Step 3 (LLM) handles another 5-10%
- Step 4 (vision embedding) handles the remaining 5%
- No custom model training needed for v1
- Evaluate accuracy, decide if fine-tuning is needed based on real error rates

### The Pragmatic Path

Start with Option D (no training required). Measure accuracy on the Dank file's 338 screens. If Steps 1-3 achieve >90% accuracy, vision is optional. If not, evaluate whether the errors are systematic (need better heuristics) or long-tail (need vision/embeddings).

Building a fully custom classifier is a significant engineering investment. It should only be undertaken if the simpler cascade demonstrably fails on real Figma files.

---

## 8. Source Index

### Figma Plugins
- Figma Autoname: https://github.com/Hugo-Dz/figma_autoname_client_app
- Figma built-in rename: https://help.figma.com/hc/en-us/articles/24004711129879
- Codia VisualStruct: https://codia.ai/visual-struct
- Anima Component Detection: https://www.animaapp.com/blog/product-updates/announcing-automatic-component-detection-in-anima/
- Builder.io Visual Copilot: https://www.builder.io/blog/figma-to-code-visual-copilot
- Locofy: https://www.locofy.ai/

### Structural Classification
- CLAY: https://arxiv.org/abs/2201.04100 / https://github.com/google-research-datasets/clay
- Screen Parsing: https://arxiv.org/abs/2109.08763
- UI Grammar: https://arxiv.org/abs/2310.15455
- ComUICoder: https://arxiv.org/html/2602.19276
- DesignCoder: https://arxiv.org/abs/2506.13663
- Tree-of-Lens: https://arxiv.org/abs/2406.19263
- Magic Layouts: https://arxiv.org/abs/2106.07615

### Vision Models
- OmniParser v2: https://huggingface.co/microsoft/OmniParser-v2.0
- UI-DETR-1: https://huggingface.co/racineai/UI-DETR-1
- Ferret-UI: https://machinelearning.apple.com/research/ferretui-mobile
- ShowUI: https://huggingface.co/showlab/ShowUI-2B
- Screen2AX: https://arxiv.org/abs/2507.16704
- GUIClip: https://huggingface.co/Jl-wei/guiclip-vit-base-patch32
- Smol2Operator: https://huggingface.co/blog/smol2operator

### Bidirectional Models
- A2UI: https://github.com/google/A2UI/
- json-render: https://github.com/vercel-labs/json-render
- SpecifyUI: https://arxiv.org/html/2509.07334v1
- UISearch: https://arxiv.org/abs/2511.19380
- Bridging Gulfs: https://arxiv.org/abs/2601.19171

### Datasets
- CLAY: https://github.com/google-research-datasets/clay
- RICO: https://interactionmining.org/rico
- MobileViews: https://arxiv.org/html/2409.14337v2
- MUD: https://github.com/sidongfeng/MUD
- WebUI: https://github.com/js0nwu/webui
- OS-Atlas data: https://huggingface.co/datasets/OS-Copilot/OS-Atlas-data
- Roboflow UI datasets: https://universe.roboflow.com/uied/ui-element-detect
