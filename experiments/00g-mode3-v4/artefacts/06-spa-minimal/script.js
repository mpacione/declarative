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
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82323"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return null; } })();
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

const n6 = await (async () => { const __src = _p2; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n6.name = "button-1";
{ const _t = n6.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n6.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Book Appointment"; } }
M["button-1"] = n6.id;

const n7 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n7.name = "icon_button-1";
M["icon_button-1"] = n7.id;

const n8 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"icon_button-2", kind:"missing_component_node", id:"5749:82323"}); return _missingComponentPlaceholder("icon_button-2", 24, 24, "icon_button-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-2", kind:"create_instance_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-2", 24, 24, "icon_button-2"); } })();
n8.name = "icon_button-2";
M["icon_button-2"] = n8.id;

const n9 = figma.createFrame();
n9.name = "image-1";
n9.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n9.cornerRadius = 8;
n9.clipsContent = false;
M["image-1"] = n9.id;

const n10 = figma.createText();
n10.name = "heading-1";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n10.id;

const n11 = figma.createText();
n11.name = "text-1";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n11.id;

const n12 = figma.createText();
n12.name = "heading-2";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n12.id;

const n13 = figma.createFrame();
n13.name = "segmented_control-1";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["segmented_control-1"] = n13.id;

const n14 = figma.createText();
n14.name = "heading-3";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n14.id;

const n15 = figma.createFrame();
n15.name = "list-1";
n15.layoutMode = "VERTICAL";
n15.itemSpacing = 8;
n15.paddingTop = 8;
n15.paddingRight = 12;
n15.paddingBottom = 8;
n15.paddingLeft = 12;
n15.cornerRadius = 8;
n15.fills = [];
n15.clipsContent = false;
M["list-1"] = n15.id;

const n16 = figma.createText();
n16.name = "text-7";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n16.id;

const n17 = figma.createText();
n17.name = "text-8";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n17.id;

const n18 = figma.createText();
n18.name = "text-2";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n18.id;

const n19 = figma.createText();
n19.name = "text-3";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n19.id;

const n20 = figma.createText();
n20.name = "text-4";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n20.id;

const n21 = figma.createFrame();
n21.name = "list_item-1";
n21.layoutMode = "VERTICAL";
n21.itemSpacing = 12;
n21.paddingTop = 12;
n21.paddingRight = 16;
n21.paddingBottom = 12;
n21.paddingLeft = 16;
n21.counterAxisAlignItems = "CENTER";
n21.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n21.clipsContent = false;
M["list_item-1"] = n21.id;

const n22 = figma.createFrame();
n22.name = "list_item-2";
n22.layoutMode = "VERTICAL";
n22.itemSpacing = 12;
n22.paddingTop = 12;
n22.paddingRight = 16;
n22.paddingBottom = 12;
n22.paddingLeft = 16;
n22.counterAxisAlignItems = "CENTER";
n22.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n22.clipsContent = false;
M["list_item-2"] = n22.id;

const n23 = figma.createFrame();
n23.name = "avatar-1";
n23.layoutMode = "VERTICAL";
n23.primaryAxisAlignItems = "CENTER";
n23.counterAxisAlignItems = "CENTER";
n23.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n23.cornerRadius = 999;
n23.clipsContent = false;
M["avatar-1"] = n23.id;

const n24 = figma.createText();
n24.name = "text-5";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n24.id;

const n25 = figma.createFrame();
n25.name = "avatar-2";
n25.layoutMode = "VERTICAL";
n25.primaryAxisAlignItems = "CENTER";
n25.counterAxisAlignItems = "CENTER";
n25.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n25.cornerRadius = 999;
n25.clipsContent = false;
M["avatar-2"] = n25.id;

const n26 = figma.createText();
n26.name = "text-6";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n26.id;


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
n1.appendChild(n7);
n1.appendChild(n8);
n2.appendChild(n9);
n9.layoutSizingHorizontal = "FILL";
n9.layoutSizingVertical = "FIXED";
n2.appendChild(n10);
try { n10.characters = "Signature Massage"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n2.appendChild(n11);
try { n11.characters = "90 minutes of pure relaxation"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n3.appendChild(n12);
try { n12.characters = "Select Time"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n3.appendChild(n13);
n4.appendChild(n14);
try { n14.characters = "Therapist"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n4.appendChild(n15);
n15.layoutSizingHorizontal = "FILL";
n15.layoutSizingVertical = "HUG";
n5.appendChild(n16);
try { n16.characters = "$180"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n5.appendChild(n17);
try { n17.characters = "Includes complimentary tea & aromatherapy"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n13.appendChild(n18);
try { n18.characters = "10:00 AM"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n13.appendChild(n19);
try { n19.characters = "2:00 PM"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n13.appendChild(n20);
try { n20.characters = "6:00 PM"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n15.appendChild(n21);
n21.layoutSizingHorizontal = "FILL";
n21.layoutSizingVertical = "HUG";
n15.appendChild(n22);
n22.layoutSizingHorizontal = "FILL";
n22.layoutSizingVertical = "HUG";
n21.appendChild(n23);
n23.layoutSizingHorizontal = "FIXED";
n23.layoutSizingVertical = "FIXED";
n21.appendChild(n24);
try { n24.characters = "Elena - Swedish Specialist"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n22.appendChild(n25);
n25.layoutSizingHorizontal = "FIXED";
n25.layoutSizingVertical = "FIXED";
n22.appendChild(n26);
try { n26.characters = "Sophia - Deep Tissue Expert"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;