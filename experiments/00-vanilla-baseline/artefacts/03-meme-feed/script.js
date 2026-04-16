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
n5.name = "image-1";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["image-1"] = n5.id;

const n6 = figma.createText();
n6.name = "text-1";
n6.layoutMode = "VERTICAL";
try { n6.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n6.id;

const n7 = figma.createFrame();
n7.name = "button_group-1";
n7.layoutMode = "VERTICAL";
n7.fills = [];
n7.clipsContent = false;
M["button_group-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "image-2";
n8.layoutMode = "VERTICAL";
n8.fills = [];
n8.clipsContent = false;
M["image-2"] = n8.id;

const n9 = figma.createText();
n9.name = "text-2";
n9.layoutMode = "VERTICAL";
try { n9.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n9.id;

const n10 = figma.createFrame();
n10.name = "button_group-2";
n10.layoutMode = "VERTICAL";
n10.fills = [];
n10.clipsContent = false;
M["button_group-2"] = n10.id;

const n11 = figma.createFrame();
n11.name = "image-3";
n11.layoutMode = "VERTICAL";
n11.fills = [];
n11.clipsContent = false;
M["image-3"] = n11.id;

const n12 = figma.createText();
n12.name = "text-3";
n12.layoutMode = "VERTICAL";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n12.id;

const n13 = figma.createFrame();
n13.name = "button_group-3";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["button_group-3"] = n13.id;

const n14 = figma.createFrame();
n14.name = "icon_button-1";
n14.layoutMode = "VERTICAL";
n14.fills = [];
n14.clipsContent = false;
M["icon_button-1"] = n14.id;

const n15 = figma.createFrame();
n15.name = "icon_button-2";
n15.layoutMode = "VERTICAL";
n15.fills = [];
n15.clipsContent = false;
M["icon_button-2"] = n15.id;

const n16 = figma.createFrame();
n16.name = "icon_button-3";
n16.layoutMode = "VERTICAL";
n16.fills = [];
n16.clipsContent = false;
M["icon_button-3"] = n16.id;

const n17 = figma.createFrame();
n17.name = "icon_button-4";
n17.layoutMode = "VERTICAL";
n17.fills = [];
n17.clipsContent = false;
M["icon_button-4"] = n17.id;

const n18 = figma.createFrame();
n18.name = "icon_button-5";
n18.layoutMode = "VERTICAL";
n18.fills = [];
n18.clipsContent = false;
M["icon_button-5"] = n18.id;

const n19 = figma.createFrame();
n19.name = "icon_button-6";
n19.layoutMode = "VERTICAL";
n19.fills = [];
n19.clipsContent = false;
M["icon_button-6"] = n19.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n0.appendChild(n2);
n0.appendChild(n3);
n0.appendChild(n4);
n2.appendChild(n5);
n2.appendChild(n6);
try { n6.characters = "Funny caption here"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n6.layoutSizingHorizontal = "FILL";
n2.appendChild(n7);
n3.appendChild(n8);
n3.appendChild(n9);
try { n9.characters = "Another caption"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n9.layoutSizingHorizontal = "FILL";
n3.appendChild(n10);
n4.appendChild(n11);
n4.appendChild(n12);
try { n12.characters = "Third caption"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n4.appendChild(n13);
n7.appendChild(n14);
n7.appendChild(n15);
n10.appendChild(n16);
n10.appendChild(n17);
n13.appendChild(n18);
n13.appendChild(n19);
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
M["__errors"] = __errors;
return M;