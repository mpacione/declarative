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
n5.name = "button-1";
n5.layoutMode = "VERTICAL";
n5.itemSpacing = 8;
n5.resize(n5.width, 44);
n5.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n5.cornerRadius = 8;
n5.clipsContent = false;
M["button-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "avatar-1";
n6.layoutMode = "VERTICAL";
n6.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n6.cornerRadius = 8;
n6.clipsContent = false;
M["avatar-1"] = n6.id;

const n7 = figma.createText();
n7.name = "text-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n7.id;

const n8 = figma.createText();
n8.name = "heading-1";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n8.id;

const n9 = figma.createFrame();
n9.name = "text_input-1";
n9.layoutMode = "VERTICAL";
n9.itemSpacing = 6;
n9.resize(n9.width, 48);
n9.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n9.strokes = [{type: "SOLID", color: {r:0.7961,g:0.8353,b:0.8824}}];
n9.cornerRadius = 8;
n9.clipsContent = false;
M["text_input-1"] = n9.id;

const n10 = figma.createFrame();
n10.name = "text_input-2";
n10.layoutMode = "VERTICAL";
n10.itemSpacing = 6;
n10.resize(n10.width, 48);
n10.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n10.strokes = [{type: "SOLID", color: {r:0.7961,g:0.8353,b:0.8824}}];
n10.cornerRadius = 8;
n10.clipsContent = false;
M["text_input-2"] = n10.id;

const n11 = figma.createText();
n11.name = "heading-2";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n11.id;

const n12 = figma.createFrame();
n12.name = "toggle-1";
n12.layoutMode = "VERTICAL";
n12.itemSpacing = 8;
n12.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n12.cornerRadius = 999;
n12.clipsContent = false;
M["toggle-1"] = n12.id;

const n13 = figma.createFrame();
n13.name = "toggle-2";
n13.layoutMode = "VERTICAL";
n13.itemSpacing = 8;
n13.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n13.cornerRadius = 999;
n13.clipsContent = false;
M["toggle-2"] = n13.id;

const n14 = figma.createFrame();
n14.name = "toggle-3";
n14.layoutMode = "VERTICAL";
n14.itemSpacing = 8;
n14.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n14.cornerRadius = 999;
n14.clipsContent = false;
M["toggle-3"] = n14.id;

const n15 = figma.createText();
n15.name = "text-9";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n15.id;

const n16 = figma.createText();
n16.name = "text-2";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n16.id;

const n17 = figma.createText();
n17.name = "text-3";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n17.id;

const n18 = figma.createText();
n18.name = "text-4";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n18.id;

const n19 = figma.createText();
n19.name = "text-5";
try { n19.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n19.id;

const n20 = figma.createText();
n20.name = "text-6";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n20.id;

const n21 = figma.createText();
n21.name = "text-7";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n21.id;

const n22 = figma.createText();
n22.name = "text-8";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n22.id;


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
n5.layoutSizingHorizontal = "HUG";
n5.layoutSizingVertical = "FIXED";
n2.appendChild(n6);
n6.layoutSizingHorizontal = "HUG";
n6.layoutSizingVertical = "HUG";
n2.appendChild(n7);
try { n7.characters = "User avatar"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n3.appendChild(n8);
try { n8.characters = "Personal Information"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n3.appendChild(n9);
n9.layoutSizingHorizontal = "FILL";
n9.layoutSizingVertical = "HUG";
n3.appendChild(n10);
n10.layoutSizingHorizontal = "FILL";
n10.layoutSizingVertical = "HUG";
n4.appendChild(n11);
try { n11.characters = "Notifications"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n4.appendChild(n12);
n12.layoutSizingHorizontal = "HUG";
n12.layoutSizingVertical = "HUG";
n4.appendChild(n13);
n13.layoutSizingHorizontal = "HUG";
n13.layoutSizingVertical = "HUG";
n4.appendChild(n14);
n14.layoutSizingHorizontal = "HUG";
n14.layoutSizingVertical = "HUG";
n5.appendChild(n15);
try { n15.characters = "Save Changes"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n9.appendChild(n16);
try { n16.characters = "Name"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n9.appendChild(n17);
try { n17.characters = "Enter your name"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n10.appendChild(n18);
try { n18.characters = "Email"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n10.appendChild(n19);
try { n19.characters = "Enter your email"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n19.layoutSizingHorizontal = "FILL";
n12.appendChild(n20);
try { n20.characters = "Push notifications"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n13.appendChild(n21);
try { n21.characters = "Email notifications"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n14.appendChild(n22);
try { n22.characters = "SMS notifications"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;