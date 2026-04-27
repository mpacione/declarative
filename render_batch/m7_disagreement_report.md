# M7.0.a disagreement report

## Summary

- Total rows: 49171
- Total flagged: 674
- Breakdown by `consensus_method`:
  - `any_unsure`: 293
  - `formal`: 26115
  - `heuristic`: 14128
  - `majority`: 3216
  - `none`: 2695
  - `three_way_disagreement`: 381
  - `unanimous`: 2343

## Pair disagreement matrix

| pair | agree | disagree | disagree % |
|---|---:|---:|---:|
| llm × vision_ps | 2929 | 3304 | 53.0% |
| llm × vision_cs | 3023 | 3210 | 51.5% |
| vision_ps × vision_cs | 4396 | 1837 | 29.5% |

## Top 50 three_way_disagreement rows

### sci_id=2292 — screen 127 ('iPad Pro 12.9" - 13'), node I5749:83110;5749:84277 ('Left')

- LLM (0.90): `header` — Part of header structure at depth 2 with horizontal layout grouping text and icon instances on left side; contains 'Filename' sample text indicating header content.
- Vision PS (0.72): `container` — Named 'Left' inside a header, HORIZONTAL layout with 5 INSTANCE + 1 TEXT children including 'Filename' text — this is a structural left section of the header bar, not a standalone interactive component.
- Vision CS (0.75): `list_item` — Named 'Left' inside a header, horizontal layout with 6 children including 'Filename' — same pattern as all prior screens.

### sci_id=2555 — screen 128 ('iPad Pro 12.9" - 14'), node I5749:83205;5749:84277 ('Left')

- LLM (0.92): `header` — Named 'Left' within a header parent, horizontal layout with 6 instances and text sample 'Filename'; typical header left-zone with app/section info.
- Vision PS (0.78): `container` — Named 'Left' inside a header, HORIZONTAL layout with 6 children (5 INSTANCE, 1 TEXT) showing 'Filename' — a layout zone grouping left-side header controls, no single specific component identity.
- Vision CS (0.75): `navigation_row` — Named 'Left', horizontal layout with 5 INSTANCE children and a TEXT 'Filename' — part of a header bar, appears to be the left navigation section with back/forward controls and filename.

### sci_id=2827 — screen 129 ('iPad Pro 12.9" - 17'), node 5749:83300 ('image-box')

- LLM (0.82): `card` — Bounded container with mixed children (frames, rectangle, text) and sample text '1024 x 1024px' suggesting content grouping; dimensions (410×446) and layout pattern indicate a card-like content group.
- Vision PS (0.88): `image` — Named 'image-box' with sample text '1024 x 1024px' (dimension label visible in screenshot below the gorilla photo), contains a RECTANGLE and multiple FRAMEs acting as selection handles — this is the image element with resize handles shown in the canvas editor.
- Vision CS (0.80): `container` — Named 'image-box', contains 11 children (9 FRAME + 1 RECTANGLE + 1 TEXT) with text '1024 x 1024px' — a canvas image editing container with resize handles and size label.

### sci_id=2828 — screen 129 ('iPad Pro 12.9" - 17'), node I5749:83312;5749:84277 ('Left')

- LLM (0.85): `container` — Horizontal layout frame with 6 children (5 instances, 1 text) labeled 'Left' as part of a header structure; structural grouping without specific component semantics.
- Vision PS (0.90): `header` — Named 'Left' inside a header parent with HORIZONTAL layout containing 6 children (5 INSTANCEs + 1 TEXT with 'Filename') — this is the left zone of the app header bar containing navigation and title controls.
- Vision CS (0.75): `navigation_row` — Named 'Left' in header with 5 INSTANCE + 1 TEXT 'Filename' — left header navigation section mirroring Screen 1.

### sci_id=2856 — screen 129 ('iPad Pro 12.9" - 17'), node 5749:83270 ('Frame 289')

- LLM (0.85): `container` — Small vertical layout frame (40×40) with 1 instance child; structural wrapper for a single child component.
- Vision PS (0.80): `avatar` — Named 'Frame 289', 40×40px square with VERTICAL layout containing 1 INSTANCE child, parent is list_item — a small square container in the leading zone of a list item, consistent with an avatar or thumbnail image placeholder.
- Vision CS (0.85): `image` — Named 'Frame 289', 40×40 with 1 INSTANCE child — thumbnail image inside list item.

### sci_id=2857 — screen 129 ('iPad Pro 12.9" - 17'), node 5749:83277 ('Frame 289')

- LLM (0.85): `container` — Small vertical layout frame (40×40) with 1 instance child; structural wrapper for a single child component.
- Vision PS (0.80): `avatar` — Named 'Frame 289', 40×40px square with VERTICAL layout containing 1 INSTANCE child, parent is list_item — identical sibling to 4667, small square in leading zone of list item consistent with avatar/thumbnail.
- Vision CS (0.85): `image` — Named 'Frame 289', 40×40 with 1 INSTANCE child — thumbnail image inside list item.

### sci_id=2858 — screen 129 ('iPad Pro 12.9" - 17'), node 5749:83284 ('Frame 289')

- LLM (0.85): `container` — Small vertical layout frame (40×40) with 1 instance child; structural wrapper for a single child component.
- Vision PS (0.80): `avatar` — Named 'Frame 289', 40×40px square with VERTICAL layout containing 1 INSTANCE child, parent is list_item — identical sibling to 4667 and 4678, small square in leading zone of list item consistent with avatar/thumbnail.
- Vision CS (0.85): `image` — Named 'Frame 289', 40×40 with 1 INSTANCE child — thumbnail image inside list item.

### sci_id=3123 — screen 130 ('iPad Pro 12.9" - 18'), node I5749:83424;5749:84277 ('Left')

- LLM (0.90): `header` — Named 'Left' within header context; horizontal layout with 'Filename' text and icon controls—typical header left zone.
- Vision PS (0.78): `container` — Named 'Left' inside a header with HORIZONTAL layout, 6 children (5 INSTANCE + 1 TEXT 'Filename') — a structural grouping of the left portion of the header bar.
- Vision CS (0.75): `navigation_row` — Named 'Left' in header with 5 INSTANCE + 1 TEXT 'Filename' — left header navigation section.

### sci_id=3377 — screen 131 ('iPad Pro 12.9" - 19'), node 5749:83436 ('image-box')

- LLM (0.80): `card` — Bounded container with mixed children (frames, shapes, text) including dimension label '1024 x 1024px'; likely a visual preview or media card.
- Vision PS (0.85): `image` — Named 'image-box' with sample text '1024 x 1024px' (image dimensions), contains a RECTANGLE (image fill), VECTOR, and TEXT children — visually corresponds to the gorilla image displayed on canvas.
- Vision CS (0.80): `container` — Named 'image-box' with 12 children and '1024 x 1024px' label — image editing canvas with resize handles.

### sci_id=3618 — screen 132 ('iPad Pro 12.9" - 20'), node 5749:83514 ('image-box')

- LLM (0.88): `card` — Bounded container (410×446) grouping 12 mixed children (frames, rectangle, text) with sample text '1024 x 1024px' indicating a media preview card.
- Vision PS (0.88): `image` — Named 'image-box' with sample text '1024 x 1024px', contains a gorilla photo in the screenshot — a static image display area with dimension metadata.
- Vision CS (0.80): `container` — Named 'image-box' with 12 children and '1024 x 1024px' label — image editing canvas with resize handles.

### sci_id=4424 — screen 135 ('iPad Pro 12.9" - 23'), node 5749:83844 ('Frame 290')

- LLM (0.85): `card` — Vertical layout with sample_text 'Tiny' grouping a frame, instance, and text label; bounded container for size variant preview.
- Vision PS (0.75): `container` — Named 'Frame 290' with VERTICAL layout and sample text 'Tiny' — a size-option selector item with label, likely part of a brush/tool size picker; structural grouping without a single canonical type.
- Vision CS (0.85): `radio` — Named 'Frame 290', 86x86, labeled 'Tiny' — preset size radio option.

### sci_id=4425 — screen 135 ('iPad Pro 12.9" - 23'), node 5749:83866 ('Frame 398')

- LLM (0.85): `card` — Vertical layout with sample_text '32 px' grouping a frame, instance, and text label; bounded container for size variant preview.
- Vision PS (0.72): `container` — Named 'Frame 398' with VERTICAL layout, sample text '32 px' — a control row showing a pixel value; parent context is 'container' and sibling frames suggest a settings/options panel.
- Vision CS (0.90): `slider` — Named 'Frame 398', 380x81, labeled '32 px' — custom size slider control.

### sci_id=4428 — screen 135 ('iPad Pro 12.9" - 23'), node 5749:83849 ('Frame 291')

- LLM (0.85): `card` — Vertical layout with sample_text 'Small' grouping a frame, instance, and text label; bounded container for size variant preview.
- Vision PS (0.75): `container` — Named 'Frame 291' with VERTICAL layout and sample text 'Small' — a size-option item in the brush size picker; structural grouping analogous to sibling 'Frame 290' (Tiny).
- Vision CS (0.85): `radio` — Named 'Frame 291', 86x86, labeled 'Small' — preset size radio option.

### sci_id=4429 — screen 135 ('iPad Pro 12.9" - 23'), node 5749:83854 ('Frame 292')

- LLM (0.85): `card` — Vertical layout with sample_text 'Medium' grouping a frame, instance, and text label; bounded container for size variant preview.
- Vision PS (0.75): `container` — Named 'Frame 292' with VERTICAL layout and sample text 'Medium' — a size-option item in the brush size picker, sibling to Tiny/Small/Large frames.
- Vision CS (0.85): `radio` — Named 'Frame 292', 86x86, labeled 'Medium' — preset size radio option.

### sci_id=4430 — screen 135 ('iPad Pro 12.9" - 23'), node 5749:83859 ('Frame 293')

- LLM (0.85): `card` — Vertical layout with sample_text 'Large' grouping a frame, instance, and text label; bounded container for size variant preview.
- Vision PS (0.75): `container` — Named 'Frame 293' with VERTICAL layout and sample text 'Large' — a size-option item in the brush size picker, sibling to the other size frames.
- Vision CS (0.85): `radio` — Named 'Frame 293', 86x86, labeled 'Large' — preset size radio option.

### sci_id=4663 — screen 136 ('iPad Pro 12.9" - 24'), node 5749:83964 ('Frame 275')

- LLM (0.82): `card` — Vertical layout frame (380×81) with 2 child frames and 1 instance, structured as a bounded content grouping typical of a card.
- Vision PS (0.85): `popover` — Named 'Frame 275' with VERTICAL layout containing 3 children; positioned at right side (12431,17976) — in the screenshot this corresponds to the 'Strength' panel with a slider and Done button, a floating popover anchored to a tool.
- Vision CS (0.88): `slider` — Named 'Frame 275', 380x81 with FRAME:2, INSTANCE:1 children — Strength slider panel with track and thumb in the background removal tool.

### sci_id=4906 — screen 137 ('iPad Pro 12.9" - 26'), node 5749:84064 ('Frame 292')

- LLM (0.80): `card` — Vertical layout (184×86) with FRAME, INSTANCE, and TEXT ('Smooth Edges'); bounded container grouping setting/option with icon, label, and interactive element.
- Vision PS (0.82): `list_item` — Named 'Frame 292', VERTICAL layout with FRAME, INSTANCE (likely icon), and TEXT ('Smooth Edges') — a labeled tool option item with icon and text, one of two sibling options visible in the popover panel.
- Vision CS (0.85): `radio` — Named 'Frame 292', 184x86, labeled 'Smooth Edges' — a preset mode option (smooth vs sharp) in the background removal tool, functioning as a radio selection.

### sci_id=4909 — screen 137 ('iPad Pro 12.9" - 26'), node 5749:84069 ('Frame 293')

- LLM (0.80): `card` — Vertical layout (184×86) with FRAME, INSTANCE, and TEXT ('Sharp Details'); parallel structure to 8227, bounded container for option/setting.
- Vision PS (0.82): `list_item` — Named 'Frame 293', VERTICAL layout with FRAME, INSTANCE, and TEXT ('Sharp Details') — a labeled tool option item parallel to Frame 292 ('Smooth Edges'), forming an options list in the tool panel.
- Vision CS (0.85): `radio` — Named 'Frame 293', 184x86, labeled 'Sharp Details' — second preset mode radio option in the background removal tool.

### sci_id=5419 — screen 139 ('iPad Pro 12.9" - 16'), node I5749:84272;5749:84277 ('Left')

- LLM (0.92): `header` — Named 'Left' within a parent header, horizontal layout with mixed INSTANCE and TEXT children including 'Filename'; consistent with header content grouping pattern.
- Vision PS (0.80): `container` — Named 'Left' inside a header, horizontal layout with 5 instances and 1 text ('Filename'); acts as the left zone of the file picker dialog's header row.
- Vision CS (0.82): `list` — Horizontal row in file picker showing source options with 5 instances and text — navigation/source selector list in the picker.

### sci_id=5810 — screen 149 ('iPad Pro 11" - 1'), node I5749:84430;5749:84285 ('Titles')

- LLM (0.92): `heading` — Vertical layout of two text children with sample_text 'Feed' in the header center; establishes section title hierarchy.
- Vision PS (0.85): `text` — Named 'Titles' with sample text 'Feed', contains 2 TEXT children in a VERTICAL layout — a small label/text block used for navigation destination labels, purely textual display.
- Vision CS (0.80): `tabs` — Named 'Titles' with vertical layout, 2 TEXT children with sample text 'Feed' — represents navigation tab labels in a tabs component.

### sci_id=5938 — screen 150 ('iPad Pro 11" - 2'), node 5749:84441 ('Frame 350')

- LLM (0.95): `container` — Generic frame with no sample_text, no distinctive name, generic children arrangement (Frame 350); structural layout container.
- Vision PS (0.85): `image` — Named 'Frame 350', 720×720 square child of the artboard container — visually corresponds to the blank white meme canvas area (1024×1024 @72dpi artboard surface shown in screenshot).
- Vision CS (0.88): `skeleton` — Named 'Frame 350', large 720×720 frame inside a container with no children — empty-frame pattern indicating a loading canvas placeholder.

### sci_id=5943 — screen 150 ('iPad Pro 11" - 2'), node I5749:84449;5749:84285 ('Titles')

- LLM (0.90): `heading` — Vertical layout with 2 text children including sample_text 'Feed' inside header center zone; section title establishing hierarchy.
- Vision PS (0.88): `text` — Named 'Titles' with VERTICAL layout, 2 TEXT children, sample_text='Feed', 43×13px — a small text label/heading inside the center toolbar area showing tab or file name text.
- Vision CS (0.80): `tabs` — Named 'Titles' with vertical layout, 2 TEXT children, sample text 'Feed' — navigation tab label container.

### sci_id=6252 — screen 152 ('iPad Pro 11" - 69'), node I5749:84606;5749:84285 ('Titles')

- LLM (0.90): `heading` — Vertical layout with two text children containing 'Feed' sample text; hierarchical label at top of header center section indicates heading.
- Vision PS (0.80): `text` — Named 'Titles' with 2 TEXT children and sample text 'Feed' in a vertical layout — a label/title display element showing navigation tab text.
- Vision CS (0.80): `tabs` — Named 'Titles', vertical layout with 2 TEXT children, sample text 'Feed' — navigation tab label container.

### sci_id=6401 — screen 153 ('iPad Pro 11" - 63'), node 5749:84617 ('Frame 350')

- LLM (0.95): `container` — Large 720×720 frame with generic name 'Frame 350' and no sample_text or distinctive children visible; pure layout container.
- Vision PS (0.82): `image` — Named 'Frame 350', 720×720 square frame (matching the '1024×1024' canvas label visible in screenshot), child of artboard container — represents the meme canvas/artboard drawing surface, a large bounded content frame.
- Vision CS (0.88): `skeleton` — Named 'Frame 350', large 720×720 frame inside a container with no children — empty-frame pattern indicating a loading canvas placeholder.

### sci_id=6406 — screen 153 ('iPad Pro 11" - 63'), node I5749:84629;5749:84285 ('Titles')

- LLM (0.88): `heading` — Vertical frame named 'Titles' with 2 TEXT children and sample_text='Feed'; establishes section hierarchy typical of heading content.
- Vision PS (0.85): `text` — Named 'Titles', vertical layout with 2 TEXT children and sample text 'Feed' — a text label/title display element inside the center header zone.
- Vision CS (0.80): `tabs` — Named 'Titles', vertical layout with 2 TEXT children, sample text 'Feed' — navigation tab label container.

### sci_id=6539 — screen 154 ('iPad Pro 11" - 3'), node I5749:84648;5749:84285 ('Titles')

- LLM (0.90): `heading` — Vertical FRAME named 'Titles' with sample text 'Feed' and 2 text children; establishes section hierarchy within header area.
- Vision PS (0.75): `tabs` — Named 'Titles' with VERTICAL layout, 2 TEXT children with sample_text='Feed' — likely a tab label or navigation title element inside the browser tab bar area, but limited evidence; classified as tabs given browser tab context.
- Vision CS (0.85): `text` — Named 'Titles' with 2 TEXT children and sample text 'Feed' in vertical layout — displays app/page title text labels in the header.

### sci_id=7934 — screen 161 ('iPad Pro 11" - 12'), node 5749:84992 ('details')

- LLM (0.80): `heading` — Horizontal frame at depth 2 (top-level details section) with sample text 'Meme-00001'; likely a descriptive heading for the screen content.
- Vision PS (0.85): `text` — Named 'details' with sample_text 'Meme-00001', horizontal layout with TEXT and FRAME children, functioning as a metadata/label row showing the file name and dimensions (visible as 'Meme-00001' label at top-left of canvas).
- Vision CS (0.80): `container` — Named 'details', horizontal layout with 1 FRAME and 1 TEXT ('Meme-00001') — metadata strip at top of artboard.

### sci_id=7943 — screen 161 ('iPad Pro 11" - 12'), node 5749:84998 ('image-box')

- LLM (0.80): `card` — Named 'image-box' with bounded container structure, multiple frame/text children including dimensions ('1024 x 1024px') and decorative elements; typical content card grouping.
- Vision PS (0.88): `image` — Named 'image-box' containing a RECTANGLE, VECTOR, and TEXT children with sample_text '1024 x 1024px'; visually shows the gorilla meme image with a blue selection border — the main editable image element in the canvas.
- Vision CS (0.80): `container` — Named 'image-box', contains 9 FRAME, 1 RECTANGLE, 1 TEXT, 1 VECTOR children — canvas image editing area with handles.

### sci_id=8228 — screen 162 ('iPad Pro 11" - 70'), node 5749:85104 ('details')

- LLM (0.88): `text` — Horizontal layout frame with sample text 'Meme-00001' indicating a filename or content identifier; minimal children suggest a single informational text element.
- Vision PS (0.85): `header` — Named 'details' with HORIZONTAL layout containing a TEXT ('Meme-00001') and a FRAME inside a container — acts as the top details/title bar of the artboard, consistent with a header pattern.
- Vision CS (0.80): `container` — Named 'details', horizontal layout with a FRAME and TEXT ('Meme-00001') — a metadata/detail row container above the canvas displaying the file name and associated controls.

### sci_id=8482 — screen 163 ('iPad Pro 11" - 13'), node 5749:85210 ('image-box')

- LLM (0.85): `card` — Bounded container with image content, metadata label '1024 x 1024px', and nested structural frames; groups related image and info content.
- Vision PS (0.87): `image` — Named 'image-box' containing RECTANGLE, VECTOR, and TEXT children with sample_text '1024 x 1024px' — the canvas image element with selection handles visible in the screenshot.
- Vision CS (0.80): `container` — Named 'image-box', 12 children — canvas image editing area with resize handles and erased content visible in screenshot.

### sci_id=8714 — screen 164 ('iPad Pro 11" - 14'), node 5749:85282 ('details')

- LLM (0.85): `heading` — Horizontal layout frame with 'Meme-00001' sample text at top of artboard; positioned as metadata/details section labeling content below.
- Vision PS (0.80): `text` — Horizontal frame with sample_text 'Meme-00001' and only 1 TEXT child plus 1 FRAME child; acts as a label/details row beneath the artboard, primarily displaying the filename text.
- Vision CS (0.80): `container` — Named 'details', horizontal layout with 1 FRAME and 1 TEXT ('Meme-00001') — metadata strip at top of artboard.

### sci_id=8987 — screen 165 ('iPad Pro 11" - 15'), node 5749:85387 ('Frame 290')

- LLM (0.80): `container` — Vertical layout frame with label 'Tiny', icon instance, and child frame; size variant indicator for a design system.
- Vision PS (0.82): `radio` — Named 'Frame 290', sample_text 'Tiny', contains a frame (dot indicator), instance, and text — one of four mutually exclusive eraser size preset options visible in the screenshot.
- Vision CS (0.88): `button` — Named 'Frame 290' with vertical layout, sample text 'Tiny', containing a frame, icon instance and text — a size preset button in the Eraser Size panel (visually shows 'Tiny' preset option).

### sci_id=8992 — screen 165 ('iPad Pro 11" - 15'), node 5749:85392 ('Frame 291')

- LLM (0.80): `container` — Vertical layout with label 'Small', icon instance, and child frame; size variant indicator.
- Vision PS (0.82): `radio` — Named 'Frame 291', sample_text 'Small', contains a frame (dot indicator), instance, and text — one of four mutually exclusive eraser size preset options.
- Vision CS (0.88): `button` — Named 'Frame 291' with vertical layout, sample text 'Small', frame/icon/text children — a size preset button in the Eraser Size panel.

### sci_id=8994 — screen 165 ('iPad Pro 11" - 15'), node 5749:85397 ('Frame 292')

- LLM (0.80): `container` — Vertical layout with label 'Medium', icon instance, and child frame; size variant indicator.
- Vision PS (0.88): `radio` — Named 'Frame 292', sample_text 'Medium', contains a frame (larger dot), instance, and text — the currently selected (highlighted green) eraser size preset in the screenshot.
- Vision CS (0.90): `button` — Named 'Frame 292' with vertical layout, sample text 'Medium', highlighted with green background in screenshot — actively selected size preset button in Eraser Size panel.

### sci_id=8996 — screen 165 ('iPad Pro 11" - 15'), node 5749:85402 ('Frame 293')

- LLM (0.80): `container` — Vertical layout with label 'Large', icon instance, and child frame; size variant indicator.
- Vision PS (0.82): `radio` — Named 'Frame 293', sample_text 'Large', contains a frame (large dot), instance, and text — one of four mutually exclusive eraser size preset options.
- Vision CS (0.88): `button` — Named 'Frame 293' with vertical layout, sample text 'Large', frame/icon/text children — a size preset button in the Eraser Size panel.

### sci_id=9236 — screen 166 ('iPad Pro 11" - 16'), node 5749:85448 ('details')

- LLM (0.85): `heading` — Small horizontal frame with sample text 'Meme-00001' positioned at top of artboard; appears to be a section header or identifier label.
- Vision PS (0.80): `container` — Named 'details' with HORIZONTAL layout showing filename text 'Meme-00001' alongside a frame child; structural metadata row at top of artboard, no specific interactive or component identity.
- Vision CS (0.80): `text` — Named 'details' with sample text 'Meme-00001' — metadata info bar showing filename above the canvas.

### sci_id=9250 — screen 166 ('iPad Pro 11" - 16'), node 5749:85482 ('Frame 290')

- LLM (0.78): `card` — Vertical auto-layout frame with sample text 'Tiny', frame, and instance children; appears to be a small content card representing a size variant.
- Vision PS (0.82): `radio` — Named 'Frame 290' with VERTICAL layout, sample_text 'Tiny', children include a FRAME (dot/circle visual), INSTANCE, and TEXT — one of four preset size options (Tiny/Small/Medium/Large) forming a mutually exclusive selection set in the Eraser Size panel.
- Vision CS (0.88): `button` — Named 'Frame 290' with vertical layout, text 'Tiny' — a size preset button in the Eraser Size panel.

### sci_id=9251 — screen 166 ('iPad Pro 11" - 16'), node 5749:85504 ('Frame 398')

- LLM (0.78): `card` — Vertical auto-layout frame with sample text '32 px', frame, and instance children; bounded container grouping size/variant information with visual elements.
- Vision PS (0.92): `slider` — Named 'Frame 398' in the Custom Size section with sample_text '32 px', containing a FRAME (track), INSTANCE (thumb), and TEXT (value label) — matches the custom size slider visible in the screenshot.
- Vision CS (0.78): `container` — Named 'Frame 398' with vertical layout, text '32 px' — the custom size section container for the slider in the Eraser Size panel.

### sci_id=9255 — screen 166 ('iPad Pro 11" - 16'), node 5749:85487 ('Frame 291')

- LLM (0.78): `card` — Vertical auto-layout frame with sample text 'Small', frame, and instance children; small content card representing a size variant.
- Vision PS (0.82): `radio` — Named 'Frame 291' with VERTICAL layout, sample_text 'Small', containing FRAME (dot), INSTANCE, and TEXT — second preset size option in the Eraser Size panel's mutually exclusive preset group.
- Vision CS (0.88): `button` — Named 'Frame 291' with vertical layout, text 'Small' — a size preset button in the Eraser Size panel.

### sci_id=9257 — screen 166 ('iPad Pro 11" - 16'), node 5749:85492 ('Frame 292')

- LLM (0.78): `card` — Vertical auto-layout frame with sample text 'Medium', frame, and instance children; small content card representing a size variant.
- Vision PS (0.82): `radio` — Named 'Frame 292' with VERTICAL layout, sample_text 'Medium', containing FRAME (dot), INSTANCE, and TEXT — third preset size option in the Eraser Size panel's mutually exclusive preset group.
- Vision CS (0.88): `button` — Named 'Frame 292' with vertical layout, text 'Medium' — a size preset button in the Eraser Size panel.

### sci_id=9259 — screen 166 ('iPad Pro 11" - 16'), node 5749:85497 ('Frame 293')

- LLM (0.78): `card` — Vertical auto-layout frame with sample text 'Large', frame, and instance children; small content card representing a size variant.
- Vision PS (0.82): `radio` — Named 'Frame 293' with VERTICAL layout, sample_text 'Large', containing FRAME (dot), INSTANCE, and TEXT — fourth preset size option in the Eraser Size panel's mutually exclusive preset group.
- Vision CS (0.88): `button` — Named 'Frame 293' with vertical layout, text 'Large' — a size preset button in the Eraser Size panel.

### sci_id=9496 — screen 167 ('iPad Pro 11" - 17'), node 5749:85543 ('details')

- LLM (0.80): `heading` — Horizontal frame with sample text 'Meme-00001' at depth 2 under artboard; text-first structure suggests a title/label role.
- Vision PS (0.80): `container` — Named 'details' with horizontal layout showing filename text 'Meme-00001' and a frame child; a structural label/info row inside the artboard container, no specific interactive component identity.
- Vision CS (0.80): `text` — Named 'details' with sample text 'Meme-00001' — metadata info bar showing filename.

### sci_id=9513 — screen 167 ('iPad Pro 11" - 17'), node 5749:85605 ('Frame 290')

- LLM (0.78): `card` — Vertical frame ('Tiny' label) with 3 children (frame, instance, text); bounded container displaying a size variant with content and label.
- Vision PS (0.78): `list_item` — Named 'Frame 290' with vertical layout, 3 children (frame, instance, text 'Tiny'); a labeled size option item in a size-selection list below the canvas.
- Vision CS (0.88): `button` — Named 'Frame 290' with vertical layout, text 'Tiny' — size preset button in Eraser Size panel.

### sci_id=9514 — screen 167 ('iPad Pro 11" - 17'), node 5749:85627 ('Frame 398')

- LLM (0.78): `card` — Vertical frame ('32 px' label) with 3 children (frame, instance, text); bounded container displaying a size variant with measurement and content.
- Vision PS (0.75): `list_item` — Named 'Frame 398' with vertical layout, 3 children (frame, instance, text '32 px'); a labeled size/dimension option item in a settings panel below the canvas.
- Vision CS (0.78): `container` — Named 'Frame 398' with vertical layout, text '32 px' — custom size section container with slider.

### sci_id=9518 — screen 167 ('iPad Pro 11" - 17'), node 5749:85610 ('Frame 291')

- LLM (0.78): `card` — Vertical frame ('Small' label) with 3 children (frame, instance, text); bounded container displaying a size variant with content and label.
- Vision PS (0.78): `list_item` — Named 'Frame 291' with vertical layout, 3 children (frame, instance, text 'Small'); a labeled size option item analogous to Frame 290 in the size selection row.
- Vision CS (0.88): `button` — Named 'Frame 291' with vertical layout, text 'Small' — size preset button in Eraser Size panel.

### sci_id=9520 — screen 167 ('iPad Pro 11" - 17'), node 5749:85615 ('Frame 292')

- LLM (0.78): `card` — Vertical frame ('Medium' label) with 3 children (frame, instance, text); bounded container displaying a size variant with content and label.
- Vision PS (0.78): `list_item` — Named 'Frame 292' with vertical layout, 3 children (frame, instance, text 'Medium'); a labeled size option item in the size selection row.
- Vision CS (0.88): `button` — Named 'Frame 292' with vertical layout, text 'Medium' — size preset button in Eraser Size panel.

### sci_id=9522 — screen 167 ('iPad Pro 11" - 17'), node 5749:85620 ('Frame 293')

- LLM (0.78): `card` — Vertical frame ('Large' label) with 3 children (frame, instance, text); bounded container displaying a size variant with content and label.
- Vision PS (0.78): `list_item` — Named 'Frame 293' with vertical layout, 3 children (frame, instance, text 'Large'); a labeled size option item in the size selection row.
- Vision CS (0.88): `button` — Named 'Frame 293' with vertical layout, text 'Large' — size preset button in Eraser Size panel.

### sci_id=10235 — screen 170 ('iPad Pro 12.9" - 28'), node 5749:85870 ('image-box')

- LLM (0.85): `card` — Bounded container with mixed content (image frames, dimensions text, icons, controls); groups related image editing content and actions.
- Vision PS (0.87): `image` — Named 'image-box' containing a gorilla photo in the screenshot with selection handles (resize handles as child frames), dimension label '1024 x 1024px', and a RECTANGLE child — a selected image element on the canvas.
- Vision CS (0.80): `container` — Named 'image-box' containing 13 children (frames, rectangle, text, vector) showing the gorilla image with selection handles and size label — the image editing/selection container.

### sci_id=10489 — screen 171 ('iPad Pro 12.9" - 29'), node 5749:85981 ('image-box')

- LLM (0.82): `card` — Bounded container with image, text ('1024 x 1024px'), and multiple child elements (10 frames, 1 rectangle, 1 text, 1 vector) forming a cohesive content unit.
- Vision PS (0.85): `image` — Named 'image-box' containing a gorilla photo with selection handles and dimension label '1024 x 1024px'; visually displays raster image content on the canvas.
- Vision CS (0.80): `container` — Named 'image-box' with 13 children including frames, rectangle, text, vector — image editing selection container showing the mirrored gorilla.

### sci_id=10490 — screen 171 ('iPad Pro 12.9" - 29'), node I5749:86080;5749:84277 ('Left')

- LLM (0.85): `container` — Horizontal layout frame with instances and text sample ('Filename') inside header; structural container for header left section.
- Vision PS (0.90): `header` — Named 'Left' inside a header parent with HORIZONTAL layout containing 5 INSTANCE children and a TEXT 'Filename'; forms the left zone of the top navigation bar.
- Vision CS (0.80): `list` — Horizontal row in app header with 5 instances and 'Filename' text — source/navigation selector list.

## Pattern clusters (flagged rows only)

Grouped by the raw (LLM, PS, CS) triple. The top patterns are the candidates for rule-v2 bias overrides.

| count | pattern |
|---:|---|
| 74 | llm=icon / vision_ps=unsure / vision_cs=container |
| 49 | llm=divider / vision_ps=unsure / vision_cs=container |
| 37 | llm=divider / vision_ps=icon / vision_cs=container |
| 36 | llm=icon / vision_ps=unsure / vision_cs=icon |
| 36 | llm=icon / vision_ps=icon_button / vision_cs=container |
| 28 | llm=divider / vision_ps=container / vision_cs=icon |
| 24 | llm=container / vision_ps=unsure / vision_cs=container |
| 20 | llm=heading / vision_ps=text / vision_cs=container |
| 19 | llm=card / vision_ps=image / vision_cs=container |
| 17 | llm=text_input / vision_ps=link / vision_cs=text |
| 16 | llm=divider / vision_ps=unsure / vision_cs=icon |
| 16 | llm=card / vision_ps=unsure / vision_cs=card |
| 15 | llm=heading / vision_ps=container / vision_cs=text |
| 14 | llm=card / vision_ps=unsure / vision_cs=button |
| 12 | llm=card / vision_ps=container / vision_cs=button |
| 12 | llm=unsure / vision_ps=icon / vision_cs=icon |
| 11 | llm=search_input / vision_ps=link / vision_cs=text |
| 10 | llm=card / vision_ps=button / vision_cs=radio |
| 8 | llm=heading / vision_ps=text / vision_cs=tabs |
| 8 | llm=card / vision_ps=list_item / vision_cs=button |
| 7 | llm=card / vision_ps=list_item / vision_cs=container |
| 7 | llm=header / vision_ps=button_group / vision_cs=container |
| 7 | llm=card / vision_ps=unsure / vision_cs=container |
| 6 | llm=container / vision_ps=card / vision_cs=image |
| 6 | llm=card / vision_ps=container / vision_cs=image |
| 5 | llm=header / vision_ps=container / vision_cs=list_item |
| 5 | llm=card / vision_ps=container / vision_cs=slider |
| 5 | llm=card / vision_ps=slider / vision_cs=container |
| 5 | llm=list_item / vision_ps=text / vision_cs=container |
| 4 | llm=card / vision_ps=container / vision_cs=radio |
| 4 | llm=container / vision_ps=radio / vision_cs=button |
| 4 | llm=card / vision_ps=radio / vision_cs=button |
| 4 | llm=card / vision_ps=unsure / vision_cs=radio |
| 4 | llm=container / vision_ps=unsure / vision_cs=icon |
| 4 | llm=container / vision_ps=button / vision_cs=card |
| 4 | llm=unsure / vision_ps=button / vision_cs=radio |
| 4 | llm=unsure / vision_ps=button / vision_cs=button |
| 4 | llm=icon / vision_ps=container / vision_cs=icon_button |
| 4 | llm=container / vision_ps=icon / vision_cs=icon_button |
| 4 | llm=text / vision_ps=heading / vision_cs=container |
| 4 | llm=card / vision_ps=toggle / vision_cs=button |
| 3 | llm=container / vision_ps=avatar / vision_cs=image |
| 3 | llm=unsure / vision_ps=image / vision_cs=image |
| 3 | llm=list_item / vision_ps=heading / vision_cs=text |
| 3 | llm=skeleton / vision_ps=image / vision_cs=container |
| 3 | llm=list_item / vision_ps=text / vision_cs=card |
| 3 | llm=container / vision_ps=divider / vision_cs=slider |
| 3 | llm=list_item / vision_ps=text / vision_cs=text_input |
| 2 | llm=header / vision_ps=container / vision_cs=navigation_row |
| 2 | llm=card / vision_ps=list_item / vision_cs=radio |
