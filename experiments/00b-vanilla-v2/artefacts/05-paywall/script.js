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
n2.name = "text-1";
try { n2.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n2.id;

const n3 = figma.createFrame();
n3.name = "card-1";
n3.layoutMode = "VERTICAL";
n3.fills = [];
n3.clipsContent = false;
M["card-1"] = n3.id;

const n4 = figma.createFrame();
n4.name = "card-2";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["card-2"] = n4.id;

const n5 = figma.createFrame();
n5.name = "card-3";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["card-3"] = n5.id;

const n6 = figma.createFrame();
n6.name = "card-4";
n6.layoutMode = "VERTICAL";
n6.fills = [];
n6.clipsContent = false;
M["card-4"] = n6.id;

const n7 = figma.createText();
n7.name = "heading-1";
n7.layoutMode = "VERTICAL";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n7.id;

const n8 = figma.createText();
n8.name = "text-2";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n8.id;

const n9 = figma.createText();
n9.name = "text-3";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n9.id;

const n10 = figma.createFrame();
n10.name = "list-1";
n10.layoutMode = "VERTICAL";
n10.fills = [];
n10.clipsContent = false;
M["list-1"] = n10.id;

const n11 = figma.createFrame();
n11.name = "button-1";
n11.layoutMode = "VERTICAL";
n11.fills = [];
n11.clipsContent = false;
M["button-1"] = n11.id;

const n12 = figma.createText();
n12.name = "heading-2";
n12.layoutMode = "VERTICAL";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n12.id;

const n13 = figma.createFrame();
n13.name = "badge-1";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["badge-1"] = n13.id;

const n14 = figma.createText();
n14.name = "text-4";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n14.id;

const n15 = figma.createText();
n15.name = "text-5";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n15.id;

const n16 = figma.createFrame();
n16.name = "list-2";
n16.layoutMode = "VERTICAL";
n16.fills = [];
n16.clipsContent = false;
M["list-2"] = n16.id;

const n17 = figma.createFrame();
n17.name = "button-2";
n17.layoutMode = "VERTICAL";
n17.fills = [];
n17.clipsContent = false;
M["button-2"] = n17.id;

const n18 = figma.createText();
n18.name = "heading-3";
n18.layoutMode = "VERTICAL";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n18.id;

const n19 = figma.createText();
n19.name = "text-6";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n19.id;

const n20 = figma.createText();
n20.name = "text-7";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n20.id;

const n21 = figma.createFrame();
n21.name = "list-3";
n21.layoutMode = "VERTICAL";
n21.fills = [];
n21.clipsContent = false;
M["list-3"] = n21.id;

const n22 = figma.createFrame();
n22.name = "button-3";
n22.layoutMode = "VERTICAL";
n22.fills = [];
n22.clipsContent = false;
M["button-3"] = n22.id;

const n23 = figma.createText();
n23.name = "heading-4";
n23.layoutMode = "VERTICAL";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-4"] = n23.id;

const n24 = figma.createText();
n24.name = "text-8";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n24.id;

const n25 = figma.createFrame();
n25.name = "avatar-1";
n25.layoutMode = "VERTICAL";
n25.fills = [];
n25.clipsContent = false;
M["avatar-1"] = n25.id;

const n26 = figma.createText();
n26.name = "text-9";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n26.id;

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

const n30 = figma.createFrame();
n30.name = "list_item-4";
n30.layoutMode = "VERTICAL";
n30.fills = [];
n30.clipsContent = false;
M["list_item-4"] = n30.id;

const n31 = figma.createFrame();
n31.name = "list_item-5";
n31.layoutMode = "VERTICAL";
n31.fills = [];
n31.clipsContent = false;
M["list_item-5"] = n31.id;

const n32 = figma.createFrame();
n32.name = "list_item-6";
n32.layoutMode = "VERTICAL";
n32.fills = [];
n32.clipsContent = false;
M["list_item-6"] = n32.id;

const n33 = figma.createFrame();
n33.name = "list_item-7";
n33.layoutMode = "VERTICAL";
n33.fills = [];
n33.clipsContent = false;
M["list_item-7"] = n33.id;

const n34 = figma.createFrame();
n34.name = "list_item-8";
n34.layoutMode = "VERTICAL";
n34.fills = [];
n34.clipsContent = false;
M["list_item-8"] = n34.id;

const n35 = figma.createFrame();
n35.name = "list_item-9";
n35.layoutMode = "VERTICAL";
n35.fills = [];
n35.clipsContent = false;
M["list_item-9"] = n35.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n0.appendChild(n2);
try { n2.characters = "Select the perfect plan for your needs"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n0.appendChild(n3);
n0.appendChild(n4);
n0.appendChild(n5);
n0.appendChild(n6);
n3.appendChild(n7);
try { n7.characters = "Starter"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n3.appendChild(n8);
try { n8.characters = "$9"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n3.appendChild(n9);
try { n9.characters = "/month"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n3.appendChild(n10);
n3.appendChild(n11);
n4.appendChild(n12);
try { n12.characters = "Professional"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n4.appendChild(n13);
n4.appendChild(n14);
try { n14.characters = "$29"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n4.appendChild(n15);
try { n15.characters = "/month"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n4.appendChild(n16);
n4.appendChild(n17);
n5.appendChild(n18);
try { n18.characters = "Enterprise"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n5.appendChild(n19);
try { n19.characters = "Custom"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n5.appendChild(n20);
try { n20.characters = "pricing"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n5.appendChild(n21);
n5.appendChild(n22);
n6.appendChild(n23);
try { n23.characters = "What Our Users Say"; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n6.appendChild(n24);
try { n24.characters = "\"This service transformed how we manage our projects. Highly recommended!\""; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n6.appendChild(n25);
n6.appendChild(n26);
try { n26.characters = "Sarah Chen, Product Manager"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
n10.appendChild(n27);
n10.appendChild(n28);
n10.appendChild(n29);
n16.appendChild(n30);
n16.appendChild(n31);
n16.appendChild(n32);
n21.appendChild(n33);
n21.appendChild(n34);
n21.appendChild(n35);
_rootPage.appendChild(n0);

// Phase 3: Hydrate — text content, position, constraints
await new Promise(r => setTimeout(r, 0));

try { n1.x = 0; } catch (__e) { __errors.push({eid:"header-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n1.y = 0; } catch (__e) { __errors.push({eid:"header-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.x = 0; } catch (__e) { __errors.push({eid:"text-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.y = 50; } catch (__e) { __errors.push({eid:"text-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n3.x = 0; } catch (__e) { __errors.push({eid:"card-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n3.y = 100; } catch (__e) { __errors.push({eid:"card-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n4.x = 0; } catch (__e) { __errors.push({eid:"card-2", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n4.y = 150; } catch (__e) { __errors.push({eid:"card-2", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n5.x = 0; } catch (__e) { __errors.push({eid:"card-3", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n5.y = 200; } catch (__e) { __errors.push({eid:"card-3", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n6.x = 0; } catch (__e) { __errors.push({eid:"card-4", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n6.y = 250; } catch (__e) { __errors.push({eid:"card-4", kind:"position_failed", error: String(__e && __e.message || __e)}); }
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;