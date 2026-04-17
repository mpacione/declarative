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
n3.name = "search_input-1";
n3.layoutMode = "VERTICAL";
n3.fills = [];
n3.clipsContent = false;
M["search_input-1"] = n3.id;

const n4 = figma.createFrame();
n4.name = "button_group-1";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["button_group-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "bottom_nav-1";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["bottom_nav-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "image-1";
n6.fills = [];
n6.clipsContent = false;
M["image-1"] = n6.id;

const n7 = figma.createText();
n7.name = "text-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n7.id;

const n8 = figma.createText();
n8.name = "heading-1";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n8.id;

const n9 = figma.createFrame();
n9.name = "list-1";
n9.layoutMode = "VERTICAL";
n9.fills = [];
n9.clipsContent = false;
M["list-1"] = n9.id;

const n10 = figma.createFrame();
n10.name = "button-1";
n10.layoutMode = "VERTICAL";
n10.fills = [];
n10.clipsContent = false;
M["button-1"] = n10.id;

const n11 = figma.createFrame();
n11.name = "button-2";
n11.layoutMode = "VERTICAL";
n11.fills = [];
n11.clipsContent = false;
M["button-2"] = n11.id;

const n12 = figma.createText();
n12.name = "text-5";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n12.id;

const n13 = figma.createText();
n13.name = "text-6";
try { n13.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n13.id;

const n14 = figma.createText();
n14.name = "text-7";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n14.id;

const n15 = figma.createText();
n15.name = "text-8";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n15.id;

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
n19.name = "avatar-1";
n19.layoutMode = "VERTICAL";
n19.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n19.cornerRadius = 8;
n19.clipsContent = false;
M["avatar-1"] = n19.id;

const n20 = figma.createText();
n20.name = "text-2";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n20.id;

const n21 = figma.createFrame();
n21.name = "avatar-2";
n21.layoutMode = "VERTICAL";
n21.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n21.cornerRadius = 8;
n21.clipsContent = false;
M["avatar-2"] = n21.id;

const n22 = figma.createText();
n22.name = "text-3";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n22.id;

const n23 = figma.createFrame();
n23.name = "avatar-3";
n23.layoutMode = "VERTICAL";
n23.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n23.cornerRadius = 8;
n23.clipsContent = false;
M["avatar-3"] = n23.id;

const n24 = figma.createText();
n24.name = "text-4";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n24.id;


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
try { n7.characters = "9:41"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n2.appendChild(n8);
try { n8.characters = "Messages"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n2.appendChild(n9);
n4.appendChild(n10);
n4.appendChild(n11);
n5.appendChild(n12);
try { n12.characters = "Messages"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n5.appendChild(n13);
try { n13.characters = "Calls"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n5.appendChild(n14);
try { n14.characters = "Contacts"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n5.appendChild(n15);
try { n15.characters = "Settings"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n9.appendChild(n16);
n9.appendChild(n17);
n9.appendChild(n18);
n16.appendChild(n19);
n19.layoutSizingHorizontal = "HUG";
n19.layoutSizingVertical = "HUG";
n16.appendChild(n20);
try { n20.characters = "Alex"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n17.appendChild(n21);
n21.layoutSizingHorizontal = "HUG";
n21.layoutSizingVertical = "HUG";
n17.appendChild(n22);
try { n22.characters = "Blake"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n18.appendChild(n23);
n23.layoutSizingHorizontal = "HUG";
n23.layoutSizingVertical = "HUG";
n18.appendChild(n24);
try { n24.characters = "Casey"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;