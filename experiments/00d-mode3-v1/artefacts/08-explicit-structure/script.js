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
n3.name = "button-2";
n3.layoutMode = "VERTICAL";
n3.itemSpacing = 8;
n3.resize(n3.width, 44);
n3.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n3.cornerRadius = 8;
n3.clipsContent = false;
M["button-2"] = n3.id;

const n4 = figma.createFrame();
n4.name = "icon_button-1";
n4.layoutMode = "VERTICAL";
n4.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n4.cornerRadius = 8;
n4.clipsContent = false;
M["icon_button-1"] = n4.id;

const n5 = figma.createText();
n5.name = "text-1";
try { n5.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "icon_button-2";
n6.layoutMode = "VERTICAL";
n6.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n6.cornerRadius = 8;
n6.clipsContent = false;
M["icon_button-2"] = n6.id;

const n7 = figma.createText();
n7.name = "heading-1";
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

const n10 = figma.createText();
n10.name = "text-4";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n10.id;

const n11 = figma.createFrame();
n11.name = "button-1";
n11.layoutMode = "VERTICAL";
n11.itemSpacing = 8;
n11.resize(n11.width, 44);
n11.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n11.cornerRadius = 8;
n11.clipsContent = false;
M["button-1"] = n11.id;

const n12 = figma.createText();
n12.name = "text-6";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n12.id;

const n13 = figma.createText();
n13.name = "text-5";
try { n13.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n13.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n0.appendChild(n3);
n3.layoutSizingHorizontal = "HUG";
n3.layoutSizingVertical = "FIXED";
n1.appendChild(n4);
n4.layoutSizingHorizontal = "FIXED";
n4.layoutSizingVertical = "FIXED";
n1.appendChild(n5);
try { n5.characters = "Title"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n5.layoutSizingHorizontal = "FILL";
n1.appendChild(n6);
n6.layoutSizingHorizontal = "FIXED";
n6.layoutSizingVertical = "FIXED";
n2.appendChild(n7);
try { n7.characters = "Heading"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n2.appendChild(n8);
try { n8.characters = "Line of body text"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n2.appendChild(n9);
try { n9.characters = "Line of body text"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n2.appendChild(n10);
try { n10.characters = "Line of body text"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n2.appendChild(n11);
n11.layoutSizingHorizontal = "HUG";
n11.layoutSizingVertical = "FIXED";
n3.appendChild(n12);
try { n12.characters = "Secondary Action"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n11.appendChild(n13);
try { n13.characters = "Primary Action"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n13.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;