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
const _p0 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82251"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return null; } })();
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82260"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return null; } })();


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

const n6 = figma.createFrame();
n6.name = "card-3";
n6.layoutMode = "VERTICAL";
n6.itemSpacing = 12;
n6.paddingTop = 16;
n6.paddingRight = 16;
n6.paddingBottom = 16;
n6.paddingLeft = 16;
n6.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n6.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n6.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n6.cornerRadius = 12;
n6.clipsContent = false;
M["card-3"] = n6.id;

const n7 = figma.createFrame();
n7.name = "card-4";
n7.layoutMode = "VERTICAL";
n7.itemSpacing = 12;
n7.paddingTop = 16;
n7.paddingRight = 16;
n7.paddingBottom = 16;
n7.paddingLeft = 16;
n7.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n7.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n7.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n7.cornerRadius = 12;
n7.clipsContent = false;
M["card-4"] = n7.id;

const n8 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n8.name = "icon_button-1";
M["icon_button-1"] = n8.id;

const n9 = figma.createText();
n9.name = "text-1";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n9.id;

const n10 = figma.createText();
n10.name = "heading-2";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n10.id;

const n11 = figma.createText();
n11.name = "text-3";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n11.id;

const n12 = figma.createFrame();
n12.name = "list-1";
n12.layoutMode = "VERTICAL";
n12.itemSpacing = 8;
n12.paddingTop = 8;
n12.paddingRight = 12;
n12.paddingBottom = 8;
n12.paddingLeft = 12;
n12.cornerRadius = 8;
n12.fills = [];
n12.clipsContent = false;
M["list-1"] = n12.id;

const n13 = figma.createFrame();
n13.name = "button-1";
n13.layoutMode = "VERTICAL";
n13.itemSpacing = 8;
n13.paddingTop = 10;
n13.paddingRight = 16;
n13.paddingBottom = 10;
n13.paddingLeft = 16;
n13.resize(n13.width, 44);
n13.primaryAxisAlignItems = "CENTER";
n13.counterAxisAlignItems = "CENTER";
n13.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n13.cornerRadius = 8;
n13.clipsContent = false;
M["button-1"] = n13.id;

const n14 = figma.createText();
n14.name = "heading-3";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n14.id;

const n15 = figma.createText();
n15.name = "text-8";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n15.id;

const n16 = figma.createFrame();
n16.name = "badge-1";
n16.layoutMode = "VERTICAL";
n16.itemSpacing = 4;
n16.paddingTop = 4;
n16.paddingRight = 8;
n16.paddingBottom = 4;
n16.paddingLeft = 8;
n16.counterAxisAlignItems = "CENTER";
n16.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n16.cornerRadius = 999;
n16.clipsContent = false;
M["badge-1"] = n16.id;

const n17 = figma.createFrame();
n17.name = "list-2";
n17.layoutMode = "VERTICAL";
n17.itemSpacing = 8;
n17.paddingTop = 8;
n17.paddingRight = 12;
n17.paddingBottom = 8;
n17.paddingLeft = 12;
n17.cornerRadius = 8;
n17.fills = [];
n17.clipsContent = false;
M["list-2"] = n17.id;

const n18 = figma.createFrame();
n18.name = "button-2";
n18.layoutMode = "VERTICAL";
n18.itemSpacing = 8;
n18.paddingTop = 10;
n18.paddingRight = 16;
n18.paddingBottom = 10;
n18.paddingLeft = 16;
n18.resize(n18.width, 44);
n18.primaryAxisAlignItems = "CENTER";
n18.counterAxisAlignItems = "CENTER";
n18.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n18.cornerRadius = 8;
n18.clipsContent = false;
M["button-2"] = n18.id;

const n19 = figma.createText();
n19.name = "heading-4";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-4"] = n19.id;

const n20 = figma.createText();
n20.name = "text-15";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-15"] = n20.id;

const n21 = figma.createFrame();
n21.name = "list-3";
n21.layoutMode = "VERTICAL";
n21.itemSpacing = 8;
n21.paddingTop = 8;
n21.paddingRight = 12;
n21.paddingBottom = 8;
n21.paddingLeft = 12;
n21.cornerRadius = 8;
n21.fills = [];
n21.clipsContent = false;
M["list-3"] = n21.id;

const n22 = figma.createFrame();
n22.name = "button-3";
n22.layoutMode = "VERTICAL";
n22.itemSpacing = 8;
n22.paddingTop = 10;
n22.paddingRight = 16;
n22.paddingBottom = 10;
n22.paddingLeft = 16;
n22.resize(n22.width, 44);
n22.primaryAxisAlignItems = "CENTER";
n22.counterAxisAlignItems = "CENTER";
n22.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n22.cornerRadius = 8;
n22.clipsContent = false;
M["button-3"] = n22.id;

const n23 = figma.createText();
n23.name = "text-21";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-21", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-21"] = n23.id;

const n24 = figma.createFrame();
n24.name = "avatar-1";
n24.layoutMode = "VERTICAL";
n24.primaryAxisAlignItems = "CENTER";
n24.counterAxisAlignItems = "CENTER";
n24.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n24.cornerRadius = 999;
n24.clipsContent = false;
M["avatar-1"] = n24.id;

const n25 = figma.createText();
n25.name = "text-22";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-22", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-22"] = n25.id;

const n26 = figma.createFrame();
n26.name = "list_item-1";
n26.layoutMode = "VERTICAL";
n26.itemSpacing = 12;
n26.paddingTop = 12;
n26.paddingRight = 16;
n26.paddingBottom = 12;
n26.paddingLeft = 16;
n26.counterAxisAlignItems = "CENTER";
n26.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n26.clipsContent = false;
M["list_item-1"] = n26.id;

const n27 = figma.createFrame();
n27.name = "list_item-2";
n27.layoutMode = "VERTICAL";
n27.itemSpacing = 12;
n27.paddingTop = 12;
n27.paddingRight = 16;
n27.paddingBottom = 12;
n27.paddingLeft = 16;
n27.counterAxisAlignItems = "CENTER";
n27.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n27.clipsContent = false;
M["list_item-2"] = n27.id;

const n28 = figma.createFrame();
n28.name = "list_item-3";
n28.layoutMode = "VERTICAL";
n28.itemSpacing = 12;
n28.paddingTop = 12;
n28.paddingRight = 16;
n28.paddingBottom = 12;
n28.paddingLeft = 16;
n28.counterAxisAlignItems = "CENTER";
n28.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n28.clipsContent = false;
M["list_item-3"] = n28.id;

const n29 = figma.createText();
n29.name = "text-7";
n29.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
try { n29.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.fontSize = 14;
M["text-7"] = n29.id;

const n30 = figma.createText();
n30.name = "text-9";
n30.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n30.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.fontSize = 12;
M["text-9"] = n30.id;

const n31 = figma.createFrame();
n31.name = "list_item-4";
n31.layoutMode = "VERTICAL";
n31.itemSpacing = 12;
n31.paddingTop = 12;
n31.paddingRight = 16;
n31.paddingBottom = 12;
n31.paddingLeft = 16;
n31.counterAxisAlignItems = "CENTER";
n31.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n31.clipsContent = false;
M["list_item-4"] = n31.id;

const n32 = figma.createFrame();
n32.name = "list_item-5";
n32.layoutMode = "VERTICAL";
n32.itemSpacing = 12;
n32.paddingTop = 12;
n32.paddingRight = 16;
n32.paddingBottom = 12;
n32.paddingLeft = 16;
n32.counterAxisAlignItems = "CENTER";
n32.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n32.clipsContent = false;
M["list_item-5"] = n32.id;

const n33 = figma.createFrame();
n33.name = "list_item-6";
n33.layoutMode = "VERTICAL";
n33.itemSpacing = 12;
n33.paddingTop = 12;
n33.paddingRight = 16;
n33.paddingBottom = 12;
n33.paddingLeft = 16;
n33.counterAxisAlignItems = "CENTER";
n33.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n33.clipsContent = false;
M["list_item-6"] = n33.id;

const n34 = figma.createFrame();
n34.name = "list_item-7";
n34.layoutMode = "VERTICAL";
n34.itemSpacing = 12;
n34.paddingTop = 12;
n34.paddingRight = 16;
n34.paddingBottom = 12;
n34.paddingLeft = 16;
n34.counterAxisAlignItems = "CENTER";
n34.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n34.clipsContent = false;
M["list_item-7"] = n34.id;

const n35 = figma.createText();
n35.name = "text-14";
n35.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
try { n35.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.fontSize = 14;
M["text-14"] = n35.id;

const n36 = figma.createFrame();
n36.name = "list_item-8";
n36.layoutMode = "VERTICAL";
n36.itemSpacing = 12;
n36.paddingTop = 12;
n36.paddingRight = 16;
n36.paddingBottom = 12;
n36.paddingLeft = 16;
n36.counterAxisAlignItems = "CENTER";
n36.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n36.clipsContent = false;
M["list_item-8"] = n36.id;

const n37 = figma.createFrame();
n37.name = "list_item-9";
n37.layoutMode = "VERTICAL";
n37.itemSpacing = 12;
n37.paddingTop = 12;
n37.paddingRight = 16;
n37.paddingBottom = 12;
n37.paddingLeft = 16;
n37.counterAxisAlignItems = "CENTER";
n37.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n37.clipsContent = false;
M["list_item-9"] = n37.id;

const n38 = figma.createFrame();
n38.name = "list_item-10";
n38.layoutMode = "VERTICAL";
n38.itemSpacing = 12;
n38.paddingTop = 12;
n38.paddingRight = 16;
n38.paddingBottom = 12;
n38.paddingLeft = 16;
n38.counterAxisAlignItems = "CENTER";
n38.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n38.clipsContent = false;
M["list_item-10"] = n38.id;

const n39 = figma.createFrame();
n39.name = "list_item-11";
n39.layoutMode = "VERTICAL";
n39.itemSpacing = 12;
n39.paddingTop = 12;
n39.paddingRight = 16;
n39.paddingBottom = 12;
n39.paddingLeft = 16;
n39.counterAxisAlignItems = "CENTER";
n39.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n39.clipsContent = false;
M["list_item-11"] = n39.id;

const n40 = figma.createText();
n40.name = "text-20";
n40.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
try { n40.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.fontSize = 14;
M["text-20"] = n40.id;

const n41 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-1", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-1", 24, 24, "icon-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-1", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-1", 24, 24, "icon-1"); } })();
n41.name = "icon-1";
M["icon-1"] = n41.id;

const n42 = figma.createText();
n42.name = "text-4";
try { n42.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n42.id;

const n43 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-2", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-2", 24, 24, "icon-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-2", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-2", 24, 24, "icon-2"); } })();
n43.name = "icon-2";
M["icon-2"] = n43.id;

const n44 = figma.createText();
n44.name = "text-5";
try { n44.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n44.id;

const n45 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-3", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-3", 24, 24, "icon-3"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-3", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-3", 24, 24, "icon-3"); } })();
n45.name = "icon-3";
M["icon-3"] = n45.id;

const n46 = figma.createText();
n46.name = "text-6";
try { n46.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n46.id;

const n47 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-4", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-4", 24, 24, "icon-4"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-4", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-4", 24, 24, "icon-4"); } })();
n47.name = "icon-4";
M["icon-4"] = n47.id;

const n48 = figma.createText();
n48.name = "text-10";
try { n48.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n48.id;

const n49 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-5", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-5", 24, 24, "icon-5"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-5", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-5", 24, 24, "icon-5"); } })();
n49.name = "icon-5";
M["icon-5"] = n49.id;

const n50 = figma.createText();
n50.name = "text-11";
try { n50.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n50.id;

const n51 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-6", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-6", 24, 24, "icon-6"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-6", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-6", 24, 24, "icon-6"); } })();
n51.name = "icon-6";
M["icon-6"] = n51.id;

const n52 = figma.createText();
n52.name = "text-12";
try { n52.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-12"] = n52.id;

const n53 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-7", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-7", 24, 24, "icon-7"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-7", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-7", 24, 24, "icon-7"); } })();
n53.name = "icon-7";
M["icon-7"] = n53.id;

const n54 = figma.createText();
n54.name = "text-13";
try { n54.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-13"] = n54.id;

const n55 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-8", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-8", 24, 24, "icon-8"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-8", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-8", 24, 24, "icon-8"); } })();
n55.name = "icon-8";
M["icon-8"] = n55.id;

const n56 = figma.createText();
n56.name = "text-16";
try { n56.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-16"] = n56.id;

const n57 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-9", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-9", 24, 24, "icon-9"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-9", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-9", 24, 24, "icon-9"); } })();
n57.name = "icon-9";
M["icon-9"] = n57.id;

const n58 = figma.createText();
n58.name = "text-17";
try { n58.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-17"] = n58.id;

const n59 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-10", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-10", 24, 24, "icon-10"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-10", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-10", 24, 24, "icon-10"); } })();
n59.name = "icon-10";
M["icon-10"] = n59.id;

const n60 = figma.createText();
n60.name = "text-18";
try { n60.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-18"] = n60.id;

const n61 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-11", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-11", 24, 24, "icon-11"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-11", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-11", 24, 24, "icon-11"); } })();
n61.name = "icon-11";
M["icon-11"] = n61.id;

const n62 = figma.createText();
n62.name = "text-19";
try { n62.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-19"] = n62.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n1.layoutSizingVertical = "FIXED";
n0.appendChild(n2);
try { n2.characters = "Unlock Premium Features"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n2.layoutSizingHorizontal = "FILL";
n0.appendChild(n3);
try { n3.characters = "Select the perfect plan for your needs"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n3.layoutSizingHorizontal = "FILL";
n0.appendChild(n4);
n4.layoutSizingHorizontal = "FILL";
n4.layoutSizingVertical = "HUG";
n0.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n5.layoutSizingVertical = "HUG";
n0.appendChild(n6);
n6.layoutSizingHorizontal = "FILL";
n6.layoutSizingVertical = "HUG";
n0.appendChild(n7);
n7.layoutSizingHorizontal = "FILL";
n7.layoutSizingVertical = "HUG";
n1.appendChild(n8);
n1.appendChild(n9);
try { n9.characters = "Choose Your Plan"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n4.appendChild(n10);
try { n10.characters = "Starter"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n4.appendChild(n11);
try { n11.characters = "$9/month"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n4.appendChild(n12);
n12.layoutSizingHorizontal = "FILL";
n12.layoutSizingVertical = "HUG";
n4.appendChild(n13);
n13.layoutSizingHorizontal = "HUG";
n13.layoutSizingVertical = "FIXED";
n5.appendChild(n14);
try { n14.characters = "Professional"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n5.appendChild(n15);
try { n15.characters = "$29/month"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n5.appendChild(n16);
n16.layoutSizingHorizontal = "HUG";
n16.layoutSizingVertical = "HUG";
n5.appendChild(n17);
n17.layoutSizingHorizontal = "FILL";
n17.layoutSizingVertical = "HUG";
n5.appendChild(n18);
n18.layoutSizingHorizontal = "HUG";
n18.layoutSizingVertical = "FIXED";
n6.appendChild(n19);
try { n19.characters = "Enterprise"; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n6.appendChild(n20);
try { n20.characters = "Custom pricing"; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n6.appendChild(n21);
n21.layoutSizingHorizontal = "FILL";
n21.layoutSizingVertical = "HUG";
n6.appendChild(n22);
n22.layoutSizingHorizontal = "HUG";
n22.layoutSizingVertical = "FIXED";
n7.appendChild(n23);
try { n23.characters = "\"This service transformed how we manage our workflow. Highly recommended!\""; } catch (__e) { __errors.push({eid:"text-21", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n7.appendChild(n24);
n24.layoutSizingHorizontal = "FIXED";
n24.layoutSizingVertical = "FIXED";
n7.appendChild(n25);
try { n25.characters = "Sarah Johnson, CEO at TechCorp"; } catch (__e) { __errors.push({eid:"text-22", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n12.appendChild(n26);
n26.layoutSizingHorizontal = "FILL";
n26.layoutSizingVertical = "HUG";
n12.appendChild(n27);
n27.layoutSizingHorizontal = "FILL";
n27.layoutSizingVertical = "HUG";
n12.appendChild(n28);
n28.layoutSizingHorizontal = "FILL";
n28.layoutSizingVertical = "HUG";
n13.appendChild(n29);
try { n29.characters = "Get Started"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.layoutSizingHorizontal = "FILL";
n16.appendChild(n30);
try { n30.characters = "Most Popular"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.layoutSizingHorizontal = "FILL";
n17.appendChild(n31);
n31.layoutSizingHorizontal = "FILL";
n31.layoutSizingVertical = "HUG";
n17.appendChild(n32);
n32.layoutSizingHorizontal = "FILL";
n32.layoutSizingVertical = "HUG";
n17.appendChild(n33);
n33.layoutSizingHorizontal = "FILL";
n33.layoutSizingVertical = "HUG";
n17.appendChild(n34);
n34.layoutSizingHorizontal = "FILL";
n34.layoutSizingVertical = "HUG";
n18.appendChild(n35);
try { n35.characters = "Subscribe Now"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n21.appendChild(n36);
n36.layoutSizingHorizontal = "FILL";
n36.layoutSizingVertical = "HUG";
n21.appendChild(n37);
n37.layoutSizingHorizontal = "FILL";
n37.layoutSizingVertical = "HUG";
n21.appendChild(n38);
n38.layoutSizingHorizontal = "FILL";
n38.layoutSizingVertical = "HUG";
n21.appendChild(n39);
n39.layoutSizingHorizontal = "FILL";
n39.layoutSizingVertical = "HUG";
n22.appendChild(n40);
try { n40.characters = "Contact Sales"; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.layoutSizingHorizontal = "FILL";
n26.appendChild(n41);
n26.appendChild(n42);
try { n42.characters = "Basic features"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.layoutSizingHorizontal = "FILL";
n27.appendChild(n43);
n27.appendChild(n44);
try { n44.characters = "Up to 10 projects"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n44.layoutSizingHorizontal = "FILL";
n28.appendChild(n45);
n28.appendChild(n46);
try { n46.characters = "Email support"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n46.layoutSizingHorizontal = "FILL";
n31.appendChild(n47);
n31.appendChild(n48);
try { n48.characters = "Advanced features"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n48.layoutSizingHorizontal = "FILL";
n32.appendChild(n49);
n32.appendChild(n50);
try { n50.characters = "Unlimited projects"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n50.layoutSizingHorizontal = "FILL";
n33.appendChild(n51);
n33.appendChild(n52);
try { n52.characters = "Priority support"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n52.layoutSizingHorizontal = "FILL";
n34.appendChild(n53);
n34.appendChild(n54);
try { n54.characters = "Team collaboration"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n54.layoutSizingHorizontal = "FILL";
n36.appendChild(n55);
n36.appendChild(n56);
try { n56.characters = "All features included"; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n56.layoutSizingHorizontal = "FILL";
n37.appendChild(n57);
n37.appendChild(n58);
try { n58.characters = "Dedicated account manager"; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n58.layoutSizingHorizontal = "FILL";
n38.appendChild(n59);
n38.appendChild(n60);
try { n60.characters = "Custom integrations"; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n60.layoutSizingHorizontal = "FILL";
n39.appendChild(n61);
n39.appendChild(n62);
try { n62.characters = "24/7 phone support"; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n62.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;