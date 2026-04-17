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
const _p0 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82247"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82247", error: String(__e && __e.message || __e)}); return null; } })();
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82260"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return null; } })();
const _p2 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82323"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return null; } })();


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

const n6 = figma.createFrame();
n6.name = "card-5";
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
M["card-5"] = n6.id;

const n7 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n7.name = "icon_button-1";
M["icon_button-1"] = n7.id;

const n8 = figma.createText();
n8.name = "text-1";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n8.id;

const n9 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"icon_button-2", kind:"missing_component_node", id:"5749:82323"}); return _missingComponentPlaceholder("icon_button-2", 24, 24, "icon_button-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-2", kind:"create_instance_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-2", 24, 24, "icon_button-2"); } })();
n9.name = "icon_button-2";
M["icon_button-2"] = n9.id;

const n10 = figma.createFrame();
n10.name = "image-1";
n10.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n10.cornerRadius = 8;
n10.clipsContent = false;
M["image-1"] = n10.id;

const n11 = figma.createFrame();
n11.name = "slider-1";
n11.layoutMode = "VERTICAL";
n11.itemSpacing = 8;
n11.paddingTop = 8;
n11.paddingRight = 12;
n11.paddingBottom = 8;
n11.paddingLeft = 12;
n11.cornerRadius = 8;
n11.fills = [];
n11.clipsContent = false;
M["slider-1"] = n11.id;

const n12 = figma.createText();
n12.name = "text-3";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n12.id;

const n13 = figma.createFrame();
n13.name = "button_group-1";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["button_group-1"] = n13.id;

const n14 = figma.createText();
n14.name = "heading-1";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n14.id;

const n15 = figma.createText();
n15.name = "text-4";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n15.id;

const n16 = figma.createText();
n16.name = "text-5";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n16.id;

const n17 = figma.createText();
n17.name = "heading-2";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n17.id;

const n18 = figma.createFrame();
n18.name = "list-1";
n18.layoutMode = "VERTICAL";
n18.itemSpacing = 8;
n18.paddingTop = 8;
n18.paddingRight = 12;
n18.paddingBottom = 8;
n18.paddingLeft = 12;
n18.cornerRadius = 8;
n18.fills = [];
n18.clipsContent = false;
M["list-1"] = n18.id;

const n19 = figma.createText();
n19.name = "text-2";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.fontSize = 14;
M["text-2"] = n19.id;

const n20 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"icon_button-3", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-3", 24, 24, "icon_button-3"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-3", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-3", 24, 24, "icon_button-3"); } })();
n20.name = "icon_button-3";
M["icon_button-3"] = n20.id;

const n21 = figma.createFrame();
n21.name = "fab-1";
n21.layoutMode = "VERTICAL";
n21.fills = [];
n21.clipsContent = false;
M["fab-1"] = n21.id;

const n22 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-4", kind:"missing_component_node", id:"5749:82247"}); return _missingComponentPlaceholder("icon_button-4", 24, 24, "icon_button-4"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-4", kind:"create_instance_failed", id:"5749:82247", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-4", 24, 24, "icon_button-4"); } })();
n22.name = "icon_button-4";
M["icon_button-4"] = n22.id;

const n23 = figma.createFrame();
n23.name = "list_item-1";
n23.layoutMode = "VERTICAL";
n23.itemSpacing = 12;
n23.paddingTop = 12;
n23.paddingRight = 16;
n23.paddingBottom = 12;
n23.paddingLeft = 16;
n23.counterAxisAlignItems = "CENTER";
n23.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n23.clipsContent = false;
M["list_item-1"] = n23.id;

const n24 = figma.createFrame();
n24.name = "list_item-2";
n24.layoutMode = "VERTICAL";
n24.itemSpacing = 12;
n24.paddingTop = 12;
n24.paddingRight = 16;
n24.paddingBottom = 12;
n24.paddingLeft = 16;
n24.counterAxisAlignItems = "CENTER";
n24.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n24.clipsContent = false;
M["list_item-2"] = n24.id;

const n25 = figma.createFrame();
n25.name = "list_item-3";
n25.layoutMode = "VERTICAL";
n25.itemSpacing = 12;
n25.paddingTop = 12;
n25.paddingRight = 16;
n25.paddingBottom = 12;
n25.paddingLeft = 16;
n25.counterAxisAlignItems = "CENTER";
n25.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n25.clipsContent = false;
M["list_item-3"] = n25.id;

const n26 = figma.createFrame();
n26.name = "list_item-4";
n26.layoutMode = "VERTICAL";
n26.itemSpacing = 12;
n26.paddingTop = 12;
n26.paddingRight = 16;
n26.paddingBottom = 12;
n26.paddingLeft = 16;
n26.counterAxisAlignItems = "CENTER";
n26.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n26.clipsContent = false;
M["list_item-4"] = n26.id;

const n27 = figma.createFrame();
n27.name = "image-2";
n27.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n27.cornerRadius = 8;
n27.clipsContent = false;
M["image-2"] = n27.id;

const n28 = figma.createText();
n28.name = "text-6";
try { n28.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n28.id;

const n29 = figma.createFrame();
n29.name = "image-3";
n29.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n29.cornerRadius = 8;
n29.clipsContent = false;
M["image-3"] = n29.id;

const n30 = figma.createText();
n30.name = "text-7";
try { n30.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n30.id;

const n31 = figma.createFrame();
n31.name = "image-4";
n31.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n31.cornerRadius = 8;
n31.clipsContent = false;
M["image-4"] = n31.id;

const n32 = figma.createText();
n32.name = "text-8";
try { n32.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n32.id;

const n33 = figma.createFrame();
n33.name = "image-5";
n33.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n33.cornerRadius = 8;
n33.clipsContent = false;
M["image-5"] = n33.id;

const n34 = figma.createText();
n34.name = "text-9";
try { n34.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n34.id;


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
n6.layoutSizingVertical = "HUG";
n1.appendChild(n7);
n1.appendChild(n8);
try { n8.characters = "Video Player"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n1.appendChild(n9);
n2.appendChild(n10);
n10.layoutSizingHorizontal = "FILL";
n10.layoutSizingVertical = "FIXED";
n3.appendChild(n11);
n11.layoutSizingHorizontal = "FILL";
n11.layoutSizingVertical = "HUG";
n3.appendChild(n12);
try { n12.characters = "2:15 / 5:00"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n4.appendChild(n13);
n5.appendChild(n14);
try { n14.characters = "Video Title"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n5.appendChild(n15);
try { n15.characters = "Channel Name"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n5.appendChild(n16);
try { n16.characters = "1.2M views • 2 days ago"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n6.appendChild(n17);
try { n17.characters = "Related Videos"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n6.appendChild(n18);
n18.layoutSizingHorizontal = "FILL";
n18.layoutSizingVertical = "HUG";
n11.appendChild(n19);
try { n19.characters = "Progress"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n13.appendChild(n20);
n13.appendChild(n21);
n13.appendChild(n22);
n18.appendChild(n23);
n23.layoutSizingHorizontal = "FILL";
n23.layoutSizingVertical = "HUG";
n18.appendChild(n24);
n24.layoutSizingHorizontal = "FILL";
n24.layoutSizingVertical = "HUG";
n18.appendChild(n25);
n25.layoutSizingHorizontal = "FILL";
n25.layoutSizingVertical = "HUG";
n18.appendChild(n26);
n26.layoutSizingHorizontal = "FILL";
n26.layoutSizingVertical = "HUG";
n23.appendChild(n27);
n27.layoutSizingHorizontal = "FILL";
n27.layoutSizingVertical = "FIXED";
n23.appendChild(n28);
try { n28.characters = "Related Video Title 1"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n28.layoutSizingHorizontal = "FILL";
n24.appendChild(n29);
n29.layoutSizingHorizontal = "FILL";
n29.layoutSizingVertical = "FIXED";
n24.appendChild(n30);
try { n30.characters = "Related Video Title 2"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.layoutSizingHorizontal = "FILL";
n25.appendChild(n31);
n31.layoutSizingHorizontal = "FILL";
n31.layoutSizingVertical = "FIXED";
n25.appendChild(n32);
try { n32.characters = "Related Video Title 3"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n26.appendChild(n33);
n33.layoutSizingHorizontal = "FILL";
n33.layoutSizingVertical = "FIXED";
n26.appendChild(n34);
try { n34.characters = "Related Video Title 4"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;