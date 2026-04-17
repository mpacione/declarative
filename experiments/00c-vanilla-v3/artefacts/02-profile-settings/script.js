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
n4.name = "button-1";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["button-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "avatar-1";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["avatar-1"] = n5.id;

const n6 = figma.createText();
n6.name = "heading-1";
try { n6.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n6.id;

const n7 = figma.createFrame();
n7.name = "text_input-1";
n7.layoutMode = "VERTICAL";
n7.fills = [];
n7.clipsContent = false;
M["text_input-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "text_input-2";
n8.layoutMode = "VERTICAL";
n8.fills = [];
n8.clipsContent = false;
M["text_input-2"] = n8.id;

const n9 = figma.createText();
n9.name = "heading-2";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n9.id;

const n10 = figma.createFrame();
n10.name = "toggle-1";
n10.layoutMode = "VERTICAL";
n10.fills = [];
n10.clipsContent = false;
M["toggle-1"] = n10.id;

const n11 = figma.createFrame();
n11.name = "toggle-2";
n11.layoutMode = "VERTICAL";
n11.fills = [];
n11.clipsContent = false;
M["toggle-2"] = n11.id;

const n12 = figma.createFrame();
n12.name = "toggle-3";
n12.layoutMode = "VERTICAL";
n12.fills = [];
n12.clipsContent = false;
M["toggle-3"] = n12.id;

const n13 = figma.createFrame();
n13.name = "toggle-4";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["toggle-4"] = n13.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n0.appendChild(n2);
n0.appendChild(n3);
n0.appendChild(n4);
n2.appendChild(n5);
n2.appendChild(n6);
try { n6.characters = "Profile Information"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n6.layoutSizingHorizontal = "FILL";
n2.appendChild(n7);
n2.appendChild(n8);
n3.appendChild(n9);
try { n9.characters = "Notifications"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n3.appendChild(n10);
n3.appendChild(n11);
n3.appendChild(n12);
n3.appendChild(n13);
_rootPage.appendChild(n0);

// Phase 3: Hydrate — text content, position, constraints
await new Promise(r => setTimeout(r, 0));

try { n1.x = 0; } catch (__e) { __errors.push({eid:"header-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n1.y = 0; } catch (__e) { __errors.push({eid:"header-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.x = 0; } catch (__e) { __errors.push({eid:"card-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.y = 50; } catch (__e) { __errors.push({eid:"card-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n3.x = 0; } catch (__e) { __errors.push({eid:"card-2", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n3.y = 100; } catch (__e) { __errors.push({eid:"card-2", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n4.x = 0; } catch (__e) { __errors.push({eid:"button-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n4.y = 150; } catch (__e) { __errors.push({eid:"button-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;