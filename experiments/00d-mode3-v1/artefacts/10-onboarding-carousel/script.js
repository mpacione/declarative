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
n1.name = "card-1";
n1.layoutMode = "VERTICAL";
n1.fills = [];
n1.clipsContent = false;
M["card-1"] = n1.id;

const n2 = figma.createFrame();
n2.name = "card-2";
n2.layoutMode = "VERTICAL";
n2.fills = [];
n2.clipsContent = false;
M["card-2"] = n2.id;

const n3 = figma.createFrame();
n3.name = "card-3";
n3.layoutMode = "VERTICAL";
n3.fills = [];
n3.clipsContent = false;
M["card-3"] = n3.id;

const n4 = figma.createFrame();
n4.name = "pagination-1";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["pagination-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "button_group-1";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["button_group-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "image-1";
n6.fills = [];
n6.clipsContent = false;
M["image-1"] = n6.id;

const n7 = figma.createText();
n7.name = "heading-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n7.id;

const n8 = figma.createText();
n8.name = "text-1";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n8.id;

const n9 = figma.createFrame();
n9.name = "image-2";
n9.fills = [];
n9.clipsContent = false;
M["image-2"] = n9.id;

const n10 = figma.createText();
n10.name = "heading-2";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n10.id;

const n11 = figma.createText();
n11.name = "text-2";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n11.id;

const n12 = figma.createFrame();
n12.name = "image-3";
n12.fills = [];
n12.clipsContent = false;
M["image-3"] = n12.id;

const n13 = figma.createText();
n13.name = "heading-3";
try { n13.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n13.id;

const n14 = figma.createText();
n14.name = "text-3";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n14.id;

const n15 = figma.createFrame();
n15.name = "button-1";
n15.layoutMode = "VERTICAL";
n15.itemSpacing = 8;
n15.resize(n15.width, 44);
n15.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n15.cornerRadius = 8;
n15.clipsContent = false;
M["button-1"] = n15.id;

const n16 = figma.createFrame();
n16.name = "button-2";
n16.layoutMode = "VERTICAL";
n16.itemSpacing = 8;
n16.resize(n16.width, 44);
n16.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n16.cornerRadius = 8;
n16.clipsContent = false;
M["button-2"] = n16.id;

const n17 = figma.createFrame();
n17.name = "button-3";
n17.layoutMode = "VERTICAL";
n17.itemSpacing = 8;
n17.resize(n17.width, 44);
n17.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n17.cornerRadius = 8;
n17.clipsContent = false;
M["button-3"] = n17.id;

const n18 = figma.createFrame();
n18.name = "button-4";
n18.layoutMode = "VERTICAL";
n18.itemSpacing = 8;
n18.resize(n18.width, 44);
n18.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n18.cornerRadius = 8;
n18.clipsContent = false;
M["button-4"] = n18.id;

const n19 = figma.createFrame();
n19.name = "button-5";
n19.layoutMode = "VERTICAL";
n19.itemSpacing = 8;
n19.resize(n19.width, 44);
n19.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n19.cornerRadius = 8;
n19.clipsContent = false;
M["button-5"] = n19.id;

const n20 = figma.createText();
n20.name = "text-4";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n20.id;

const n21 = figma.createText();
n21.name = "text-5";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n21.id;

const n22 = figma.createText();
n22.name = "text-6";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n22.id;

const n23 = figma.createText();
n23.name = "text-7";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n23.id;

const n24 = figma.createText();
n24.name = "text-8";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n24.id;


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
n1.appendChild(n6);
n1.appendChild(n7);
try { n7.characters = "Welcome to Our App"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n1.appendChild(n8);
try { n8.characters = "Discover amazing features designed to make your life easier"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n2.appendChild(n9);
n2.appendChild(n10);
try { n10.characters = "Powerful Features"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n2.appendChild(n11);
try { n11.characters = "Access everything you need in one intuitive interface"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n3.appendChild(n12);
n3.appendChild(n13);
try { n13.characters = "Get Started Now"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n3.appendChild(n14);
try { n14.characters = "Join thousands of users enjoying seamless productivity"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n4.appendChild(n15);
n15.layoutSizingHorizontal = "HUG";
n15.layoutSizingVertical = "FIXED";
n4.appendChild(n16);
n16.layoutSizingHorizontal = "HUG";
n16.layoutSizingVertical = "FIXED";
n4.appendChild(n17);
n17.layoutSizingHorizontal = "HUG";
n17.layoutSizingVertical = "FIXED";
n5.appendChild(n18);
n18.layoutSizingHorizontal = "HUG";
n18.layoutSizingVertical = "FIXED";
n5.appendChild(n19);
n19.layoutSizingHorizontal = "HUG";
n19.layoutSizingVertical = "FIXED";
n15.appendChild(n20);
try { n20.characters = "1"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n16.appendChild(n21);
try { n21.characters = "2"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n17.appendChild(n22);
try { n22.characters = "3"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n18.appendChild(n23);
try { n23.characters = "Back"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n19.appendChild(n24);
try { n24.characters = "Next"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;