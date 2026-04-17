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
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82457"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return null; } })();


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

const n5 = figma.createFrame();
n5.name = "card-4";
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
M["card-4"] = n5.id;

const n6 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n6.name = "button-1";
{ const _t = n6.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n6.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Settings"; } }
M["button-1"] = n6.id;

const n7 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-2", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-2", 24, 24, "button-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-2", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-2", 24, 24, "button-2"); } })();
n7.name = "button-2";
{ const _t = n7.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n7.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "About"; } }
M["button-2"] = n7.id;

const n8 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n8.name = "icon_button-1";
M["icon_button-1"] = n8.id;

const n9 = figma.createText();
n9.name = "heading-1";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n9.id;

const n10 = figma.createFrame();
n10.name = "list-1";
n10.layoutMode = "VERTICAL";
n10.itemSpacing = 8;
n10.paddingTop = 8;
n10.paddingRight = 12;
n10.paddingBottom = 8;
n10.paddingLeft = 12;
n10.cornerRadius = 8;
n10.fills = [];
n10.clipsContent = false;
M["list-1"] = n10.id;

const n11 = figma.createText();
n11.name = "heading-2";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n11.id;

const n12 = figma.createFrame();
n12.name = "list-2";
n12.layoutMode = "VERTICAL";
n12.itemSpacing = 8;
n12.paddingTop = 8;
n12.paddingRight = 12;
n12.paddingBottom = 8;
n12.paddingLeft = 12;
n12.cornerRadius = 8;
n12.fills = [];
n12.clipsContent = false;
M["list-2"] = n12.id;

const n13 = figma.createText();
n13.name = "heading-3";
try { n13.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n13.id;

const n14 = figma.createFrame();
n14.name = "list-3";
n14.layoutMode = "VERTICAL";
n14.itemSpacing = 8;
n14.paddingTop = 8;
n14.paddingRight = 12;
n14.paddingBottom = 8;
n14.paddingLeft = 12;
n14.cornerRadius = 8;
n14.fills = [];
n14.clipsContent = false;
M["list-3"] = n14.id;

const n15 = figma.createText();
n15.name = "heading-4";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-4"] = n15.id;

const n16 = figma.createFrame();
n16.name = "list-4";
n16.layoutMode = "VERTICAL";
n16.itemSpacing = 8;
n16.paddingTop = 8;
n16.paddingRight = 12;
n16.paddingBottom = 8;
n16.paddingLeft = 12;
n16.cornerRadius = 8;
n16.fills = [];
n16.clipsContent = false;
M["list-4"] = n16.id;

const n17 = figma.createFrame();
n17.name = "list_item-1";
n17.layoutMode = "VERTICAL";
n17.itemSpacing = 12;
n17.paddingTop = 12;
n17.paddingRight = 16;
n17.paddingBottom = 12;
n17.paddingLeft = 16;
n17.counterAxisAlignItems = "CENTER";
n17.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n17.clipsContent = false;
M["list_item-1"] = n17.id;

const n18 = figma.createFrame();
n18.name = "list_item-2";
n18.layoutMode = "VERTICAL";
n18.itemSpacing = 12;
n18.paddingTop = 12;
n18.paddingRight = 16;
n18.paddingBottom = 12;
n18.paddingLeft = 16;
n18.counterAxisAlignItems = "CENTER";
n18.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n18.clipsContent = false;
M["list_item-2"] = n18.id;

const n19 = figma.createFrame();
n19.name = "list_item-3";
n19.layoutMode = "VERTICAL";
n19.itemSpacing = 12;
n19.paddingTop = 12;
n19.paddingRight = 16;
n19.paddingBottom = 12;
n19.paddingLeft = 16;
n19.counterAxisAlignItems = "CENTER";
n19.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n19.clipsContent = false;
M["list_item-3"] = n19.id;

const n20 = figma.createFrame();
n20.name = "list_item-4";
n20.layoutMode = "VERTICAL";
n20.itemSpacing = 12;
n20.paddingTop = 12;
n20.paddingRight = 16;
n20.paddingBottom = 12;
n20.paddingLeft = 16;
n20.counterAxisAlignItems = "CENTER";
n20.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n20.clipsContent = false;
M["list_item-4"] = n20.id;

const n21 = figma.createFrame();
n21.name = "list_item-5";
n21.layoutMode = "VERTICAL";
n21.itemSpacing = 12;
n21.paddingTop = 12;
n21.paddingRight = 16;
n21.paddingBottom = 12;
n21.paddingLeft = 16;
n21.counterAxisAlignItems = "CENTER";
n21.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n21.clipsContent = false;
M["list_item-5"] = n21.id;

const n22 = figma.createFrame();
n22.name = "list_item-6";
n22.layoutMode = "VERTICAL";
n22.itemSpacing = 12;
n22.paddingTop = 12;
n22.paddingRight = 16;
n22.paddingBottom = 12;
n22.paddingLeft = 16;
n22.counterAxisAlignItems = "CENTER";
n22.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n22.clipsContent = false;
M["list_item-6"] = n22.id;

const n23 = figma.createFrame();
n23.name = "list_item-7";
n23.layoutMode = "VERTICAL";
n23.itemSpacing = 12;
n23.paddingTop = 12;
n23.paddingRight = 16;
n23.paddingBottom = 12;
n23.paddingLeft = 16;
n23.counterAxisAlignItems = "CENTER";
n23.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n23.clipsContent = false;
M["list_item-7"] = n23.id;

const n24 = figma.createFrame();
n24.name = "list_item-8";
n24.layoutMode = "VERTICAL";
n24.itemSpacing = 12;
n24.paddingTop = 12;
n24.paddingRight = 16;
n24.paddingBottom = 12;
n24.paddingLeft = 16;
n24.counterAxisAlignItems = "CENTER";
n24.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n24.clipsContent = false;
M["list_item-8"] = n24.id;

const n25 = figma.createFrame();
n25.name = "list_item-9";
n25.layoutMode = "VERTICAL";
n25.itemSpacing = 12;
n25.paddingTop = 12;
n25.paddingRight = 16;
n25.paddingBottom = 12;
n25.paddingLeft = 16;
n25.counterAxisAlignItems = "CENTER";
n25.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n25.clipsContent = false;
M["list_item-9"] = n25.id;

const n26 = figma.createFrame();
n26.name = "list_item-10";
n26.layoutMode = "VERTICAL";
n26.itemSpacing = 12;
n26.paddingTop = 12;
n26.paddingRight = 16;
n26.paddingBottom = 12;
n26.paddingLeft = 16;
n26.counterAxisAlignItems = "CENTER";
n26.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n26.clipsContent = false;
M["list_item-10"] = n26.id;

const n27 = figma.createFrame();
n27.name = "list_item-11";
n27.layoutMode = "VERTICAL";
n27.itemSpacing = 12;
n27.paddingTop = 12;
n27.paddingRight = 16;
n27.paddingBottom = 12;
n27.paddingLeft = 16;
n27.counterAxisAlignItems = "CENTER";
n27.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n27.clipsContent = false;
M["list_item-11"] = n27.id;

const n28 = figma.createFrame();
n28.name = "list_item-12";
n28.layoutMode = "VERTICAL";
n28.itemSpacing = 12;
n28.paddingTop = 12;
n28.paddingRight = 16;
n28.paddingBottom = 12;
n28.paddingLeft = 16;
n28.counterAxisAlignItems = "CENTER";
n28.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n28.clipsContent = false;
M["list_item-12"] = n28.id;

const n29 = figma.createFrame();
n29.name = "list_item-13";
n29.layoutMode = "VERTICAL";
n29.itemSpacing = 12;
n29.paddingTop = 12;
n29.paddingRight = 16;
n29.paddingBottom = 12;
n29.paddingLeft = 16;
n29.counterAxisAlignItems = "CENTER";
n29.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n29.clipsContent = false;
M["list_item-13"] = n29.id;

const n30 = figma.createFrame();
n30.name = "list_item-14";
n30.layoutMode = "VERTICAL";
n30.itemSpacing = 12;
n30.paddingTop = 12;
n30.paddingRight = 16;
n30.paddingBottom = 12;
n30.paddingLeft = 16;
n30.counterAxisAlignItems = "CENTER";
n30.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n30.clipsContent = false;
M["list_item-14"] = n30.id;

const n31 = figma.createText();
n31.name = "text-1";
try { n31.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n31.id;

const n32 = figma.createText();
n32.name = "text-2";
try { n32.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n32.id;

const n33 = figma.createText();
n33.name = "text-3";
try { n33.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n33.id;

const n34 = figma.createText();
n34.name = "text-4";
try { n34.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n34.id;

const n35 = figma.createText();
n35.name = "text-5";
try { n35.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n35.id;

const n36 = figma.createText();
n36.name = "text-6";
try { n36.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n36.id;

const n37 = figma.createText();
n37.name = "text-7";
try { n37.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n37.id;

const n38 = figma.createText();
n38.name = "text-8";
try { n38.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n38.id;

const n39 = figma.createText();
n39.name = "text-9";
try { n39.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n39.id;

const n40 = figma.createText();
n40.name = "text-10";
try { n40.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n40.id;

const n41 = figma.createText();
n41.name = "text-11";
try { n41.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n41.id;

const n42 = figma.createText();
n42.name = "text-12";
try { n42.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-12"] = n42.id;

const n43 = figma.createText();
n43.name = "text-13";
try { n43.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-13"] = n43.id;

const n44 = figma.createText();
n44.name = "text-14";
try { n44.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-14"] = n44.id;


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
n0.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n5.layoutSizingVertical = "HUG";
n0.appendChild(n6);
n6.layoutSizingHorizontal = "FILL";
n0.appendChild(n7);
n7.layoutSizingHorizontal = "FILL";
n1.appendChild(n8);
n2.appendChild(n9);
try { n9.characters = "Device Information"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n2.appendChild(n10);
n10.layoutSizingHorizontal = "FILL";
n10.layoutSizingVertical = "HUG";
n3.appendChild(n11);
try { n11.characters = "Battery & Performance"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n3.appendChild(n12);
n12.layoutSizingHorizontal = "FILL";
n12.layoutSizingVertical = "HUG";
n4.appendChild(n13);
try { n13.characters = "Camera System"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n4.appendChild(n14);
n14.layoutSizingHorizontal = "FILL";
n14.layoutSizingVertical = "HUG";
n5.appendChild(n15);
try { n15.characters = "Display"; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n5.appendChild(n16);
n16.layoutSizingHorizontal = "FILL";
n16.layoutSizingVertical = "HUG";
n10.appendChild(n17);
n17.layoutSizingHorizontal = "FILL";
n17.layoutSizingVertical = "HUG";
n10.appendChild(n18);
n18.layoutSizingHorizontal = "FILL";
n18.layoutSizingVertical = "HUG";
n10.appendChild(n19);
n19.layoutSizingHorizontal = "FILL";
n19.layoutSizingVertical = "HUG";
n10.appendChild(n20);
n20.layoutSizingHorizontal = "FILL";
n20.layoutSizingVertical = "HUG";
n12.appendChild(n21);
n21.layoutSizingHorizontal = "FILL";
n21.layoutSizingVertical = "HUG";
n12.appendChild(n22);
n22.layoutSizingHorizontal = "FILL";
n22.layoutSizingVertical = "HUG";
n12.appendChild(n23);
n23.layoutSizingHorizontal = "FILL";
n23.layoutSizingVertical = "HUG";
n14.appendChild(n24);
n24.layoutSizingHorizontal = "FILL";
n24.layoutSizingVertical = "HUG";
n14.appendChild(n25);
n25.layoutSizingHorizontal = "FILL";
n25.layoutSizingVertical = "HUG";
n14.appendChild(n26);
n26.layoutSizingHorizontal = "FILL";
n26.layoutSizingVertical = "HUG";
n14.appendChild(n27);
n27.layoutSizingHorizontal = "FILL";
n27.layoutSizingVertical = "HUG";
n16.appendChild(n28);
n28.layoutSizingHorizontal = "FILL";
n28.layoutSizingVertical = "HUG";
n16.appendChild(n29);
n29.layoutSizingHorizontal = "FILL";
n29.layoutSizingVertical = "HUG";
n16.appendChild(n30);
n30.layoutSizingHorizontal = "FILL";
n30.layoutSizingVertical = "HUG";
n17.appendChild(n31);
try { n31.characters = "Model: iPhone 13 Pro Max"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.layoutSizingHorizontal = "FILL";
n18.appendChild(n32);
try { n32.characters = "Storage: 256GB"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n19.appendChild(n33);
try { n33.characters = "Color: Sierra Blue"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.layoutSizingHorizontal = "FILL";
n20.appendChild(n34);
try { n34.characters = "iOS Version: 16.0"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.layoutSizingHorizontal = "FILL";
n21.appendChild(n35);
try { n35.characters = "Battery Health: 98%"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n22.appendChild(n36);
try { n36.characters = "Processor: A15 Bionic"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.layoutSizingHorizontal = "FILL";
n23.appendChild(n37);
try { n37.characters = "RAM: 6GB"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n37.layoutSizingHorizontal = "FILL";
n24.appendChild(n38);
try { n38.characters = "Main: 12MP Wide"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.layoutSizingHorizontal = "FILL";
n25.appendChild(n39);
try { n39.characters = "Ultra Wide: 12MP"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n39.layoutSizingHorizontal = "FILL";
n26.appendChild(n40);
try { n40.characters = "Telephoto: 12MP (3x)"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.layoutSizingHorizontal = "FILL";
n27.appendChild(n41);
try { n41.characters = "Front: 12MP TrueDepth"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.layoutSizingHorizontal = "FILL";
n28.appendChild(n42);
try { n42.characters = "Size: 6.7 inches"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.layoutSizingHorizontal = "FILL";
n29.appendChild(n43);
try { n43.characters = "Resolution: 2796 x 1290"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n43.layoutSizingHorizontal = "FILL";
n30.appendChild(n44);
try { n44.characters = "ProMotion: 120Hz"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n44.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;