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
n3.name = "tabs-1";
n3.layoutMode = "VERTICAL";
n3.fills = [];
n3.clipsContent = false;
M["tabs-1"] = n3.id;

const n4 = figma.createFrame();
n4.name = "list-1";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["list-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "card-2";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["card-2"] = n5.id;

const n6 = figma.createFrame();
n6.name = "bottom_nav-1";
n6.layoutMode = "VERTICAL";
n6.fills = [];
n6.clipsContent = false;
M["bottom_nav-1"] = n6.id;

const n7 = figma.createFrame();
n7.name = "icon_button-1";
n7.layoutMode = "VERTICAL";
n7.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n7.cornerRadius = 8;
n7.clipsContent = false;
M["icon_button-1"] = n7.id;

const n8 = figma.createText();
n8.name = "heading-1";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n8.id;

const n9 = figma.createFrame();
n9.name = "icon_button-2";
n9.layoutMode = "VERTICAL";
n9.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n9.cornerRadius = 8;
n9.clipsContent = false;
M["icon_button-2"] = n9.id;

const n10 = figma.createFrame();
n10.name = "image-1";
n10.fills = [];
n10.clipsContent = false;
M["image-1"] = n10.id;

const n11 = figma.createText();
n11.name = "heading-2";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n11.id;

const n12 = figma.createText();
n12.name = "text-1";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n12.id;

const n13 = figma.createText();
n13.name = "text-2";
try { n13.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n13.id;

const n14 = figma.createText();
n14.name = "text-3";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n14.id;

const n15 = figma.createText();
n15.name = "text-4";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n15.id;

const n16 = figma.createFrame();
n16.name = "list_item-1";
n16.layoutMode = "VERTICAL";
n16.fills = [];
n16.clipsContent = false;
M["list_item-1"] = n16.id;

const n17 = figma.createFrame();
n17.name = "list_item-2";
n17.layoutMode = "VERTICAL";
n17.fills = [];
n17.clipsContent = false;
M["list_item-2"] = n17.id;

const n18 = figma.createFrame();
n18.name = "list_item-3";
n18.layoutMode = "VERTICAL";
n18.fills = [];
n18.clipsContent = false;
M["list_item-3"] = n18.id;

const n19 = figma.createText();
n19.name = "heading-3";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n19.id;

const n20 = figma.createText();
n20.name = "text-11";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n20.id;

const n21 = figma.createFrame();
n21.name = "button-1";
n21.layoutMode = "VERTICAL";
n21.itemSpacing = 8;
n21.resize(n21.width, 44);
n21.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n21.cornerRadius = 8;
n21.clipsContent = false;
M["button-1"] = n21.id;

const n22 = figma.createText();
n22.name = "text-13";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-13"] = n22.id;

const n23 = figma.createText();
n23.name = "text-14";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-14"] = n23.id;

const n24 = figma.createText();
n24.name = "text-15";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-15"] = n24.id;

const n25 = figma.createText();
n25.name = "text-16";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-16"] = n25.id;

const n26 = figma.createFrame();
n26.name = "image-2";
n26.fills = [];
n26.clipsContent = false;
M["image-2"] = n26.id;

const n27 = figma.createText();
n27.name = "text-5";
try { n27.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n27.id;

const n28 = figma.createFrame();
n28.name = "badge-1";
n28.layoutMode = "VERTICAL";
n28.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n28.cornerRadius = 8;
n28.clipsContent = false;
M["badge-1"] = n28.id;

const n29 = figma.createFrame();
n29.name = "icon_button-3";
n29.layoutMode = "VERTICAL";
n29.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n29.cornerRadius = 8;
n29.clipsContent = false;
M["icon_button-3"] = n29.id;

const n30 = figma.createFrame();
n30.name = "image-3";
n30.fills = [];
n30.clipsContent = false;
M["image-3"] = n30.id;

const n31 = figma.createText();
n31.name = "text-7";
try { n31.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n31.id;

const n32 = figma.createFrame();
n32.name = "badge-2";
n32.layoutMode = "VERTICAL";
n32.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n32.cornerRadius = 8;
n32.clipsContent = false;
M["badge-2"] = n32.id;

const n33 = figma.createFrame();
n33.name = "icon_button-4";
n33.layoutMode = "VERTICAL";
n33.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n33.cornerRadius = 8;
n33.clipsContent = false;
M["icon_button-4"] = n33.id;

const n34 = figma.createFrame();
n34.name = "image-4";
n34.fills = [];
n34.clipsContent = false;
M["image-4"] = n34.id;

const n35 = figma.createText();
n35.name = "text-9";
try { n35.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n35.id;

const n36 = figma.createFrame();
n36.name = "badge-3";
n36.layoutMode = "VERTICAL";
n36.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n36.cornerRadius = 8;
n36.clipsContent = false;
M["badge-3"] = n36.id;

const n37 = figma.createFrame();
n37.name = "icon_button-5";
n37.layoutMode = "VERTICAL";
n37.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n37.cornerRadius = 8;
n37.clipsContent = false;
M["icon_button-5"] = n37.id;

const n38 = figma.createText();
n38.name = "text-12";
try { n38.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-12"] = n38.id;

const n39 = figma.createText();
n39.name = "text-6";
try { n39.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n39.id;

const n40 = figma.createText();
n40.name = "text-8";
try { n40.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n40.id;

const n41 = figma.createText();
n41.name = "text-10";
try { n41.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n41.id;


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
n7.layoutSizingHorizontal = "FIXED";
n7.layoutSizingVertical = "FIXED";
n1.appendChild(n8);
try { n8.characters = "Discover"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n1.appendChild(n9);
n9.layoutSizingHorizontal = "FIXED";
n9.layoutSizingVertical = "FIXED";
n2.appendChild(n10);
n2.appendChild(n11);
try { n11.characters = "Summer Collection 2024"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n2.appendChild(n12);
try { n12.characters = "Explore limited edition items curated just for you"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n3.appendChild(n13);
try { n13.characters = "Trending"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n3.appendChild(n14);
try { n14.characters = "New"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n3.appendChild(n15);
try { n15.characters = "Saved"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n4.appendChild(n16);
n4.appendChild(n17);
n4.appendChild(n18);
n5.appendChild(n19);
try { n19.characters = "Special Offer"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n5.appendChild(n20);
try { n20.characters = "Get 30% off on your next purchase"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n5.appendChild(n21);
n21.layoutSizingHorizontal = "HUG";
n21.layoutSizingVertical = "FIXED";
n6.appendChild(n22);
try { n22.characters = "Home"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n6.appendChild(n23);
try { n23.characters = "Search"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n6.appendChild(n24);
try { n24.characters = "Messages"; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n6.appendChild(n25);
try { n25.characters = "Profile"; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n16.appendChild(n26);
n16.appendChild(n27);
try { n27.characters = "Wireless Headphones"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n27.layoutSizingHorizontal = "FILL";
n16.appendChild(n28);
n28.layoutSizingHorizontal = "HUG";
n28.layoutSizingVertical = "HUG";
n16.appendChild(n29);
n29.layoutSizingHorizontal = "FIXED";
n29.layoutSizingVertical = "FIXED";
n17.appendChild(n30);
n17.appendChild(n31);
try { n31.characters = "Smart Watch Pro"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n31.layoutSizingHorizontal = "FILL";
n17.appendChild(n32);
n32.layoutSizingHorizontal = "HUG";
n32.layoutSizingVertical = "HUG";
n17.appendChild(n33);
n33.layoutSizingHorizontal = "FIXED";
n33.layoutSizingVertical = "FIXED";
n18.appendChild(n34);
n18.appendChild(n35);
try { n35.characters = "Premium Backpack"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n18.appendChild(n36);
n36.layoutSizingHorizontal = "HUG";
n36.layoutSizingVertical = "HUG";
n18.appendChild(n37);
n37.layoutSizingHorizontal = "FIXED";
n37.layoutSizingVertical = "FIXED";
n21.appendChild(n38);
try { n38.characters = "Claim Now"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.layoutSizingHorizontal = "FILL";
n28.appendChild(n39);
try { n39.characters = "Featured"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n39.layoutSizingHorizontal = "FILL";
n32.appendChild(n40);
try { n40.characters = "Hot"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.layoutSizingHorizontal = "FILL";
n36.appendChild(n41);
try { n41.characters = "New"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;