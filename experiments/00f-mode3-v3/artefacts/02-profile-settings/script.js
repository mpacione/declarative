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
n1.fills = [];
n1.clipsContent = false;
M["header-1"] = n1.id;

const n2 = figma.createFrame();
n2.name = "card-1";
n2.layoutMode = "VERTICAL";
n2.fills = [];
n2.clipsContent = false;
M["card-1"] = n2.id;

const n3 = figma.createFrame();
n3.name = "card-2";
n3.layoutMode = "VERTICAL";
n3.fills = [];
n3.clipsContent = false;
M["card-2"] = n3.id;

const n4 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n4.name = "button-1";
{ const _t = n4.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n4.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Save Changes"; } }
M["button-1"] = n4.id;

const n5 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n5.name = "icon_button-1";
M["icon_button-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "avatar-1";
n6.layoutMode = "VERTICAL";
n6.primaryAxisAlignItems = "CENTER";
n6.counterAxisAlignItems = "CENTER";
n6.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n6.cornerRadius = 999;
n6.clipsContent = false;
M["avatar-1"] = n6.id;

const n7 = figma.createText();
n7.name = "heading-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "text_input-1";
n8.layoutMode = "VERTICAL";
n8.itemSpacing = 6;
n8.resize(n8.width, 48);
n8.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n8.strokes = [{type: "SOLID", color: {r:0.7961,g:0.8353,b:0.8824}}];
n8.cornerRadius = 8;
n8.clipsContent = false;
M["text_input-1"] = n8.id;

const n9 = figma.createFrame();
n9.name = "text_input-2";
n9.layoutMode = "VERTICAL";
n9.itemSpacing = 6;
n9.resize(n9.width, 48);
n9.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n9.strokes = [{type: "SOLID", color: {r:0.7961,g:0.8353,b:0.8824}}];
n9.cornerRadius = 8;
n9.clipsContent = false;
M["text_input-2"] = n9.id;

const n10 = figma.createText();
n10.name = "heading-2";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n10.id;

const n11 = figma.createFrame();
n11.name = "toggle-1";
n11.layoutMode = "VERTICAL";
n11.itemSpacing = 8;
n11.counterAxisAlignItems = "CENTER";
n11.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n11.cornerRadius = 999;
n11.clipsContent = false;
M["toggle-1"] = n11.id;

const n12 = figma.createFrame();
n12.name = "toggle-2";
n12.layoutMode = "VERTICAL";
n12.itemSpacing = 8;
n12.counterAxisAlignItems = "CENTER";
n12.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n12.cornerRadius = 999;
n12.clipsContent = false;
M["toggle-2"] = n12.id;

const n13 = figma.createFrame();
n13.name = "toggle-3";
n13.layoutMode = "VERTICAL";
n13.itemSpacing = 8;
n13.counterAxisAlignItems = "CENTER";
n13.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n13.cornerRadius = 999;
n13.clipsContent = false;
M["toggle-3"] = n13.id;

const n14 = figma.createFrame();
n14.name = "toggle-4";
n14.layoutMode = "VERTICAL";
n14.itemSpacing = 8;
n14.counterAxisAlignItems = "CENTER";
n14.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n14.cornerRadius = 999;
n14.clipsContent = false;
M["toggle-4"] = n14.id;

const n15 = figma.createText();
n15.name = "text-1";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.fontSize = 14;
M["text-1"] = n15.id;

const n16 = figma.createText();
n16.name = "text-2";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.fontSize = 14;
M["text-2"] = n16.id;

const n17 = figma.createText();
n17.name = "text-3";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.fontSize = 14;
M["text-3"] = n17.id;

const n18 = figma.createText();
n18.name = "text-4";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.fontSize = 14;
M["text-4"] = n18.id;

const n19 = figma.createText();
n19.name = "text-5";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.fontSize = 14;
M["text-5"] = n19.id;

const n20 = figma.createText();
n20.name = "text-6";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.fontSize = 14;
M["text-6"] = n20.id;

const n21 = figma.createText();
n21.name = "text-7";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.fontSize = 14;
M["text-7"] = n21.id;

const n22 = figma.createText();
n22.name = "text-8";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.fontSize = 14;
M["text-8"] = n22.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n0.appendChild(n3);
n3.layoutSizingHorizontal = "FILL";
n0.appendChild(n4);
n4.layoutSizingHorizontal = "FILL";
n1.appendChild(n5);
n2.appendChild(n6);
n6.layoutSizingHorizontal = "FIXED";
n6.layoutSizingVertical = "FIXED";
n2.appendChild(n7);
try { n7.characters = "Profile"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n2.appendChild(n8);
n8.layoutSizingHorizontal = "FILL";
n8.layoutSizingVertical = "HUG";
n2.appendChild(n9);
n9.layoutSizingHorizontal = "FILL";
n9.layoutSizingVertical = "HUG";
n3.appendChild(n10);
try { n10.characters = "Notifications"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n3.appendChild(n11);
n11.layoutSizingHorizontal = "HUG";
n11.layoutSizingVertical = "HUG";
n3.appendChild(n12);
n12.layoutSizingHorizontal = "HUG";
n12.layoutSizingVertical = "HUG";
n3.appendChild(n13);
n13.layoutSizingHorizontal = "HUG";
n13.layoutSizingVertical = "HUG";
n3.appendChild(n14);
n14.layoutSizingHorizontal = "HUG";
n14.layoutSizingVertical = "HUG";
n8.appendChild(n15);
try { n15.characters = "Name"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n8.appendChild(n16);
try { n16.characters = "John Doe"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n9.appendChild(n17);
try { n17.characters = "Email"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n9.appendChild(n18);
try { n18.characters = "john@example.com"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n11.appendChild(n19);
try { n19.characters = "Push notifications"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n12.appendChild(n20);
try { n20.characters = "Email alerts"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n13.appendChild(n21);
try { n21.characters = "Marketing emails"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n14.appendChild(n22);
try { n22.characters = "Weekly digest"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;