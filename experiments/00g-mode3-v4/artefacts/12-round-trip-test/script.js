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
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82453"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82453", error: String(__e && __e.message || __e)}); return null; } })();
const _p2 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82461"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return null; } })();


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
n2.itemSpacing = 12;
n2.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n2.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n2.cornerRadius = 12;
n2.clipsContent = false;
M["card-1"] = n2.id;

const n3 = figma.createFrame();
n3.name = "card-2";
n3.layoutMode = "VERTICAL";
n3.itemSpacing = 12;
n3.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n3.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n3.cornerRadius = 12;
n3.clipsContent = false;
M["card-2"] = n3.id;

const n4 = figma.createFrame();
n4.name = "card-3";
n4.layoutMode = "VERTICAL";
n4.itemSpacing = 12;
n4.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n4.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n4.cornerRadius = 12;
n4.clipsContent = false;
M["card-3"] = n4.id;

const n5 = figma.createFrame();
n5.name = "card-4";
n5.layoutMode = "VERTICAL";
n5.itemSpacing = 12;
n5.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n5.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n5.cornerRadius = 12;
n5.clipsContent = false;
M["card-4"] = n5.id;

const n6 = figma.createFrame();
n6.name = "card-5";
n6.layoutMode = "VERTICAL";
n6.itemSpacing = 12;
n6.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n6.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n6.cornerRadius = 12;
n6.clipsContent = false;
M["card-5"] = n6.id;

const n7 = figma.createFrame();
n7.name = "button_group-1";
n7.layoutMode = "VERTICAL";
n7.fills = [];
n7.clipsContent = false;
M["button_group-1"] = n7.id;

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
n10.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n10.cornerRadius = 8;
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
n12.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n12.cornerRadius = 8;
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
n14.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n14.cornerRadius = 8;
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
n16.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n16.cornerRadius = 8;
n16.clipsContent = false;
M["list-4"] = n16.id;

const n17 = figma.createText();
n17.name = "heading-5";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-5"] = n17.id;

const n18 = figma.createFrame();
n18.name = "toggle-1";
n18.layoutMode = "VERTICAL";
n18.itemSpacing = 8;
n18.counterAxisAlignItems = "CENTER";
n18.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n18.cornerRadius = 999;
n18.clipsContent = false;
M["toggle-1"] = n18.id;

const n19 = figma.createFrame();
n19.name = "toggle-2";
n19.layoutMode = "VERTICAL";
n19.itemSpacing = 8;
n19.counterAxisAlignItems = "CENTER";
n19.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n19.cornerRadius = 999;
n19.clipsContent = false;
M["toggle-2"] = n19.id;

const n20 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n20.name = "button-1";
{ const _t = n20.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n20.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Settings"; } }
M["button-1"] = n20.id;

const n21 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-2", kind:"missing_component_node", id:"5749:82453"}); return _missingComponentPlaceholder("button-2", 24, 24, "button-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-2", kind:"create_instance_failed", id:"5749:82453", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-2", 24, 24, "button-2"); } })();
n21.name = "button-2";
{ const _t = n21.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n21.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "About"; } }
M["button-2"] = n21.id;

const n22 = figma.createFrame();
n22.name = "list_item-1";
n22.layoutMode = "VERTICAL";
n22.itemSpacing = 12;
n22.counterAxisAlignItems = "CENTER";
n22.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n22.clipsContent = false;
M["list_item-1"] = n22.id;

const n23 = figma.createFrame();
n23.name = "list_item-2";
n23.layoutMode = "VERTICAL";
n23.itemSpacing = 12;
n23.counterAxisAlignItems = "CENTER";
n23.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n23.clipsContent = false;
M["list_item-2"] = n23.id;

const n24 = figma.createFrame();
n24.name = "list_item-3";
n24.layoutMode = "VERTICAL";
n24.itemSpacing = 12;
n24.counterAxisAlignItems = "CENTER";
n24.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n24.clipsContent = false;
M["list_item-3"] = n24.id;

const n25 = figma.createFrame();
n25.name = "list_item-4";
n25.layoutMode = "VERTICAL";
n25.itemSpacing = 12;
n25.counterAxisAlignItems = "CENTER";
n25.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n25.clipsContent = false;
M["list_item-4"] = n25.id;

const n26 = figma.createFrame();
n26.name = "list_item-5";
n26.layoutMode = "VERTICAL";
n26.itemSpacing = 12;
n26.counterAxisAlignItems = "CENTER";
n26.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n26.clipsContent = false;
M["list_item-5"] = n26.id;

const n27 = figma.createFrame();
n27.name = "list_item-6";
n27.layoutMode = "VERTICAL";
n27.itemSpacing = 12;
n27.counterAxisAlignItems = "CENTER";
n27.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n27.clipsContent = false;
M["list_item-6"] = n27.id;

const n28 = figma.createFrame();
n28.name = "list_item-7";
n28.layoutMode = "VERTICAL";
n28.itemSpacing = 12;
n28.counterAxisAlignItems = "CENTER";
n28.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n28.clipsContent = false;
M["list_item-7"] = n28.id;

const n29 = figma.createFrame();
n29.name = "list_item-8";
n29.layoutMode = "VERTICAL";
n29.itemSpacing = 12;
n29.counterAxisAlignItems = "CENTER";
n29.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n29.clipsContent = false;
M["list_item-8"] = n29.id;

const n30 = figma.createFrame();
n30.name = "list_item-9";
n30.layoutMode = "VERTICAL";
n30.itemSpacing = 12;
n30.counterAxisAlignItems = "CENTER";
n30.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n30.clipsContent = false;
M["list_item-9"] = n30.id;

const n31 = figma.createFrame();
n31.name = "list_item-10";
n31.layoutMode = "VERTICAL";
n31.itemSpacing = 12;
n31.counterAxisAlignItems = "CENTER";
n31.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n31.clipsContent = false;
M["list_item-10"] = n31.id;

const n32 = figma.createFrame();
n32.name = "list_item-11";
n32.layoutMode = "VERTICAL";
n32.itemSpacing = 12;
n32.counterAxisAlignItems = "CENTER";
n32.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n32.clipsContent = false;
M["list_item-11"] = n32.id;

const n33 = figma.createText();
n33.name = "text-12";
try { n33.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.fontSize = 14;
M["text-12"] = n33.id;

const n34 = figma.createText();
n34.name = "text-13";
try { n34.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.fontSize = 14;
M["text-13"] = n34.id;

const n35 = figma.createText();
n35.name = "text-1";
try { n35.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n35.id;

const n36 = figma.createText();
n36.name = "text-2";
try { n36.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n36.id;

const n37 = figma.createText();
n37.name = "text-3";
try { n37.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n37.id;

const n38 = figma.createText();
n38.name = "text-4";
try { n38.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n38.id;

const n39 = figma.createText();
n39.name = "text-5";
try { n39.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n39.id;

const n40 = figma.createText();
n40.name = "text-6";
try { n40.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n40.id;

const n41 = figma.createText();
n41.name = "text-7";
try { n41.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n41.id;

const n42 = figma.createText();
n42.name = "text-8";
try { n42.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n42.id;

const n43 = figma.createText();
n43.name = "text-9";
try { n43.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n43.id;

const n44 = figma.createText();
n44.name = "text-10";
try { n44.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n44.id;

const n45 = figma.createText();
n45.name = "text-11";
try { n45.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n45.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
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
n6.layoutSizingVertical = "HUG";
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
try { n11.characters = "Battery & Power"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n3.appendChild(n12);
n12.layoutSizingHorizontal = "FILL";
n12.layoutSizingVertical = "HUG";
n4.appendChild(n13);
try { n13.characters = "Display"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n4.appendChild(n14);
n14.layoutSizingHorizontal = "FILL";
n14.layoutSizingVertical = "HUG";
n5.appendChild(n15);
try { n15.characters = "Camera"; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n5.appendChild(n16);
n16.layoutSizingHorizontal = "FILL";
n16.layoutSizingVertical = "HUG";
n6.appendChild(n17);
try { n17.characters = "Security"; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n6.appendChild(n18);
n18.layoutSizingHorizontal = "HUG";
n18.layoutSizingVertical = "HUG";
n6.appendChild(n19);
n19.layoutSizingHorizontal = "HUG";
n19.layoutSizingVertical = "HUG";
n7.appendChild(n20);
n7.appendChild(n21);
n10.appendChild(n22);
n22.layoutSizingHorizontal = "FILL";
n22.layoutSizingVertical = "HUG";
n10.appendChild(n23);
n23.layoutSizingHorizontal = "FILL";
n23.layoutSizingVertical = "HUG";
n10.appendChild(n24);
n24.layoutSizingHorizontal = "FILL";
n24.layoutSizingVertical = "HUG";
n12.appendChild(n25);
n25.layoutSizingHorizontal = "FILL";
n25.layoutSizingVertical = "HUG";
n12.appendChild(n26);
n26.layoutSizingHorizontal = "FILL";
n26.layoutSizingVertical = "HUG";
n14.appendChild(n27);
n27.layoutSizingHorizontal = "FILL";
n27.layoutSizingVertical = "HUG";
n14.appendChild(n28);
n28.layoutSizingHorizontal = "FILL";
n28.layoutSizingVertical = "HUG";
n14.appendChild(n29);
n29.layoutSizingHorizontal = "FILL";
n29.layoutSizingVertical = "HUG";
n16.appendChild(n30);
n30.layoutSizingHorizontal = "FILL";
n30.layoutSizingVertical = "HUG";
n16.appendChild(n31);
n31.layoutSizingHorizontal = "FILL";
n31.layoutSizingVertical = "HUG";
n16.appendChild(n32);
n32.layoutSizingHorizontal = "FILL";
n32.layoutSizingVertical = "HUG";
n18.appendChild(n33);
try { n33.characters = "Face ID"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.layoutSizingHorizontal = "FILL";
n19.appendChild(n34);
try { n34.characters = "Encrypted Backup"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.layoutSizingHorizontal = "FILL";
n22.appendChild(n35);
try { n35.characters = "Model: iPhone 13 Pro Max"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n23.appendChild(n36);
try { n36.characters = "Storage: 256GB"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.layoutSizingHorizontal = "FILL";
n24.appendChild(n37);
try { n37.characters = "Color: Sierra Blue"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n37.layoutSizingHorizontal = "FILL";
n25.appendChild(n38);
try { n38.characters = "Battery Health: 98%"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.layoutSizingHorizontal = "FILL";
n26.appendChild(n39);
try { n39.characters = "Charging: Fast Charge Enabled"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n39.layoutSizingHorizontal = "FILL";
n27.appendChild(n40);
try { n40.characters = "Screen Size: 6.7 inches"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.layoutSizingHorizontal = "FILL";
n28.appendChild(n41);
try { n41.characters = "Resolution: 2778 x 1284"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.layoutSizingHorizontal = "FILL";
n29.appendChild(n42);
try { n42.characters = "ProMotion: 120Hz"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.layoutSizingHorizontal = "FILL";
n30.appendChild(n43);
try { n43.characters = "Rear: Triple 12MP Camera System"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n43.layoutSizingHorizontal = "FILL";
n31.appendChild(n44);
try { n44.characters = "Front: 12MP TrueDepth"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n44.layoutSizingHorizontal = "FILL";
n32.appendChild(n45);
try { n45.characters = "Video: 4K ProRes Recording"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n45.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;