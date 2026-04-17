const __errors = [];
await (async () => { try { await figma.loadFontAsync({family: "Inter", style: "Regular"}); } catch (__e) { __errors.push({kind:"font_load_failed", family:"Inter", style:"Regular", error: String(__e && __e.message || __e)}); } })();
await (async () => { try { await figma.loadFontAsync({family: "Inter", style: "Semi Bold"}); } catch (__e) { __errors.push({kind:"font_load_failed", family:"Inter", style:"Semi Bold", error: String(__e && __e.message || __e)}); } })();
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
n1.name = "drawer-1";
n1.layoutMode = "VERTICAL";
n1.fills = [];
n1.clipsContent = false;
M["drawer-1"] = n1.id;

const n2 = figma.createFrame();
n2.name = "header-1";
n2.layoutMode = "VERTICAL";
n2.fills = [];
n2.clipsContent = false;
M["header-1"] = n2.id;

const n3 = figma.createFrame();
n3.name = "list-1";
n3.layoutMode = "VERTICAL";
n3.fills = [];
n3.clipsContent = false;
M["list-1"] = n3.id;

const n4 = figma.createFrame();
n4.name = "button-1";
n4.layoutMode = "VERTICAL";
n4.itemSpacing = 8;
n4.resize(n4.width, 44);
n4.primaryAxisAlignItems = "CENTER";
n4.counterAxisAlignItems = "CENTER";
n4.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n4.cornerRadius = 8;
n4.clipsContent = false;
M["button-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "avatar-1";
n5.layoutMode = "VERTICAL";
n5.primaryAxisAlignItems = "CENTER";
n5.counterAxisAlignItems = "CENTER";
n5.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n5.cornerRadius = 999;
n5.clipsContent = false;
M["avatar-1"] = n5.id;

const n6 = figma.createText();
n6.name = "heading-1";
try { n6.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n6.id;

const n7 = figma.createText();
n7.name = "text-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "navigation_row-1";
n8.layoutMode = "VERTICAL";
n8.fills = [];
n8.clipsContent = false;
M["navigation_row-1"] = n8.id;

const n9 = figma.createFrame();
n9.name = "navigation_row-2";
n9.layoutMode = "VERTICAL";
n9.fills = [];
n9.clipsContent = false;
M["navigation_row-2"] = n9.id;

const n10 = figma.createFrame();
n10.name = "navigation_row-3";
n10.layoutMode = "VERTICAL";
n10.fills = [];
n10.clipsContent = false;
M["navigation_row-3"] = n10.id;

const n11 = figma.createFrame();
n11.name = "navigation_row-4";
n11.layoutMode = "VERTICAL";
n11.fills = [];
n11.clipsContent = false;
M["navigation_row-4"] = n11.id;

const n12 = figma.createFrame();
n12.name = "navigation_row-5";
n12.layoutMode = "VERTICAL";
n12.fills = [];
n12.clipsContent = false;
M["navigation_row-5"] = n12.id;

const n13 = figma.createFrame();
n13.name = "navigation_row-6";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["navigation_row-6"] = n13.id;

const n14 = figma.createText();
n14.name = "text-8";
n14.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n14.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.fontSize = 14;
M["text-8"] = n14.id;

const n15 = figma.createFrame();
n15.name = "icon-1";
n15.layoutMode = "VERTICAL";
n15.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n15.cornerRadius = 4;
n15.clipsContent = false;
M["icon-1"] = n15.id;

const n16 = figma.createText();
n16.name = "text-2";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n16.id;

const n17 = figma.createFrame();
n17.name = "icon-2";
n17.layoutMode = "VERTICAL";
n17.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n17.cornerRadius = 4;
n17.clipsContent = false;
M["icon-2"] = n17.id;

const n18 = figma.createText();
n18.name = "text-3";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n18.id;

const n19 = figma.createFrame();
n19.name = "icon-3";
n19.layoutMode = "VERTICAL";
n19.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n19.cornerRadius = 4;
n19.clipsContent = false;
M["icon-3"] = n19.id;

const n20 = figma.createText();
n20.name = "text-4";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n20.id;

const n21 = figma.createFrame();
n21.name = "icon-4";
n21.layoutMode = "VERTICAL";
n21.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n21.cornerRadius = 4;
n21.clipsContent = false;
M["icon-4"] = n21.id;

const n22 = figma.createText();
n22.name = "text-5";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n22.id;

const n23 = figma.createFrame();
n23.name = "icon-5";
n23.layoutMode = "VERTICAL";
n23.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n23.cornerRadius = 4;
n23.clipsContent = false;
M["icon-5"] = n23.id;

const n24 = figma.createText();
n24.name = "text-6";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n24.id;

const n25 = figma.createFrame();
n25.name = "icon-6";
n25.layoutMode = "VERTICAL";
n25.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n25.cornerRadius = 4;
n25.clipsContent = false;
M["icon-6"] = n25.id;

const n26 = figma.createText();
n26.name = "text-7";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n26.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n1.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n1.appendChild(n3);
n1.appendChild(n4);
n4.layoutSizingHorizontal = "HUG";
n4.layoutSizingVertical = "FIXED";
n2.appendChild(n5);
n5.layoutSizingHorizontal = "FIXED";
n5.layoutSizingVertical = "FIXED";
n2.appendChild(n6);
try { n6.characters = "Menu"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n6.layoutSizingHorizontal = "FILL";
n2.appendChild(n7);
try { n7.characters = "Navigation"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n3.appendChild(n8);
n3.appendChild(n9);
n3.appendChild(n10);
n3.appendChild(n11);
n3.appendChild(n12);
n3.appendChild(n13);
n4.appendChild(n14);
try { n14.characters = "Sign Out"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n8.appendChild(n15);
n15.layoutSizingHorizontal = "FIXED";
n15.layoutSizingVertical = "FIXED";
n8.appendChild(n16);
try { n16.characters = "Home"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n9.appendChild(n17);
n17.layoutSizingHorizontal = "FIXED";
n17.layoutSizingVertical = "FIXED";
n9.appendChild(n18);
try { n18.characters = "Search"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n10.appendChild(n19);
n19.layoutSizingHorizontal = "FIXED";
n19.layoutSizingVertical = "FIXED";
n10.appendChild(n20);
try { n20.characters = "Settings"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n11.appendChild(n21);
n21.layoutSizingHorizontal = "FIXED";
n21.layoutSizingVertical = "FIXED";
n11.appendChild(n22);
try { n22.characters = "Profile"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n12.appendChild(n23);
n23.layoutSizingHorizontal = "FIXED";
n23.layoutSizingVertical = "FIXED";
n12.appendChild(n24);
try { n24.characters = "Notifications"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n13.appendChild(n25);
n25.layoutSizingHorizontal = "FIXED";
n25.layoutSizingVertical = "FIXED";
n13.appendChild(n26);
try { n26.characters = "Help"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;