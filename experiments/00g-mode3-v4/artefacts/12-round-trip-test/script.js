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

const n7 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n7.name = "button-1";
{ const _t = n7.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n7.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "View Full Specs"; } }
M["button-1"] = n7.id;

const n8 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n8.name = "icon_button-1";
M["icon_button-1"] = n8.id;

const n9 = figma.createText();
n9.name = "heading-1";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n9.id;

const n10 = figma.createText();
n10.name = "text-1";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n10.id;

const n11 = figma.createText();
n11.name = "text-2";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n11.id;

const n12 = figma.createText();
n12.name = "text-3";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n12.id;

const n13 = figma.createText();
n13.name = "heading-2";
try { n13.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n13.id;

const n14 = figma.createText();
n14.name = "text-4";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n14.id;

const n15 = figma.createText();
n15.name = "text-5";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n15.id;

const n16 = figma.createText();
n16.name = "text-6";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n16.id;

const n17 = figma.createText();
n17.name = "heading-3";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n17.id;

const n18 = figma.createText();
n18.name = "text-7";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n18.id;

const n19 = figma.createText();
n19.name = "text-8";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n19.id;

const n20 = figma.createText();
n20.name = "text-9";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n20.id;

const n21 = figma.createText();
n21.name = "heading-4";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-4"] = n21.id;

const n22 = figma.createText();
n22.name = "text-10";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n22.id;

const n23 = figma.createText();
n23.name = "text-11";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n23.id;

const n24 = figma.createText();
n24.name = "text-12";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-12"] = n24.id;

const n25 = figma.createText();
n25.name = "heading-5";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-5"] = n25.id;

const n26 = figma.createFrame();
n26.name = "toggle-1";
n26.layoutMode = "VERTICAL";
n26.itemSpacing = 8;
n26.counterAxisAlignItems = "CENTER";
n26.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n26.cornerRadius = 999;
n26.clipsContent = false;
M["toggle-1"] = n26.id;

const n27 = figma.createFrame();
n27.name = "toggle-2";
n27.layoutMode = "VERTICAL";
n27.itemSpacing = 8;
n27.counterAxisAlignItems = "CENTER";
n27.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n27.cornerRadius = 999;
n27.clipsContent = false;
M["toggle-2"] = n27.id;

const n28 = figma.createFrame();
n28.name = "toggle-3";
n28.layoutMode = "VERTICAL";
n28.itemSpacing = 8;
n28.counterAxisAlignItems = "CENTER";
n28.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n28.cornerRadius = 999;
n28.clipsContent = false;
M["toggle-3"] = n28.id;

const n29 = figma.createText();
n29.name = "text-13";
try { n29.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.fontSize = 14;
M["text-13"] = n29.id;

const n30 = figma.createText();
n30.name = "text-14";
try { n30.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.fontSize = 14;
M["text-14"] = n30.id;

const n31 = figma.createText();
n31.name = "text-15";
try { n31.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.fontSize = 14;
M["text-15"] = n31.id;


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
n0.appendChild(n7);
n7.layoutSizingHorizontal = "FILL";
n1.appendChild(n8);
n2.appendChild(n9);
try { n9.characters = "Device Information"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n2.appendChild(n10);
try { n10.characters = "Model: iPhone 13 Pro Max"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n2.appendChild(n11);
try { n11.characters = "Storage: 256GB"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n2.appendChild(n12);
try { n12.characters = "Color: Sierra Blue"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n3.appendChild(n13);
try { n13.characters = "Display"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n3.appendChild(n14);
try { n14.characters = "6.7-inch Super Retina XDR"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n3.appendChild(n15);
try { n15.characters = "Resolution: 2796 x 1290"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n3.appendChild(n16);
try { n16.characters = "120Hz ProMotion"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n4.appendChild(n17);
try { n17.characters = "Camera"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n4.appendChild(n18);
try { n18.characters = "Rear: 12MP Triple Camera"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n4.appendChild(n19);
try { n19.characters = "Front: 12MP TrueDepth"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n4.appendChild(n20);
try { n20.characters = "Night Mode & ProRAW"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n5.appendChild(n21);
try { n21.characters = "Performance"; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n5.appendChild(n22);
try { n22.characters = "Chip: A15 Bionic"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n5.appendChild(n23);
try { n23.characters = "RAM: 6GB"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n5.appendChild(n24);
try { n24.characters = "Battery: 4373 mAh"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n6.appendChild(n25);
try { n25.characters = "Connectivity"; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n6.appendChild(n26);
n26.layoutSizingHorizontal = "HUG";
n26.layoutSizingVertical = "HUG";
n6.appendChild(n27);
n27.layoutSizingHorizontal = "HUG";
n27.layoutSizingVertical = "HUG";
n6.appendChild(n28);
n28.layoutSizingHorizontal = "HUG";
n28.layoutSizingVertical = "HUG";
n26.appendChild(n29);
try { n29.characters = "5G"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.layoutSizingHorizontal = "FILL";
n27.appendChild(n30);
try { n30.characters = "WiFi 6E"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.layoutSizingHorizontal = "FILL";
n28.appendChild(n31);
try { n31.characters = "Bluetooth 5.3"; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;