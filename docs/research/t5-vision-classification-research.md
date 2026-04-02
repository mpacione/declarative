# T5 Vision-Based UI Component Classification Research

## Executive Summary

Vision-based UI classification is a rapidly maturing field, driven primarily by the GUI agent / computer-use boom of 2024-2025. The key finding: **vision alone is not the answer, but vision + structure hybrids consistently outperform either approach in isolation**. For Declarative Design's component classification pipeline, vision is most valuable as a verification/fallback layer and for catching things structural analysis misses (visual styling, rendered appearance, icon semantics).

---

## 1. Vision-Based UI Element Detection and Classification

### 1.1 OmniParser (Microsoft, 2024-2025) -- The Current Standard

Architecture: YOLOv8 (fine-tuned) for interactive element detection + Florence-2 (fine-tuned) for icon captioning/description.

**Key numbers:**
- **0.6s per frame** on A100 GPU, **0.8s on RTX 4090** (V2, Feb 2025)
- GPT-4V icon labeling accuracy: 70.5% baseline -> **93.8% with OmniParser** preprocessing
- ScreenSpot Pro grounding: GPT-4o alone = 0.8% -> **OmniParser+GPT-4o = 39.6%**
- V2 reduced latency by 60% vs V1 via smaller icon caption image sizes
- Detection threshold: 0.05 (conservative, catches more elements)

**What it detects:** Buttons, icons, text fields, interactive regions. Trained on curated web page data with automatic annotation of clickable/actionable regions.

**Relevance to Declarative Design:** OmniParser's approach (detect interactable regions + caption them) maps well to component classification. The detection model finds bounding boxes; the caption model describes what each element does. This two-stage approach could be adapted: detect component regions from a Figma render, then classify each region.

Sources: [OmniParser GitHub](https://github.com/microsoft/OmniParser), [OmniParser V2 - Microsoft Research](https://www.microsoft.com/en-us/research/articles/omniparser-v2-turning-any-llm-into-a-computer-use-agent/)

### 1.2 UI-DETR (2024-2025)

A fine-tuned RF-DETR-M specifically for UI element detection. Identifies **98 UI element types**.

**Key numbers:**
- **70.8% accuracy on WebClick benchmark** (vs 58.8% for OmniParser)
- Optimized detection threshold of 0.35 (vs 0.05 for OmniParser)
- Prioritizes robust localization over fine-grained classification -- the insight being that knowing WHERE interactive elements are matters more than distinguishing dozens of subtypes

**Architecture insight:** Uses RF-DETR (transformer-based detector), not YOLO. Transformers handle overlapping/nested UI elements better than anchor-based detectors because they use set prediction (no NMS post-processing needed).

Source: [UI-DETR-1 on Hugging Face](https://huggingface.co/racineai/UI-DETR-1)

### 1.3 YOLO Variants for UI Detection

Multiple studies have benchmarked YOLO models on UI element detection:

**Best reported numbers (2024):**
- YOLOv9 fine-tuned: **up to 95.5% mAP** when adapted from desktop to web interfaces
- YOLOv5: best at AP@0.5
- YOLOv7: best at AP[0.5:0.95] (outperforms v5, v6, v8 by 1.3-3.4%)
- YOLOv8 on Rico dataset: **mAP50 = 0.56**, precision 0.58, recall 0.55
- YOLOv8 trained on VNIS dataset: detects **21 UI element types** from mobile screenshots

**Key insight:** YOLO models work well for coarse detection (find all elements) but struggle with fine-grained classification of component types (is this a Card or a Section?). The 95.5% mAP number is cross-domain transfer (desktop->web), not 21-class classification.

Sources: [YOLO GUI Detection paper](https://arxiv.org/html/2408.03507v1), [YOLOv8 Mobile UI Training](https://medium.com/@eslamelmishtawy/how-i-trained-yolov8-to-detect-mobile-ui-elements-using-the-vnis-dataset-f7f4b582fc09)

### 1.4 ScreenAI (Google, 2024)

5B parameter Vision-Language Model for UI and infographics understanding.

**Architecture:** PaLI backbone + pix2struct flexible patching (preserves aspect ratio). Uses DETR-based layout annotator internally.

**Key capability -- Screen Annotation task:** Identifies UI element type, location (bounding box), and description. Element types include: image, pictogram, button, text, and others.

**Numbers:**
- State-of-the-art on WebSRC and MoTIF (UI tasks)
- Best-in-class on Chart QA, DocVQA, InfographicVQA vs models of similar size
- Only 5B parameters (much smaller than GPT-4V class models)

**Relevance:** ScreenAI's Screen Annotation task is essentially what we want -- given a screenshot, output a structured list of (type, bounding_box, description) for each UI element. The question is whether this granularity maps to our component taxonomy (Card, Toggle, Datepicker, etc.) or stays at coarser levels (button, text, image).

Sources: [ScreenAI Paper](https://arxiv.org/abs/2402.04615), [Google Research Blog](https://research.google/blog/screenai-a-visual-language-model-for-ui-and-visually-situated-language-understanding/)

### 1.5 Ferret-UI (Apple, 2024)

Multimodal LLM specifically for mobile UI understanding. ECCV 2024.

**Key innovations:**
- "Any resolution" processing: splits screens into sub-images based on aspect ratio (portrait -> horizontal split, landscape -> vertical split)
- Handles the unique challenge of UI: elongated aspect ratios + very small objects of interest (icons, tiny text)
- Trained on elementary UI tasks: icon recognition, find text, widget listing, detailed description

**Numbers:**
- **Surpasses GPT-4V on ALL elementary UI tasks**
- Supports referring (what is at this location?) and grounding (where is this element?)

**Ferret-UI 2** extends to cross-platform: iPhone, Android, iPad, Webpage, AppleTV.

**Relevance:** Ferret-UI demonstrates that UI-specific fine-tuning dramatically improves VLM performance on UI tasks. A model fine-tuned for Figma component classification would likely far exceed general-purpose VLM accuracy.

Sources: [Ferret-UI - Apple ML](https://machinelearning.apple.com/research/ferretui-mobile), [Ferret-UI 2](https://machinelearning.apple.com/research/ferret-ui-2)

### 1.6 ShowUI (CVPR 2025)

Vision-Language-Action model for GUI agents. Only 2B parameters.

**Key innovations:**
- UI-Guided Visual Token Selection: builds patch-wise connected graph from screenshots, selects representative tokens per component
- **Achieves grounding accuracy rivaling models 10x its size**
- 90% fewer hallucinated actions than larger models

**Numbers:** Won Outstanding Paper Award at NeurIPS 2024 Open-World Agents workshop.

Source: [ShowUI GitHub](https://github.com/showlab/ShowUI)

### 1.7 SeeClick (ACL 2024)

Visual GUI agent that relies ONLY on screenshots for task automation (no DOM, no accessibility tree).

**Key finding:** Surpassed CogAgent (a strong baseline) with a smaller model size and less training data. However, **all models struggle with locating icons/widgets** -- non-text elements remain hard for vision-only approaches.

**Important insight for us:** VLMs tend to localize visually salient objects (text, icons) whereas actual interactive targets often include surrounding whitespace/padding. This means vision-based detection may identify the visual element but miss the full component boundary.

Source: [SeeClick Paper](https://arxiv.org/abs/2401.10935)

---

## 2. Combined Vision + Structure Approaches

### 2.1 UIBert (Google, 2021 -- still foundational)

Transformer-based joint image-text model for UI understanding.

**Key insight:** Heterogeneous features in a UI are self-aligned -- image and text features of UI components are predictive of each other. Five pretraining tasks exploit this self-alignment.

**Numbers:** Outperforms strong multimodal baselines by **up to 9.26% accuracy** on nine downstream UI tasks.

**Relevance:** Validates the hypothesis that combining visual + textual + structural features yields better classification than any single modality.

Source: [UIBert Paper](https://arxiv.org/abs/2107.13731)

### 2.2 Screen2Vec (2021 -- still relevant)

Self-supervised embeddings for GUI screens and components using a Heterogeneous Attention-based Multimodal Positional (HAMP) graph neural network.

**What it combines:** Visual features + structural layout + user interaction context (from trace data). Generates embeddings without manual annotation.

**Relevance for component classification:** Screen2Vec embeddings could theoretically be used to classify components by similarity -- embed a component, find nearest neighbors among reference embeddings of known types.

Source: [Screen2Vec Paper](https://www.semanticscholar.org/paper/Screen2Vec:-Semantic-Embedding-of-GUI-Screens-and-Li-Popowski/b50d3b055d369f390facba2106f75f70d51167c8)

### 2.3 Screen2AX (2025) -- **Most relevant hybrid**

First framework to automatically create accessibility tree metadata from a single screenshot.

**Architecture:** Vision-language models + object detection models -> detect, describe, and organize UI elements hierarchically (tree structure from pixels).

**Key numbers:**
- **77-79% F1 score** in reconstructing complete accessibility trees from screenshots
- **2.2x performance improvement** over native accessibility representations
- **Surpasses OmniParser V2** on ScreenSpot benchmark

**Why this matters for Declarative Design:** Screen2AX proves that you can reconstruct tree structure FROM vision. This is the inverse of what we currently do (start with Figma's tree). But the hybrid approach -- using vision to VALIDATE or AUGMENT an existing tree -- is the sweet spot.

Source: [Screen2AX Paper](https://arxiv.org/abs/2507.16704)

### 2.4 UIED -- Hybrid CV + Deep Learning

Combines old-fashioned computer vision (edge detection, contours) for locating graphical elements with a CNN classifier for classification.

**Key finding:** Neither traditional CV nor deep learning alone is best. The combination handles GUI-specific challenges: overlapping elements, elements very close together, diverse visual styles.

Source: [UIED GitHub](https://github.com/MulongXie/UIED)

### 2.5 When Does Adding Vision IMPROVE Classification vs. Structure-Only?

Based on the research, vision adds value in these specific scenarios:

1. **Missing or incorrect structural metadata** -- When the accessibility tree / view hierarchy is incomplete, noisy, or absent (common in web apps, custom components)
2. **Icon and image classification** -- Structure can tell you "there's an image here" but not what it depicts. Vision identifies icons (search, settings, hamburger menu) that inform component type
3. **Visual similarity to known patterns** -- A component might have unusual structural markup but LOOK like a standard Card/Button/Toggle
4. **Cross-platform consistency** -- The same component looks similar on iOS, Android, and web but has very different structural representations
5. **Custom/non-standard components** -- Developers build custom components that don't map to standard widget types in the tree but visually follow established patterns
6. **Rendered state matters** -- A checkbox that is checked vs. unchecked, a toggle that is on vs. off, a dropdown that is open vs. closed

**When vision is NOT needed (structure is sufficient):**
- Standard platform widgets with proper accessibility labels
- Components with clear type information in the tree (e.g., Figma component instances with names)
- Text-based classification (button text, label text)
- Layout relationships (parent-child, sibling order)

---

## 3. Object Detection vs. Semantic Segmentation for UI

### 3.1 Object Detection (Bounding Boxes)

This is the dominant paradigm for UI. Used by: OmniParser (YOLOv8), UI-DETR (RF-DETR), ScreenAI (DETR-based), and most practical systems.

**Advantages:**
- Fast (YOLO: real-time, DETR: near real-time)
- Well-suited to discrete UI elements (buttons, icons, fields)
- Mature tooling and training pipelines
- Easy to map bounding boxes to component instances

**Limitations:**
- Struggles with nested/overlapping components (Card containing Buttons)
- Bounding box doesn't capture exact component shape
- IoU thresholds can be tricky for UI elements of very different sizes

### 3.2 Semantic Segmentation

Pixel-level classification of UI regions. Less common for component detection.

**Where it helps:**
- Background vs. content region detection
- Zone detection (header/body/footer)
- Identifying layout regions before component-level analysis

**Not practical for:** Individual component classification (too expensive, overkill for discrete elements).

### 3.3 Instance Segmentation

Individual component instances with pixel-precise boundaries. SAM (Segment Anything) could theoretically do this.

**SAM for UI:** SAM is designed for natural images and would need fine-tuning for UI. The rectangular, grid-aligned nature of UI elements means bounding boxes are usually sufficient -- instance segmentation adds cost without much benefit for rectangular components.

**Where SAM-style segmentation helps:** Non-rectangular UI elements (circular avatars, custom shapes, overlapping decorative elements).

### 3.4 Verdict

**Object detection is the right choice for component classification.** Semantic segmentation is useful for zone/layout detection (a preprocessing step), but component classification is fundamentally about identifying discrete objects, not labeling pixels.

---

## 4. OCR and Text-Based Classification

Text content is a powerful signal for component classification. Research consistently shows that combining OCR with visual detection improves accuracy.

### 4.1 How Text Helps Classification

| Text Content | Likely Component |
|---|---|
| "Submit", "Save", "Cancel", "OK" | Button |
| "Search...", "Type here..." | Text Input / Search Bar |
| "Jan", "Feb" or date patterns | Datepicker |
| Long paragraph text | Text Block / Article Body |
| "@username", email patterns | User mention / Email field |
| "$", price patterns | Price display / Payment field |
| "1 of 5", page numbers | Pagination |
| Tab-like labels ("Home", "Profile", "Settings") | Tab Bar / Navigation |

### 4.2 OmniParser's Text Approach

OmniParser uses Florence-2 for icon captioning -- it doesn't just OCR the text, it describes the function of visual elements. This functional description is often more useful than raw text for classification.

### 4.3 Practical Impact

Text is already available in Figma's structured data (no OCR needed). The vision angle adds value when:
- Text is embedded in images/icons (OCR required)
- Text is decorative/styled in ways that hide its semantic role
- Placeholder text vs. actual content needs to be distinguished visually

---

## 5. Layout Analysis and Zone Detection

### 5.1 Screen-Level Zone Detection

Research approaches for identifying high-level screen structure from screenshots:

- **ScreenSeg** (Apple): On-device screenshot layout analysis, detecting header/content/footer zones
- **WebUI dataset**: 400K web pages with screenshots and semantic annotations, used to train zone classifiers
- **CLAY pipeline**: Uses ResNet + GNN + Transformer for two-phase classification (filter invalid nodes, then classify remaining nodes). **F1 scores: 82.7% and 85.9%** for the two phases

### 5.2 Screen Type Classification

Research on classifying entire screens by type (settings, profile, feed, etc.):

- **Rico dataset** (66K UIs from 9.7K Android apps) enables app type and screen type classification
- **MobileViews** (600K+ screenshot-view hierarchy pairs from 20K+ modern apps) used for tappability prediction, element relationship prediction, and UI component identification
- Container type classification: seven types defined (lists, grids, tables, tab bars, etc.)

### 5.3 Navigation Pattern Detection

Vision can detect navigation patterns that may not be explicit in structure:
- Tab bar at bottom of screen (mobile pattern)
- Sidebar navigation (desktop pattern)
- Hamburger menu icon -> drawer navigation
- Breadcrumb trails
- Bottom sheet / modal overlay patterns

**Relevance:** Zone detection from renders could be a useful preprocessing step -- identify "this region is a navigation bar" before classifying individual components within it.

---

## 6. Embedding-Based Approaches

### 6.1 UIClip (UIST 2024)

CLIP fine-tuned for UI design quality assessment. Initialized from CLIP B/32, fine-tuned in four stages.

**Training data:** 2.3M+ UI screenshots (99.9% synthetic via JitterWeb + human-rated BetterApp dataset).

**What it measures:** Design quality, not component type. But the embeddings encode UI-specific visual features that could theoretically be repurposed for component similarity.

**Relevance:** UIClip proves that CLIP fine-tuned on UI data learns meaningful UI-specific representations. A similar approach could be used to fine-tune CLIP for component TYPE classification rather than quality assessment.

Source: [UIClip](https://uimodeling.github.io/uiclip/)

### 6.2 CLIP for Component Classification (Theoretical Approach)

The approach would be:
1. Render each component (or crop its bounding box from a screenshot)
2. Encode with CLIP (or UI-fine-tuned CLIP)
3. Compare against reference embeddings of canonical component types
4. Classify based on cosine similarity

**Advantages:**
- Zero-shot classification possible (describe component types in text, match images against descriptions)
- Could handle novel/custom components by similarity to known types
- Fast inference (single forward pass per component)

**Challenges:**
- CLIP was trained on natural images, not UI components (needs fine-tuning)
- UI components can look very different across design systems (a Material Design button vs. a custom button)
- Small visual differences matter a lot in UI (a TextField vs. a Button can look similar)

### 6.3 ColPali (2024)

Multi-vector visual retrieval using PaliGemma-3B + ColBERT-style late interaction.

**Architecture:** Vision transformer (SigLIP-So400m) -> Gemma 2B language model -> 128-dim patch embeddings. Late interaction scoring matches query tokens to document patches.

**Relevance for component matching:** ColPali's multi-vector approach preserves spatial information -- each patch of an image gets its own embedding. For UI components, this means the model could attend to specific visual features (the dropdown arrow, the checkbox square, the toggle track) rather than collapsing the entire component into a single vector.

**Potential application:** Build a reference database of component type renderings. Given a new component screenshot, use ColPali-style multi-vector retrieval to find the most similar reference type.

Source: [ColPali Paper](https://arxiv.org/abs/2407.01449)

---

## 7. Figma-Specific and Design-Tool Vision Approaches

### 7.1 Design-to-Code Tools

**Locofy.ai:** Uses Large Design Models (LDMs) built on an ensemble of computer vision and transformer models. Multi-model object detection automatically recognizes elements and extracts features from designs.

**Builder.io:** Supports semantic and native tag recognition from Figma designs.

**Anima:** Figma to React/HTML/Vue code with high fidelity.

**Common pattern:** These tools all use vision models to supplement Figma's structural data, particularly for:
- Identifying semantic HTML tags from visual appearance
- Detecting component boundaries when Figma layers don't align with logical components
- Recognizing common patterns (navigation bars, card grids, form layouts)

### 7.2 MCP + AI Integration (2025-2026)

Multiple platforms added MCP support in early 2026, enabling AI agents to interact with design tools. This suggests a trend toward:
- AI agents that can "see" design files and classify components
- Automated component recognition as a service
- Vision-based quality checks on design system usage

### 7.3 What Figma Already Provides vs. What Vision Adds

**Figma provides (structural):**
- Node type (Frame, Group, Text, Rectangle, etc.)
- Component instance names and variant properties
- Auto-layout direction and properties
- Layer hierarchy and naming
- Fill, stroke, effect properties

**Vision adds:**
- Visual pattern recognition (this LOOKS like a card regardless of how it's structured)
- Icon identification and semantic meaning
- Rendered text reading (when text is in images)
- Layout pattern detection from rendered output
- Cross-design-system pattern matching
- Validation that structural analysis matches visual reality

---

## 8. Accuracy Numbers Summary

### Detection Accuracy (mAP / F1)

| Model/Method | Metric | Score | Task | Year |
|---|---|---|---|---|
| YOLOv9 (fine-tuned, domain transfer) | mAP | **95.5%** | Cross-domain UI detection | 2024 |
| OmniParser + GPT-4V icon labeling | Accuracy | **93.8%** | Icon classification | 2024 |
| CLAY pipeline phase 2 | F1 | **85.9%** | UI element classification | 2022 |
| CLAY pipeline phase 1 | F1 | **82.7%** | Invalid node filtering | 2022 |
| Screen2AX | F1 | **77-79%** | Accessibility tree reconstruction | 2025 |
| UI-DETR-1 | Accuracy | **70.8%** | WebClick element detection | 2025 |
| OmniParser V2 | Accuracy | **58.8%** | WebClick element detection | 2025 |
| YOLOv8 on Rico | mAP50 | **0.56** | 21-class UI element detection | 2024 |

### GUI Grounding (ScreenSpot-Pro -- tiny targets, high-res)

| Model | ScreenSpot-Pro Accuracy | Params | Year |
|---|---|---|---|
| ScreenSeekeR (OS-Atlas-7B enhanced) | **48.1%** | 7B | 2025 |
| GUI-Actor-7B (Qwen2.5-VL) | **44.6%** | 7B | 2025 |
| OmniParser V2 + GPT-4o | **39.6%** | varies | 2025 |
| UI-TARS-72B | **38.1%** | 72B | 2025 |
| ZonUI-3B | **28.7%** | 3B | 2025 |
| OS-Atlas-7B (baseline) | **18.9%** | 7B | 2024 |
| GPT-4o (no preprocessing) | **0.8%** | large | 2024 |

### Processing Speed

| Model | Latency | Hardware | Year |
|---|---|---|---|
| OmniParser V2 | **0.6s/frame** | A100 GPU | 2025 |
| OmniParser V2 | **0.8s/frame** | RTX 4090 | 2025 |
| FastVLM (Apple) | ~8x faster than ViT-L/14 | On-device | 2025 |
| YOLO variants | **5-15ms/frame** | GPU | 2024 |

### Error Modes -- What Vision Gets Wrong

1. **Non-text elements (icons/widgets):** All models struggle here. Text elements are much easier to detect and classify than icons
2. **Touch target vs. visual element mismatch:** Vision identifies the visible element but misses surrounding padding/whitespace that forms the actual interactive region
3. **Tiny targets:** ScreenSpot-Pro average target size is 0.07% of screen area -- extremely challenging
4. **Nested/overlapping components:** A Card containing Buttons, a Modal containing a Form -- vision models tend to detect the inner elements but miss the outer container
5. **Custom styled components:** A heavily styled button that doesn't look like a "standard" button
6. **State-dependent appearance:** Same component looks different when hovered, focused, disabled, or expanded

---

## 9. Hybrid Cascade Strategies

### 9.1 Structure-First, Vision-Second (Recommended for Declarative Design)

```
Figma Tree Analysis (fast, high confidence for known patterns)
  |
  v
Confident classification? --> YES --> Done
  |
  NO (ambiguous structure)
  v
Vision Analysis (render component, classify from image)
  |
  v
Combined confidence score --> Final classification
```

**When to invoke vision:**
- Structural classifier confidence is below threshold
- Node has unusual structure that doesn't match known patterns
- Component is a custom/unknown type
- Validation step (spot-check structural classifications)

**Advantages:**
- Fast path for the 80%+ of components that are structurally clear
- Vision handles the hard 20% where structure is ambiguous
- No GPU cost for easy cases

### 9.2 Vision-First, Structure-Second

```
Screenshot of entire screen
  |
  v
Object detection (OmniParser/YOLO) --> bounding boxes + coarse types
  |
  v
Map bounding boxes to Figma tree nodes
  |
  v
Use structural data to refine classifications
```

**When this is better:**
- Starting from a screenshot (no tree available)
- Figma file is poorly structured (flat hierarchy, no naming)
- Cross-tool analysis (compare Figma design to live website)

### 9.3 Parallel + Fusion

```
Structural Analysis ----\
                         \
                          --> Fusion (weighted combination) --> Final class
                         /
Vision Analysis --------/
```

**Complexity vs. accuracy tradeoff:** Research (UIBert, Screen2Vec) shows this yields the best accuracy (+5-9% over single modality), but adds significant complexity and latency.

### 9.4 Practical Recommendation for Declarative Design

**Phase 1 (now):** Structure-only classification using Figma tree data. This is what the current system does and covers the majority of cases.

**Phase 2 (future):** Add vision as a verification layer:
- Render ambiguous components
- Use a lightweight model (CLIP-based similarity or small YOLO) to cross-check structural classification
- Flag disagreements for review

**Phase 3 (aspirational):** Full hybrid with embedding-based retrieval:
- Build reference embedding database of canonical component types (rendered screenshots)
- For unknown/custom components, embed and find nearest canonical type
- Use ColPali-style multi-vector matching for spatial-aware comparison

---

## 10. Key Takeaways for Declarative Design

1. **Vision is not a replacement for structural analysis -- it's a complement.** Structure is faster, cheaper, and more reliable for standard components. Vision catches what structure misses.

2. **The GPU agent ecosystem provides free infrastructure.** OmniParser, UI-DETR, ShowUI, and others provide pre-trained models that can detect UI elements from screenshots. We don't need to train our own.

3. **Embedding-based classification is the most promising approach** for our use case. Rather than training a detector, render a component, embed it, and compare to reference embeddings of canonical types. This requires no training data specific to our taxonomy.

4. **Text content is the cheapest win.** Before invoking any vision model, checking text content ("Submit" -> Button, date patterns -> Datepicker) provides high-confidence classification signals at zero GPU cost.

5. **The hybrid cascade (structure-first, vision-fallback) is the right architecture.** It preserves speed for easy cases while handling ambiguity.

6. **Processing speed is already fast enough.** OmniParser V2 processes a frame in 0.6-0.8s. YOLO variants run at 5-15ms. For batch processing Figma files (not real-time), even the slower models are acceptable.

7. **The 77-79% F1 for vision-reconstructed trees (Screen2AX) sets a useful baseline.** When we have Figma's actual tree, we should be significantly above this because we start with ground truth structure.

8. **Icon/widget classification remains the hardest problem.** All vision models struggle with non-text UI elements. For Figma, we have the advantage of knowing fill colors, stroke properties, and dimensions -- which helps disambiguate icons from other elements.

9. **Fine-tuning CLIP on UI data (a la UIClip) is proven to work.** If we build an embedding-based classifier, fine-tuning on UI-specific data (even synthetically generated) dramatically improves performance.

10. **MobileViews (600K+ pairs) and MUD (18K clean UIs) are the best current datasets** for training or evaluating UI classification models. Rico (66K UIs) is older but still widely used as a benchmark.
