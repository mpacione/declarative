const __errors = [];
await (async () => { try { await figma.loadFontAsync({family: "Inter", style: "Regular"}); } catch (__e) { __errors.push({kind:"font_load_failed", family:"Inter", style:"Regular", error: String(__e && __e.message || __e)}); } })();
await (async () => { try { await figma.loadFontAsync({family: "Inter", style: "Semi Bold"}); } catch (__e) { __errors.push({kind:"font_load_failed", family:"Inter", style:"Semi Bold", error: String(__e && __e.message || __e)}); } })();
const M = {};
const _rootPage = figma.currentPage;
// Missing-component wireframe placeholder: emitted when a Mode 1
// createInstance falls back (deleted/unpublished/stripped component).
// Architectural-style diagonal hatching inside a bordered frame.
//
// Design notes:
// - Hatch: parallel 45° lines, ~12px apart, mid-grey. This is the
//   standard convention in architectural/engineering drawings for
//   'unfilled / to be specified' regions. Reads clearly as a
//   placeholder at any aspect ratio, scales nicely.
// - Mid-grey (0.5) on strokes/text so the wireframe stays visible
//   even if downstream DB overrides clobber the frame fill.
// - Hatch is skipped when the frame is tiny (< 40x40) — pattern
//   just looks like noise at icon sizes.
// - Name label appears only when the frame is >= 64x32.
// - setPluginData('__ph','1') marks the returned frame so the
//   caller can gate subsequent visual-property writes (the DB's
//   overrides for the real component shouldn't be applied to the
//   placeholder).
const _MIN_LABEL_W = 64, _MIN_LABEL_H = 32;
const _MIN_HATCH = 40;
const _HATCH_STRIDE = 12;
function _missingComponentPlaceholder(name, w, h, eid) {
  __errors.push({kind:"component_missing", eid, name, w, h});
  const f = figma.createFrame();
  f.resize(w || 24, h || 24);
  f.fills = [];
  f.strokes = [{type:"SOLID", color:{r:0.5,g:0.5,b:0.5}}];
  f.strokeWeight = 1;
  f.clipsContent = true;
  try { f.setPluginData('__ph', '1'); } catch (__e) {}
  const actualW = f.width, actualH = f.height;
  // Diagonal hatch pattern, clipped by frame bounds.
  // Skipped at tiny sizes (icon-sized placeholders look like noise).
  if (actualW >= _MIN_HATCH && actualH >= _MIN_HATCH) {
    const total = actualW + actualH;
    const lineLen = total * 1.5;  // long enough to always span the frame at 45°
    for (let offset = -actualH; offset <= actualW + actualH; offset += _HATCH_STRIDE) {
      const ln = figma.createLine();
      // Subtle opacity so stacked placeholders (e.g. overlay over
      // modal over background) don't compound into an opaque
      // mesh. 15% reads as 'placeholder texture' without
      // competing with any real content that overlays it.
      ln.strokes = [{type:"SOLID", color:{r:0.5,g:0.5,b:0.5}, opacity:0.15}];
      ln.strokeWeight = 1;
      ln.resize(lineLen, 0);
      // Plugin API rotation: +45 is visually CCW (up-right).
      // Line starts at (offset, actualH) on or below the frame's
      // bottom edge and goes up-right, clipped to the frame.
      ln.rotation = 45;
      ln.x = offset;
      ln.y = actualH;
      f.appendChild(ln);
    }
  }
  if (actualW >= _MIN_LABEL_W && actualH >= _MIN_LABEL_H && name) {
    try {
      const t = figma.createText();
      t.fontName = {family:"Inter", style:"Regular"};
      t.fontSize = 10;
      t.characters = String(name);
      t.x = 4; t.y = 4;
      t.fills = [{type:"SOLID", color:{r:0.5,g:0.5,b:0.5}}];
      f.appendChild(t);
    } catch (__e) {}
  }
  return f;
}
// Helper to gate a setter on whether the target is a placeholder.
// Used to prevent DB visual overrides (fills/strokes/effects) from
// clobbering the placeholder's wireframe appearance.
function _isPh(n) { try { return n.getPluginData('__ph') === '1'; } catch (__e) { return false; } }
// Pre-fetch component nodes (deduplicated, null-safe)
const _p0 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82247"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82247", error: String(__e && __e.message || __e)}); return null; } })();
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82260"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return null; } })();
const _p2 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82457"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return null; } })();


try {
// Phase 1: Materialize — create nodes, set intrinsic properties
const n0 = figma.createFrame();
n0.name = "screen-1";
n0.layoutMode = "VERTICAL";
n0.itemSpacing = 12;
n0.paddingTop = 16;
n0.paddingRight = 16;
n0.paddingBottom = 16;
n0.paddingLeft = 16;
n0.resize(428.0, 926.0);
n0.fills = [{type: "SOLID", color: {r:0.9647,g:0.9647,b:0.9647}}];
n0.clipsContent = false;
M["screen-1"] = n0.id;

const n1 = figma.createFrame();
n1.name = "header-1";
n1.layoutMode = "VERTICAL";
n1.fills = [];
n1.clipsContent = false;
M["header-1"] = n1.id;

const n2 = figma.createFrame();
n2.name = "card-1";
n2.layoutMode = "VERTICAL";
n2.fills = [];
n2.clipsContent = false;
M["card-1"] = n2.id;

const n3 = figma.createFrame();
n3.name = "card-2";
n3.layoutMode = "VERTICAL";
n3.fills = [];
n3.clipsContent = false;
M["card-2"] = n3.id;

const n4 = figma.createFrame();
n4.name = "card-3";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["card-3"] = n4.id;

const n5 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"button-4", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-4", 24, 24, "button-4"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-4", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-4", 24, 24, "button-4"); } })();
n5.name = "button-4";
{ const _t = n5.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n5.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Surprise Me"; } }
M["button-4"] = n5.id;

const n6 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n6.name = "icon_button-1";
M["icon_button-1"] = n6.id;

const n7 = figma.createText();
n7.name = "heading-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "list-1";
n8.layoutMode = "VERTICAL";
n8.fills = [];
n8.clipsContent = false;
M["list-1"] = n8.id;

const n9 = figma.createText();
n9.name = "heading-2";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n9.id;

const n10 = figma.createFrame();
n10.name = "button_group-1";
n10.layoutMode = "VERTICAL";
n10.fills = [];
n10.clipsContent = false;
M["button_group-1"] = n10.id;

const n11 = figma.createText();
n11.name = "heading-3";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n11.id;

const n12 = figma.createFrame();
n12.name = "list-2";
n12.layoutMode = "VERTICAL";
n12.fills = [];
n12.clipsContent = false;
M["list-2"] = n12.id;

const n13 = figma.createFrame();
n13.name = "list_item-1";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["list_item-1"] = n13.id;

const n14 = figma.createFrame();
n14.name = "list_item-2";
n14.layoutMode = "VERTICAL";
n14.fills = [];
n14.clipsContent = false;
M["list_item-2"] = n14.id;

const n15 = figma.createFrame();
n15.name = "list_item-3";
n15.layoutMode = "VERTICAL";
n15.fills = [];
n15.clipsContent = false;
M["list_item-3"] = n15.id;

const n16 = figma.createFrame();
n16.name = "button-1";
n16.layoutMode = "VERTICAL";
n16.itemSpacing = 8;
n16.resize(n16.width, 44);
n16.primaryAxisAlignItems = "CENTER";
n16.counterAxisAlignItems = "CENTER";
n16.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n16.cornerRadius = 8;
n16.clipsContent = false;
M["button-1"] = n16.id;

const n17 = figma.createFrame();
n17.name = "button-2";
n17.layoutMode = "VERTICAL";
n17.itemSpacing = 8;
n17.resize(n17.width, 44);
n17.primaryAxisAlignItems = "CENTER";
n17.counterAxisAlignItems = "CENTER";
n17.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n17.cornerRadius = 8;
n17.clipsContent = false;
M["button-2"] = n17.id;

const n18 = figma.createFrame();
n18.name = "button-3";
n18.layoutMode = "VERTICAL";
n18.itemSpacing = 8;
n18.resize(n18.width, 44);
n18.primaryAxisAlignItems = "CENTER";
n18.counterAxisAlignItems = "CENTER";
n18.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n18.cornerRadius = 8;
n18.clipsContent = false;
M["button-3"] = n18.id;

const n19 = figma.createFrame();
n19.name = "list_item-4";
n19.layoutMode = "VERTICAL";
n19.fills = [];
n19.clipsContent = false;
M["list_item-4"] = n19.id;

const n20 = figma.createFrame();
n20.name = "list_item-5";
n20.layoutMode = "VERTICAL";
n20.fills = [];
n20.clipsContent = false;
M["list_item-5"] = n20.id;

const n21 = figma.createFrame();
n21.name = "avatar-1";
n21.layoutMode = "VERTICAL";
n21.primaryAxisAlignItems = "CENTER";
n21.counterAxisAlignItems = "CENTER";
n21.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n21.cornerRadius = 999;
n21.clipsContent = false;
M["avatar-1"] = n21.id;

const n22 = figma.createText();
n22.name = "text-1";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n22.id;

const n23 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-1", kind:"missing_component_node", id:"5749:82247"}); return _missingComponentPlaceholder("icon-1", 24, 24, "icon-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-1", kind:"create_instance_failed", id:"5749:82247", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-1", 24, 24, "icon-1"); } })();
n23.name = "icon-1";
M["icon-1"] = n23.id;

const n24 = figma.createFrame();
n24.name = "avatar-2";
n24.layoutMode = "VERTICAL";
n24.primaryAxisAlignItems = "CENTER";
n24.counterAxisAlignItems = "CENTER";
n24.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n24.cornerRadius = 999;
n24.clipsContent = false;
M["avatar-2"] = n24.id;

const n25 = figma.createText();
n25.name = "text-2";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n25.id;

const n26 = figma.createFrame();
n26.name = "badge-1";
n26.layoutMode = "VERTICAL";
n26.itemSpacing = 4;
n26.counterAxisAlignItems = "CENTER";
n26.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n26.cornerRadius = 999;
n26.clipsContent = false;
M["badge-1"] = n26.id;

const n27 = figma.createFrame();
n27.name = "avatar-3";
n27.layoutMode = "VERTICAL";
n27.primaryAxisAlignItems = "CENTER";
n27.counterAxisAlignItems = "CENTER";
n27.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n27.cornerRadius = 999;
n27.clipsContent = false;
M["avatar-3"] = n27.id;

const n28 = figma.createText();
n28.name = "text-4";
try { n28.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n28.id;

const n29 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-2", kind:"missing_component_node", id:"5749:82247"}); return _missingComponentPlaceholder("icon-2", 24, 24, "icon-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-2", kind:"create_instance_failed", id:"5749:82247", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-2", 24, 24, "icon-2"); } })();
n29.name = "icon-2";
M["icon-2"] = n29.id;

const n30 = figma.createText();
n30.name = "text-5";
n30.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
try { n30.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.fontSize = 14;
M["text-5"] = n30.id;

const n31 = figma.createText();
n31.name = "text-6";
n31.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
try { n31.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.fontSize = 14;
M["text-6"] = n31.id;

const n32 = figma.createText();
n32.name = "text-7";
n32.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
try { n32.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.fontSize = 14;
M["text-7"] = n32.id;

const n33 = figma.createText();
n33.name = "text-8";
try { n33.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n33.id;

const n34 = figma.createFrame();
n34.name = "badge-2";
n34.layoutMode = "VERTICAL";
n34.itemSpacing = 4;
n34.counterAxisAlignItems = "CENTER";
n34.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n34.cornerRadius = 999;
n34.clipsContent = false;
M["badge-2"] = n34.id;

const n35 = figma.createText();
n35.name = "text-10";
try { n35.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n35.id;

const n36 = figma.createFrame();
n36.name = "badge-3";
n36.layoutMode = "VERTICAL";
n36.itemSpacing = 4;
n36.counterAxisAlignItems = "CENTER";
n36.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n36.cornerRadius = 999;
n36.clipsContent = false;
M["badge-3"] = n36.id;

const n37 = figma.createText();
n37.name = "text-3";
n37.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n37.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n37.fontSize = 12;
M["text-3"] = n37.id;

const n38 = figma.createText();
n38.name = "text-9";
n38.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n38.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.fontSize = 12;
M["text-9"] = n38.id;

const n39 = figma.createText();
n39.name = "text-11";
n39.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n39.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n39.fontSize = 12;
M["text-11"] = n39.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n0.appendChild(n3);
n3.layoutSizingHorizontal = "FILL";
n0.appendChild(n4);
n4.layoutSizingHorizontal = "FILL";
n0.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n1.appendChild(n6);
n2.appendChild(n7);
try { n7.characters = "Featured Collections"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n2.appendChild(n8);
n3.appendChild(n9);
try { n9.characters = "Explore by Mood"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n3.appendChild(n10);
n4.appendChild(n11);
try { n11.characters = "Quick Stats"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n4.appendChild(n12);
n8.appendChild(n13);
n8.appendChild(n14);
n8.appendChild(n15);
n10.appendChild(n16);
n16.layoutSizingHorizontal = "HUG";
n16.layoutSizingVertical = "FIXED";
n10.appendChild(n17);
n17.layoutSizingHorizontal = "HUG";
n17.layoutSizingVertical = "FIXED";
n10.appendChild(n18);
n18.layoutSizingHorizontal = "HUG";
n18.layoutSizingVertical = "FIXED";
n12.appendChild(n19);
n12.appendChild(n20);
n13.appendChild(n21);
n21.layoutSizingHorizontal = "FIXED";
n21.layoutSizingVertical = "FIXED";
n13.appendChild(n22);
try { n22.characters = "Trending Creatives"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n13.appendChild(n23);
n14.appendChild(n24);
n24.layoutSizingHorizontal = "FIXED";
n24.layoutSizingVertical = "FIXED";
n14.appendChild(n25);
try { n25.characters = "New & Worthy"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n14.appendChild(n26);
n26.layoutSizingHorizontal = "HUG";
n26.layoutSizingVertical = "HUG";
n15.appendChild(n27);
n27.layoutSizingHorizontal = "FIXED";
n27.layoutSizingVertical = "FIXED";
n15.appendChild(n28);
try { n28.characters = "Viral Picks"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n28.layoutSizingHorizontal = "FILL";
n15.appendChild(n29);
n16.appendChild(n30);
try { n30.characters = "Energetic"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.layoutSizingHorizontal = "FILL";
n17.appendChild(n31);
try { n31.characters = "Chill"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.layoutSizingHorizontal = "FILL";
n18.appendChild(n32);
try { n32.characters = "Dark"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n19.appendChild(n33);
try { n33.characters = "Items Discovered"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.layoutSizingHorizontal = "FILL";
n19.appendChild(n34);
n34.layoutSizingHorizontal = "HUG";
n34.layoutSizingVertical = "HUG";
n20.appendChild(n35);
try { n35.characters = "Saved for Later"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n20.appendChild(n36);
n36.layoutSizingHorizontal = "HUG";
n36.layoutSizingVertical = "HUG";
n26.appendChild(n37);
try { n37.characters = "NEW"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n37.layoutSizingHorizontal = "FILL";
n34.appendChild(n38);
try { n38.characters = "247"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.layoutSizingHorizontal = "FILL";
n36.appendChild(n39);
try { n39.characters = "48"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n39.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;