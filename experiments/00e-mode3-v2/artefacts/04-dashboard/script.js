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

const n4 = await (async () => { const __src = _p0; if (!__src) { __errors.push({eid:"icon_button-1", kind:"missing_component_node", id:"5749:82260"}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } try { return __src.createInstance(); } catch (__e) { __errors.push({eid:"icon_button-1", kind:"create_instance_failed", id:"5749:82260", error: String(__e && __e.message || __e)}); return _missingComponentPlaceholder("icon_button-1", 24, 24, "icon_button-1"); } })();
n4.name = "icon_button-1";
M["icon_button-1"] = n4.id;

const n5 = figma.createText();
n5.name = "heading-1";
try { n5.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "image-1";
n6.fills = [];
n6.clipsContent = false;
M["image-1"] = n6.id;

const n7 = figma.createText();
n7.name = "heading-2";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n7.id;

const n8 = figma.createFrame();
n8.name = "table-1";
n8.layoutMode = "VERTICAL";
n8.fills = [];
n8.clipsContent = false;
M["table-1"] = n8.id;

const n9 = figma.createText();
n9.name = "text-1";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n9.id;

const n10 = figma.createText();
n10.name = "text-2";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n10.id;

const n11 = figma.createText();
n11.name = "text-3";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n11.id;

const n12 = figma.createText();
n12.name = "text-4";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n12.id;

const n13 = figma.createFrame();
n13.name = "list_item-1";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["list_item-1"] = n13.id;

const n14 = figma.createFrame();
n14.name = "list_item-2";
n14.layoutMode = "VERTICAL";
n14.fills = [];
n14.clipsContent = false;
M["list_item-2"] = n14.id;

const n15 = figma.createFrame();
n15.name = "list_item-3";
n15.layoutMode = "VERTICAL";
n15.fills = [];
n15.clipsContent = false;
M["list_item-3"] = n15.id;

const n16 = figma.createFrame();
n16.name = "list_item-4";
n16.layoutMode = "VERTICAL";
n16.fills = [];
n16.clipsContent = false;
M["list_item-4"] = n16.id;

const n17 = figma.createText();
n17.name = "text-5";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n17.id;

const n18 = figma.createText();
n18.name = "text-6";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n18.id;

const n19 = figma.createText();
n19.name = "text-7";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n19.id;

const n20 = figma.createFrame();
n20.name = "badge-1";
n20.layoutMode = "VERTICAL";
n20.counterAxisAlignItems = "CENTER";
n20.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n20.cornerRadius = 8;
n20.clipsContent = false;
M["badge-1"] = n20.id;

const n21 = figma.createText();
n21.name = "text-9";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n21.id;

const n22 = figma.createText();
n22.name = "text-10";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n22.id;

const n23 = figma.createText();
n23.name = "text-11";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n23.id;

const n24 = figma.createFrame();
n24.name = "badge-2";
n24.layoutMode = "VERTICAL";
n24.counterAxisAlignItems = "CENTER";
n24.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n24.cornerRadius = 8;
n24.clipsContent = false;
M["badge-2"] = n24.id;

const n25 = figma.createText();
n25.name = "text-13";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-13"] = n25.id;

const n26 = figma.createText();
n26.name = "text-14";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-14"] = n26.id;

const n27 = figma.createText();
n27.name = "text-15";
try { n27.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-15"] = n27.id;

const n28 = figma.createFrame();
n28.name = "badge-3";
n28.layoutMode = "VERTICAL";
n28.counterAxisAlignItems = "CENTER";
n28.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n28.cornerRadius = 8;
n28.clipsContent = false;
M["badge-3"] = n28.id;

const n29 = figma.createText();
n29.name = "text-17";
try { n29.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-17"] = n29.id;

const n30 = figma.createText();
n30.name = "text-18";
try { n30.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-18"] = n30.id;

const n31 = figma.createText();
n31.name = "text-19";
try { n31.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-19"] = n31.id;

const n32 = figma.createFrame();
n32.name = "badge-4";
n32.layoutMode = "VERTICAL";
n32.counterAxisAlignItems = "CENTER";
n32.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n32.cornerRadius = 8;
n32.clipsContent = false;
M["badge-4"] = n32.id;

const n33 = figma.createText();
n33.name = "text-8";
try { n33.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.fontSize = 14;
M["text-8"] = n33.id;

const n34 = figma.createText();
n34.name = "text-12";
try { n34.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.fontSize = 14;
M["text-12"] = n34.id;

const n35 = figma.createText();
n35.name = "text-16";
try { n35.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.fontSize = 14;
M["text-16"] = n35.id;

const n36 = figma.createText();
n36.name = "text-20";
try { n36.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.fontSize = 14;
M["text-20"] = n36.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n0.appendChild(n3);
n3.layoutSizingHorizontal = "FILL";
n1.appendChild(n4);
n2.appendChild(n5);
try { n5.characters = "Performance Overview"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n5.layoutSizingHorizontal = "FILL";
n2.appendChild(n6);
n3.appendChild(n7);
try { n7.characters = "Recent Transactions"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n3.appendChild(n8);
n8.appendChild(n9);
try { n9.characters = "Date"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n8.appendChild(n10);
try { n10.characters = "Description"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n8.appendChild(n11);
try { n11.characters = "Amount"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n8.appendChild(n12);
try { n12.characters = "Status"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n8.appendChild(n13);
n8.appendChild(n14);
n8.appendChild(n15);
n8.appendChild(n16);
n13.appendChild(n17);
try { n17.characters = "2024-01-15"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n13.appendChild(n18);
try { n18.characters = "Payment received"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n13.appendChild(n19);
try { n19.characters = "$1,250.00"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n13.appendChild(n20);
n20.layoutSizingHorizontal = "HUG";
n20.layoutSizingVertical = "HUG";
n14.appendChild(n21);
try { n21.characters = "2024-01-14"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n14.appendChild(n22);
try { n22.characters = "Invoice #2847"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n14.appendChild(n23);
try { n23.characters = "$3,500.00"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n14.appendChild(n24);
n24.layoutSizingHorizontal = "HUG";
n24.layoutSizingVertical = "HUG";
n15.appendChild(n25);
try { n25.characters = "2024-01-13"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n15.appendChild(n26);
try { n26.characters = "Refund processed"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
n15.appendChild(n27);
try { n27.characters = "-$450.00"; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n27.layoutSizingHorizontal = "FILL";
n15.appendChild(n28);
n28.layoutSizingHorizontal = "HUG";
n28.layoutSizingVertical = "HUG";
n16.appendChild(n29);
try { n29.characters = "2024-01-12"; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.layoutSizingHorizontal = "FILL";
n16.appendChild(n30);
try { n30.characters = "Monthly subscription"; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.layoutSizingHorizontal = "FILL";
n16.appendChild(n31);
try { n31.characters = "$99.99"; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.layoutSizingHorizontal = "FILL";
n16.appendChild(n32);
n32.layoutSizingHorizontal = "HUG";
n32.layoutSizingVertical = "HUG";
n20.appendChild(n33);
try { n33.characters = "Completed"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.layoutSizingHorizontal = "FILL";
n24.appendChild(n34);
try { n34.characters = "Completed"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.layoutSizingHorizontal = "FILL";
n28.appendChild(n35);
try { n35.characters = "Completed"; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n32.appendChild(n36);
try { n36.characters = "Pending"; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;