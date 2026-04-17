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

const n2 = figma.createText();
n2.name = "text-1";
try { n2.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n2.id;

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
n6.name = "card-4";
n6.layoutMode = "VERTICAL";
n6.fills = [];
n6.clipsContent = false;
M["card-4"] = n6.id;

const n7 = figma.createText();
n7.name = "heading-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-1"] = n7.id;

const n8 = figma.createText();
n8.name = "text-2";
try { n8.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-2"] = n8.id;

const n9 = figma.createFrame();
n9.name = "list-1";
n9.layoutMode = "VERTICAL";
n9.fills = [];
n9.clipsContent = false;
M["list-1"] = n9.id;

const n10 = figma.createFrame();
n10.name = "button-1";
n10.layoutMode = "VERTICAL";
n10.fills = [];
n10.clipsContent = false;
M["button-1"] = n10.id;

const n11 = figma.createText();
n11.name = "heading-2";
try { n11.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n11.id;

const n12 = figma.createText();
n12.name = "text-6";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n12.id;

const n13 = figma.createFrame();
n13.name = "badge-1";
n13.layoutMode = "VERTICAL";
n13.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n13.cornerRadius = 8;
n13.clipsContent = false;
M["badge-1"] = n13.id;

const n14 = figma.createFrame();
n14.name = "list-2";
n14.layoutMode = "VERTICAL";
n14.fills = [];
n14.clipsContent = false;
M["list-2"] = n14.id;

const n15 = figma.createFrame();
n15.name = "button-2";
n15.layoutMode = "VERTICAL";
n15.fills = [];
n15.clipsContent = false;
M["button-2"] = n15.id;

const n16 = figma.createText();
n16.name = "heading-3";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n16.id;

const n17 = figma.createText();
n17.name = "text-11";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-11"] = n17.id;

const n18 = figma.createFrame();
n18.name = "list-3";
n18.layoutMode = "VERTICAL";
n18.fills = [];
n18.clipsContent = false;
M["list-3"] = n18.id;

const n19 = figma.createFrame();
n19.name = "button-3";
n19.layoutMode = "VERTICAL";
n19.fills = [];
n19.clipsContent = false;
M["button-3"] = n19.id;

const n20 = figma.createText();
n20.name = "heading-4";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-4"] = n20.id;

const n21 = figma.createText();
n21.name = "text-15";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-15"] = n21.id;

const n22 = figma.createText();
n22.name = "text-16";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-16"] = n22.id;

const n23 = figma.createFrame();
n23.name = "avatar-1";
n23.layoutMode = "VERTICAL";
n23.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n23.cornerRadius = 8;
n23.clipsContent = false;
M["avatar-1"] = n23.id;

const n24 = figma.createFrame();
n24.name = "list_item-1";
n24.layoutMode = "VERTICAL";
n24.fills = [];
n24.clipsContent = false;
M["list_item-1"] = n24.id;

const n25 = figma.createFrame();
n25.name = "list_item-2";
n25.layoutMode = "VERTICAL";
n25.fills = [];
n25.clipsContent = false;
M["list_item-2"] = n25.id;

const n26 = figma.createFrame();
n26.name = "list_item-3";
n26.layoutMode = "VERTICAL";
n26.fills = [];
n26.clipsContent = false;
M["list_item-3"] = n26.id;

const n27 = figma.createText();
n27.name = "text-7";
try { n27.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-7"] = n27.id;

const n28 = figma.createFrame();
n28.name = "list_item-4";
n28.layoutMode = "VERTICAL";
n28.fills = [];
n28.clipsContent = false;
M["list_item-4"] = n28.id;

const n29 = figma.createFrame();
n29.name = "list_item-5";
n29.layoutMode = "VERTICAL";
n29.fills = [];
n29.clipsContent = false;
M["list_item-5"] = n29.id;

const n30 = figma.createFrame();
n30.name = "list_item-6";
n30.layoutMode = "VERTICAL";
n30.fills = [];
n30.clipsContent = false;
M["list_item-6"] = n30.id;

const n31 = figma.createFrame();
n31.name = "list_item-7";
n31.layoutMode = "VERTICAL";
n31.fills = [];
n31.clipsContent = false;
M["list_item-7"] = n31.id;

const n32 = figma.createFrame();
n32.name = "list_item-8";
n32.layoutMode = "VERTICAL";
n32.fills = [];
n32.clipsContent = false;
M["list_item-8"] = n32.id;

const n33 = figma.createFrame();
n33.name = "list_item-9";
n33.layoutMode = "VERTICAL";
n33.fills = [];
n33.clipsContent = false;
M["list_item-9"] = n33.id;

const n34 = figma.createText();
n34.name = "text-3";
try { n34.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n34.id;

const n35 = figma.createText();
n35.name = "text-4";
try { n35.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n35.id;

const n36 = figma.createText();
n36.name = "text-5";
try { n36.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n36.id;

const n37 = figma.createText();
n37.name = "text-8";
try { n37.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n37.id;

const n38 = figma.createText();
n38.name = "text-9";
try { n38.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n38.id;

const n39 = figma.createText();
n39.name = "text-10";
try { n39.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-10"] = n39.id;

const n40 = figma.createText();
n40.name = "text-12";
try { n40.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-12"] = n40.id;

const n41 = figma.createText();
n41.name = "text-13";
try { n41.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-13"] = n41.id;

const n42 = figma.createText();
n42.name = "text-14";
try { n42.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-14"] = n42.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
try { n2.characters = "Select the perfect plan for your needs"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n2.layoutSizingHorizontal = "FILL";
n0.appendChild(n3);
n3.layoutSizingHorizontal = "FILL";
n0.appendChild(n4);
n4.layoutSizingHorizontal = "FILL";
n0.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n0.appendChild(n6);
n6.layoutSizingHorizontal = "FILL";
n3.appendChild(n7);
try { n7.characters = "Starter"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n3.appendChild(n8);
try { n8.characters = "$9/month"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n8.layoutSizingHorizontal = "FILL";
n3.appendChild(n9);
n3.appendChild(n10);
n4.appendChild(n11);
try { n11.characters = "Professional"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n4.appendChild(n12);
try { n12.characters = "$29/month"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n4.appendChild(n13);
n13.layoutSizingHorizontal = "HUG";
n13.layoutSizingVertical = "HUG";
n4.appendChild(n14);
n4.appendChild(n15);
n5.appendChild(n16);
try { n16.characters = "Enterprise"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n5.appendChild(n17);
try { n17.characters = "Custom pricing"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n5.appendChild(n18);
n5.appendChild(n19);
n6.appendChild(n20);
try { n20.characters = "What customers say"; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n6.appendChild(n21);
try { n21.characters = "\"This service transformed how we work. Highly recommended!\""; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "FILL";
n6.appendChild(n22);
try { n22.characters = "— Sarah Chen, Product Manager"; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n6.appendChild(n23);
n23.layoutSizingHorizontal = "HUG";
n23.layoutSizingVertical = "HUG";
n9.appendChild(n24);
n9.appendChild(n25);
n9.appendChild(n26);
n13.appendChild(n27);
try { n27.characters = "Most Popular"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n27.layoutSizingHorizontal = "FILL";
n14.appendChild(n28);
n14.appendChild(n29);
n14.appendChild(n30);
n18.appendChild(n31);
n18.appendChild(n32);
n18.appendChild(n33);
n24.appendChild(n34);
try { n34.characters = "5 projects"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.layoutSizingHorizontal = "FILL";
n25.appendChild(n35);
try { n35.characters = "Basic support"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n26.appendChild(n36);
try { n36.characters = "1 GB storage"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.layoutSizingHorizontal = "FILL";
n28.appendChild(n37);
try { n37.characters = "Unlimited projects"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n37.layoutSizingHorizontal = "FILL";
n29.appendChild(n38);
try { n38.characters = "Priority support"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.layoutSizingHorizontal = "FILL";
n30.appendChild(n39);
try { n39.characters = "100 GB storage"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n39.layoutSizingHorizontal = "FILL";
n31.appendChild(n40);
try { n40.characters = "Unlimited everything"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n40.layoutSizingHorizontal = "FILL";
n32.appendChild(n41);
try { n41.characters = "24/7 dedicated support"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.layoutSizingHorizontal = "FILL";
n33.appendChild(n42);
try { n42.characters = "Unlimited storage"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;