# Figma MCP Feasibility Probes — Results

Date: 2025-03-25
File: Dank (Experimental) — drxXOUOdYEBBQ09mrXJeYu
Page: Dank 1.0 — 1312:136189

## File Profile

- Canvas: "Dank 1.0" — 25,547 nodes total
- Screens: ~90 iPhone (428×926), ~69 iPad 11" (834×1194), ~69 iPad 12.9" (1536×1152) — ~230 total
- Components (unpublished): ~100+ icons, 4 button variants, 1 input field, nav/top-nav, nav/tabs, iOS chrome elements, logo
- Additional frames: "Buttons and Controls" (component exploration), "Modals and Popups", "Website Image"
- Existing variables: 0
- Existing styles: 0
- Design system maturity: None — all values hardcoded

## Official Figma MCP Probes

### Auth and Permissions
- User: Matt Pacione (hello@humanistic.ca)
- Plan: Humanistic, Pro tier, Full seat, Expert seat type
- No permission blockers

### get_metadata (full page)
- Result: 2.4M characters, 25,547 XML elements
- Content: Node IDs, names, types, positions, sizes — no style properties
- Verdict: Good for tree structure, useless for design values

### get_design_context (single component: button/large/solid)
- Result: React + Tailwind code representation
- Extracted values: Zinc 950 (#09090B), Zinc 300 (#D4D4D8)
- Verdict: Useful for code gen, not for raw value extraction at scale

### use_figma — Variable Creation
- Create variable collection: OK
- Create COLOR variable: OK
- Set value via setValueForMode: OK
- Bind variable to node fill (setBoundVariableForPaint): OK
- Create FLOAT variable (spacing/radius): OK
- Bulk create 20 variables in single call: OK

### use_figma — Bulk Read (single iPhone screen: 2219:235687)
- Nodes traversed: 204
- Output size: ~37K characters
- Properties extracted: fills (RGBA), strokes, cornerRadius, fontSize, fontFamily, fontWeight, lineHeight, letterSpacing, effects, auto-layout (layoutMode, padding, itemSpacing)
- Time: ~3 seconds
- Verdict: Full property depth. ~200 nodes/call is comfortable.

### Throughput Estimate
- 230 screens x ~200 nodes x 1 call/screen = ~230 extraction calls
- ~3-5 sec/call = ~12-20 minutes for full extraction
- use_figma code field limit: 50,000 characters
- Return payload: uncapped (37K+ observed)

## Console MCP Probes

### Connection
- Transport: WebSocket via Desktop Bridge plugin
- Port: 9224 (fallback from 9223)
- Status: Connected to Dank (Experimental), page Dank 1.0

### figma_get_design_system_kit
- Result: 0 components, 0 styles, 0 tokens
- Reason: Only returns published library assets. Dank components are local/unpublished.
- Verdict: Not useful for this file.

### figma_audit_design_system
- Overall score: 62/100
- Naming: 100, Tokens: 0, Component Metadata: 83, Accessibility: 67, Consistency: 100, Coverage: 0

### figma_lint_design
- Nodes scanned: 119 (top-level only)
- Findings: 100 issues (2 critical WCAG, 77 default names, 19 no-autolayout, 2 detached components)

### figma_get_file_data (depth 3, single iPhone screen)
- Output: 110K characters for one screen
- Properties: fills, cornerRadius, layoutMode, padding, itemSpacing, effects, strokes
- Limitation: Instances collapsed — internals not expanded
- Verdict: Rich but heavy. Use summary for tree, targeted full for properties.

### figma_setup_design_tokens
- Test: Created collection with 1 mode and 4 tokens (2 COLOR, 2 FLOAT) in single atomic call
- Capacity: Up to 100 tokens per call
- Verdict: Killer feature. One call to stand up entire token system.

### figma_execute vs use_figma
- figma_execute uses documentAccess: dynamic-page (requires async API)
- use_figma uses synchronous Plugin API
- Verdict: Complementary. Official for sync traversal, Console for dedicated tools.

## Key Constraints
1. get_design_context is for code gen, not extraction
2. get_design_system_kit only sees published library assets
3. Instance nodes are opaque in tree reads
4. Console figma_execute requires async API methods
5. 110K per screen at full verbosity — needs management
6. Lint/audit scoped to top-level by default
