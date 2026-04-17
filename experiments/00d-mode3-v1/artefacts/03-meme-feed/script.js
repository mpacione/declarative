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
n2.name = "list-1";
n2.layoutMode = "VERTICAL";
n2.fills = [];
n2.clipsContent = false;
M["list-1"] = n2.id;

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
n6.name = "image-1";
n6.fills = [];
n6.clipsContent = false;
M["image-1"] = n6.id;

const n7 = figma.createFrame();
n7.name = "button_group-1";
n7.layoutMode = "VERTICAL";
n7.fills = [];
n7.clipsContent = false;
M["button_group-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "image-2";
n8.fills = [];
n8.clipsContent = false;
M["image-2"] = n8.id;

const n9 = figma.createFrame();
n9.name = "button_group-2";
n9.layoutMode = "VERTICAL";
n9.fills = [];
n9.clipsContent = false;
M["button_group-2"] = n9.id;

const n10 = figma.createFrame();
n10.name = "image-3";
n10.fills = [];
n10.clipsContent = false;
M["image-3"] = n10.id;

const n11 = figma.createFrame();
n11.name = "button_group-3";
n11.layoutMode = "VERTICAL";
n11.fills = [];
n11.clipsContent = false;
M["button_group-3"] = n11.id;

const n12 = figma.createFrame();
n12.name = "button-1";
n12.layoutMode = "VERTICAL";
n12.itemSpacing = 8;
n12.resize(n12.width, 44);
n12.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n12.cornerRadius = 8;
n12.clipsContent = false;
M["button-1"] = n12.id;

const n13 = figma.createFrame();
n13.name = "button-2";
n13.layoutMode = "VERTICAL";
n13.itemSpacing = 8;
n13.resize(n13.width, 44);
n13.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n13.cornerRadius = 8;
n13.clipsContent = false;
M["button-2"] = n13.id;

const n14 = figma.createFrame();
n14.name = "button-3";
n14.layoutMode = "VERTICAL";
n14.itemSpacing = 8;
n14.resize(n14.width, 44);
n14.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n14.cornerRadius = 8;
n14.clipsContent = false;
M["button-3"] = n14.id;

const n15 = figma.createFrame();
n15.name = "button-4";
n15.layoutMode = "VERTICAL";
n15.itemSpacing = 8;
n15.resize(n15.width, 44);
n15.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n15.cornerRadius = 8;
n15.clipsContent = false;
M["button-4"] = n15.id;

const n16 = figma.createFrame();
n16.name = "button-5";
n16.layoutMode = "VERTICAL";
n16.itemSpacing = 8;
n16.resize(n16.width, 44);
n16.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n16.cornerRadius = 8;
n16.clipsContent = false;
M["button-5"] = n16.id;

const n17 = figma.createFrame();
n17.name = "button-6";
n17.layoutMode = "VERTICAL";
n17.itemSpacing = 8;
n17.resize(n17.width, 44);
n17.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n17.cornerRadius = 8;
n17.clipsContent = false;
M["button-6"] = n17.id;

const n18 = figma.createText();
n18.name = "text-1";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n18.id;

const n19 = figma.createText();
n19.name = "text-2";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n19.id;

const n20 = figma.createText();
n20.name = "text-3";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n20.id;

const n21 = figma.createText();
n21.name = "text-4";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n21.id;

const n22 = figma.createText();
n22.name = "text-5";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n22.id;

const n23 = figma.createText();
n23.name = "text-6";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n23.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n2.appendChild(n3);
n3.layoutSizingHorizontal = "FILL";
n2.appendChild(n4);
n4.layoutSizingHorizontal = "FILL";
n2.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n3.appendChild(n6);
n3.appendChild(n7);
n4.appendChild(n8);
n4.appendChild(n9);
n5.appendChild(n10);
n5.appendChild(n11);
n7.appendChild(n12);
n12.layoutSizingHorizontal = "HUG";
n12.layoutSizingVertical = "FIXED";
n7.appendChild(n13);
n13.layoutSizingHorizontal = "HUG";
n13.layoutSizingVertical = "FIXED";
n9.appendChild(n14);
n14.layoutSizingHorizontal = "HUG";
n14.layoutSizingVertical = "FIXED";
n9.appendChild(n15);
n15.layoutSizingHorizontal = "HUG";
n15.layoutSizingVertical = "FIXED";
n11.appendChild(n16);
n16.layoutSizingHorizontal = "HUG";
n16.layoutSizingVertical = "FIXED";
n11.appendChild(n17);
n17.layoutSizingHorizontal = "HUG";
n17.layoutSizingVertical = "FIXED";
n12.appendChild(n18);
try { n18.characters = "👍 Upvote"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n13.appendChild(n19);
try { n19.characters = "Share"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n14.appendChild(n20);
try { n20.characters = "👍 Upvote"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n15.appendChild(n21);
try { n21.characters = "Share"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n16.appendChild(n22);
try { n22.characters = "👍 Upvote"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n17.appendChild(n23);
try { n23.characters = "Share"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;