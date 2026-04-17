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

const n3 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n3.name = "icon_button-1";
M["icon_button-1"] = n3.id;

const n4 = figma.createFrame();
n4.name = "list-1";
n4.layoutMode = "VERTICAL";
n4.itemSpacing = 8;
n4.paddingTop = 8;
n4.paddingRight = 12;
n4.paddingBottom = 8;
n4.paddingLeft = 12;
n4.cornerRadius = 8;
n4.fills = [];
n4.clipsContent = false;
M["list-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "list_item-1";
n5.layoutMode = "VERTICAL";
n5.itemSpacing = 12;
n5.paddingTop = 12;
n5.paddingRight = 16;
n5.paddingBottom = 12;
n5.paddingLeft = 16;
n5.counterAxisAlignItems = "CENTER";
n5.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n5.clipsContent = false;
M["list_item-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "list_item-2";
n6.layoutMode = "VERTICAL";
n6.itemSpacing = 12;
n6.paddingTop = 12;
n6.paddingRight = 16;
n6.paddingBottom = 12;
n6.paddingLeft = 16;
n6.counterAxisAlignItems = "CENTER";
n6.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n6.clipsContent = false;
M["list_item-2"] = n6.id;

const n7 = figma.createFrame();
n7.name = "list_item-3";
n7.layoutMode = "VERTICAL";
n7.itemSpacing = 12;
n7.paddingTop = 12;
n7.paddingRight = 16;
n7.paddingBottom = 12;
n7.paddingLeft = 16;
n7.counterAxisAlignItems = "CENTER";
n7.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n7.clipsContent = false;
M["list_item-3"] = n7.id;

const n8 = figma.createFrame();
n8.name = "list_item-4";
n8.layoutMode = "VERTICAL";
n8.itemSpacing = 12;
n8.paddingTop = 12;
n8.paddingRight = 16;
n8.paddingBottom = 12;
n8.paddingLeft = 16;
n8.counterAxisAlignItems = "CENTER";
n8.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n8.clipsContent = false;
M["list_item-4"] = n8.id;

const n9 = figma.createFrame();
n9.name = "list_item-5";
n9.layoutMode = "VERTICAL";
n9.itemSpacing = 12;
n9.paddingTop = 12;
n9.paddingRight = 16;
n9.paddingBottom = 12;
n9.paddingLeft = 16;
n9.counterAxisAlignItems = "CENTER";
n9.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n9.clipsContent = false;
M["list_item-5"] = n9.id;

const n10 = figma.createFrame();
n10.name = "list_item-6";
n10.layoutMode = "VERTICAL";
n10.itemSpacing = 12;
n10.paddingTop = 12;
n10.paddingRight = 16;
n10.paddingBottom = 12;
n10.paddingLeft = 16;
n10.counterAxisAlignItems = "CENTER";
n10.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n10.clipsContent = false;
M["list_item-6"] = n10.id;

const n11 = figma.createFrame();
n11.name = "list_item-7";
n11.layoutMode = "VERTICAL";
n11.itemSpacing = 12;
n11.paddingTop = 12;
n11.paddingRight = 16;
n11.paddingBottom = 12;
n11.paddingLeft = 16;
n11.counterAxisAlignItems = "CENTER";
n11.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n11.clipsContent = false;
M["list_item-7"] = n11.id;

const n12 = figma.createFrame();
n12.name = "list_item-8";
n12.layoutMode = "VERTICAL";
n12.itemSpacing = 12;
n12.paddingTop = 12;
n12.paddingRight = 16;
n12.paddingBottom = 12;
n12.paddingLeft = 16;
n12.counterAxisAlignItems = "CENTER";
n12.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n12.clipsContent = false;
M["list_item-8"] = n12.id;

const n13 = figma.createFrame();
n13.name = "list_item-9";
n13.layoutMode = "VERTICAL";
n13.itemSpacing = 12;
n13.paddingTop = 12;
n13.paddingRight = 16;
n13.paddingBottom = 12;
n13.paddingLeft = 16;
n13.counterAxisAlignItems = "CENTER";
n13.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n13.clipsContent = false;
M["list_item-9"] = n13.id;

const n14 = figma.createFrame();
n14.name = "list_item-10";
n14.layoutMode = "VERTICAL";
n14.itemSpacing = 12;
n14.paddingTop = 12;
n14.paddingRight = 16;
n14.paddingBottom = 12;
n14.paddingLeft = 16;
n14.counterAxisAlignItems = "CENTER";
n14.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n14.clipsContent = false;
M["list_item-10"] = n14.id;

const n15 = figma.createText();
n15.name = "text-1";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n15.id;

const n16 = figma.createText();
n16.name = "text-2";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n16.id;

const n17 = figma.createFrame();
n17.name = "badge-1";
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
M["badge-1"] = n17.id;

const n18 = figma.createText();
n18.name = "text-4";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n18.id;

const n19 = figma.createFrame();
n19.name = "badge-2";
n19.layoutMode = "VERTICAL";
n19.itemSpacing = 4;
n19.paddingTop = 4;
n19.paddingRight = 8;
n19.paddingBottom = 4;
n19.paddingLeft = 8;
n19.counterAxisAlignItems = "CENTER";
n19.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n19.cornerRadius = 999;
n19.clipsContent = false;
M["badge-2"] = n19.id;

const n20 = figma.createText();
n20.name = "text-6";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n20.id;

const n21 = figma.createFrame();
n21.name = "badge-3";
n21.layoutMode = "VERTICAL";
n21.itemSpacing = 4;
n21.paddingTop = 4;
n21.paddingRight = 8;
n21.paddingBottom = 4;
n21.paddingLeft = 8;
n21.counterAxisAlignItems = "CENTER";
n21.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n21.cornerRadius = 999;
n21.clipsContent = false;
M["badge-3"] = n21.id;

const n22 = figma.createText();
n22.name = "text-8";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n22.id;

const n23 = figma.createText();
n23.name = "text-9";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n23.id;

const n24 = figma.createFrame();
n24.name = "badge-4";
n24.layoutMode = "VERTICAL";
n24.itemSpacing = 4;
n24.paddingTop = 4;
n24.paddingRight = 8;
n24.paddingBottom = 4;
n24.paddingLeft = 8;
n24.counterAxisAlignItems = "CENTER";
n24.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n24.cornerRadius = 999;
n24.clipsContent = false;
M["badge-4"] = n24.id;

const n25 = figma.createText();
n25.name = "text-11";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n25.id;

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
n27.name = "text-13";
try { n27.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-13"] = n27.id;

const n28 = figma.createFrame();
n28.name = "badge-6";
n28.layoutMode = "VERTICAL";
n28.itemSpacing = 4;
n28.paddingTop = 4;
n28.paddingRight = 8;
n28.paddingBottom = 4;
n28.paddingLeft = 8;
n28.counterAxisAlignItems = "CENTER";
n28.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n28.cornerRadius = 999;
n28.clipsContent = false;
M["badge-6"] = n28.id;

const n29 = figma.createText();
n29.name = "text-15";
try { n29.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-15"] = n29.id;

const n30 = figma.createFrame();
n30.name = "badge-7";
n30.layoutMode = "VERTICAL";
n30.itemSpacing = 4;
n30.paddingTop = 4;
n30.paddingRight = 8;
n30.paddingBottom = 4;
n30.paddingLeft = 8;
n30.counterAxisAlignItems = "CENTER";
n30.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n30.cornerRadius = 999;
n30.clipsContent = false;
M["badge-7"] = n30.id;

const n31 = figma.createText();
n31.name = "text-17";
try { n31.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-17"] = n31.id;

const n32 = figma.createText();
n32.name = "text-3";
n32.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n32.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.fontSize = 12;
M["text-3"] = n32.id;

const n33 = figma.createText();
n33.name = "text-5";
n33.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n33.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.fontSize = 12;
M["text-5"] = n33.id;

const n34 = figma.createText();
n34.name = "text-7";
n34.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n34.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.fontSize = 12;
M["text-7"] = n34.id;

const n35 = figma.createText();
n35.name = "text-10";
n35.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n35.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.fontSize = 12;
M["text-10"] = n35.id;

const n36 = figma.createText();
n36.name = "text-12";
n36.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n36.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.fontSize = 12;
M["text-12"] = n36.id;

const n37 = figma.createText();
n37.name = "text-14";
n37.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n37.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n37.fontSize = 12;
M["text-14"] = n37.id;

const n38 = figma.createText();
n38.name = "text-16";
n38.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n38.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.fontSize = 12;
M["text-16"] = n38.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n1.layoutSizingVertical = "FIXED";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n2.layoutSizingVertical = "HUG";
n1.appendChild(n3);
n2.appendChild(n4);
n4.layoutSizingHorizontal = "FILL";
n4.layoutSizingVertical = "HUG";
n4.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n5.layoutSizingVertical = "HUG";
n4.appendChild(n6);
n6.layoutSizingHorizontal = "FILL";
n6.layoutSizingVertical = "HUG";
n4.appendChild(n7);
n7.layoutSizingHorizontal = "FILL";
n7.layoutSizingVertical = "HUG";
n4.appendChild(n8);
n8.layoutSizingHorizontal = "FILL";
n8.layoutSizingVertical = "HUG";
n4.appendChild(n9);
n9.layoutSizingHorizontal = "FILL";
n9.layoutSizingVertical = "HUG";
n4.appendChild(n10);
n10.layoutSizingHorizontal = "FILL";
n10.layoutSizingVertical = "HUG";
n4.appendChild(n11);
n11.layoutSizingHorizontal = "FILL";
n11.layoutSizingVertical = "HUG";
n4.appendChild(n12);
n12.layoutSizingHorizontal = "FILL";
n12.layoutSizingVertical = "HUG";
n4.appendChild(n13);
n13.layoutSizingHorizontal = "FILL";
n13.layoutSizingVertical = "HUG";
n4.appendChild(n14);
n14.layoutSizingHorizontal = "FILL";
n14.layoutSizingVertical = "HUG";
n5.appendChild(n15);
try { n15.characters = "8:00 AM"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n6.appendChild(n16);
try { n16.characters = "9:00 AM"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n6.appendChild(n17);
n17.layoutSizingHorizontal = "HUG";
n17.layoutSizingVertical = "HUG";
n7.appendChild(n18);
try { n18.characters = "10:00 AM"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n7.appendChild(n19);
n19.layoutSizingHorizontal = "HUG";
n19.layoutSizingVertical = "HUG";
n8.appendChild(n20);
try { n20.characters = "11:00 AM"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n8.appendChild(n21);
n21.layoutSizingHorizontal = "HUG";
n21.layoutSizingVertical = "HUG";
n9.appendChild(n22);
try { n22.characters = "12:00 PM"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n10.appendChild(n23);
try { n23.characters = "1:00 PM"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n10.appendChild(n24);
n24.layoutSizingHorizontal = "HUG";
n24.layoutSizingVertical = "HUG";
n11.appendChild(n25);
try { n25.characters = "2:00 PM"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n11.appendChild(n26);
n26.layoutSizingHorizontal = "HUG";
n26.layoutSizingVertical = "HUG";
n12.appendChild(n27);
try { n27.characters = "3:00 PM"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n27.layoutSizingHorizontal = "FILL";
n12.appendChild(n28);
n28.layoutSizingHorizontal = "HUG";
n28.layoutSizingVertical = "HUG";
n13.appendChild(n29);
try { n29.characters = "4:00 PM"; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.layoutSizingHorizontal = "FILL";
n13.appendChild(n30);
n30.layoutSizingHorizontal = "HUG";
n30.layoutSizingVertical = "HUG";
n14.appendChild(n31);
try { n31.characters = "5:00 PM"; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.layoutSizingHorizontal = "FILL";
n17.appendChild(n32);
try { n32.characters = "Team Standup"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n19.appendChild(n33);
try { n33.characters = "Design Review"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.layoutSizingHorizontal = "FILL";
n21.appendChild(n34);
try { n34.characters = "Design Review"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.layoutSizingHorizontal = "FILL";
n24.appendChild(n35);
try { n35.characters = "Lunch Break"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n26.appendChild(n36);
try { n36.characters = "Lunch Break"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.layoutSizingHorizontal = "FILL";
n28.appendChild(n37);
try { n37.characters = "Client Call"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n37.layoutSizingHorizontal = "FILL";
n30.appendChild(n38);
try { n38.characters = "Client Call"; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;