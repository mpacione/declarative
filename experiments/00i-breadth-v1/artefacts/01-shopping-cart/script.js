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
n3.name = "card-5";
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
M["card-5"] = n3.id;

const n4 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n4.name = "button-1";
{ const _t = n4.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n4.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Proceed to Checkout"; } }
M["button-1"] = n4.id;

const n5 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n5.name = "icon_button-1";
M["icon_button-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "list-1";
n6.layoutMode = "VERTICAL";
n6.itemSpacing = 8;
n6.paddingTop = 8;
n6.paddingRight = 12;
n6.paddingBottom = 8;
n6.paddingLeft = 12;
n6.cornerRadius = 8;
n6.fills = [];
n6.clipsContent = false;
M["list-1"] = n6.id;

const n7 = figma.createText();
n7.name = "text-7";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n7.id;

const n8 = figma.createText();
n8.name = "text-8";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n8.id;

const n9 = figma.createText();
n9.name = "heading-1";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n9.id;

const n10 = figma.createFrame();
n10.name = "list_item-1";
n10.layoutMode = "VERTICAL";
n10.itemSpacing = 12;
n10.paddingTop = 12;
n10.paddingRight = 16;
n10.paddingBottom = 12;
n10.paddingLeft = 16;
n10.counterAxisAlignItems = "CENTER";
n10.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n10.clipsContent = false;
M["list_item-1"] = n10.id;

const n11 = figma.createFrame();
n11.name = "list_item-2";
n11.layoutMode = "VERTICAL";
n11.itemSpacing = 12;
n11.paddingTop = 12;
n11.paddingRight = 16;
n11.paddingBottom = 12;
n11.paddingLeft = 16;
n11.counterAxisAlignItems = "CENTER";
n11.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n11.clipsContent = false;
M["list_item-2"] = n11.id;

const n12 = figma.createFrame();
n12.name = "list_item-3";
n12.layoutMode = "VERTICAL";
n12.itemSpacing = 12;
n12.paddingTop = 12;
n12.paddingRight = 16;
n12.paddingBottom = 12;
n12.paddingLeft = 16;
n12.counterAxisAlignItems = "CENTER";
n12.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n12.clipsContent = false;
M["list_item-3"] = n12.id;

const n13 = figma.createFrame();
n13.name = "image-1";
n13.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n13.cornerRadius = 8;
n13.clipsContent = false;
M["image-1"] = n13.id;

const n14 = figma.createFrame();
n14.name = "card-2";
n14.layoutMode = "VERTICAL";
n14.itemSpacing = 12;
n14.paddingTop = 16;
n14.paddingRight = 16;
n14.paddingBottom = 16;
n14.paddingLeft = 16;
n14.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n14.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n14.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n14.cornerRadius = 12;
n14.clipsContent = false;
M["card-2"] = n14.id;

const n15 = figma.createFrame();
n15.name = "image-2";
n15.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n15.cornerRadius = 8;
n15.clipsContent = false;
M["image-2"] = n15.id;

const n16 = figma.createFrame();
n16.name = "card-3";
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
M["card-3"] = n16.id;

const n17 = figma.createFrame();
n17.name = "image-3";
n17.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n17.cornerRadius = 8;
n17.clipsContent = false;
M["image-3"] = n17.id;

const n18 = figma.createFrame();
n18.name = "card-4";
n18.layoutMode = "VERTICAL";
n18.itemSpacing = 12;
n18.paddingTop = 16;
n18.paddingRight = 16;
n18.paddingBottom = 16;
n18.paddingLeft = 16;
n18.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n18.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n18.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n18.cornerRadius = 12;
n18.clipsContent = false;
M["card-4"] = n18.id;

const n19 = figma.createText();
n19.name = "text-1";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n19.id;

const n20 = figma.createText();
n20.name = "text-2";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n20.id;

const n21 = figma.createFrame();
n21.name = "stepper-1";
n21.layoutMode = "VERTICAL";
n21.fills = [];
n21.clipsContent = false;
M["stepper-1"] = n21.id;

const n22 = figma.createText();
n22.name = "text-3";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n22.id;

const n23 = figma.createText();
n23.name = "text-4";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n23.id;

const n24 = figma.createFrame();
n24.name = "stepper-2";
n24.layoutMode = "VERTICAL";
n24.fills = [];
n24.clipsContent = false;
M["stepper-2"] = n24.id;

const n25 = figma.createText();
n25.name = "text-5";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n25.id;

const n26 = figma.createText();
n26.name = "text-6";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n26.id;

const n27 = figma.createFrame();
n27.name = "stepper-3";
n27.layoutMode = "VERTICAL";
n27.fills = [];
n27.clipsContent = false;
M["stepper-3"] = n27.id;


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
n2.appendChild(n6);
n6.layoutSizingHorizontal = "FILL";
n6.layoutSizingVertical = "HUG";
n3.appendChild(n7);
try { n7.characters = "Subtotal: $117.97"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n3.appendChild(n8);
try { n8.characters = "Shipping: $10.00"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n3.appendChild(n9);
try { n9.characters = "Total: $127.97"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n6.appendChild(n10);
n10.layoutSizingHorizontal = "FILL";
n10.layoutSizingVertical = "HUG";
n6.appendChild(n11);
n11.layoutSizingHorizontal = "FILL";
n11.layoutSizingVertical = "HUG";
n6.appendChild(n12);
n12.layoutSizingHorizontal = "FILL";
n12.layoutSizingVertical = "HUG";
n10.appendChild(n13);
n13.layoutSizingHorizontal = "FILL";
n13.layoutSizingVertical = "FIXED";
n10.appendChild(n14);
n14.layoutSizingHorizontal = "FILL";
n14.layoutSizingVertical = "HUG";
n11.appendChild(n15);
n15.layoutSizingHorizontal = "FILL";
n15.layoutSizingVertical = "FIXED";
n11.appendChild(n16);
n16.layoutSizingHorizontal = "FILL";
n16.layoutSizingVertical = "HUG";
n12.appendChild(n17);
n17.layoutSizingHorizontal = "FILL";
n17.layoutSizingVertical = "FIXED";
n12.appendChild(n18);
n18.layoutSizingHorizontal = "FILL";
n18.layoutSizingVertical = "HUG";
n14.appendChild(n19);
try { n19.characters = "Wireless Headphones"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n14.appendChild(n20);
try { n20.characters = "$79.99"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n14.appendChild(n21);
n16.appendChild(n22);
try { n22.characters = "USB-C Cable"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n16.appendChild(n23);
try { n23.characters = "$12.99"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n16.appendChild(n24);
n18.appendChild(n25);
try { n25.characters = "Phone Case"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n18.appendChild(n26);
try { n26.characters = "$24.99"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
n18.appendChild(n27);
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;