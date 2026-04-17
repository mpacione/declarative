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
const _p0 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82260"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return null; } })();
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82310"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82310", error: String(__e && __e.message || __e)}); return null; } })();


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
n2.name = "search_input-1";
n2.layoutMode = "VERTICAL";
n2.itemSpacing = 6;
n2.paddingTop = 10;
n2.paddingRight = 12;
n2.paddingBottom = 10;
n2.paddingLeft = 12;
n2.resize(n2.width, 48);
n2.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n2.strokes = [{type: "SOLID", color: {r:0.7961,g:0.8353,b:0.8824}}];
n2.cornerRadius = 8;
n2.clipsContent = false;
M["search_input-1"] = n2.id;

const n3 = figma.createFrame();
n3.name = "list-1";
n3.layoutMode = "VERTICAL";
n3.itemSpacing = 8;
n3.paddingTop = 8;
n3.paddingRight = 12;
n3.paddingBottom = 8;
n3.paddingLeft = 12;
n3.cornerRadius = 8;
n3.fills = [];
n3.clipsContent = false;
M["list-1"] = n3.id;

const n4 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n4.name = "icon_button-1";
M["icon_button-1"] = n4.id;

const n5 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"icon_button-2", kind:"missing_component_node", id:"5749:82310"}); return _missingComponentPlaceholder("icon_button-2", 24, 24, "icon_button-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-2", kind:"create_instance_failed", id:"5749:82310", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-2", 24, 24, "icon_button-2"); } })();
n5.name = "icon_button-2";
M["icon_button-2"] = n5.id;

const n6 = figma.createText();
n6.name = "text-1";
try { n6.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n6.fontSize = 14;
M["text-1"] = n6.id;

const n7 = figma.createFrame();
n7.name = "list_item-1";
n7.layoutMode = "VERTICAL";
n7.itemSpacing = 12;
n7.paddingTop = 12;
n7.paddingRight = 16;
n7.paddingBottom = 12;
n7.paddingLeft = 16;
n7.counterAxisAlignItems = "CENTER";
n7.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n7.clipsContent = false;
M["list_item-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "list_item-2";
n8.layoutMode = "VERTICAL";
n8.itemSpacing = 12;
n8.paddingTop = 12;
n8.paddingRight = 16;
n8.paddingBottom = 12;
n8.paddingLeft = 16;
n8.counterAxisAlignItems = "CENTER";
n8.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n8.clipsContent = false;
M["list_item-2"] = n8.id;

const n9 = figma.createFrame();
n9.name = "list_item-3";
n9.layoutMode = "VERTICAL";
n9.itemSpacing = 12;
n9.paddingTop = 12;
n9.paddingRight = 16;
n9.paddingBottom = 12;
n9.paddingLeft = 16;
n9.counterAxisAlignItems = "CENTER";
n9.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n9.clipsContent = false;
M["list_item-3"] = n9.id;

const n10 = figma.createFrame();
n10.name = "list_item-4";
n10.layoutMode = "VERTICAL";
n10.itemSpacing = 12;
n10.paddingTop = 12;
n10.paddingRight = 16;
n10.paddingBottom = 12;
n10.paddingLeft = 16;
n10.counterAxisAlignItems = "CENTER";
n10.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n10.clipsContent = false;
M["list_item-4"] = n10.id;

const n11 = figma.createFrame();
n11.name = "list_item-5";
n11.layoutMode = "VERTICAL";
n11.itemSpacing = 12;
n11.paddingTop = 12;
n11.paddingRight = 16;
n11.paddingBottom = 12;
n11.paddingLeft = 16;
n11.counterAxisAlignItems = "CENTER";
n11.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n11.clipsContent = false;
M["list_item-5"] = n11.id;

const n12 = figma.createFrame();
n12.name = "avatar-1";
n12.layoutMode = "VERTICAL";
n12.primaryAxisAlignItems = "CENTER";
n12.counterAxisAlignItems = "CENTER";
n12.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n12.cornerRadius = 999;
n12.clipsContent = false;
M["avatar-1"] = n12.id;

const n13 = figma.createFrame();
n13.name = "card-1";
n13.layoutMode = "VERTICAL";
n13.itemSpacing = 12;
n13.paddingTop = 16;
n13.paddingRight = 16;
n13.paddingBottom = 16;
n13.paddingLeft = 16;
n13.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n13.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n13.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n13.cornerRadius = 12;
n13.clipsContent = false;
M["card-1"] = n13.id;

const n14 = figma.createFrame();
n14.name = "badge-1";
n14.layoutMode = "VERTICAL";
n14.itemSpacing = 4;
n14.paddingTop = 4;
n14.paddingRight = 8;
n14.paddingBottom = 4;
n14.paddingLeft = 8;
n14.counterAxisAlignItems = "CENTER";
n14.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n14.cornerRadius = 999;
n14.clipsContent = false;
M["badge-1"] = n14.id;

const n15 = figma.createFrame();
n15.name = "avatar-2";
n15.layoutMode = "VERTICAL";
n15.primaryAxisAlignItems = "CENTER";
n15.counterAxisAlignItems = "CENTER";
n15.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n15.cornerRadius = 999;
n15.clipsContent = false;
M["avatar-2"] = n15.id;

const n16 = figma.createFrame();
n16.name = "card-2";
n16.layoutMode = "VERTICAL";
n16.itemSpacing = 12;
n16.paddingTop = 16;
n16.paddingRight = 16;
n16.paddingBottom = 16;
n16.paddingLeft = 16;
n16.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n16.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n16.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n16.cornerRadius = 12;
n16.clipsContent = false;
M["card-2"] = n16.id;

const n17 = figma.createFrame();
n17.name = "badge-2";
n17.layoutMode = "VERTICAL";
n17.itemSpacing = 4;
n17.paddingTop = 4;
n17.paddingRight = 8;
n17.paddingBottom = 4;
n17.paddingLeft = 8;
n17.counterAxisAlignItems = "CENTER";
n17.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n17.cornerRadius = 999;
n17.clipsContent = false;
M["badge-2"] = n17.id;

const n18 = figma.createFrame();
n18.name = "avatar-3";
n18.layoutMode = "VERTICAL";
n18.primaryAxisAlignItems = "CENTER";
n18.counterAxisAlignItems = "CENTER";
n18.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n18.cornerRadius = 999;
n18.clipsContent = false;
M["avatar-3"] = n18.id;

const n19 = figma.createFrame();
n19.name = "card-3";
n19.layoutMode = "VERTICAL";
n19.itemSpacing = 12;
n19.paddingTop = 16;
n19.paddingRight = 16;
n19.paddingBottom = 16;
n19.paddingLeft = 16;
n19.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n19.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n19.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n19.cornerRadius = 12;
n19.clipsContent = false;
M["card-3"] = n19.id;

const n20 = figma.createFrame();
n20.name = "badge-3";
n20.layoutMode = "VERTICAL";
n20.itemSpacing = 4;
n20.paddingTop = 4;
n20.paddingRight = 8;
n20.paddingBottom = 4;
n20.paddingLeft = 8;
n20.counterAxisAlignItems = "CENTER";
n20.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n20.cornerRadius = 999;
n20.clipsContent = false;
M["badge-3"] = n20.id;

const n21 = figma.createFrame();
n21.name = "avatar-4";
n21.layoutMode = "VERTICAL";
n21.primaryAxisAlignItems = "CENTER";
n21.counterAxisAlignItems = "CENTER";
n21.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n21.cornerRadius = 999;
n21.clipsContent = false;
M["avatar-4"] = n21.id;

const n22 = figma.createFrame();
n22.name = "card-4";
n22.layoutMode = "VERTICAL";
n22.itemSpacing = 12;
n22.paddingTop = 16;
n22.paddingRight = 16;
n22.paddingBottom = 16;
n22.paddingLeft = 16;
n22.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n22.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n22.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n22.cornerRadius = 12;
n22.clipsContent = false;
M["card-4"] = n22.id;

const n23 = figma.createFrame();
n23.name = "badge-4";
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
M["badge-4"] = n23.id;

const n24 = figma.createFrame();
n24.name = "avatar-5";
n24.layoutMode = "VERTICAL";
n24.primaryAxisAlignItems = "CENTER";
n24.counterAxisAlignItems = "CENTER";
n24.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n24.cornerRadius = 999;
n24.clipsContent = false;
M["avatar-5"] = n24.id;

const n25 = figma.createFrame();
n25.name = "card-5";
n25.layoutMode = "VERTICAL";
n25.itemSpacing = 12;
n25.paddingTop = 16;
n25.paddingRight = 16;
n25.paddingBottom = 16;
n25.paddingLeft = 16;
n25.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n25.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n25.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n25.cornerRadius = 12;
n25.clipsContent = false;
M["card-5"] = n25.id;

const n26 = figma.createFrame();
n26.name = "badge-5";
n26.layoutMode = "VERTICAL";
n26.itemSpacing = 4;
n26.paddingTop = 4;
n26.paddingRight = 8;
n26.paddingBottom = 4;
n26.paddingLeft = 8;
n26.counterAxisAlignItems = "CENTER";
n26.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n26.cornerRadius = 999;
n26.clipsContent = false;
M["badge-5"] = n26.id;

const n27 = figma.createText();
n27.name = "text-2";
try { n27.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n27.id;

const n28 = figma.createText();
n28.name = "text-3";
try { n28.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n28.id;

const n29 = figma.createText();
n29.name = "text-4";
n29.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n29.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.fontSize = 12;
M["text-4"] = n29.id;

const n30 = figma.createText();
n30.name = "text-5";
try { n30.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n30.id;

const n31 = figma.createText();
n31.name = "text-6";
try { n31.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n31.id;

const n32 = figma.createText();
n32.name = "text-7";
n32.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n32.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.fontSize = 12;
M["text-7"] = n32.id;

const n33 = figma.createText();
n33.name = "text-8";
try { n33.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n33.id;

const n34 = figma.createText();
n34.name = "text-9";
try { n34.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n34.id;

const n35 = figma.createText();
n35.name = "text-10";
n35.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n35.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.fontSize = 12;
M["text-10"] = n35.id;

const n36 = figma.createText();
n36.name = "text-11";
try { n36.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n36.id;

const n37 = figma.createText();
n37.name = "text-12";
try { n37.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-12"] = n37.id;

const n38 = figma.createText();
n38.name = "text-13";
n38.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n38.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.fontSize = 12;
M["text-13"] = n38.id;

const n39 = figma.createText();
n39.name = "text-14";
try { n39.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-14"] = n39.id;

const n40 = figma.createText();
n40.name = "text-15";
try { n40.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-15"] = n40.id;

const n41 = figma.createText();
n41.name = "text-16";
n41.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n41.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.fontSize = 12;
M["text-16"] = n41.id;


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
n1.appendChild(n4);
n1.appendChild(n5);
n2.appendChild(n6);
try { n6.characters = "Search contacts"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n6.layoutSizingHorizontal = "FILL";
n3.appendChild(n7);
n7.layoutSizingHorizontal = "FILL";
n7.layoutSizingVertical = "HUG";
n3.appendChild(n8);
n8.layoutSizingHorizontal = "FILL";
n8.layoutSizingVertical = "HUG";
n3.appendChild(n9);
n9.layoutSizingHorizontal = "FILL";
n9.layoutSizingVertical = "HUG";
n3.appendChild(n10);
n10.layoutSizingHorizontal = "FILL";
n10.layoutSizingVertical = "HUG";
n3.appendChild(n11);
n11.layoutSizingHorizontal = "FILL";
n11.layoutSizingVertical = "HUG";
n7.appendChild(n12);
n12.layoutSizingHorizontal = "FIXED";
n12.layoutSizingVertical = "FIXED";
n7.appendChild(n13);
n13.layoutSizingHorizontal = "FILL";
n13.layoutSizingVertical = "HUG";
n7.appendChild(n14);
n14.layoutSizingHorizontal = "HUG";
n14.layoutSizingVertical = "HUG";
n8.appendChild(n15);
n15.layoutSizingHorizontal = "FIXED";
n15.layoutSizingVertical = "FIXED";
n8.appendChild(n16);
n16.layoutSizingHorizontal = "FILL";
n16.layoutSizingVertical = "HUG";
n8.appendChild(n17);
n17.layoutSizingHorizontal = "HUG";
n17.layoutSizingVertical = "HUG";
n9.appendChild(n18);
n18.layoutSizingHorizontal = "FIXED";
n18.layoutSizingVertical = "FIXED";
n9.appendChild(n19);
n19.layoutSizingHorizontal = "FILL";
n19.layoutSizingVertical = "HUG";
n9.appendChild(n20);
n20.layoutSizingHorizontal = "HUG";
n20.layoutSizingVertical = "HUG";
n10.appendChild(n21);
n21.layoutSizingHorizontal = "FIXED";
n21.layoutSizingVertical = "FIXED";
n10.appendChild(n22);
n22.layoutSizingHorizontal = "FILL";
n22.layoutSizingVertical = "HUG";
n10.appendChild(n23);
n23.layoutSizingHorizontal = "HUG";
n23.layoutSizingVertical = "HUG";
n11.appendChild(n24);
n24.layoutSizingHorizontal = "FIXED";
n24.layoutSizingVertical = "FIXED";
n11.appendChild(n25);
n25.layoutSizingHorizontal = "FILL";
n25.layoutSizingVertical = "HUG";
n11.appendChild(n26);
n26.layoutSizingHorizontal = "HUG";
n26.layoutSizingVertical = "HUG";
n13.appendChild(n27);
try { n27.characters = "John Doe"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n27.layoutSizingHorizontal = "FILL";
n13.appendChild(n28);
try { n28.characters = "Last seen 2 hours ago"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n28.layoutSizingHorizontal = "FILL";
n14.appendChild(n29);
try { n29.characters = "Online"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.layoutSizingHorizontal = "FILL";
n16.appendChild(n30);
try { n30.characters = "Sarah Miller"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.layoutSizingHorizontal = "FILL";
n16.appendChild(n31);
try { n31.characters = "Last seen 30 minutes ago"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.layoutSizingHorizontal = "FILL";
n17.appendChild(n32);
try { n32.characters = "Online"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n19.appendChild(n33);
try { n33.characters = "Michael Chen"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.layoutSizingHorizontal = "FILL";
n19.appendChild(n34);
try { n34.characters = "Last seen 1 day ago"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.layoutSizingHorizontal = "FILL";
n20.appendChild(n35);
try { n35.characters = "Offline"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n22.appendChild(n36);
try { n36.characters = "Emma Johnson"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.layoutSizingHorizontal = "FILL";
n22.appendChild(n37);
try { n37.characters = "Last seen 5 minutes ago"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n37.layoutSizingHorizontal = "FILL";
n23.appendChild(n38);
try { n38.characters = "Online"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.layoutSizingHorizontal = "FILL";
n25.appendChild(n39);
try { n39.characters = "Robert Park"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n39.layoutSizingHorizontal = "FILL";
n25.appendChild(n40);
try { n40.characters = "Last seen 3 days ago"; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.layoutSizingHorizontal = "FILL";
n26.appendChild(n41);
try { n41.characters = "Offline"; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;