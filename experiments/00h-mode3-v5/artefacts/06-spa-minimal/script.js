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
n4.name = "card-6";
n4.layoutMode = "VERTICAL";
n4.fills = [];
n4.clipsContent = false;
M["card-6"] = n4.id;

const n5 = figma.createFrame();
n5.name = "card-7";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["card-7"] = n5.id;

const n6 = figma.createFrame();
n6.name = "icon_button-1";
n6.layoutMode = "VERTICAL";
n6.primaryAxisAlignItems = "CENTER";
n6.counterAxisAlignItems = "CENTER";
n6.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n6.cornerRadius = 8;
n6.clipsContent = false;
M["icon_button-1"] = n6.id;

const n7 = figma.createText();
n7.name = "text-1";
try { n7.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n7.id;

const n8 = figma.createFrame();
n8.name = "icon_button-2";
n8.layoutMode = "VERTICAL";
n8.primaryAxisAlignItems = "CENTER";
n8.counterAxisAlignItems = "CENTER";
n8.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n8.cornerRadius = 8;
n8.clipsContent = false;
M["icon_button-2"] = n8.id;

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
n12.name = "card-2";
n12.layoutMode = "VERTICAL";
n12.fills = [];
n12.clipsContent = false;
M["card-2"] = n12.id;

const n13 = figma.createFrame();
n13.name = "card-3";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["card-3"] = n13.id;

const n14 = figma.createFrame();
n14.name = "card-4";
n14.layoutMode = "VERTICAL";
n14.fills = [];
n14.clipsContent = false;
M["card-4"] = n14.id;

const n15 = figma.createFrame();
n15.name = "card-5";
n15.layoutMode = "VERTICAL";
n15.fills = [];
n15.clipsContent = false;
M["card-5"] = n15.id;

const n16 = figma.createText();
n16.name = "heading-6";
try { n16.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-6"] = n16.id;

const n17 = figma.createFrame();
n17.name = "date_picker-1";
n17.layoutMode = "VERTICAL";
n17.fills = [];
n17.clipsContent = false;
M["date_picker-1"] = n17.id;

const n18 = figma.createFrame();
n18.name = "select-1";
n18.layoutMode = "VERTICAL";
n18.counterAxisAlignItems = "CENTER";
n18.fills = [{type: "SOLID", color: {r:0.9725,g:0.9804,b:0.9882}}];
n18.cornerRadius = 8;
n18.clipsContent = false;
M["select-1"] = n18.id;

const n19 = figma.createFrame();
n19.name = "button-1";
n19.layoutMode = "VERTICAL";
n19.itemSpacing = 8;
n19.resize(n19.width, 44);
n19.primaryAxisAlignItems = "CENTER";
n19.counterAxisAlignItems = "CENTER";
n19.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n19.cornerRadius = 8;
n19.clipsContent = false;
M["button-1"] = n19.id;

const n20 = figma.createText();
n20.name = "text-9";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n20.id;

const n21 = figma.createText();
n21.name = "link-1";
try { n21.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"link-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["link-1"] = n21.id;

const n22 = figma.createFrame();
n22.name = "image-2";
n22.fills = [];
n22.clipsContent = false;
M["image-2"] = n22.id;

const n23 = figma.createText();
n23.name = "heading-2";
try { n23.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-2"] = n23.id;

const n24 = figma.createText();
n24.name = "text-3";
try { n24.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n24.id;

const n25 = figma.createFrame();
n25.name = "image-3";
n25.fills = [];
n25.clipsContent = false;
M["image-3"] = n25.id;

const n26 = figma.createText();
n26.name = "heading-3";
try { n26.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-3"] = n26.id;

const n27 = figma.createText();
n27.name = "text-4";
try { n27.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n27.id;

const n28 = figma.createFrame();
n28.name = "image-4";
n28.fills = [];
n28.clipsContent = false;
M["image-4"] = n28.id;

const n29 = figma.createText();
n29.name = "heading-4";
try { n29.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-4"] = n29.id;

const n30 = figma.createText();
n30.name = "text-5";
try { n30.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-5"] = n30.id;

const n31 = figma.createFrame();
n31.name = "image-5";
n31.fills = [];
n31.clipsContent = false;
M["image-5"] = n31.id;

const n32 = figma.createText();
n32.name = "heading-5";
try { n32.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["heading-5"] = n32.id;

const n33 = figma.createText();
n33.name = "text-6";
try { n33.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-6"] = n33.id;

const n34 = figma.createText();
n34.name = "text-7";
try { n34.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.fontSize = 14;
M["text-7"] = n34.id;

const n35 = figma.createText();
n35.name = "text-8";
n35.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n35.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.fontSize = 14;
M["text-8"] = n35.id;

const n36 = figma.createText();
n36.name = "text-10";
n36.fills = [{type: "SOLID", color: {r:0.1451,g:0.3882,b:0.9216}}];
try { n36.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.fontSize = 14;
M["text-10"] = n36.id;


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
n6.layoutSizingHorizontal = "FIXED";
n6.layoutSizingVertical = "FIXED";
n1.appendChild(n7);
try { n7.characters = "SERENITY"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n7.layoutSizingHorizontal = "FILL";
n1.appendChild(n8);
n8.layoutSizingHorizontal = "FIXED";
n8.layoutSizingVertical = "FIXED";
n2.appendChild(n9);
n2.appendChild(n10);
try { n10.characters = "Escape to Tranquility"; } catch (__e) { __errors.push({eid:"heading-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n2.appendChild(n11);
try { n11.characters = "Indulge in our curated wellness experiences"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n11.layoutSizingHorizontal = "FILL";
n3.appendChild(n12);
n12.layoutSizingHorizontal = "FILL";
n3.appendChild(n13);
n13.layoutSizingHorizontal = "FILL";
n3.appendChild(n14);
n14.layoutSizingHorizontal = "FILL";
n3.appendChild(n15);
n15.layoutSizingHorizontal = "FILL";
n4.appendChild(n16);
try { n16.characters = "Reserve Your Experience"; } catch (__e) { __errors.push({eid:"heading-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n16.layoutSizingHorizontal = "FILL";
n4.appendChild(n17);
n4.appendChild(n18);
n18.layoutSizingHorizontal = "HUG";
n18.layoutSizingVertical = "HUG";
n4.appendChild(n19);
n19.layoutSizingHorizontal = "HUG";
n19.layoutSizingVertical = "FIXED";
n5.appendChild(n20);
try { n20.characters = "+1 (555) 123-4567 • hello@serenity.spa"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n5.appendChild(n21);
try { n21.characters = "Visit us at 123 Wellness Ave, Calm City"; } catch (__e) { __errors.push({eid:"link-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n21.layoutSizingHorizontal = "HUG";
n21.layoutSizingVertical = "HUG";
n12.appendChild(n22);
n12.appendChild(n23);
try { n23.characters = "Swedish Massage"; } catch (__e) { __errors.push({eid:"heading-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n23.layoutSizingHorizontal = "FILL";
n12.appendChild(n24);
try { n24.characters = "$180 / 60 min"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n24.layoutSizingHorizontal = "FILL";
n13.appendChild(n25);
n13.appendChild(n26);
try { n26.characters = "Hydrating Facial"; } catch (__e) { __errors.push({eid:"heading-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n26.layoutSizingHorizontal = "FILL";
n13.appendChild(n27);
try { n27.characters = "$150 / 50 min"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n27.layoutSizingHorizontal = "FILL";
n14.appendChild(n28);
n14.appendChild(n29);
try { n29.characters = "Aromatherapy"; } catch (__e) { __errors.push({eid:"heading-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.layoutSizingHorizontal = "FILL";
n14.appendChild(n30);
try { n30.characters = "$120 / 45 min"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n30.layoutSizingHorizontal = "FILL";
n15.appendChild(n31);
n15.appendChild(n32);
try { n32.characters = "Hot Stone Therapy"; } catch (__e) { __errors.push({eid:"heading-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n15.appendChild(n33);
try { n33.characters = "$200 / 75 min"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n33.layoutSizingHorizontal = "FILL";
n18.appendChild(n34);
try { n34.characters = "Select Time"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n34.layoutSizingHorizontal = "FILL";
n19.appendChild(n35);
try { n35.characters = "Book Now"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n21.appendChild(n36);
try { n36.characters = "Visit us at 123 Wellness Ave, Calm City"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n36.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;