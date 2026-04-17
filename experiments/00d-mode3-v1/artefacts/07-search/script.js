const __errors = [];
await (async () => { try { await figma.loadFontAsync({family: "Inter", style: "Regular"}); } catch (__e) { __errors.push({kind:"font_load_failed", family:"Inter", style:"Regular", error: String(__e && __e.message || __e)}); } })();
const M = {};
const _rootPage = figma.currentPage;



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
n4.name = "icon_button-1";
n4.layoutMode = "VERTICAL";
n4.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n4.cornerRadius = 8;
n4.clipsContent = false;
M["icon_button-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "search_input-1";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["search_input-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "icon_button-2";
n6.layoutMode = "VERTICAL";
n6.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n6.cornerRadius = 8;
n6.clipsContent = false;
M["icon_button-2"] = n6.id;

const n7 = figma.createText();
n7.name = "heading-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "list-1";
n8.layoutMode = "VERTICAL";
n8.fills = [];
n8.clipsContent = false;
M["list-1"] = n8.id;

const n9 = figma.createText();
n9.name = "heading-2";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n9.id;

const n10 = figma.createFrame();
n10.name = "list-2";
n10.layoutMode = "VERTICAL";
n10.fills = [];
n10.clipsContent = false;
M["list-2"] = n10.id;

const n11 = figma.createFrame();
n11.name = "list_item-1";
n11.layoutMode = "VERTICAL";
n11.fills = [];
n11.clipsContent = false;
M["list_item-1"] = n11.id;

const n12 = figma.createFrame();
n12.name = "list_item-2";
n12.layoutMode = "VERTICAL";
n12.fills = [];
n12.clipsContent = false;
M["list_item-2"] = n12.id;

const n13 = figma.createFrame();
n13.name = "list_item-3";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["list_item-3"] = n13.id;

const n14 = figma.createFrame();
n14.name = "list_item-4";
n14.layoutMode = "VERTICAL";
n14.fills = [];
n14.clipsContent = false;
M["list_item-4"] = n14.id;

const n15 = figma.createFrame();
n15.name = "list_item-5";
n15.layoutMode = "VERTICAL";
n15.fills = [];
n15.clipsContent = false;
M["list_item-5"] = n15.id;

const n16 = figma.createFrame();
n16.name = "list_item-6";
n16.layoutMode = "VERTICAL";
n16.fills = [];
n16.clipsContent = false;
M["list_item-6"] = n16.id;

const n17 = figma.createFrame();
n17.name = "icon-1";
n17.layoutMode = "VERTICAL";
n17.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n17.cornerRadius = 8;
n17.clipsContent = false;
M["icon-1"] = n17.id;

const n18 = figma.createText();
n18.name = "text-1";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n18.id;

const n19 = figma.createFrame();
n19.name = "icon-2";
n19.layoutMode = "VERTICAL";
n19.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n19.cornerRadius = 8;
n19.clipsContent = false;
M["icon-2"] = n19.id;

const n20 = figma.createText();
n20.name = "text-2";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n20.id;

const n21 = figma.createFrame();
n21.name = "icon-3";
n21.layoutMode = "VERTICAL";
n21.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n21.cornerRadius = 8;
n21.clipsContent = false;
M["icon-3"] = n21.id;

const n22 = figma.createText();
n22.name = "text-3";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n22.id;

const n23 = figma.createFrame();
n23.name = "icon-4";
n23.layoutMode = "VERTICAL";
n23.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n23.cornerRadius = 8;
n23.clipsContent = false;
M["icon-4"] = n23.id;

const n24 = figma.createText();
n24.name = "text-4";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n24.id;

const n25 = figma.createFrame();
n25.name = "icon-5";
n25.layoutMode = "VERTICAL";
n25.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n25.cornerRadius = 8;
n25.clipsContent = false;
M["icon-5"] = n25.id;

const n26 = figma.createText();
n26.name = "text-5";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n26.id;

const n27 = figma.createFrame();
n27.name = "icon-6";
n27.layoutMode = "VERTICAL";
n27.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n27.cornerRadius = 8;
n27.clipsContent = false;
M["icon-6"] = n27.id;

const n28 = figma.createText();
n28.name = "text-6";
try { n28.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n28.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n0.appendChild(n3);
n3.layoutSizingHorizontal = "FILL";
n1.appendChild(n4);
n4.layoutSizingHorizontal = "FIXED";
n4.layoutSizingVertical = "FIXED";
n1.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n1.appendChild(n6);
n6.layoutSizingHorizontal = "FIXED";
n6.layoutSizingVertical = "FIXED";
n2.appendChild(n7);
try { n7.characters = "Recent Searches"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n2.appendChild(n8);
n3.appendChild(n9);
try { n9.characters = "Popular Searches"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n3.appendChild(n10);
n8.appendChild(n11);
n8.appendChild(n12);
n8.appendChild(n13);
n10.appendChild(n14);
n10.appendChild(n15);
n10.appendChild(n16);
n11.appendChild(n17);
n17.layoutSizingHorizontal = "HUG";
n17.layoutSizingVertical = "HUG";
n11.appendChild(n18);
try { n18.characters = "iPhone 15 Pro"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n12.appendChild(n19);
n19.layoutSizingHorizontal = "HUG";
n19.layoutSizingVertical = "HUG";
n12.appendChild(n20);
try { n20.characters = "MacBook Air M2"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n13.appendChild(n21);
n21.layoutSizingHorizontal = "HUG";
n21.layoutSizingVertical = "HUG";
n13.appendChild(n22);
try { n22.characters = "AirPods Pro"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n14.appendChild(n23);
n23.layoutSizingHorizontal = "HUG";
n23.layoutSizingVertical = "HUG";
n14.appendChild(n24);
try { n24.characters = "Electronics"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n15.appendChild(n25);
n25.layoutSizingHorizontal = "HUG";
n25.layoutSizingVertical = "HUG";
n15.appendChild(n26);
try { n26.characters = "Fashion"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
n16.appendChild(n27);
n27.layoutSizingHorizontal = "HUG";
n27.layoutSizingVertical = "HUG";
n16.appendChild(n28);
try { n28.characters = "Home & Garden"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n28.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;