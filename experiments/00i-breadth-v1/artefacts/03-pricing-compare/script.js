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
const _p0 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82251"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return null; } })();
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82260"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return null; } })();
const _p2 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82323"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return null; } })();
const _p3 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82457"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return null; } })();


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
n1.itemSpacing = 8;
n1.paddingTop = 12;
n1.paddingRight = 16;
n1.paddingBottom = 12;
n1.paddingLeft = 16;
n1.resize(n1.width, 56);
n1.primaryAxisAlignItems = "SPACE_BETWEEN";
n1.counterAxisAlignItems = "CENTER";
n1.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n1.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n1.clipsContent = false;
M["header-1"] = n1.id;

const n2 = figma.createText();
n2.name = "heading-1";
try { n2.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n2.id;

const n3 = figma.createText();
n3.name = "text-2";
try { n3.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n3.id;

const n4 = figma.createFrame();
n4.name = "card-1";
n4.layoutMode = "VERTICAL";
n4.itemSpacing = 12;
n4.paddingTop = 16;
n4.paddingRight = 16;
n4.paddingBottom = 16;
n4.paddingLeft = 16;
n4.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n4.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n4.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n4.cornerRadius = 12;
n4.clipsContent = false;
M["card-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "card-2";
n5.layoutMode = "VERTICAL";
n5.itemSpacing = 12;
n5.paddingTop = 16;
n5.paddingRight = 16;
n5.paddingBottom = 16;
n5.paddingLeft = 16;
n5.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n5.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n5.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n5.cornerRadius = 12;
n5.clipsContent = false;
M["card-2"] = n5.id;

const n6 = await (async () => { const __src = _p3; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n6.name = "button-1";
{ const _t = n6.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n6.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Get Started"; } }
M["button-1"] = n6.id;

const n7 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n7.name = "icon_button-1";
M["icon_button-1"] = n7.id;

const n8 = figma.createText();
n8.name = "text-1";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n8.id;

const n9 = figma.createFrame();
n9.name = "table-1";
n9.layoutMode = "VERTICAL";
n9.fills = [];
n9.clipsContent = false;
M["table-1"] = n9.id;

const n10 = figma.createText();
n10.name = "heading-2";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n10.id;

const n11 = figma.createFrame();
n11.name = "list-1";
n11.layoutMode = "VERTICAL";
n11.itemSpacing = 8;
n11.paddingTop = 8;
n11.paddingRight = 12;
n11.paddingBottom = 8;
n11.paddingLeft = 12;
n11.cornerRadius = 8;
n11.fills = [];
n11.clipsContent = false;
M["list-1"] = n11.id;

const n12 = figma.createText();
n12.name = "text-3";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n12.id;

const n13 = figma.createText();
n13.name = "text-4";
try { n13.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n13.id;

const n14 = figma.createText();
n14.name = "text-5";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n14.id;

const n15 = figma.createText();
n15.name = "text-6";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n15.id;

const n16 = figma.createText();
n16.name = "text-7";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n16.id;

const n17 = figma.createText();
n17.name = "text-8";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n17.id;

const n18 = figma.createText();
n18.name = "text-9";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n18.id;

const n19 = figma.createText();
n19.name = "text-10";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n19.id;

const n20 = figma.createText();
n20.name = "text-11";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n20.id;

const n21 = figma.createText();
n21.name = "text-12";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-12"] = n21.id;

const n22 = figma.createText();
n22.name = "text-13";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-13"] = n22.id;

const n23 = figma.createText();
n23.name = "text-14";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-14"] = n23.id;

const n24 = figma.createText();
n24.name = "text-15";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-15"] = n24.id;

const n25 = figma.createText();
n25.name = "text-16";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-16"] = n25.id;

const n26 = figma.createText();
n26.name = "text-17";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-17"] = n26.id;

const n27 = figma.createText();
n27.name = "text-18";
try { n27.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-18"] = n27.id;

const n28 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"icon-1", kind:"missing_component_node", id:"5749:82323"}); return _missingComponentPlaceholder("icon-1", 24, 24, "icon-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-1", kind:"create_instance_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-1", 24, 24, "icon-1"); } })();
n28.name = "icon-1";
M["icon-1"] = n28.id;

const n29 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-2", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-2", 24, 24, "icon-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-2", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-2", 24, 24, "icon-2"); } })();
n29.name = "icon-2";
M["icon-2"] = n29.id;

const n30 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-3", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-3", 24, 24, "icon-3"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-3", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-3", 24, 24, "icon-3"); } })();
n30.name = "icon-3";
M["icon-3"] = n30.id;

const n31 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-4", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-4", 24, 24, "icon-4"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-4", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-4", 24, 24, "icon-4"); } })();
n31.name = "icon-4";
M["icon-4"] = n31.id;

const n32 = figma.createText();
n32.name = "text-19";
try { n32.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-19"] = n32.id;

const n33 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"icon-5", kind:"missing_component_node", id:"5749:82323"}); return _missingComponentPlaceholder("icon-5", 24, 24, "icon-5"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-5", kind:"create_instance_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-5", 24, 24, "icon-5"); } })();
n33.name = "icon-5";
M["icon-5"] = n33.id;

const n34 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"icon-6", kind:"missing_component_node", id:"5749:82323"}); return _missingComponentPlaceholder("icon-6", 24, 24, "icon-6"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-6", kind:"create_instance_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-6", 24, 24, "icon-6"); } })();
n34.name = "icon-6";
M["icon-6"] = n34.id;

const n35 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-7", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-7", 24, 24, "icon-7"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-7", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-7", 24, 24, "icon-7"); } })();
n35.name = "icon-7";
M["icon-7"] = n35.id;

const n36 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-8", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-8", 24, 24, "icon-8"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-8", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-8", 24, 24, "icon-8"); } })();
n36.name = "icon-8";
M["icon-8"] = n36.id;

const n37 = figma.createText();
n37.name = "text-20";
try { n37.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-20"] = n37.id;

const n38 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"icon-9", kind:"missing_component_node", id:"5749:82323"}); return _missingComponentPlaceholder("icon-9", 24, 24, "icon-9"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-9", kind:"create_instance_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-9", 24, 24, "icon-9"); } })();
n38.name = "icon-9";
M["icon-9"] = n38.id;

const n39 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-10", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-10", 24, 24, "icon-10"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-10", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-10", 24, 24, "icon-10"); } })();
n39.name = "icon-10";
M["icon-10"] = n39.id;

const n40 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-11", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-11", 24, 24, "icon-11"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-11", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-11", 24, 24, "icon-11"); } })();
n40.name = "icon-11";
M["icon-11"] = n40.id;

const n41 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-12", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-12", 24, 24, "icon-12"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-12", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-12", 24, 24, "icon-12"); } })();
n41.name = "icon-12";
M["icon-12"] = n41.id;

const n42 = figma.createText();
n42.name = "text-21";
try { n42.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-21", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-21"] = n42.id;

const n43 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"icon-13", kind:"missing_component_node", id:"5749:82323"}); return _missingComponentPlaceholder("icon-13", 24, 24, "icon-13"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-13", kind:"create_instance_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-13", 24, 24, "icon-13"); } })();
n43.name = "icon-13";
M["icon-13"] = n43.id;

const n44 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"icon-14", kind:"missing_component_node", id:"5749:82323"}); return _missingComponentPlaceholder("icon-14", 24, 24, "icon-14"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-14", kind:"create_instance_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-14", 24, 24, "icon-14"); } })();
n44.name = "icon-14";
M["icon-14"] = n44.id;

const n45 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"icon-15", kind:"missing_component_node", id:"5749:82323"}); return _missingComponentPlaceholder("icon-15", 24, 24, "icon-15"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-15", kind:"create_instance_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-15", 24, 24, "icon-15"); } })();
n45.name = "icon-15";
M["icon-15"] = n45.id;

const n46 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-16", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-16", 24, 24, "icon-16"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-16", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-16", 24, 24, "icon-16"); } })();
n46.name = "icon-16";
M["icon-16"] = n46.id;

const n47 = figma.createFrame();
n47.name = "list_item-1";
n47.layoutMode = "VERTICAL";
n47.itemSpacing = 12;
n47.paddingTop = 12;
n47.paddingRight = 16;
n47.paddingBottom = 12;
n47.paddingLeft = 16;
n47.counterAxisAlignItems = "CENTER";
n47.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n47.clipsContent = false;
M["list_item-1"] = n47.id;

const n48 = figma.createFrame();
n48.name = "list_item-2";
n48.layoutMode = "VERTICAL";
n48.itemSpacing = 12;
n48.paddingTop = 12;
n48.paddingRight = 16;
n48.paddingBottom = 12;
n48.paddingLeft = 16;
n48.counterAxisAlignItems = "CENTER";
n48.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n48.clipsContent = false;
M["list_item-2"] = n48.id;

const n49 = figma.createFrame();
n49.name = "list_item-3";
n49.layoutMode = "VERTICAL";
n49.itemSpacing = 12;
n49.paddingTop = 12;
n49.paddingRight = 16;
n49.paddingBottom = 12;
n49.paddingLeft = 16;
n49.counterAxisAlignItems = "CENTER";
n49.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n49.clipsContent = false;
M["list_item-3"] = n49.id;

const n50 = figma.createFrame();
n50.name = "list_item-4";
n50.layoutMode = "VERTICAL";
n50.itemSpacing = 12;
n50.paddingTop = 12;
n50.paddingRight = 16;
n50.paddingBottom = 12;
n50.paddingLeft = 16;
n50.counterAxisAlignItems = "CENTER";
n50.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n50.clipsContent = false;
M["list_item-4"] = n50.id;

const n51 = figma.createText();
n51.name = "text-22";
try { n51.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-22", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-22"] = n51.id;

const n52 = figma.createText();
n52.name = "text-23";
try { n52.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-23", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-23"] = n52.id;

const n53 = figma.createText();
n53.name = "text-24";
try { n53.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-24", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-24"] = n53.id;

const n54 = figma.createText();
n54.name = "text-25";
try { n54.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-25", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-25"] = n54.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n1.layoutSizingVertical = "FIXED";
n0.appendChild(n2);
try { n2.characters = "Compare Our Plans"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n2.layoutSizingHorizontal = "FILL";
n0.appendChild(n3);
try { n3.characters = "Choose the perfect plan for your needs"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n3.layoutSizingHorizontal = "FILL";
n0.appendChild(n4);
n4.layoutSizingHorizontal = "FILL";
n4.layoutSizingVertical = "HUG";
n0.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n5.layoutSizingVertical = "HUG";
n0.appendChild(n6);
n6.layoutSizingHorizontal = "FILL";
n1.appendChild(n7);
n1.appendChild(n8);
try { n8.characters = "Pricing Plans"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n4.appendChild(n9);
n5.appendChild(n10);
try { n10.characters = "Pricing"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n5.appendChild(n11);
n11.layoutSizingHorizontal = "FILL";
n11.layoutSizingVertical = "HUG";
n9.appendChild(n12);
try { n12.characters = "Feature"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n9.appendChild(n13);
try { n13.characters = "Free"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n9.appendChild(n14);
try { n14.characters = "Pro"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n9.appendChild(n15);
try { n15.characters = "Team"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n9.appendChild(n16);
try { n16.characters = "Enterprise"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n9.appendChild(n17);
try { n17.characters = "Users"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n9.appendChild(n18);
try { n18.characters = "1"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n9.appendChild(n19);
try { n19.characters = "Unlimited"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n9.appendChild(n20);
try { n20.characters = "Unlimited"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n9.appendChild(n21);
try { n21.characters = "Unlimited"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n9.appendChild(n22);
try { n22.characters = "Storage"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n9.appendChild(n23);
try { n23.characters = "5 GB"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n9.appendChild(n24);
try { n24.characters = "100 GB"; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n9.appendChild(n25);
try { n25.characters = "1 TB"; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n9.appendChild(n26);
try { n26.characters = "Custom"; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
n9.appendChild(n27);
try { n27.characters = "API Access"; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n27.layoutSizingHorizontal = "FILL";
n9.appendChild(n28);
n9.appendChild(n29);
n9.appendChild(n30);
n9.appendChild(n31);
n9.appendChild(n32);
try { n32.characters = "Priority Support"; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n9.appendChild(n33);
n9.appendChild(n34);
n9.appendChild(n35);
n9.appendChild(n36);
n9.appendChild(n37);
try { n37.characters = "Advanced Analytics"; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n37.layoutSizingHorizontal = "FILL";
n9.appendChild(n38);
n9.appendChild(n39);
n9.appendChild(n40);
n9.appendChild(n41);
n9.appendChild(n42);
try { n42.characters = "Custom Integrations"; } catch (__e) { __errors.push({eid:"text-21", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.layoutSizingHorizontal = "FILL";
n9.appendChild(n43);
n9.appendChild(n44);
n9.appendChild(n45);
n9.appendChild(n46);
n11.appendChild(n47);
n47.layoutSizingHorizontal = "FILL";
n47.layoutSizingVertical = "HUG";
n11.appendChild(n48);
n48.layoutSizingHorizontal = "FILL";
n48.layoutSizingVertical = "HUG";
n11.appendChild(n49);
n49.layoutSizingHorizontal = "FILL";
n49.layoutSizingVertical = "HUG";
n11.appendChild(n50);
n50.layoutSizingHorizontal = "FILL";
n50.layoutSizingVertical = "HUG";
n47.appendChild(n51);
try { n51.characters = "Free — $0/month"; } catch (__e) { __errors.push({eid:"text-22", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n51.layoutSizingHorizontal = "FILL";
n48.appendChild(n52);
try { n52.characters = "Pro — $29/month"; } catch (__e) { __errors.push({eid:"text-23", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n52.layoutSizingHorizontal = "FILL";
n49.appendChild(n53);
try { n53.characters = "Team — $99/month"; } catch (__e) { __errors.push({eid:"text-24", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n53.layoutSizingHorizontal = "FILL";
n50.appendChild(n54);
try { n54.characters = "Enterprise — Custom pricing"; } catch (__e) { __errors.push({eid:"text-25", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n54.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;