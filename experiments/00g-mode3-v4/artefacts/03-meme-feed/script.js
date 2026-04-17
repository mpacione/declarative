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
const _p0 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82310"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82310", error: String(__e && __e.message || __e)}); return null; } })();
const _p1 = await (async () => { try { return await figma.getNodeByIdAsync("5749:82461"); } catch (__e) { __errors.push({kind:"prefetch_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return null; } })();


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
n2.name = "list-1";
n2.layoutMode = "VERTICAL";
n2.itemSpacing = 8;
n2.paddingTop = 8;
n2.paddingRight = 12;
n2.paddingBottom = 8;
n2.paddingLeft = 12;
n2.cornerRadius = 8;
n2.fills = [];
n2.clipsContent = false;
M["list-1"] = n2.id;

const n3 = figma.createText();
n3.name = "text-1";
try { n3.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n3.id;

const n4 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82310"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82310", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n4.name = "icon_button-1";
M["icon_button-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "card-1";
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
M["card-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "card-2";
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
M["card-2"] = n6.id;

const n7 = figma.createFrame();
n7.name = "card-3";
n7.layoutMode = "VERTICAL";
n7.itemSpacing = 12;
n7.paddingTop = 16;
n7.paddingRight = 16;
n7.paddingBottom = 16;
n7.paddingLeft = 16;
n7.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n7.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n7.effects = [{type: "DROP_SHADOW", visible: true, blendMode: "NORMAL", color: {r:0.0,g:0.0,b:0.0,a:0.102}, offset: {x:0,y:2}, radius: 4, spread: 0}];
n7.cornerRadius = 12;
n7.clipsContent = false;
M["card-3"] = n7.id;

const n8 = figma.createFrame();
n8.name = "avatar-1";
n8.layoutMode = "VERTICAL";
n8.primaryAxisAlignItems = "CENTER";
n8.counterAxisAlignItems = "CENTER";
n8.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n8.cornerRadius = 999;
n8.clipsContent = false;
M["avatar-1"] = n8.id;

const n9 = figma.createText();
n9.name = "text-2";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n9.id;

const n10 = figma.createFrame();
n10.name = "image-1";
n10.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n10.cornerRadius = 8;
n10.clipsContent = false;
M["image-1"] = n10.id;

const n11 = figma.createText();
n11.name = "text-3";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n11.id;

const n12 = figma.createFrame();
n12.name = "button_group-1";
n12.layoutMode = "VERTICAL";
n12.fills = [];
n12.clipsContent = false;
M["button_group-1"] = n12.id;

const n13 = figma.createFrame();
n13.name = "avatar-2";
n13.layoutMode = "VERTICAL";
n13.primaryAxisAlignItems = "CENTER";
n13.counterAxisAlignItems = "CENTER";
n13.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n13.cornerRadius = 999;
n13.clipsContent = false;
M["avatar-2"] = n13.id;

const n14 = figma.createText();
n14.name = "text-4";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n14.id;

const n15 = figma.createFrame();
n15.name = "image-2";
n15.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n15.cornerRadius = 8;
n15.clipsContent = false;
M["image-2"] = n15.id;

const n16 = figma.createText();
n16.name = "text-5";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n16.id;

const n17 = figma.createFrame();
n17.name = "button_group-2";
n17.layoutMode = "VERTICAL";
n17.fills = [];
n17.clipsContent = false;
M["button_group-2"] = n17.id;

const n18 = figma.createFrame();
n18.name = "avatar-3";
n18.layoutMode = "VERTICAL";
n18.primaryAxisAlignItems = "CENTER";
n18.counterAxisAlignItems = "CENTER";
n18.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n18.cornerRadius = 999;
n18.clipsContent = false;
M["avatar-3"] = n18.id;

const n19 = figma.createText();
n19.name = "text-6";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n19.id;

const n20 = figma.createFrame();
n20.name = "image-3";
n20.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n20.cornerRadius = 8;
n20.clipsContent = false;
M["image-3"] = n20.id;

const n21 = figma.createText();
n21.name = "text-7";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n21.id;

const n22 = figma.createFrame();
n22.name = "button_group-3";
n22.layoutMode = "VERTICAL";
n22.fills = [];
n22.clipsContent = false;
M["button_group-3"] = n22.id;

const n23 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n23.name = "button-1";
{ const _t = n23.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n23.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "👍 Upvote"; } }
M["button-1"] = n23.id;

const n24 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-2", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-2", 24, 24, "button-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-2", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-2", 24, 24, "button-2"); } })();
n24.name = "button-2";
{ const _t = n24.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n24.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Share"; } }
M["button-2"] = n24.id;

const n25 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-3", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-3", 24, 24, "button-3"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-3", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-3", 24, 24, "button-3"); } })();
n25.name = "button-3";
{ const _t = n25.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n25.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "👍 Upvote"; } }
M["button-3"] = n25.id;

const n26 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-4", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-4", 24, 24, "button-4"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-4", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-4", 24, 24, "button-4"); } })();
n26.name = "button-4";
{ const _t = n26.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n26.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Share"; } }
M["button-4"] = n26.id;

const n27 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-5", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-5", 24, 24, "button-5"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-5", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-5", 24, 24, "button-5"); } })();
n27.name = "button-5";
{ const _t = n27.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n27.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "👍 Upvote"; } }
M["button-5"] = n27.id;

const n28 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-6", kind:"missing_component_node", id:"5749:82461"}); return _missingComponentPlaceholder("button-6", 24, 24, "button-6"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-6", kind:"create_instance_failed", id:"5749:82461", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-6", 24, 24, "button-6"); } })();
n28.name = "button-6";
{ const _t = n28.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n28.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Share"; } }
M["button-6"] = n28.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n1.layoutSizingVertical = "FIXED";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n2.layoutSizingVertical = "HUG";
n1.appendChild(n3);
try { n3.characters = "Memes"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n3.layoutSizingHorizontal = "FILL";
n1.appendChild(n4);
n2.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n5.layoutSizingVertical = "HUG";
n2.appendChild(n6);
n6.layoutSizingHorizontal = "FILL";
n6.layoutSizingVertical = "HUG";
n2.appendChild(n7);
n7.layoutSizingHorizontal = "FILL";
n7.layoutSizingVertical = "HUG";
n5.appendChild(n8);
n8.layoutSizingHorizontal = "FIXED";
n8.layoutSizingVertical = "FIXED";
n5.appendChild(n9);
try { n9.characters = "john_doe"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n5.appendChild(n10);
n10.layoutSizingHorizontal = "FILL";
n10.layoutSizingVertical = "FIXED";
n5.appendChild(n11);
try { n11.characters = "When you finally understand the assignment"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n5.appendChild(n12);
n6.appendChild(n13);
n13.layoutSizingHorizontal = "FIXED";
n13.layoutSizingVertical = "FIXED";
n6.appendChild(n14);
try { n14.characters = "sarah_memes"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n6.appendChild(n15);
n15.layoutSizingHorizontal = "FILL";
n15.layoutSizingVertical = "FIXED";
n6.appendChild(n16);
try { n16.characters = "POV: You're reading this in your head"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n6.appendChild(n17);
n7.appendChild(n18);
n18.layoutSizingHorizontal = "FIXED";
n18.layoutSizingVertical = "FIXED";
n7.appendChild(n19);
try { n19.characters = "meme_central"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n7.appendChild(n20);
n20.layoutSizingHorizontal = "FILL";
n20.layoutSizingVertical = "FIXED";
n7.appendChild(n21);
try { n21.characters = "Me pretending to understand what's happening"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n7.appendChild(n22);
n12.appendChild(n23);
n12.appendChild(n24);
n17.appendChild(n25);
n17.appendChild(n26);
n22.appendChild(n27);
n22.appendChild(n28);
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;