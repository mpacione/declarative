const __errors = [];
await (async () => { try { await figma.loadFontAsync({family: "Inter", style: "Regular"}); } catch (__e) { __errors.push({kind:"font_load_failed", family:"Inter", style:"Regular", error: String(__e && __e.message || __e)}); } })();
const M = {};
const _rootPage = figma.currentPage;


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
n2.name = "drawer-1";
n2.layoutMode = "VERTICAL";
n2.fills = [];
n2.clipsContent = false;
M["drawer-1"] = n2.id;

const n3 = figma.createFrame();
n3.name = "navigation_row-1";
n3.layoutMode = "VERTICAL";
n3.fills = [];
n3.clipsContent = false;
M["navigation_row-1"] = n3.id;

const n4 = figma.createFrame();
n4.name = "navigation_row-2";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["navigation_row-2"] = n4.id;

const n5 = figma.createFrame();
n5.name = "navigation_row-3";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["navigation_row-3"] = n5.id;

const n6 = figma.createFrame();
n6.name = "navigation_row-4";
n6.layoutMode = "VERTICAL";
n6.fills = [];
n6.clipsContent = false;
M["navigation_row-4"] = n6.id;

const n7 = figma.createFrame();
n7.name = "navigation_row-5";
n7.layoutMode = "VERTICAL";
n7.fills = [];
n7.clipsContent = false;
M["navigation_row-5"] = n7.id;

const n8 = figma.createFrame();
n8.name = "navigation_row-6";
n8.layoutMode = "VERTICAL";
n8.fills = [];
n8.clipsContent = false;
M["navigation_row-6"] = n8.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n0.appendChild(n2);
n2.appendChild(n3);
n2.appendChild(n4);
n2.appendChild(n5);
n2.appendChild(n6);
n2.appendChild(n7);
n2.appendChild(n8);
_rootPage.appendChild(n0);

// Phase 3: Hydrate — text content, position, constraints
await new Promise(r => setTimeout(r, 0));

try { n1.x = 0; } catch (__e) { __errors.push({eid:"header-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n1.y = 0; } catch (__e) { __errors.push({eid:"header-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.x = 0; } catch (__e) { __errors.push({eid:"drawer-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.y = 50; } catch (__e) { __errors.push({eid:"drawer-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
M["__errors"] = __errors;
return M;