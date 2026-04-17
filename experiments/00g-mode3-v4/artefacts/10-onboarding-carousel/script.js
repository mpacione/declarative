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
n2.itemSpacing = 12;
n2.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n2.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n2.cornerRadius = 12;
n2.clipsContent = false;
M["card-1"] = n2.id;

const n3 = figma.createFrame();
n3.name = "card-2";
n3.layoutMode = "VERTICAL";
n3.itemSpacing = 12;
n3.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n3.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n3.cornerRadius = 12;
n3.clipsContent = false;
M["card-2"] = n3.id;

const n4 = figma.createFrame();
n4.name = "card-3";
n4.layoutMode = "VERTICAL";
n4.itemSpacing = 12;
n4.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n4.strokes = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n4.cornerRadius = 12;
n4.clipsContent = false;
M["card-3"] = n4.id;

const n5 = figma.createFrame();
n5.name = "pagination-1";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["pagination-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "button-4";
n6.layoutMode = "VERTICAL";
n6.itemSpacing = 8;
n6.resize(n6.width, 44);
n6.primaryAxisAlignItems = "CENTER";
n6.counterAxisAlignItems = "CENTER";
n6.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n6.cornerRadius = 8;
n6.clipsContent = false;
M["button-4"] = n6.id;

const n7 = figma.createText();
n7.name = "link-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"link-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["link-1"] = n7.id;

const n8 = figma.createText();
n8.name = "text-1";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n8.id;

const n9 = figma.createFrame();
n9.name = "image-1";
n9.fills = [];
n9.clipsContent = false;
M["image-1"] = n9.id;

const n10 = figma.createText();
n10.name = "heading-1";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n10.id;

const n11 = figma.createText();
n11.name = "text-2";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n11.id;

const n12 = figma.createFrame();
n12.name = "image-2";
n12.fills = [];
n12.clipsContent = false;
M["image-2"] = n12.id;

const n13 = figma.createText();
n13.name = "heading-2";
try { n13.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n13.id;

const n14 = figma.createText();
n14.name = "text-3";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n14.id;

const n15 = figma.createFrame();
n15.name = "image-3";
n15.fills = [];
n15.clipsContent = false;
M["image-3"] = n15.id;

const n16 = figma.createText();
n16.name = "heading-3";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n16.id;

const n17 = figma.createText();
n17.name = "text-4";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n17.id;

const n18 = figma.createFrame();
n18.name = "button-1";
n18.layoutMode = "VERTICAL";
n18.itemSpacing = 8;
n18.resize(n18.width, 44);
n18.primaryAxisAlignItems = "CENTER";
n18.counterAxisAlignItems = "CENTER";
n18.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n18.cornerRadius = 8;
n18.clipsContent = false;
M["button-1"] = n18.id;

const n19 = figma.createFrame();
n19.name = "button-2";
n19.layoutMode = "VERTICAL";
n19.itemSpacing = 8;
n19.resize(n19.width, 44);
n19.primaryAxisAlignItems = "CENTER";
n19.counterAxisAlignItems = "CENTER";
n19.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n19.cornerRadius = 8;
n19.clipsContent = false;
M["button-2"] = n19.id;

const n20 = figma.createFrame();
n20.name = "button-3";
n20.layoutMode = "VERTICAL";
n20.itemSpacing = 8;
n20.resize(n20.width, 44);
n20.primaryAxisAlignItems = "CENTER";
n20.counterAxisAlignItems = "CENTER";
n20.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n20.cornerRadius = 8;
n20.clipsContent = false;
M["button-3"] = n20.id;

const n21 = figma.createText();
n21.name = "text-8";
n21.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
try { n21.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.fontSize = 14;
M["text-8"] = n21.id;

const n22 = figma.createText();
n22.name = "text-9";
n22.fills = [{type: "SOLID", color: {r:0.1451,g:0.3882,b:0.9216}}];
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.fontSize = 14;
M["text-9"] = n22.id;

const n23 = figma.createText();
n23.name = "text-5";
n23.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n23.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.fontSize = 14;
M["text-5"] = n23.id;

const n24 = figma.createText();
n24.name = "text-6";
n24.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n24.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.fontSize = 14;
M["text-6"] = n24.id;

const n25 = figma.createText();
n25.name = "text-7";
n25.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n25.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.fontSize = 14;
M["text-7"] = n25.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n2.layoutSizingVertical = "HUG";
n0.appendChild(n3);
n3.layoutSizingHorizontal = "FILL";
n3.layoutSizingVertical = "HUG";
n0.appendChild(n4);
n4.layoutSizingHorizontal = "FILL";
n4.layoutSizingVertical = "HUG";
n0.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n0.appendChild(n6);
n6.layoutSizingHorizontal = "HUG";
n6.layoutSizingVertical = "FIXED";
n0.appendChild(n7);
try { n7.characters = "Skip"; } catch (__e) { __errors.push({eid:"link-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "HUG";
n7.layoutSizingVertical = "HUG";
n1.appendChild(n8);
n8.layoutSizingHorizontal = "FILL";
n2.appendChild(n9);
n2.appendChild(n10);
try { n10.characters = "Welcome to Your Journey"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n2.appendChild(n11);
try { n11.characters = "Discover amazing features designed to enhance your experience"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n3.appendChild(n12);
n3.appendChild(n13);
try { n13.characters = "Stay Connected"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
n3.appendChild(n14);
try { n14.characters = "Keep up with everything that matters to you in one place"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n4.appendChild(n15);
n4.appendChild(n16);
try { n16.characters = "Get Started Now"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n4.appendChild(n17);
try { n17.characters = "Create your account and unlock all the possibilities"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n5.appendChild(n18);
n18.layoutSizingHorizontal = "HUG";
n18.layoutSizingVertical = "FIXED";
n5.appendChild(n19);
n19.layoutSizingHorizontal = "HUG";
n19.layoutSizingVertical = "FIXED";
n5.appendChild(n20);
n20.layoutSizingHorizontal = "HUG";
n20.layoutSizingVertical = "FIXED";
n6.appendChild(n21);
try { n21.characters = "Next"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n7.appendChild(n22);
try { n22.characters = "Skip"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n18.appendChild(n23);
try { n23.characters = "1"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n19.appendChild(n24);
try { n24.characters = "2"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n20.appendChild(n25);
try { n25.characters = "3"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;