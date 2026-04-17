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
n3.name = "list-1";
n3.layoutMode = "VERTICAL";
n3.fills = [];
n3.clipsContent = false;
M["list-1"] = n3.id;

const n4 = figma.createFrame();
n4.name = "bottom_nav-1";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["bottom_nav-1"] = n4.id;

const n5 = figma.createText();
n5.name = "text-1";
try { n5.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "icon-1";
n6.layoutMode = "VERTICAL";
n6.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n6.cornerRadius = 4;
n6.clipsContent = false;
M["icon-1"] = n6.id;

const n7 = figma.createFrame();
n7.name = "icon-2";
n7.layoutMode = "VERTICAL";
n7.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n7.cornerRadius = 4;
n7.clipsContent = false;
M["icon-2"] = n7.id;

const n8 = figma.createFrame();
n8.name = "icon-3";
n8.layoutMode = "VERTICAL";
n8.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n8.cornerRadius = 4;
n8.clipsContent = false;
M["icon-3"] = n8.id;

const n9 = figma.createText();
n9.name = "heading-1";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n9.id;

const n10 = figma.createText();
n10.name = "text-2";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n10.id;

const n11 = figma.createFrame();
n11.name = "image-1";
n11.fills = [];
n11.clipsContent = false;
M["image-1"] = n11.id;

const n12 = figma.createText();
n12.name = "text-3";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n12.id;

const n13 = figma.createFrame();
n13.name = "button_group-1";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["button_group-1"] = n13.id;

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
n18.name = "icon_button-1";
n18.layoutMode = "VERTICAL";
n18.primaryAxisAlignItems = "CENTER";
n18.counterAxisAlignItems = "CENTER";
n18.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n18.cornerRadius = 8;
n18.clipsContent = false;
M["icon_button-1"] = n18.id;

const n19 = figma.createFrame();
n19.name = "icon_button-2";
n19.layoutMode = "VERTICAL";
n19.primaryAxisAlignItems = "CENTER";
n19.counterAxisAlignItems = "CENTER";
n19.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n19.cornerRadius = 8;
n19.clipsContent = false;
M["icon_button-2"] = n19.id;

const n20 = figma.createFrame();
n20.name = "icon_button-3";
n20.layoutMode = "VERTICAL";
n20.primaryAxisAlignItems = "CENTER";
n20.counterAxisAlignItems = "CENTER";
n20.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n20.cornerRadius = 8;
n20.clipsContent = false;
M["icon_button-3"] = n20.id;

const n21 = figma.createFrame();
n21.name = "icon_button-4";
n21.layoutMode = "VERTICAL";
n21.primaryAxisAlignItems = "CENTER";
n21.counterAxisAlignItems = "CENTER";
n21.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n21.cornerRadius = 8;
n21.clipsContent = false;
M["icon_button-4"] = n21.id;

const n22 = figma.createFrame();
n22.name = "button-1";
n22.layoutMode = "VERTICAL";
n22.itemSpacing = 8;
n22.resize(n22.width, 44);
n22.primaryAxisAlignItems = "CENTER";
n22.counterAxisAlignItems = "CENTER";
n22.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n22.cornerRadius = 8;
n22.clipsContent = false;
M["button-1"] = n22.id;

const n23 = figma.createFrame();
n23.name = "button-2";
n23.layoutMode = "VERTICAL";
n23.itemSpacing = 8;
n23.resize(n23.width, 44);
n23.primaryAxisAlignItems = "CENTER";
n23.counterAxisAlignItems = "CENTER";
n23.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n23.cornerRadius = 8;
n23.clipsContent = false;
M["button-2"] = n23.id;

const n24 = figma.createFrame();
n24.name = "icon-4";
n24.layoutMode = "VERTICAL";
n24.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n24.cornerRadius = 4;
n24.clipsContent = false;
M["icon-4"] = n24.id;

const n25 = figma.createText();
n25.name = "text-6";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n25.id;

const n26 = figma.createFrame();
n26.name = "icon-5";
n26.layoutMode = "VERTICAL";
n26.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n26.cornerRadius = 4;
n26.clipsContent = false;
M["icon-5"] = n26.id;

const n27 = figma.createText();
n27.name = "text-7";
try { n27.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n27.id;

const n28 = figma.createFrame();
n28.name = "icon-6";
n28.layoutMode = "VERTICAL";
n28.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n28.cornerRadius = 4;
n28.clipsContent = false;
M["icon-6"] = n28.id;

const n29 = figma.createText();
n29.name = "text-8";
try { n29.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n29.id;

const n30 = figma.createFrame();
n30.name = "icon-7";
n30.layoutMode = "VERTICAL";
n30.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n30.cornerRadius = 4;
n30.clipsContent = false;
M["icon-7"] = n30.id;

const n31 = figma.createText();
n31.name = "text-9";
try { n31.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n31.id;

const n32 = figma.createText();
n32.name = "text-4";
n32.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n32.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.fontSize = 14;
M["text-4"] = n32.id;

const n33 = figma.createText();
n33.name = "text-5";
n33.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n33.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.fontSize = 14;
M["text-5"] = n33.id;


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
try { n5.characters = "9:41"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n5.layoutSizingHorizontal = "FILL";
n1.appendChild(n6);
n6.layoutSizingHorizontal = "FIXED";
n6.layoutSizingVertical = "FIXED";
n1.appendChild(n7);
n7.layoutSizingHorizontal = "FIXED";
n7.layoutSizingVertical = "FIXED";
n1.appendChild(n8);
n8.layoutSizingHorizontal = "FIXED";
n8.layoutSizingVertical = "FIXED";
n2.appendChild(n9);
try { n9.characters = "iPhone 13 Pro Max"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n2.appendChild(n10);
try { n10.characters = "Powerful. Pro. Max."; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n2.appendChild(n11);
n2.appendChild(n12);
try { n12.characters = "The largest iPhone display ever. A new camera system with advanced computational photography. And a powerful chip that does it all."; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n2.appendChild(n13);
n3.appendChild(n14);
n3.appendChild(n15);
n3.appendChild(n16);
n3.appendChild(n17);
n4.appendChild(n18);
n18.layoutSizingHorizontal = "FIXED";
n18.layoutSizingVertical = "FIXED";
n4.appendChild(n19);
n19.layoutSizingHorizontal = "FIXED";
n19.layoutSizingVertical = "FIXED";
n4.appendChild(n20);
n20.layoutSizingHorizontal = "FIXED";
n20.layoutSizingVertical = "FIXED";
n4.appendChild(n21);
n21.layoutSizingHorizontal = "FIXED";
n21.layoutSizingVertical = "FIXED";
n13.appendChild(n22);
n22.layoutSizingHorizontal = "HUG";
n22.layoutSizingVertical = "FIXED";
n13.appendChild(n23);
n23.layoutSizingHorizontal = "HUG";
n23.layoutSizingVertical = "FIXED";
n14.appendChild(n24);
n24.layoutSizingHorizontal = "FIXED";
n24.layoutSizingVertical = "FIXED";
n14.appendChild(n25);
try { n25.characters = "Pro Camera System with 48MP main camera"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n15.appendChild(n26);
n26.layoutSizingHorizontal = "FIXED";
n26.layoutSizingVertical = "FIXED";
n15.appendChild(n27);
try { n27.characters = "6.7-inch Super Retina XDR display"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n27.layoutSizingHorizontal = "FILL";
n16.appendChild(n28);
n28.layoutSizingHorizontal = "FIXED";
n28.layoutSizingVertical = "FIXED";
n16.appendChild(n29);
try { n29.characters = "A15 Bionic chip for lightning-fast performance"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.layoutSizingHorizontal = "FILL";
n17.appendChild(n30);
n30.layoutSizingHorizontal = "FIXED";
n30.layoutSizingVertical = "FIXED";
n17.appendChild(n31);
try { n31.characters = "All-day battery life with fast charging"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.layoutSizingHorizontal = "FILL";
n22.appendChild(n32);
try { n32.characters = "Learn More"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n23.appendChild(n33);
try { n33.characters = "Buy Now"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;