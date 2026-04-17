const __errors = [];
await (async () => { try { await figma.loadFontAsync({family: "Inter", style: "Regular"}); } catch (__e) { __errors.push({kind:"font_load_failed", family:"Inter", style:"Regular", error: String(__e && __e.message || __e)}); } })();
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
const _p0 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82260"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return null; } })();
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82461"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return null; } })();


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
n2.name = "list-1";
n2.layoutMode = "VERTICAL";
n2.fills = [];
n2.clipsContent = false;
M["list-1"] = n2.id;

const n3 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n3.name = "icon_button-1";
M["icon_button-1"] = n3.id;

const n4 = figma.createFrame();
n4.name = "card-1";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["card-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "card-2";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["card-2"] = n5.id;

const n6 = figma.createFrame();
n6.name = "card-3";
n6.layoutMode = "VERTICAL";
n6.fills = [];
n6.clipsContent = false;
M["card-3"] = n6.id;

const n7 = figma.createFrame();
n7.name = "card-4";
n7.layoutMode = "VERTICAL";
n7.fills = [];
n7.clipsContent = false;
M["card-4"] = n7.id;

const n8 = figma.createFrame();
n8.name = "image-1";
n8.fills = [];
n8.clipsContent = false;
M["image-1"] = n8.id;

const n9 = figma.createFrame();
n9.name = "button_group-1";
n9.layoutMode = "VERTICAL";
n9.fills = [];
n9.clipsContent = false;
M["button_group-1"] = n9.id;

const n10 = figma.createFrame();
n10.name = "image-2";
n10.fills = [];
n10.clipsContent = false;
M["image-2"] = n10.id;

const n11 = figma.createFrame();
n11.name = "button_group-2";
n11.layoutMode = "VERTICAL";
n11.fills = [];
n11.clipsContent = false;
M["button_group-2"] = n11.id;

const n12 = figma.createFrame();
n12.name = "image-3";
n12.fills = [];
n12.clipsContent = false;
M["image-3"] = n12.id;

const n13 = figma.createFrame();
n13.name = "button_group-3";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["button_group-3"] = n13.id;

const n14 = figma.createFrame();
n14.name = "image-4";
n14.fills = [];
n14.clipsContent = false;
M["image-4"] = n14.id;

const n15 = figma.createFrame();
n15.name = "button_group-4";
n15.layoutMode = "VERTICAL";
n15.fills = [];
n15.clipsContent = false;
M["button_group-4"] = n15.id;

const n16 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n16.name = "button-1";
{ const _t = n16.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n16.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "👍 Upvote"; } }
M["button-1"] = n16.id;

const n17 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-2", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-2", 24, 24, "button-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-2", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-2", 24, 24, "button-2"); } })();
n17.name = "button-2";
{ const _t = n17.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n17.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "↗️ Share"; } }
M["button-2"] = n17.id;

const n18 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-3", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-3", 24, 24, "button-3"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-3", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-3", 24, 24, "button-3"); } })();
n18.name = "button-3";
{ const _t = n18.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n18.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "👍 Upvote"; } }
M["button-3"] = n18.id;

const n19 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-4", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-4", 24, 24, "button-4"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-4", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-4", 24, 24, "button-4"); } })();
n19.name = "button-4";
{ const _t = n19.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n19.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "↗️ Share"; } }
M["button-4"] = n19.id;

const n20 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-5", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-5", 24, 24, "button-5"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-5", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-5", 24, 24, "button-5"); } })();
n20.name = "button-5";
{ const _t = n20.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n20.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "👍 Upvote"; } }
M["button-5"] = n20.id;

const n21 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-6", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-6", 24, 24, "button-6"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-6", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-6", 24, 24, "button-6"); } })();
n21.name = "button-6";
{ const _t = n21.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n21.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "↗️ Share"; } }
M["button-6"] = n21.id;

const n22 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-7", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-7", 24, 24, "button-7"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-7", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-7", 24, 24, "button-7"); } })();
n22.name = "button-7";
{ const _t = n22.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n22.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "👍 Upvote"; } }
M["button-7"] = n22.id;

const n23 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-8", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-8", 24, 24, "button-8"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-8", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-8", 24, 24, "button-8"); } })();
n23.name = "button-8";
{ const _t = n23.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n23.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "↗️ Share"; } }
M["button-8"] = n23.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n1.appendChild(n3);
n2.appendChild(n4);
n4.layoutSizingHorizontal = "FILL";
n2.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n2.appendChild(n6);
n6.layoutSizingHorizontal = "FILL";
n2.appendChild(n7);
n7.layoutSizingHorizontal = "FILL";
n4.appendChild(n8);
n4.appendChild(n9);
n5.appendChild(n10);
n5.appendChild(n11);
n6.appendChild(n12);
n6.appendChild(n13);
n7.appendChild(n14);
n7.appendChild(n15);
n9.appendChild(n16);
n9.appendChild(n17);
n11.appendChild(n18);
n11.appendChild(n19);
n13.appendChild(n20);
n13.appendChild(n21);
n15.appendChild(n22);
n15.appendChild(n23);
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;