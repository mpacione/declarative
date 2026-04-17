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
n5.name = "icon_button-1";
n5.layoutMode = "VERTICAL";
n5.primaryAxisAlignItems = "CENTER";
n5.counterAxisAlignItems = "CENTER";
n5.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n5.cornerRadius = 8;
n5.clipsContent = false;
M["icon_button-1"] = n5.id;

const n6 = figma.createText();
n6.name = "text-1";
try { n6.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n6.id;

const n7 = figma.createText();
n7.name = "heading-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "avatar-1";
n8.layoutMode = "VERTICAL";
n8.primaryAxisAlignItems = "CENTER";
n8.counterAxisAlignItems = "CENTER";
n8.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n8.cornerRadius = 999;
n8.clipsContent = false;
M["avatar-1"] = n8.id;

const n9 = figma.createFrame();
n9.name = "text_input-1";
n9.layoutMode = "VERTICAL";
n9.itemSpacing = 6;
n9.resize(n9.width, 48);
n9.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n9.strokes = [{type: "SOLID", color: {r:0.7961,g:0.8353,b:0.8824}}];
n9.cornerRadius = 8;
n9.clipsContent = false;
M["text_input-1"] = n9.id;

const n10 = figma.createFrame();
n10.name = "text_input-2";
n10.layoutMode = "VERTICAL";
n10.itemSpacing = 6;
n10.resize(n10.width, 48);
n10.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n10.strokes = [{type: "SOLID", color: {r:0.7961,g:0.8353,b:0.8824}}];
n10.cornerRadius = 8;
n10.clipsContent = false;
M["text_input-2"] = n10.id;

const n11 = figma.createText();
n11.name = "heading-2";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n11.id;

const n12 = figma.createFrame();
n12.name = "list-1";
n12.layoutMode = "VERTICAL";
n12.fills = [];
n12.clipsContent = false;
M["list-1"] = n12.id;

const n13 = figma.createText();
n13.name = "text-10";
n13.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n13.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.fontSize = 14;
M["text-10"] = n13.id;

const n14 = figma.createText();
n14.name = "text-2";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.fontSize = 14;
M["text-2"] = n14.id;

const n15 = figma.createText();
n15.name = "text-3";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.fontSize = 14;
M["text-3"] = n15.id;

const n16 = figma.createText();
n16.name = "text-4";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.fontSize = 14;
M["text-4"] = n16.id;

const n17 = figma.createText();
n17.name = "text-5";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.fontSize = 14;
M["text-5"] = n17.id;

const n18 = figma.createFrame();
n18.name = "navigation_row-1";
n18.layoutMode = "VERTICAL";
n18.fills = [];
n18.clipsContent = false;
M["navigation_row-1"] = n18.id;

const n19 = figma.createFrame();
n19.name = "navigation_row-2";
n19.layoutMode = "VERTICAL";
n19.fills = [];
n19.clipsContent = false;
M["navigation_row-2"] = n19.id;

const n20 = figma.createFrame();
n20.name = "navigation_row-3";
n20.layoutMode = "VERTICAL";
n20.fills = [];
n20.clipsContent = false;
M["navigation_row-3"] = n20.id;

const n21 = figma.createFrame();
n21.name = "navigation_row-4";
n21.layoutMode = "VERTICAL";
n21.fills = [];
n21.clipsContent = false;
M["navigation_row-4"] = n21.id;

const n22 = figma.createText();
n22.name = "text-6";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n22.id;

const n23 = figma.createFrame();
n23.name = "toggle-1";
n23.layoutMode = "VERTICAL";
n23.itemSpacing = 8;
n23.counterAxisAlignItems = "CENTER";
n23.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n23.cornerRadius = 999;
n23.clipsContent = false;
M["toggle-1"] = n23.id;

const n24 = figma.createText();
n24.name = "text-7";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n24.id;

const n25 = figma.createFrame();
n25.name = "toggle-2";
n25.layoutMode = "VERTICAL";
n25.itemSpacing = 8;
n25.counterAxisAlignItems = "CENTER";
n25.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n25.cornerRadius = 999;
n25.clipsContent = false;
M["toggle-2"] = n25.id;

const n26 = figma.createText();
n26.name = "text-8";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n26.id;

const n27 = figma.createFrame();
n27.name = "toggle-3";
n27.layoutMode = "VERTICAL";
n27.itemSpacing = 8;
n27.counterAxisAlignItems = "CENTER";
n27.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n27.cornerRadius = 999;
n27.clipsContent = false;
M["toggle-3"] = n27.id;

const n28 = figma.createText();
n28.name = "text-9";
try { n28.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n28.id;

const n29 = figma.createFrame();
n29.name = "toggle-4";
n29.layoutMode = "VERTICAL";
n29.itemSpacing = 8;
n29.counterAxisAlignItems = "CENTER";
n29.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n29.cornerRadius = 999;
n29.clipsContent = false;
M["toggle-4"] = n29.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n0.appendChild(n3);
n3.layoutSizingHorizontal = "FILL";
n0.appendChild(n4);
n4.layoutSizingHorizontal = "HUG";
n4.layoutSizingVertical = "FIXED";
n1.appendChild(n5);
n5.layoutSizingHorizontal = "FIXED";
n5.layoutSizingVertical = "FIXED";
n1.appendChild(n6);
try { n6.characters = "Settings"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n6.layoutSizingHorizontal = "FILL";
n2.appendChild(n7);
try { n7.characters = "Profile"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n2.appendChild(n8);
n8.layoutSizingHorizontal = "FIXED";
n8.layoutSizingVertical = "FIXED";
n2.appendChild(n9);
n9.layoutSizingHorizontal = "FILL";
n9.layoutSizingVertical = "HUG";
n2.appendChild(n10);
n10.layoutSizingHorizontal = "FILL";
n10.layoutSizingVertical = "HUG";
n3.appendChild(n11);
try { n11.characters = "Notifications"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n3.appendChild(n12);
n4.appendChild(n13);
try { n13.characters = "Save Changes"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n9.appendChild(n14);
try { n14.characters = "Name"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n9.appendChild(n15);
try { n15.characters = "Enter your name"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n10.appendChild(n16);
try { n16.characters = "Email"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n10.appendChild(n17);
try { n17.characters = "Enter your email"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n12.appendChild(n18);
n12.appendChild(n19);
n12.appendChild(n20);
n12.appendChild(n21);
n18.appendChild(n22);
try { n22.characters = "Email Notifications"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n18.appendChild(n23);
n23.layoutSizingHorizontal = "HUG";
n23.layoutSizingVertical = "HUG";
n19.appendChild(n24);
try { n24.characters = "Push Notifications"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n19.appendChild(n25);
n25.layoutSizingHorizontal = "HUG";
n25.layoutSizingVertical = "HUG";
n20.appendChild(n26);
try { n26.characters = "Marketing Emails"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
n20.appendChild(n27);
n27.layoutSizingHorizontal = "HUG";
n27.layoutSizingVertical = "HUG";
n21.appendChild(n28);
try { n28.characters = "SMS Alerts"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n28.layoutSizingHorizontal = "FILL";
n21.appendChild(n29);
n29.layoutSizingHorizontal = "HUG";
n29.layoutSizingVertical = "HUG";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;