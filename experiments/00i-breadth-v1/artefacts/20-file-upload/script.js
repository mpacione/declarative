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
const _p0 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82251"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return null; } })();
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82260"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return null; } })();
const _p2 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82457"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return null; } })();


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

const n4 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n4.name = "button-1";
{ const _t = n4.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n4.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Upload All"; } }
M["button-1"] = n4.id;

const n5 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n5.name = "icon_button-1";
M["icon_button-1"] = n5.id;

const n6 = figma.createText();
n6.name = "heading-1";
try { n6.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n6.id;

const n7 = figma.createFrame();
n7.name = "file_upload-1";
n7.layoutMode = "VERTICAL";
n7.fills = [];
n7.clipsContent = false;
M["file_upload-1"] = n7.id;

const n8 = figma.createText();
n8.name = "heading-2";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n8.id;

const n9 = figma.createFrame();
n9.name = "list-1";
n9.layoutMode = "VERTICAL";
n9.itemSpacing = 8;
n9.paddingTop = 8;
n9.paddingRight = 12;
n9.paddingBottom = 8;
n9.paddingLeft = 12;
n9.cornerRadius = 8;
n9.fills = [];
n9.clipsContent = false;
M["list-1"] = n9.id;

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

const n13 = figma.createText();
n13.name = "text-1";
try { n13.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n13.id;

const n14 = figma.createFrame();
n14.name = "slider-1";
n14.layoutMode = "VERTICAL";
n14.itemSpacing = 8;
n14.paddingTop = 8;
n14.paddingRight = 12;
n14.paddingBottom = 8;
n14.paddingLeft = 12;
n14.cornerRadius = 8;
n14.fills = [];
n14.clipsContent = false;
M["slider-1"] = n14.id;

const n15 = figma.createText();
n15.name = "text-2";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n15.id;

const n16 = figma.createText();
n16.name = "text-3";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n16.id;

const n17 = figma.createFrame();
n17.name = "slider-2";
n17.layoutMode = "VERTICAL";
n17.itemSpacing = 8;
n17.paddingTop = 8;
n17.paddingRight = 12;
n17.paddingBottom = 8;
n17.paddingLeft = 12;
n17.cornerRadius = 8;
n17.fills = [];
n17.clipsContent = false;
M["slider-2"] = n17.id;

const n18 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon-1", kind:"missing_component_node", id:"5749:82251"}); return _missingComponentPlaceholder("icon-1", 24, 24, "icon-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon-1", kind:"create_instance_failed", id:"5749:82251", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon-1", 24, 24, "icon-1"); } })();
n18.name = "icon-1";
M["icon-1"] = n18.id;

const n19 = figma.createText();
n19.name = "text-4";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n19.id;

const n20 = figma.createFrame();
n20.name = "slider-3";
n20.layoutMode = "VERTICAL";
n20.itemSpacing = 8;
n20.paddingTop = 8;
n20.paddingRight = 12;
n20.paddingBottom = 8;
n20.paddingLeft = 12;
n20.cornerRadius = 8;
n20.fills = [];
n20.clipsContent = false;
M["slider-3"] = n20.id;

const n21 = figma.createText();
n21.name = "text-5";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n21.id;


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
try { n6.characters = "Drag and drop files here"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n6.layoutSizingHorizontal = "FILL";
n2.appendChild(n7);
n3.appendChild(n8);
try { n8.characters = "Files to Upload"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n3.appendChild(n9);
n9.layoutSizingHorizontal = "FILL";
n9.layoutSizingVertical = "HUG";
n9.appendChild(n10);
n10.layoutSizingHorizontal = "FILL";
n10.layoutSizingVertical = "HUG";
n9.appendChild(n11);
n11.layoutSizingHorizontal = "FILL";
n11.layoutSizingVertical = "HUG";
n9.appendChild(n12);
n12.layoutSizingHorizontal = "FILL";
n12.layoutSizingVertical = "HUG";
n10.appendChild(n13);
try { n13.characters = "document.pdf"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n10.appendChild(n14);
n14.layoutSizingHorizontal = "FILL";
n14.layoutSizingVertical = "HUG";
n10.appendChild(n15);
try { n15.characters = "45%"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n11.appendChild(n16);
try { n16.characters = "image.jpg"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n11.appendChild(n17);
n17.layoutSizingHorizontal = "FILL";
n17.layoutSizingVertical = "HUG";
n11.appendChild(n18);
n12.appendChild(n19);
try { n19.characters = "presentation.pptx"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n12.appendChild(n20);
n20.layoutSizingHorizontal = "FILL";
n20.layoutSizingVertical = "HUG";
n12.appendChild(n21);
try { n21.characters = "Pending"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;