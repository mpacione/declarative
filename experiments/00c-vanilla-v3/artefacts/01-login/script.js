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

const n1 = figma.createText();
n1.name = "heading-1";
try { n1.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n1.id;

const n2 = figma.createFrame();
n2.name = "card-1";
n2.layoutMode = "VERTICAL";
n2.fills = [];
n2.clipsContent = false;
M["card-1"] = n2.id;

const n3 = figma.createText();
n3.name = "link-1";
try { n3.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"link-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["link-1"] = n3.id;

const n4 = figma.createText();
n4.name = "text-1";
try { n4.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "text_input-1";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["text_input-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "text_input-2";
n6.layoutMode = "VERTICAL";
n6.fills = [];
n6.clipsContent = false;
M["text_input-2"] = n6.id;

const n7 = figma.createFrame();
n7.name = "button-1";
n7.layoutMode = "VERTICAL";
n7.fills = [];
n7.clipsContent = false;
M["button-1"] = n7.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
try { n1.characters = "Sign In"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n0.appendChild(n2);
n0.appendChild(n3);
try { n3.characters = "Forgot password?"; } catch (__e) { __errors.push({eid:"link-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n0.appendChild(n4);
try { n4.characters = "Don't have an account? Sign up"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n2.appendChild(n5);
n2.appendChild(n6);
n2.appendChild(n7);
_rootPage.appendChild(n0);

// Phase 3: Hydrate — text content, position, constraints
await new Promise(r => setTimeout(r, 0));

try { n1.x = 0; } catch (__e) { __errors.push({eid:"heading-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n1.y = 0; } catch (__e) { __errors.push({eid:"heading-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.x = 0; } catch (__e) { __errors.push({eid:"card-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n2.y = 50; } catch (__e) { __errors.push({eid:"card-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n3.x = 0; } catch (__e) { __errors.push({eid:"link-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n3.y = 100; } catch (__e) { __errors.push({eid:"link-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n4.x = 0; } catch (__e) { __errors.push({eid:"text-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
try { n4.y = 150; } catch (__e) { __errors.push({eid:"text-1", kind:"position_failed", error: String(__e && __e.message || __e)}); }
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;