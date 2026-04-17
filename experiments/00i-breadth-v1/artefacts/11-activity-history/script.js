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
const _p0 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82234"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82234", error: String(__e && __e.message || __e)}); return null; } })();
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82251"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return null; } })();
const _p2 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82260"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return null; } })();
const _p3 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82310"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82310", error: String(__e && __e.message || __e)}); return null; } })();
const _p4 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82429"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82429", error: String(__e && __e.message || __e)}); return null; } })();


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

const n2 = figma.createFrame();
n2.name = "card-1";
n2.layoutMode = "VERTICAL";
n2.itemSpacing = 12;
n2.paddingTop = 16;
n2.paddingRight = 16;
n2.paddingBottom = 16;
n2.paddingLeft = 16;
n2.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n2.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n2.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n2.cornerRadius = 12;
n2.clipsContent = false;
M["card-1"] = n2.id;

const n3 = figma.createFrame();
n3.name = "card-2";
n3.layoutMode = "VERTICAL";
n3.itemSpacing = 12;
n3.paddingTop = 16;
n3.paddingRight = 16;
n3.paddingBottom = 16;
n3.paddingLeft = 16;
n3.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n3.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n3.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n3.cornerRadius = 12;
n3.clipsContent = false;
M["card-2"] = n3.id;

const n4 = figma.createFrame();
n4.name = "card-3";
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
M["card-3"] = n4.id;

const n5 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n5.name = "icon_button-1";
M["icon_button-1"] = n5.id;

const n6 = figma.createText();
n6.name = "heading-1";
try { n6.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n6.id;

const n7 = figma.createFrame();
n7.name = "list-1";
n7.layoutMode = "VERTICAL";
n7.itemSpacing = 8;
n7.paddingTop = 8;
n7.paddingRight = 12;
n7.paddingBottom = 8;
n7.paddingLeft = 12;
n7.cornerRadius = 8;
n7.fills = [];
n7.clipsContent = false;
M["list-1"] = n7.id;

const n8 = figma.createText();
n8.name = "heading-2";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n8.id;

const n9 = figma.createFrame();
n9.name = "list-2";
n9.layoutMode = "VERTICAL";
n9.itemSpacing = 8;
n9.paddingTop = 8;
n9.paddingRight = 12;
n9.paddingBottom = 8;
n9.paddingLeft = 12;
n9.cornerRadius = 8;
n9.fills = [];
n9.clipsContent = false;
M["list-2"] = n9.id;

const n10 = figma.createText();
n10.name = "heading-3";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n10.id;

const n11 = figma.createFrame();
n11.name = "list-3";
n11.layoutMode = "VERTICAL";
n11.itemSpacing = 8;
n11.paddingTop = 8;
n11.paddingRight = 12;
n11.paddingBottom = 8;
n11.paddingLeft = 12;
n11.cornerRadius = 8;
n11.fills = [];
n11.clipsContent = false;
M["list-3"] = n11.id;

const n12 = figma.createFrame();
n12.name = "list_item-1";
n12.layoutMode = "VERTICAL";
n12.itemSpacing = 12;
n12.paddingTop = 12;
n12.paddingRight = 16;
n12.paddingBottom = 12;
n12.paddingLeft = 16;
n12.counterAxisAlignItems = "CENTER";
n12.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n12.clipsContent = false;
M["list_item-1"] = n12.id;

const n13 = figma.createFrame();
n13.name = "list_item-2";
n13.layoutMode = "VERTICAL";
n13.itemSpacing = 12;
n13.paddingTop = 12;
n13.paddingRight = 16;
n13.paddingBottom = 12;
n13.paddingLeft = 16;
n13.counterAxisAlignItems = "CENTER";
n13.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n13.clipsContent = false;
M["list_item-2"] = n13.id;

const n14 = figma.createFrame();
n14.name = "list_item-3";
n14.layoutMode = "VERTICAL";
n14.itemSpacing = 12;
n14.paddingTop = 12;
n14.paddingRight = 16;
n14.paddingBottom = 12;
n14.paddingLeft = 16;
n14.counterAxisAlignItems = "CENTER";
n14.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n14.clipsContent = false;
M["list_item-3"] = n14.id;

const n15 = figma.createFrame();
n15.name = "list_item-4";
n15.layoutMode = "VERTICAL";
n15.itemSpacing = 12;
n15.paddingTop = 12;
n15.paddingRight = 16;
n15.paddingBottom = 12;
n15.paddingLeft = 16;
n15.counterAxisAlignItems = "CENTER";
n15.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n15.clipsContent = false;
M["list_item-4"] = n15.id;

const n16 = figma.createFrame();
n16.name = "list_item-5";
n16.layoutMode = "VERTICAL";
n16.itemSpacing = 12;
n16.paddingTop = 12;
n16.paddingRight = 16;
n16.paddingBottom = 12;
n16.paddingLeft = 16;
n16.counterAxisAlignItems = "CENTER";
n16.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n16.clipsContent = false;
M["list_item-5"] = n16.id;

const n17 = figma.createFrame();
n17.name = "list_item-6";
n17.layoutMode = "VERTICAL";
n17.itemSpacing = 12;
n17.paddingTop = 12;
n17.paddingRight = 16;
n17.paddingBottom = 12;
n17.paddingLeft = 16;
n17.counterAxisAlignItems = "CENTER";
n17.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n17.clipsContent = false;
M["list_item-6"] = n17.id;

const n18 = figma.createFrame();
n18.name = "list_item-7";
n18.layoutMode = "VERTICAL";
n18.itemSpacing = 12;
n18.paddingTop = 12;
n18.paddingRight = 16;
n18.paddingBottom = 12;
n18.paddingLeft = 16;
n18.counterAxisAlignItems = "CENTER";
n18.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n18.clipsContent = false;
M["list_item-7"] = n18.id;

const n19 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-1", kind:"missing_component_node", id:"5749:82234"}); return _missingComponentPlaceholder("icon-1", 24, 24, "icon-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-1", kind:"create_instance_failed", id:"5749:82234", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-1", 24, 24, "icon-1"); } })();
n19.name = "icon-1";
M["icon-1"] = n19.id;

const n20 = figma.createText();
n20.name = "text-1";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n20.id;

const n21 = figma.createText();
n21.name = "text-2";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n21.id;

const n22 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"icon-2", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-2", 24, 24, "icon-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-2", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-2", 24, 24, "icon-2"); } })();
n22.name = "icon-2";
M["icon-2"] = n22.id;

const n23 = figma.createText();
n23.name = "text-3";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n23.id;

const n24 = figma.createText();
n24.name = "text-4";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n24.id;

const n25 = await (async () => { const __src = _p3; if (!__src) { __errors.push({eid:"icon-3", kind:"missing_component_node", id:"5749:82310"}); return _missingComponentPlaceholder("icon-3", 24, 24, "icon-3"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-3", kind:"create_instance_failed", id:"5749:82310", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-3", 24, 24, "icon-3"); } })();
n25.name = "icon-3";
M["icon-3"] = n25.id;

const n26 = figma.createText();
n26.name = "text-5";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n26.id;

const n27 = figma.createText();
n27.name = "text-6";
try { n27.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n27.id;

const n28 = await (async () => { const __src = _p4; if (!__src) { __errors.push({eid:"icon-4", kind:"missing_component_node", id:"5749:82429"}); return _missingComponentPlaceholder("icon-4", 24, 24, "icon-4"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-4", kind:"create_instance_failed", id:"5749:82429", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-4", 24, 24, "icon-4"); } })();
n28.name = "icon-4";
M["icon-4"] = n28.id;

const n29 = figma.createText();
n29.name = "text-7";
try { n29.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n29.id;

const n30 = figma.createText();
n30.name = "text-8";
try { n30.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n30.id;

const n31 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-5", kind:"missing_component_node", id:"5749:82234"}); return _missingComponentPlaceholder("icon-5", 24, 24, "icon-5"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-5", kind:"create_instance_failed", id:"5749:82234", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-5", 24, 24, "icon-5"); } })();
n31.name = "icon-5";
M["icon-5"] = n31.id;

const n32 = figma.createText();
n32.name = "text-9";
try { n32.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n32.id;

const n33 = figma.createText();
n33.name = "text-10";
try { n33.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n33.id;

const n34 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"icon-6", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-6", 24, 24, "icon-6"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-6", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-6", 24, 24, "icon-6"); } })();
n34.name = "icon-6";
M["icon-6"] = n34.id;

const n35 = figma.createText();
n35.name = "text-11";
try { n35.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n35.id;

const n36 = figma.createText();
n36.name = "text-12";
try { n36.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-12"] = n36.id;

const n37 = await (async () => { const __src = _p3; if (!__src) { __errors.push({eid:"icon-7", kind:"missing_component_node", id:"5749:82310"}); return _missingComponentPlaceholder("icon-7", 24, 24, "icon-7"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-7", kind:"create_instance_failed", id:"5749:82310", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-7", 24, 24, "icon-7"); } })();
n37.name = "icon-7";
M["icon-7"] = n37.id;

const n38 = figma.createText();
n38.name = "text-13";
try { n38.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-13"] = n38.id;

const n39 = figma.createText();
n39.name = "text-14";
try { n39.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-14"] = n39.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n1.layoutSizingVertical = "FIXED";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n2.layoutSizingVertical = "HUG";
n0.appendChild(n3);
n3.layoutSizingHorizontal = "FILL";
n3.layoutSizingVertical = "HUG";
n0.appendChild(n4);
n4.layoutSizingHorizontal = "FILL";
n4.layoutSizingVertical = "HUG";
n1.appendChild(n5);
n2.appendChild(n6);
try { n6.characters = "Today"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n6.layoutSizingHorizontal = "FILL";
n2.appendChild(n7);
n7.layoutSizingHorizontal = "FILL";
n7.layoutSizingVertical = "HUG";
n3.appendChild(n8);
try { n8.characters = "Yesterday"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n3.appendChild(n9);
n9.layoutSizingHorizontal = "FILL";
n9.layoutSizingVertical = "HUG";
n4.appendChild(n10);
try { n10.characters = "Last Week"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n4.appendChild(n11);
n11.layoutSizingHorizontal = "FILL";
n11.layoutSizingVertical = "HUG";
n7.appendChild(n12);
n12.layoutSizingHorizontal = "FILL";
n12.layoutSizingVertical = "HUG";
n7.appendChild(n13);
n13.layoutSizingHorizontal = "FILL";
n13.layoutSizingVertical = "HUG";
n7.appendChild(n14);
n14.layoutSizingHorizontal = "FILL";
n14.layoutSizingVertical = "HUG";
n9.appendChild(n15);
n15.layoutSizingHorizontal = "FILL";
n15.layoutSizingVertical = "HUG";
n9.appendChild(n16);
n16.layoutSizingHorizontal = "FILL";
n16.layoutSizingVertical = "HUG";
n11.appendChild(n17);
n17.layoutSizingHorizontal = "FILL";
n17.layoutSizingVertical = "HUG";
n11.appendChild(n18);
n18.layoutSizingHorizontal = "FILL";
n18.layoutSizingVertical = "HUG";
n12.appendChild(n19);
n12.appendChild(n20);
try { n20.characters = "Payment received"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n12.appendChild(n21);
try { n21.characters = "2:45 PM"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n13.appendChild(n22);
n13.appendChild(n23);
try { n23.characters = "Task completed"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n13.appendChild(n24);
try { n24.characters = "1:30 PM"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n14.appendChild(n25);
n14.appendChild(n26);
try { n26.characters = "New file created"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
n14.appendChild(n27);
try { n27.characters = "11:15 AM"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n27.layoutSizingHorizontal = "FILL";
n15.appendChild(n28);
n15.appendChild(n29);
try { n29.characters = "Item deleted"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.layoutSizingHorizontal = "FILL";
n15.appendChild(n30);
try { n30.characters = "4:20 PM"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.layoutSizingHorizontal = "FILL";
n16.appendChild(n31);
n16.appendChild(n32);
try { n32.characters = "Payment sent"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n16.appendChild(n33);
try { n33.characters = "3:00 PM"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.layoutSizingHorizontal = "FILL";
n17.appendChild(n34);
n17.appendChild(n35);
try { n35.characters = "Project milestone reached"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n17.appendChild(n36);
try { n36.characters = "Mar 15, 2:30 PM"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.layoutSizingHorizontal = "FILL";
n18.appendChild(n37);
n18.appendChild(n38);
try { n38.characters = "Account updated"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.layoutSizingHorizontal = "FILL";
n18.appendChild(n39);
try { n39.characters = "Mar 12, 10:45 AM"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n39.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;