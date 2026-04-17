const __errors = [];
await (async () => { try { await figma.loadFontAsync({family: "Inter", style: "Regular"}); } catch (__e) { __errors.push({kind:"font_load_failed", family:"Inter", style:"Regular", error: String(__e && __e.message || __e)}); } })();
const M = {};
const _rootPage = figma.currentPage;



try {
// Phase 1: Materialize — create nodes, set intrinsic properties
const n0 = figma.createFrame();
n0.name = "screen-1";
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

const n2 = figma.createText();
n2.name = "heading-1";
try { n2.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n2.id;

const n3 = figma.createText();
n3.name = "text-1";
try { n3.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n3.id;

const n4 = figma.createFrame();
n4.name = "card-1";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["card-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "card-2";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["card-2"] = n5.id;

const n6 = figma.createFrame();
n6.name = "card-3";
n6.layoutMode = "VERTICAL";
n6.fills = [];
n6.clipsContent = false;
M["card-3"] = n6.id;

const n7 = figma.createFrame();
n7.name = "card-4";
n7.layoutMode = "VERTICAL";
n7.fills = [];
n7.clipsContent = false;
M["card-4"] = n7.id;

const n8 = figma.createText();
n8.name = "heading-2";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n8.id;

const n9 = figma.createText();
n9.name = "heading-3";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n9.id;

const n10 = figma.createText();
n10.name = "text-2";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n10.id;

const n11 = figma.createFrame();
n11.name = "list-1";
n11.layoutMode = "VERTICAL";
n11.fills = [];
n11.clipsContent = false;
M["list-1"] = n11.id;

const n12 = figma.createFrame();
n12.name = "button-1";
n12.layoutMode = "VERTICAL";
n12.fills = [];
n12.clipsContent = false;
M["button-1"] = n12.id;

const n13 = figma.createFrame();
n13.name = "badge-1";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["badge-1"] = n13.id;

const n14 = figma.createText();
n14.name = "heading-4";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-4"] = n14.id;

const n15 = figma.createText();
n15.name = "heading-5";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-5"] = n15.id;

const n16 = figma.createText();
n16.name = "text-3";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n16.id;

const n17 = figma.createFrame();
n17.name = "list-2";
n17.layoutMode = "VERTICAL";
n17.fills = [];
n17.clipsContent = false;
M["list-2"] = n17.id;

const n18 = figma.createFrame();
n18.name = "button-2";
n18.layoutMode = "VERTICAL";
n18.fills = [];
n18.clipsContent = false;
M["button-2"] = n18.id;

const n19 = figma.createText();
n19.name = "heading-6";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-6"] = n19.id;

const n20 = figma.createText();
n20.name = "heading-7";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-7"] = n20.id;

const n21 = figma.createText();
n21.name = "text-4";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n21.id;

const n22 = figma.createFrame();
n22.name = "list-3";
n22.layoutMode = "VERTICAL";
n22.fills = [];
n22.clipsContent = false;
M["list-3"] = n22.id;

const n23 = figma.createFrame();
n23.name = "button-3";
n23.layoutMode = "VERTICAL";
n23.fills = [];
n23.clipsContent = false;
M["button-3"] = n23.id;

const n24 = figma.createText();
n24.name = "heading-8";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-8"] = n24.id;

const n25 = figma.createText();
n25.name = "text-5";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n25.id;

const n26 = figma.createText();
n26.name = "text-6";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n26.id;

const n27 = figma.createFrame();
n27.name = "avatar-1";
n27.layoutMode = "VERTICAL";
n27.fills = [];
n27.clipsContent = false;
M["avatar-1"] = n27.id;

const n28 = figma.createFrame();
n28.name = "list_item-1";
n28.layoutMode = "VERTICAL";
n28.fills = [];
n28.clipsContent = false;
M["list_item-1"] = n28.id;

const n29 = figma.createFrame();
n29.name = "list_item-2";
n29.layoutMode = "VERTICAL";
n29.fills = [];
n29.clipsContent = false;
M["list_item-2"] = n29.id;

const n30 = figma.createFrame();
n30.name = "list_item-3";
n30.layoutMode = "VERTICAL";
n30.fills = [];
n30.clipsContent = false;
M["list_item-3"] = n30.id;

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


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n0.appendChild(n2);
try { n2.characters = "Simple, Transparent Pricing"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n0.appendChild(n3);
try { n3.characters = "Select the plan that works best for you"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n0.appendChild(n4);
n0.appendChild(n5);
n0.appendChild(n6);
n0.appendChild(n7);
n4.appendChild(n8);
try { n8.characters = "Starter"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n4.appendChild(n9);
try { n9.characters = "$9/month"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n4.appendChild(n10);
try { n10.characters = "Perfect for getting started"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n4.appendChild(n11);
n4.appendChild(n12);
n5.appendChild(n13);
n5.appendChild(n14);
try { n14.characters = "Professional"; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n5.appendChild(n15);
try { n15.characters = "$29/month"; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n5.appendChild(n16);
try { n16.characters = "For growing teams"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n5.appendChild(n17);
n5.appendChild(n18);
n6.appendChild(n19);
try { n19.characters = "Enterprise"; } catch (__e) { __errors.push({eid:"heading-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n6.appendChild(n20);
try { n20.characters = "Custom"; } catch (__e) { __errors.push({eid:"heading-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n6.appendChild(n21);
try { n21.characters = "For large organizations"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n6.appendChild(n22);
n6.appendChild(n23);
n7.appendChild(n24);
try { n24.characters = "What Our Customers Say"; } catch (__e) { __errors.push({eid:"heading-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n7.appendChild(n25);
try { n25.characters = "\"This platform has completely transformed how we manage our projects. The Professional plan gives us everything we need at an excellent price.\""; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n7.appendChild(n26);
try { n26.characters = "Sarah Chen, Product Manager at TechCorp"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
n7.appendChild(n27);
n11.appendChild(n28);
n11.appendChild(n29);
n11.appendChild(n30);
n17.appendChild(n31);
n17.appendChild(n32);
n17.appendChild(n33);
n17.appendChild(n34);
n22.appendChild(n35);
n22.appendChild(n36);
n22.appendChild(n37);
n22.appendChild(n38);
_rootPage.appendChild(n0);

// Phase 3: Hydrate — text content, position, constraints
await new Promise(r => setTimeout(r, 0));

try { n1.x = 0; } catch (__e) { __errors.push({eid:"header-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n1.y = 0; } catch (__e) { __errors.push({eid:"header-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.x = 0; } catch (__e) { __errors.push({eid:"heading-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.y = 50; } catch (__e) { __errors.push({eid:"heading-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n3.x = 0; } catch (__e) { __errors.push({eid:"text-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n3.y = 100; } catch (__e) { __errors.push({eid:"text-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n4.x = 0; } catch (__e) { __errors.push({eid:"card-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n4.y = 150; } catch (__e) { __errors.push({eid:"card-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n5.x = 0; } catch (__e) { __errors.push({eid:"card-2", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n5.y = 200; } catch (__e) { __errors.push({eid:"card-2", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n6.x = 0; } catch (__e) { __errors.push({eid:"card-3", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n6.y = 250; } catch (__e) { __errors.push({eid:"card-3", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n7.x = 0; } catch (__e) { __errors.push({eid:"card-4", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n7.y = 300; } catch (__e) { __errors.push({eid:"card-4", kind:"position_failed", error: String(__e && __e.message || __e)}); }
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;