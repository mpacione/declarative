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
n4.name = "card-5";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["card-5"] = n4.id;

const n5 = figma.createFrame();
n5.name = "image-1";
n5.fills = [];
n5.clipsContent = false;
M["image-1"] = n5.id;

const n6 = figma.createText();
n6.name = "heading-1";
try { n6.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n6.id;

const n7 = figma.createText();
n7.name = "text-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "card-2";
n8.layoutMode = "VERTICAL";
n8.fills = [];
n8.clipsContent = false;
M["card-2"] = n8.id;

const n9 = figma.createFrame();
n9.name = "card-3";
n9.layoutMode = "VERTICAL";
n9.fills = [];
n9.clipsContent = false;
M["card-3"] = n9.id;

const n10 = figma.createFrame();
n10.name = "card-4";
n10.layoutMode = "VERTICAL";
n10.fills = [];
n10.clipsContent = false;
M["card-4"] = n10.id;

const n11 = figma.createText();
n11.name = "heading-5";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-5"] = n11.id;

const n12 = figma.createFrame();
n12.name = "button-1";
n12.layoutMode = "VERTICAL";
n12.itemSpacing = 8;
n12.resize(n12.width, 44);
n12.primaryAxisAlignItems = "CENTER";
n12.counterAxisAlignItems = "CENTER";
n12.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n12.cornerRadius = 8;
n12.clipsContent = false;
M["button-1"] = n12.id;

const n13 = figma.createFrame();
n13.name = "icon-1";
n13.layoutMode = "VERTICAL";
n13.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n13.cornerRadius = 4;
n13.clipsContent = false;
M["icon-1"] = n13.id;

const n14 = figma.createText();
n14.name = "heading-2";
try { n14.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n14.id;

const n15 = figma.createText();
n15.name = "text-2";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n15.id;

const n16 = figma.createFrame();
n16.name = "icon-2";
n16.layoutMode = "VERTICAL";
n16.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n16.cornerRadius = 4;
n16.clipsContent = false;
M["icon-2"] = n16.id;

const n17 = figma.createText();
n17.name = "heading-3";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n17.id;

const n18 = figma.createText();
n18.name = "text-3";
try { n18.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n18.id;

const n19 = figma.createFrame();
n19.name = "icon-3";
n19.layoutMode = "VERTICAL";
n19.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
n19.cornerRadius = 4;
n19.clipsContent = false;
M["icon-3"] = n19.id;

const n20 = figma.createText();
n20.name = "heading-4";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-4"] = n20.id;

const n21 = figma.createText();
n21.name = "text-4";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n21.id;

const n22 = figma.createText();
n22.name = "text-5";
n22.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n22.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.fontSize = 14;
M["text-5"] = n22.id;


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
n2.appendChild(n5);
n2.appendChild(n6);
try { n6.characters = "Discover Something Cool"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n6.layoutSizingHorizontal = "FILL";
n2.appendChild(n7);
try { n7.characters = "Experience cutting-edge technology and design that transforms your world."; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n3.appendChild(n8);
n8.layoutSizingHorizontal = "FILL";
n3.appendChild(n9);
n9.layoutSizingHorizontal = "FILL";
n3.appendChild(n10);
n10.layoutSizingHorizontal = "FILL";
n4.appendChild(n11);
try { n11.characters = "Ready to Get Started?"; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n4.appendChild(n12);
n12.layoutSizingHorizontal = "HUG";
n12.layoutSizingVertical = "FIXED";
n8.appendChild(n13);
n13.layoutSizingHorizontal = "FIXED";
n13.layoutSizingVertical = "FIXED";
n8.appendChild(n14);
try { n14.characters = "Lightning Fast"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n14.layoutSizingHorizontal = "FILL";
n8.appendChild(n15);
try { n15.characters = "Blazing fast performance that keeps up with your pace."; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n9.appendChild(n16);
n16.layoutSizingHorizontal = "FIXED";
n16.layoutSizingVertical = "FIXED";
n9.appendChild(n17);
try { n17.characters = "Secure & Reliable"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n9.appendChild(n18);
try { n18.characters = "Enterprise-grade security with 99.9% uptime guarantee."; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n18.layoutSizingHorizontal = "FILL";
n10.appendChild(n19);
n19.layoutSizingHorizontal = "FIXED";
n19.layoutSizingVertical = "FIXED";
n10.appendChild(n20);
try { n20.characters = "Beautifully Designed"; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n10.appendChild(n21);
try { n21.characters = "Stunning UI that delights users and drives engagement."; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n12.appendChild(n22);
try { n22.characters = "Explore Now"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;