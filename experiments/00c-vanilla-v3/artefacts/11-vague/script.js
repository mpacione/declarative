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
n4.name = "card-3";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["card-3"] = n4.id;

const n5 = figma.createFrame();
n5.name = "card-4";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["card-4"] = n5.id;

const n6 = figma.createFrame();
n6.name = "fab-1";
n6.layoutMode = "VERTICAL";
n6.fills = [];
n6.clipsContent = false;
M["fab-1"] = n6.id;

const n7 = figma.createText();
n7.name = "heading-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "image-1";
n8.fills = [];
n8.clipsContent = false;
M["image-1"] = n8.id;

const n9 = figma.createText();
n9.name = "text-1";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n9.id;

const n10 = figma.createText();
n10.name = "heading-2";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n10.id;

const n11 = figma.createFrame();
n11.name = "list-1";
n11.layoutMode = "VERTICAL";
n11.fills = [];
n11.clipsContent = false;
M["list-1"] = n11.id;

const n12 = figma.createText();
n12.name = "heading-3";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n12.id;

const n13 = figma.createFrame();
n13.name = "toggle_group-1";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["toggle_group-1"] = n13.id;

const n14 = figma.createText();
n14.name = "heading-4";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-4"] = n14.id;

const n15 = figma.createFrame();
n15.name = "button_group-1";
n15.layoutMode = "VERTICAL";
n15.fills = [];
n15.clipsContent = false;
M["button_group-1"] = n15.id;

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

const n19 = figma.createFrame();
n19.name = "toggle-1";
n19.layoutMode = "VERTICAL";
n19.fills = [];
n19.clipsContent = false;
M["toggle-1"] = n19.id;

const n20 = figma.createFrame();
n20.name = "toggle-2";
n20.layoutMode = "VERTICAL";
n20.fills = [];
n20.clipsContent = false;
M["toggle-2"] = n20.id;

const n21 = figma.createFrame();
n21.name = "toggle-3";
n21.layoutMode = "VERTICAL";
n21.fills = [];
n21.clipsContent = false;
M["toggle-3"] = n21.id;

const n22 = figma.createFrame();
n22.name = "button-1";
n22.layoutMode = "VERTICAL";
n22.fills = [];
n22.clipsContent = false;
M["button-1"] = n22.id;

const n23 = figma.createFrame();
n23.name = "button-2";
n23.layoutMode = "VERTICAL";
n23.fills = [];
n23.clipsContent = false;
M["button-2"] = n23.id;

const n24 = figma.createFrame();
n24.name = "button-3";
n24.layoutMode = "VERTICAL";
n24.fills = [];
n24.clipsContent = false;
M["button-3"] = n24.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n0.appendChild(n2);
n0.appendChild(n3);
n0.appendChild(n4);
n0.appendChild(n5);
n0.appendChild(n6);
n2.appendChild(n7);
try { n7.characters = "Featured"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n2.appendChild(n8);
n2.appendChild(n9);
try { n9.characters = "Discover amazing things happening right now"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n3.appendChild(n10);
try { n10.characters = "Explore"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n3.appendChild(n11);
n4.appendChild(n12);
try { n12.characters = "Your Interests"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n4.appendChild(n13);
n5.appendChild(n14);
try { n14.characters = "Quick Actions"; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n5.appendChild(n15);
n11.appendChild(n16);
n11.appendChild(n17);
n11.appendChild(n18);
n13.appendChild(n19);
n13.appendChild(n20);
n13.appendChild(n21);
n15.appendChild(n22);
n15.appendChild(n23);
n15.appendChild(n24);
_rootPage.appendChild(n0);

// Phase 3: Hydrate — text content, position, constraints
await new Promise(r => setTimeout(r, 0));

try { n1.x = 0; } catch (__e) { __errors.push({eid:"header-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n1.y = 0; } catch (__e) { __errors.push({eid:"header-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.x = 0; } catch (__e) { __errors.push({eid:"card-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.y = 50; } catch (__e) { __errors.push({eid:"card-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n3.x = 0; } catch (__e) { __errors.push({eid:"card-2", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n3.y = 100; } catch (__e) { __errors.push({eid:"card-2", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n4.x = 0; } catch (__e) { __errors.push({eid:"card-3", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n4.y = 150; } catch (__e) { __errors.push({eid:"card-3", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n5.x = 0; } catch (__e) { __errors.push({eid:"card-4", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n5.y = 200; } catch (__e) { __errors.push({eid:"card-4", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n6.x = 0; } catch (__e) { __errors.push({eid:"fab-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n6.y = 250; } catch (__e) { __errors.push({eid:"fab-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;