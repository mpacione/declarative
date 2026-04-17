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

const n4 = figma.createFrame();
n4.name = "card-3";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["card-3"] = n4.id;

const n5 = figma.createFrame();
n5.name = "card-4";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["card-4"] = n5.id;

const n6 = figma.createFrame();
n6.name = "card-5";
n6.layoutMode = "VERTICAL";
n6.fills = [];
n6.clipsContent = false;
M["card-5"] = n6.id;

const n7 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82323"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82323", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n7.name = "icon_button-1";
M["icon_button-1"] = n7.id;

const n8 = figma.createText();
n8.name = "heading-1";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n8.id;

const n9 = figma.createText();
n9.name = "text-1";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n9.id;

const n10 = figma.createText();
n10.name = "heading-2";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n10.id;

const n11 = figma.createText();
n11.name = "heading-3";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n11.id;

const n12 = figma.createFrame();
n12.name = "list-1";
n12.layoutMode = "VERTICAL";
n12.fills = [];
n12.clipsContent = false;
M["list-1"] = n12.id;

const n13 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-1", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-1", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-1", 24, 24, "button-1"); } })();
n13.name = "button-1";
{ const _t = n13.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n13.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Choose Plan"; } }
M["button-1"] = n13.id;

const n14 = figma.createText();
n14.name = "heading-4";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-4"] = n14.id;

const n15 = figma.createText();
n15.name = "heading-5";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-5"] = n15.id;

const n16 = figma.createFrame();
n16.name = "badge-1";
n16.layoutMode = "VERTICAL";
n16.counterAxisAlignItems = "CENTER";
n16.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n16.cornerRadius = 8;
n16.clipsContent = false;
M["badge-1"] = n16.id;

const n17 = figma.createFrame();
n17.name = "list-2";
n17.layoutMode = "VERTICAL";
n17.fills = [];
n17.clipsContent = false;
M["list-2"] = n17.id;

const n18 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-2", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-2", 24, 24, "button-2"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-2", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-2", 24, 24, "button-2"); } })();
n18.name = "button-2";
{ const _t = n18.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n18.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Choose Plan"; } }
M["button-2"] = n18.id;

const n19 = figma.createText();
n19.name = "heading-6";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-6"] = n19.id;

const n20 = figma.createText();
n20.name = "text-10";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n20.id;

const n21 = figma.createFrame();
n21.name = "list-3";
n21.layoutMode = "VERTICAL";
n21.fills = [];
n21.clipsContent = false;
M["list-3"] = n21.id;

const n22 = await (async () => { const __src = _p1; if (!__src) { __errors.push({eid:"button-3", kind:"missing_component_node", id:"5749:82457"}); return _missingComponentPlaceholder("button-3", 24, 24, "button-3"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"button-3", kind:"create_instance_failed", id:"5749:82457", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("button-3", 24, 24, "button-3"); } })();
n22.name = "button-3";
{ const _t = n22.findOne(n => n.type === "TEXT" && /^(title|label|heading)$/i.test(n.name)) || n22.findOne(n => n.type === "TEXT"); if (_t) { await figma.loadFontAsync(_t.fontName); _t.characters = "Contact Sales"; } }
M["button-3"] = n22.id;

const n23 = figma.createText();
n23.name = "heading-7";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-7"] = n23.id;

const n24 = figma.createText();
n24.name = "text-15";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-15"] = n24.id;

const n25 = figma.createText();
n25.name = "text-16";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-16"] = n25.id;

const n26 = figma.createFrame();
n26.name = "avatar-1";
n26.layoutMode = "VERTICAL";
n26.counterAxisAlignItems = "CENTER";
n26.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n26.cornerRadius = 8;
n26.clipsContent = false;
M["avatar-1"] = n26.id;

const n27 = figma.createFrame();
n27.name = "list_item-1";
n27.layoutMode = "VERTICAL";
n27.fills = [];
n27.clipsContent = false;
M["list_item-1"] = n27.id;

const n28 = figma.createFrame();
n28.name = "list_item-2";
n28.layoutMode = "VERTICAL";
n28.fills = [];
n28.clipsContent = false;
M["list_item-2"] = n28.id;

const n29 = figma.createFrame();
n29.name = "list_item-3";
n29.layoutMode = "VERTICAL";
n29.fills = [];
n29.clipsContent = false;
M["list_item-3"] = n29.id;

const n30 = figma.createText();
n30.name = "text-5";
try { n30.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.fontSize = 14;
M["text-5"] = n30.id;

const n31 = figma.createFrame();
n31.name = "list_item-4";
n31.layoutMode = "VERTICAL";
n31.fills = [];
n31.clipsContent = false;
M["list_item-4"] = n31.id;

const n32 = figma.createFrame();
n32.name = "list_item-5";
n32.layoutMode = "VERTICAL";
n32.fills = [];
n32.clipsContent = false;
M["list_item-5"] = n32.id;

const n33 = figma.createFrame();
n33.name = "list_item-6";
n33.layoutMode = "VERTICAL";
n33.fills = [];
n33.clipsContent = false;
M["list_item-6"] = n33.id;

const n34 = figma.createFrame();
n34.name = "list_item-7";
n34.layoutMode = "VERTICAL";
n34.fills = [];
n34.clipsContent = false;
M["list_item-7"] = n34.id;

const n35 = figma.createFrame();
n35.name = "list_item-8";
n35.layoutMode = "VERTICAL";
n35.fills = [];
n35.clipsContent = false;
M["list_item-8"] = n35.id;

const n36 = figma.createFrame();
n36.name = "list_item-9";
n36.layoutMode = "VERTICAL";
n36.fills = [];
n36.clipsContent = false;
M["list_item-9"] = n36.id;

const n37 = figma.createFrame();
n37.name = "list_item-10";
n37.layoutMode = "VERTICAL";
n37.fills = [];
n37.clipsContent = false;
M["list_item-10"] = n37.id;

const n38 = figma.createFrame();
n38.name = "list_item-11";
n38.layoutMode = "VERTICAL";
n38.fills = [];
n38.clipsContent = false;
M["list_item-11"] = n38.id;

const n39 = figma.createText();
n39.name = "text-2";
try { n39.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n39.id;

const n40 = figma.createText();
n40.name = "text-3";
try { n40.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n40.id;

const n41 = figma.createText();
n41.name = "text-4";
try { n41.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n41.id;

const n42 = figma.createText();
n42.name = "text-6";
try { n42.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n42.id;

const n43 = figma.createText();
n43.name = "text-7";
try { n43.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n43.id;

const n44 = figma.createText();
n44.name = "text-8";
try { n44.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n44.id;

const n45 = figma.createText();
n45.name = "text-9";
try { n45.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n45.id;

const n46 = figma.createText();
n46.name = "text-11";
try { n46.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n46.id;

const n47 = figma.createText();
n47.name = "text-12";
try { n47.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-12"] = n47.id;

const n48 = figma.createText();
n48.name = "text-13";
try { n48.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-13"] = n48.id;

const n49 = figma.createText();
n49.name = "text-14";
try { n49.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-14"] = n49.id;


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
n0.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n0.appendChild(n6);
n6.layoutSizingHorizontal = "FILL";
n1.appendChild(n7);
n2.appendChild(n8);
try { n8.characters = "Pricing Plans"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n2.appendChild(n9);
try { n9.characters = "Select the perfect plan for your needs"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n3.appendChild(n10);
try { n10.characters = "Starter"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n3.appendChild(n11);
try { n11.characters = "$9/month"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n3.appendChild(n12);
n3.appendChild(n13);
n4.appendChild(n14);
try { n14.characters = "Professional"; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n4.appendChild(n15);
try { n15.characters = "$29/month"; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n4.appendChild(n16);
n16.layoutSizingHorizontal = "HUG";
n16.layoutSizingVertical = "HUG";
n4.appendChild(n17);
n4.appendChild(n18);
n5.appendChild(n19);
try { n19.characters = "Enterprise"; } catch (__e) { __errors.push({eid:"heading-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n5.appendChild(n20);
try { n20.characters = "Custom pricing"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n5.appendChild(n21);
n5.appendChild(n22);
n6.appendChild(n23);
try { n23.characters = "What Our Users Say"; } catch (__e) { __errors.push({eid:"heading-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n6.appendChild(n24);
try { n24.characters = "\"This platform transformed how we manage our projects. Highly recommended!\""; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n6.appendChild(n25);
try { n25.characters = "— Sarah Johnson, CEO at TechStartup"; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n6.appendChild(n26);
n26.layoutSizingHorizontal = "HUG";
n26.layoutSizingVertical = "HUG";
n12.appendChild(n27);
n12.appendChild(n28);
n12.appendChild(n29);
n16.appendChild(n30);
try { n30.characters = "Most Popular"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.layoutSizingHorizontal = "FILL";
n17.appendChild(n31);
n17.appendChild(n32);
n17.appendChild(n33);
n17.appendChild(n34);
n21.appendChild(n35);
n21.appendChild(n36);
n21.appendChild(n37);
n21.appendChild(n38);
n27.appendChild(n39);
try { n39.characters = "Up to 10 projects"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n39.layoutSizingHorizontal = "FILL";
n28.appendChild(n40);
try { n40.characters = "Basic analytics"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.layoutSizingHorizontal = "FILL";
n29.appendChild(n41);
try { n41.characters = "Email support"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.layoutSizingHorizontal = "FILL";
n31.appendChild(n42);
try { n42.characters = "Unlimited projects"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.layoutSizingHorizontal = "FILL";
n32.appendChild(n43);
try { n43.characters = "Advanced analytics"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n43.layoutSizingHorizontal = "FILL";
n33.appendChild(n44);
try { n44.characters = "Priority support"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n44.layoutSizingHorizontal = "FILL";
n34.appendChild(n45);
try { n45.characters = "Custom integrations"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n45.layoutSizingHorizontal = "FILL";
n35.appendChild(n46);
try { n46.characters = "Everything in Professional"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n46.layoutSizingHorizontal = "FILL";
n36.appendChild(n47);
try { n47.characters = "Dedicated account manager"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n47.layoutSizingHorizontal = "FILL";
n37.appendChild(n48);
try { n48.characters = "Custom SLA"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n48.layoutSizingHorizontal = "FILL";
n38.appendChild(n49);
try { n49.characters = "Advanced security"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n49.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;