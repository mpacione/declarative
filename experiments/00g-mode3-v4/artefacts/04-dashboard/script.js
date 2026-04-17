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
const _p0 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82323"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return null; } })();
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

const n4 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n4.name = "button-1";
{ const _t = n4.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n4.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "View All Transactions"; } }
M["button-1"] = n4.id;

const n5 = figma.createText();
n5.name = "text-1";
try { n5.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n5.id;

const n6 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82323"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n6.name = "icon_button-1";
M["icon_button-1"] = n6.id;

const n7 = figma.createText();
n7.name = "heading-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "image-1";
n8.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n8.cornerRadius = 8;
n8.clipsContent = false;
M["image-1"] = n8.id;

const n9 = figma.createText();
n9.name = "heading-2";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n9.id;

const n10 = figma.createFrame();
n10.name = "table-1";
n10.layoutMode = "VERTICAL";
n10.fills = [];
n10.clipsContent = false;
M["table-1"] = n10.id;

const n11 = figma.createText();
n11.name = "text-2";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n11.id;

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

const n15 = figma.createFrame();
n15.name = "list_item-1";
n15.layoutMode = "VERTICAL";
n15.itemSpacing = 12;
n15.paddingTop = 12;
n15.paddingRight = 16;
n15.paddingBottom = 12;
n15.paddingLeft = 16;
n15.counterAxisAlignItems = "CENTER";
n15.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n15.clipsContent = false;
M["list_item-1"] = n15.id;

const n16 = figma.createFrame();
n16.name = "list_item-2";
n16.layoutMode = "VERTICAL";
n16.itemSpacing = 12;
n16.paddingTop = 12;
n16.paddingRight = 16;
n16.paddingBottom = 12;
n16.paddingLeft = 16;
n16.counterAxisAlignItems = "CENTER";
n16.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n16.clipsContent = false;
M["list_item-2"] = n16.id;

const n17 = figma.createFrame();
n17.name = "list_item-3";
n17.layoutMode = "VERTICAL";
n17.itemSpacing = 12;
n17.paddingTop = 12;
n17.paddingRight = 16;
n17.paddingBottom = 12;
n17.paddingLeft = 16;
n17.counterAxisAlignItems = "CENTER";
n17.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n17.clipsContent = false;
M["list_item-3"] = n17.id;

const n18 = figma.createFrame();
n18.name = "list_item-4";
n18.layoutMode = "VERTICAL";
n18.itemSpacing = 12;
n18.paddingTop = 12;
n18.paddingRight = 16;
n18.paddingBottom = 12;
n18.paddingLeft = 16;
n18.counterAxisAlignItems = "CENTER";
n18.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n18.clipsContent = false;
M["list_item-4"] = n18.id;

const n19 = figma.createFrame();
n19.name = "list_item-5";
n19.layoutMode = "VERTICAL";
n19.itemSpacing = 12;
n19.paddingTop = 12;
n19.paddingRight = 16;
n19.paddingBottom = 12;
n19.paddingLeft = 16;
n19.counterAxisAlignItems = "CENTER";
n19.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n19.clipsContent = false;
M["list_item-5"] = n19.id;

const n20 = figma.createText();
n20.name = "text-6";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n20.id;

const n21 = figma.createText();
n21.name = "text-7";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n21.id;

const n22 = figma.createText();
n22.name = "text-8";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n22.id;

const n23 = figma.createFrame();
n23.name = "badge-1";
n23.layoutMode = "VERTICAL";
n23.itemSpacing = 4;
n23.paddingTop = 4;
n23.paddingRight = 8;
n23.paddingBottom = 4;
n23.paddingLeft = 8;
n23.counterAxisAlignItems = "CENTER";
n23.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n23.cornerRadius = 999;
n23.clipsContent = false;
M["badge-1"] = n23.id;

const n24 = figma.createText();
n24.name = "text-10";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n24.id;

const n25 = figma.createText();
n25.name = "text-11";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n25.id;

const n26 = figma.createText();
n26.name = "text-12";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-12"] = n26.id;

const n27 = figma.createFrame();
n27.name = "badge-2";
n27.layoutMode = "VERTICAL";
n27.itemSpacing = 4;
n27.paddingTop = 4;
n27.paddingRight = 8;
n27.paddingBottom = 4;
n27.paddingLeft = 8;
n27.counterAxisAlignItems = "CENTER";
n27.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n27.cornerRadius = 999;
n27.clipsContent = false;
M["badge-2"] = n27.id;

const n28 = figma.createText();
n28.name = "text-14";
try { n28.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-14"] = n28.id;

const n29 = figma.createText();
n29.name = "text-15";
try { n29.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-15"] = n29.id;

const n30 = figma.createText();
n30.name = "text-16";
try { n30.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-16"] = n30.id;

const n31 = figma.createFrame();
n31.name = "badge-3";
n31.layoutMode = "VERTICAL";
n31.itemSpacing = 4;
n31.paddingTop = 4;
n31.paddingRight = 8;
n31.paddingBottom = 4;
n31.paddingLeft = 8;
n31.counterAxisAlignItems = "CENTER";
n31.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n31.cornerRadius = 999;
n31.clipsContent = false;
M["badge-3"] = n31.id;

const n32 = figma.createText();
n32.name = "text-18";
try { n32.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-18"] = n32.id;

const n33 = figma.createText();
n33.name = "text-19";
try { n33.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-19"] = n33.id;

const n34 = figma.createText();
n34.name = "text-20";
try { n34.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-20"] = n34.id;

const n35 = figma.createFrame();
n35.name = "badge-4";
n35.layoutMode = "VERTICAL";
n35.itemSpacing = 4;
n35.paddingTop = 4;
n35.paddingRight = 8;
n35.paddingBottom = 4;
n35.paddingLeft = 8;
n35.counterAxisAlignItems = "CENTER";
n35.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n35.cornerRadius = 999;
n35.clipsContent = false;
M["badge-4"] = n35.id;

const n36 = figma.createText();
n36.name = "text-22";
try { n36.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-22", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-22"] = n36.id;

const n37 = figma.createText();
n37.name = "text-23";
try { n37.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-23", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-23"] = n37.id;

const n38 = figma.createText();
n38.name = "text-24";
try { n38.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-24", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-24"] = n38.id;

const n39 = figma.createFrame();
n39.name = "badge-5";
n39.layoutMode = "VERTICAL";
n39.itemSpacing = 4;
n39.paddingTop = 4;
n39.paddingRight = 8;
n39.paddingBottom = 4;
n39.paddingLeft = 8;
n39.counterAxisAlignItems = "CENTER";
n39.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n39.cornerRadius = 999;
n39.clipsContent = false;
M["badge-5"] = n39.id;

const n40 = figma.createText();
n40.name = "text-9";
n40.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n40.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.fontSize = 12;
M["text-9"] = n40.id;

const n41 = figma.createText();
n41.name = "text-13";
n41.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n41.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.fontSize = 12;
M["text-13"] = n41.id;

const n42 = figma.createText();
n42.name = "text-17";
n42.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n42.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.fontSize = 12;
M["text-17"] = n42.id;

const n43 = figma.createText();
n43.name = "text-21";
n43.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n43.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-21", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n43.fontSize = 12;
M["text-21"] = n43.id;

const n44 = figma.createText();
n44.name = "text-25";
n44.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n44.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-25", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n44.fontSize = 12;
M["text-25"] = n44.id;


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
n1.appendChild(n5);
try { n5.characters = "Dashboard"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n5.layoutSizingHorizontal = "FILL";
n1.appendChild(n6);
n2.appendChild(n7);
try { n7.characters = "Revenue Trend"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n2.appendChild(n8);
n8.layoutSizingHorizontal = "FILL";
n8.layoutSizingVertical = "FIXED";
n3.appendChild(n9);
try { n9.characters = "Recent Transactions"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n3.appendChild(n10);
n10.appendChild(n11);
try { n11.characters = "Date"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n10.appendChild(n12);
try { n12.characters = "Description"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n10.appendChild(n13);
try { n13.characters = "Amount"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n10.appendChild(n14);
try { n14.characters = "Status"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n10.appendChild(n15);
n15.layoutSizingHorizontal = "FILL";
n15.layoutSizingVertical = "HUG";
n10.appendChild(n16);
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
n15.appendChild(n20);
try { n20.characters = "2024-01-15"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n15.appendChild(n21);
try { n21.characters = "Payment received"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n15.appendChild(n22);
try { n22.characters = "$2,500.00"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n15.appendChild(n23);
n23.layoutSizingHorizontal = "HUG";
n23.layoutSizingVertical = "HUG";
n16.appendChild(n24);
try { n24.characters = "2024-01-14"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n16.appendChild(n25);
try { n25.characters = "Invoice #1024"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n16.appendChild(n26);
try { n26.characters = "$1,800.00"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
n16.appendChild(n27);
n27.layoutSizingHorizontal = "HUG";
n27.layoutSizingVertical = "HUG";
n17.appendChild(n28);
try { n28.characters = "2024-01-13"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n28.layoutSizingHorizontal = "FILL";
n17.appendChild(n29);
try { n29.characters = "Refund processed"; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.layoutSizingHorizontal = "FILL";
n17.appendChild(n30);
try { n30.characters = "-$450.00"; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.layoutSizingHorizontal = "FILL";
n17.appendChild(n31);
n31.layoutSizingHorizontal = "HUG";
n31.layoutSizingVertical = "HUG";
n18.appendChild(n32);
try { n32.characters = "2024-01-12"; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n18.appendChild(n33);
try { n33.characters = "Invoice #1023"; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.layoutSizingHorizontal = "FILL";
n18.appendChild(n34);
try { n34.characters = "$3,200.00"; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.layoutSizingHorizontal = "FILL";
n18.appendChild(n35);
n35.layoutSizingHorizontal = "HUG";
n35.layoutSizingVertical = "HUG";
n19.appendChild(n36);
try { n36.characters = "2024-01-11"; } catch (__e) { __errors.push({eid:"text-22", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.layoutSizingHorizontal = "FILL";
n19.appendChild(n37);
try { n37.characters = "Payment received"; } catch (__e) { __errors.push({eid:"text-23", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n37.layoutSizingHorizontal = "FILL";
n19.appendChild(n38);
try { n38.characters = "$1,200.00"; } catch (__e) { __errors.push({eid:"text-24", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.layoutSizingHorizontal = "FILL";
n19.appendChild(n39);
n39.layoutSizingHorizontal = "HUG";
n39.layoutSizingVertical = "HUG";
n23.appendChild(n40);
try { n40.characters = "Completed"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.layoutSizingHorizontal = "FILL";
n27.appendChild(n41);
try { n41.characters = "Completed"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.layoutSizingHorizontal = "FILL";
n31.appendChild(n42);
try { n42.characters = "Completed"; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.layoutSizingHorizontal = "FILL";
n35.appendChild(n43);
try { n43.characters = "Pending"; } catch (__e) { __errors.push({eid:"text-21", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n43.layoutSizingHorizontal = "FILL";
n39.appendChild(n44);
try { n44.characters = "Completed"; } catch (__e) { __errors.push({eid:"text-25", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n44.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;