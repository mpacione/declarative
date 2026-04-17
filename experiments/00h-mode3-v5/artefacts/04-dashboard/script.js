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

const n4 = figma.createText();
n4.name = "text-1";
try { n4.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n4.id;

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
n6.name = "heading-1";
try { n6.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n6.id;

const n7 = figma.createFrame();
n7.name = "image-1";
n7.fills = [];
n7.clipsContent = false;
M["image-1"] = n7.id;

const n8 = figma.createText();
n8.name = "heading-2";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n8.id;

const n9 = figma.createFrame();
n9.name = "table-1";
n9.layoutMode = "VERTICAL";
n9.fills = [];
n9.clipsContent = false;
M["table-1"] = n9.id;

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

const n13 = figma.createText();
n13.name = "text-5";
try { n13.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n13.id;

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

const n18 = figma.createFrame();
n18.name = "list_item-5";
n18.layoutMode = "VERTICAL";
n18.fills = [];
n18.clipsContent = false;
M["list_item-5"] = n18.id;

const n19 = figma.createText();
n19.name = "text-6";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n19.id;

const n20 = figma.createText();
n20.name = "text-7";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n20.id;

const n21 = figma.createText();
n21.name = "text-8";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n21.id;

const n22 = figma.createFrame();
n22.name = "badge-1";
n22.layoutMode = "VERTICAL";
n22.itemSpacing = 4;
n22.counterAxisAlignItems = "CENTER";
n22.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n22.cornerRadius = 999;
n22.clipsContent = false;
M["badge-1"] = n22.id;

const n23 = figma.createText();
n23.name = "text-10";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n23.id;

const n24 = figma.createText();
n24.name = "text-11";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n24.id;

const n25 = figma.createText();
n25.name = "text-12";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-12"] = n25.id;

const n26 = figma.createFrame();
n26.name = "badge-2";
n26.layoutMode = "VERTICAL";
n26.itemSpacing = 4;
n26.counterAxisAlignItems = "CENTER";
n26.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n26.cornerRadius = 999;
n26.clipsContent = false;
M["badge-2"] = n26.id;

const n27 = figma.createText();
n27.name = "text-14";
try { n27.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-14"] = n27.id;

const n28 = figma.createText();
n28.name = "text-15";
try { n28.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-15"] = n28.id;

const n29 = figma.createText();
n29.name = "text-16";
try { n29.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-16"] = n29.id;

const n30 = figma.createFrame();
n30.name = "badge-3";
n30.layoutMode = "VERTICAL";
n30.itemSpacing = 4;
n30.counterAxisAlignItems = "CENTER";
n30.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n30.cornerRadius = 999;
n30.clipsContent = false;
M["badge-3"] = n30.id;

const n31 = figma.createText();
n31.name = "text-18";
try { n31.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-18"] = n31.id;

const n32 = figma.createText();
n32.name = "text-19";
try { n32.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-19"] = n32.id;

const n33 = figma.createText();
n33.name = "text-20";
try { n33.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-20"] = n33.id;

const n34 = figma.createFrame();
n34.name = "badge-4";
n34.layoutMode = "VERTICAL";
n34.itemSpacing = 4;
n34.counterAxisAlignItems = "CENTER";
n34.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n34.cornerRadius = 999;
n34.clipsContent = false;
M["badge-4"] = n34.id;

const n35 = figma.createText();
n35.name = "text-22";
try { n35.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-22", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-22"] = n35.id;

const n36 = figma.createText();
n36.name = "text-23";
try { n36.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-23", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-23"] = n36.id;

const n37 = figma.createText();
n37.name = "text-24";
try { n37.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-24", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-24"] = n37.id;

const n38 = figma.createFrame();
n38.name = "badge-5";
n38.layoutMode = "VERTICAL";
n38.itemSpacing = 4;
n38.counterAxisAlignItems = "CENTER";
n38.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n38.cornerRadius = 999;
n38.clipsContent = false;
M["badge-5"] = n38.id;

const n39 = figma.createText();
n39.name = "text-9";
n39.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n39.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n39.fontSize = 12;
M["text-9"] = n39.id;

const n40 = figma.createText();
n40.name = "text-13";
n40.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n40.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.fontSize = 12;
M["text-13"] = n40.id;

const n41 = figma.createText();
n41.name = "text-17";
n41.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n41.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.fontSize = 12;
M["text-17"] = n41.id;

const n42 = figma.createText();
n42.name = "text-21";
n42.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n42.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-21", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.fontSize = 12;
M["text-21"] = n42.id;

const n43 = figma.createText();
n43.name = "text-25";
n43.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n43.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-25", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n43.fontSize = 12;
M["text-25"] = n43.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n0.appendChild(n3);
n3.layoutSizingHorizontal = "FILL";
n1.appendChild(n4);
try { n4.characters = "Dashboard"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n4.layoutSizingHorizontal = "FILL";
n1.appendChild(n5);
n5.layoutSizingHorizontal = "FIXED";
n5.layoutSizingVertical = "FIXED";
n2.appendChild(n6);
try { n6.characters = "Revenue Trend"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n6.layoutSizingHorizontal = "FILL";
n2.appendChild(n7);
n3.appendChild(n8);
try { n8.characters = "Recent Transactions"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n3.appendChild(n9);
n9.appendChild(n10);
try { n10.characters = "Date"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n9.appendChild(n11);
try { n11.characters = "Description"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n9.appendChild(n12);
try { n12.characters = "Amount"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n9.appendChild(n13);
try { n13.characters = "Status"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n9.appendChild(n14);
n9.appendChild(n15);
n9.appendChild(n16);
n9.appendChild(n17);
n9.appendChild(n18);
n14.appendChild(n19);
try { n19.characters = "2024-01-15"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n14.appendChild(n20);
try { n20.characters = "Client Payment"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n14.appendChild(n21);
try { n21.characters = "$2,500.00"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n14.appendChild(n22);
n22.layoutSizingHorizontal = "HUG";
n22.layoutSizingVertical = "HUG";
n15.appendChild(n23);
try { n23.characters = "2024-01-14"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n15.appendChild(n24);
try { n24.characters = "Vendor Invoice"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n15.appendChild(n25);
try { n25.characters = "-$1,200.00"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n15.appendChild(n26);
n26.layoutSizingHorizontal = "HUG";
n26.layoutSizingVertical = "HUG";
n16.appendChild(n27);
try { n27.characters = "2024-01-13"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n27.layoutSizingHorizontal = "FILL";
n16.appendChild(n28);
try { n28.characters = "Refund Request"; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n28.layoutSizingHorizontal = "FILL";
n16.appendChild(n29);
try { n29.characters = "-$350.00"; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.layoutSizingHorizontal = "FILL";
n16.appendChild(n30);
n30.layoutSizingHorizontal = "HUG";
n30.layoutSizingVertical = "HUG";
n17.appendChild(n31);
try { n31.characters = "2024-01-12"; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.layoutSizingHorizontal = "FILL";
n17.appendChild(n32);
try { n32.characters = "Service Fee"; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n17.appendChild(n33);
try { n33.characters = "-$99.99"; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.layoutSizingHorizontal = "FILL";
n17.appendChild(n34);
n34.layoutSizingHorizontal = "HUG";
n34.layoutSizingVertical = "HUG";
n18.appendChild(n35);
try { n35.characters = "2024-01-11"; } catch (__e) { __errors.push({eid:"text-22", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n18.appendChild(n36);
try { n36.characters = "Subscription Renewal"; } catch (__e) { __errors.push({eid:"text-23", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.layoutSizingHorizontal = "FILL";
n18.appendChild(n37);
try { n37.characters = "$5,000.00"; } catch (__e) { __errors.push({eid:"text-24", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n37.layoutSizingHorizontal = "FILL";
n18.appendChild(n38);
n38.layoutSizingHorizontal = "HUG";
n38.layoutSizingVertical = "HUG";
n22.appendChild(n39);
try { n39.characters = "Completed"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n39.layoutSizingHorizontal = "FILL";
n26.appendChild(n40);
try { n40.characters = "Completed"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.layoutSizingHorizontal = "FILL";
n30.appendChild(n41);
try { n41.characters = "Pending"; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.layoutSizingHorizontal = "FILL";
n34.appendChild(n42);
try { n42.characters = "Completed"; } catch (__e) { __errors.push({eid:"text-21", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.layoutSizingHorizontal = "FILL";
n38.appendChild(n43);
try { n43.characters = "Completed"; } catch (__e) { __errors.push({eid:"text-25", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n43.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;