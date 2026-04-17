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
n1.name = "header-1";
n1.layoutMode = "VERTICAL";
n1.fills = [];
n1.clipsContent = false;
M["header-1"] = n1.id;

const n2 = figma.createFrame();
n2.name = "tabs-1";
n2.layoutMode = "VERTICAL";
n2.fills = [];
n2.clipsContent = false;
M["tabs-1"] = n2.id;

const n3 = figma.createFrame();
n3.name = "button_group-1";
n3.layoutMode = "VERTICAL";
n3.fills = [];
n3.clipsContent = false;
M["button_group-1"] = n3.id;

const n4 = figma.createFrame();
n4.name = "list-1";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["list-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "icon_button-1";
n5.layoutMode = "VERTICAL";
n5.primaryAxisAlignItems = "CENTER";
n5.counterAxisAlignItems = "CENTER";
n5.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n5.cornerRadius = 8;
n5.clipsContent = false;
M["icon_button-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "search_input-1";
n6.layoutMode = "VERTICAL";
n6.fills = [];
n6.clipsContent = false;
M["search_input-1"] = n6.id;

const n7 = figma.createFrame();
n7.name = "icon_button-2";
n7.layoutMode = "VERTICAL";
n7.primaryAxisAlignItems = "CENTER";
n7.counterAxisAlignItems = "CENTER";
n7.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n7.cornerRadius = 8;
n7.clipsContent = false;
M["icon_button-2"] = n7.id;

const n8 = figma.createText();
n8.name = "text-1";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n8.id;

const n9 = figma.createText();
n9.name = "text-2";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n9.id;

const n10 = figma.createText();
n10.name = "text-3";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n10.id;

const n11 = figma.createFrame();
n11.name = "button-1";
n11.layoutMode = "VERTICAL";
n11.itemSpacing = 8;
n11.resize(n11.width, 44);
n11.primaryAxisAlignItems = "CENTER";
n11.counterAxisAlignItems = "CENTER";
n11.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n11.cornerRadius = 8;
n11.clipsContent = false;
M["button-1"] = n11.id;

const n12 = figma.createFrame();
n12.name = "button-2";
n12.layoutMode = "VERTICAL";
n12.itemSpacing = 8;
n12.resize(n12.width, 44);
n12.primaryAxisAlignItems = "CENTER";
n12.counterAxisAlignItems = "CENTER";
n12.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n12.cornerRadius = 8;
n12.clipsContent = false;
M["button-2"] = n12.id;

const n13 = figma.createFrame();
n13.name = "button-3";
n13.layoutMode = "VERTICAL";
n13.itemSpacing = 8;
n13.resize(n13.width, 44);
n13.primaryAxisAlignItems = "CENTER";
n13.counterAxisAlignItems = "CENTER";
n13.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n13.cornerRadius = 8;
n13.clipsContent = false;
M["button-3"] = n13.id;

const n14 = figma.createFrame();
n14.name = "list_item-1";
n14.layoutMode = "VERTICAL";
n14.fills = [];
n14.clipsContent = false;
M["list_item-1"] = n14.id;

const n15 = figma.createFrame();
n15.name = "list_item-2";
n15.layoutMode = "VERTICAL";
n15.fills = [];
n15.clipsContent = false;
M["list_item-2"] = n15.id;

const n16 = figma.createFrame();
n16.name = "list_item-3";
n16.layoutMode = "VERTICAL";
n16.fills = [];
n16.clipsContent = false;
M["list_item-3"] = n16.id;

const n17 = figma.createFrame();
n17.name = "list_item-4";
n17.layoutMode = "VERTICAL";
n17.fills = [];
n17.clipsContent = false;
M["list_item-4"] = n17.id;

const n18 = figma.createText();
n18.name = "text-4";
n18.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n18.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.fontSize = 14;
M["text-4"] = n18.id;

const n19 = figma.createText();
n19.name = "text-5";
n19.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n19.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.fontSize = 14;
M["text-5"] = n19.id;

const n20 = figma.createText();
n20.name = "text-6";
n20.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n20.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.fontSize = 14;
M["text-6"] = n20.id;

const n21 = figma.createFrame();
n21.name = "avatar-1";
n21.layoutMode = "VERTICAL";
n21.primaryAxisAlignItems = "CENTER";
n21.counterAxisAlignItems = "CENTER";
n21.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n21.cornerRadius = 999;
n21.clipsContent = false;
M["avatar-1"] = n21.id;

const n22 = figma.createText();
n22.name = "text-7";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n22.id;

const n23 = figma.createFrame();
n23.name = "icon-1";
n23.layoutMode = "VERTICAL";
n23.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n23.cornerRadius = 4;
n23.clipsContent = false;
M["icon-1"] = n23.id;

const n24 = figma.createFrame();
n24.name = "avatar-2";
n24.layoutMode = "VERTICAL";
n24.primaryAxisAlignItems = "CENTER";
n24.counterAxisAlignItems = "CENTER";
n24.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n24.cornerRadius = 999;
n24.clipsContent = false;
M["avatar-2"] = n24.id;

const n25 = figma.createText();
n25.name = "text-8";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n25.id;

const n26 = figma.createFrame();
n26.name = "icon-2";
n26.layoutMode = "VERTICAL";
n26.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n26.cornerRadius = 4;
n26.clipsContent = false;
M["icon-2"] = n26.id;

const n27 = figma.createFrame();
n27.name = "avatar-3";
n27.layoutMode = "VERTICAL";
n27.primaryAxisAlignItems = "CENTER";
n27.counterAxisAlignItems = "CENTER";
n27.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n27.cornerRadius = 999;
n27.clipsContent = false;
M["avatar-3"] = n27.id;

const n28 = figma.createText();
n28.name = "text-9";
try { n28.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n28.id;

const n29 = figma.createFrame();
n29.name = "icon-3";
n29.layoutMode = "VERTICAL";
n29.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n29.cornerRadius = 4;
n29.clipsContent = false;
M["icon-3"] = n29.id;

const n30 = figma.createFrame();
n30.name = "avatar-4";
n30.layoutMode = "VERTICAL";
n30.primaryAxisAlignItems = "CENTER";
n30.counterAxisAlignItems = "CENTER";
n30.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n30.cornerRadius = 999;
n30.clipsContent = false;
M["avatar-4"] = n30.id;

const n31 = figma.createText();
n31.name = "text-10";
try { n31.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n31.id;

const n32 = figma.createFrame();
n32.name = "icon-4";
n32.layoutMode = "VERTICAL";
n32.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n32.cornerRadius = 4;
n32.clipsContent = false;
M["icon-4"] = n32.id;


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
n5.layoutSizingHorizontal = "FIXED";
n5.layoutSizingVertical = "FIXED";
n1.appendChild(n6);
n6.layoutSizingHorizontal = "FILL";
n1.appendChild(n7);
n7.layoutSizingHorizontal = "FIXED";
n7.layoutSizingVertical = "FIXED";
n2.appendChild(n8);
try { n8.characters = "All"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n2.appendChild(n9);
try { n9.characters = "Recent"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n2.appendChild(n10);
try { n10.characters = "Saved"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n3.appendChild(n11);
n11.layoutSizingHorizontal = "HUG";
n11.layoutSizingVertical = "FIXED";
n3.appendChild(n12);
n12.layoutSizingHorizontal = "HUG";
n12.layoutSizingVertical = "FIXED";
n3.appendChild(n13);
n13.layoutSizingHorizontal = "HUG";
n13.layoutSizingVertical = "FIXED";
n4.appendChild(n14);
n4.appendChild(n15);
n4.appendChild(n16);
n4.appendChild(n17);
n11.appendChild(n18);
try { n18.characters = "All Categories"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n12.appendChild(n19);
try { n19.characters = "Price"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n13.appendChild(n20);
try { n20.characters = "Rating"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n14.appendChild(n21);
n21.layoutSizingHorizontal = "FIXED";
n21.layoutSizingVertical = "FIXED";
n14.appendChild(n22);
try { n22.characters = "Search Result 1"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n14.appendChild(n23);
n23.layoutSizingHorizontal = "FIXED";
n23.layoutSizingVertical = "FIXED";
n15.appendChild(n24);
n24.layoutSizingHorizontal = "FIXED";
n24.layoutSizingVertical = "FIXED";
n15.appendChild(n25);
try { n25.characters = "Search Result 2"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n15.appendChild(n26);
n26.layoutSizingHorizontal = "FIXED";
n26.layoutSizingVertical = "FIXED";
n16.appendChild(n27);
n27.layoutSizingHorizontal = "FIXED";
n27.layoutSizingVertical = "FIXED";
n16.appendChild(n28);
try { n28.characters = "Search Result 3"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n28.layoutSizingHorizontal = "FILL";
n16.appendChild(n29);
n29.layoutSizingHorizontal = "FIXED";
n29.layoutSizingVertical = "FIXED";
n17.appendChild(n30);
n30.layoutSizingHorizontal = "FIXED";
n30.layoutSizingVertical = "FIXED";
n17.appendChild(n31);
try { n31.characters = "Search Result 4"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.layoutSizingHorizontal = "FILL";
n17.appendChild(n32);
n32.layoutSizingHorizontal = "FIXED";
n32.layoutSizingVertical = "FIXED";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;