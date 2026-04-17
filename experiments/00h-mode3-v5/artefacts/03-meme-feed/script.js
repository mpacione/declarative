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
n2.name = "list-1";
n2.layoutMode = "VERTICAL";
n2.fills = [];
n2.clipsContent = false;
M["list-1"] = n2.id;

const n3 = figma.createText();
n3.name = "text-1";
try { n3.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-1"] = n3.id;

const n4 = figma.createFrame();
n4.name = "icon_button-1";
n4.layoutMode = "VERTICAL";
n4.primaryAxisAlignItems = "CENTER";
n4.counterAxisAlignItems = "CENTER";
n4.fills = [{type: "SOLID", color: {r:1.0,g:1.0,b:1.0}}];
n4.cornerRadius = 8;
n4.clipsContent = false;
M["icon_button-1"] = n4.id;

const n5 = figma.createFrame();
n5.name = "card-1";
n5.layoutMode = "VERTICAL";
n5.fills = [];
n5.clipsContent = false;
M["card-1"] = n5.id;

const n6 = figma.createFrame();
n6.name = "card-2";
n6.layoutMode = "VERTICAL";
n6.fills = [];
n6.clipsContent = false;
M["card-2"] = n6.id;

const n7 = figma.createFrame();
n7.name = "card-3";
n7.layoutMode = "VERTICAL";
n7.fills = [];
n7.clipsContent = false;
M["card-3"] = n7.id;

const n8 = figma.createFrame();
n8.name = "card-4";
n8.layoutMode = "VERTICAL";
n8.fills = [];
n8.clipsContent = false;
M["card-4"] = n8.id;

const n9 = figma.createFrame();
n9.name = "avatar-1";
n9.layoutMode = "VERTICAL";
n9.primaryAxisAlignItems = "CENTER";
n9.counterAxisAlignItems = "CENTER";
n9.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n9.cornerRadius = 999;
n9.clipsContent = false;
M["avatar-1"] = n9.id;

const n10 = figma.createText();
n10.name = "text-3";
try { n10.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-3"] = n10.id;

const n11 = figma.createFrame();
n11.name = "image-1";
n11.fills = [];
n11.clipsContent = false;
M["image-1"] = n11.id;

const n12 = figma.createText();
n12.name = "text-4";
try { n12.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-4"] = n12.id;

const n13 = figma.createFrame();
n13.name = "button_group-1";
n13.layoutMode = "VERTICAL";
n13.fills = [];
n13.clipsContent = false;
M["button_group-1"] = n13.id;

const n14 = figma.createFrame();
n14.name = "avatar-2";
n14.layoutMode = "VERTICAL";
n14.primaryAxisAlignItems = "CENTER";
n14.counterAxisAlignItems = "CENTER";
n14.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n14.cornerRadius = 999;
n14.clipsContent = false;
M["avatar-2"] = n14.id;

const n15 = figma.createText();
n15.name = "text-8";
try { n15.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-8"] = n15.id;

const n16 = figma.createFrame();
n16.name = "image-2";
n16.fills = [];
n16.clipsContent = false;
M["image-2"] = n16.id;

const n17 = figma.createText();
n17.name = "text-9";
try { n17.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-9"] = n17.id;

const n18 = figma.createFrame();
n18.name = "button_group-2";
n18.layoutMode = "VERTICAL";
n18.fills = [];
n18.clipsContent = false;
M["button_group-2"] = n18.id;

const n19 = figma.createFrame();
n19.name = "avatar-3";
n19.layoutMode = "VERTICAL";
n19.primaryAxisAlignItems = "CENTER";
n19.counterAxisAlignItems = "CENTER";
n19.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n19.cornerRadius = 999;
n19.clipsContent = false;
M["avatar-3"] = n19.id;

const n20 = figma.createText();
n20.name = "text-13";
try { n20.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-13"] = n20.id;

const n21 = figma.createFrame();
n21.name = "image-3";
n21.fills = [];
n21.clipsContent = false;
M["image-3"] = n21.id;

const n22 = figma.createText();
n22.name = "text-14";
try { n22.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-14"] = n22.id;

const n23 = figma.createFrame();
n23.name = "button_group-3";
n23.layoutMode = "VERTICAL";
n23.fills = [];
n23.clipsContent = false;
M["button_group-3"] = n23.id;

const n24 = figma.createFrame();
n24.name = "avatar-4";
n24.layoutMode = "VERTICAL";
n24.primaryAxisAlignItems = "CENTER";
n24.counterAxisAlignItems = "CENTER";
n24.fills = [{type: "SOLID", color: {r:0.8863,g:0.9098,b:0.9412}}];
n24.cornerRadius = 999;
n24.clipsContent = false;
M["avatar-4"] = n24.id;

const n25 = figma.createText();
n25.name = "text-18";
try { n25.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-18"] = n25.id;

const n26 = figma.createFrame();
n26.name = "image-4";
n26.fills = [];
n26.clipsContent = false;
M["image-4"] = n26.id;

const n27 = figma.createText();
n27.name = "text-19";
try { n27.fontName = {family: "Inter", style: "Regular"}; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
M["text-19"] = n27.id;

const n28 = figma.createFrame();
n28.name = "button_group-4";
n28.layoutMode = "VERTICAL";
n28.fills = [];
n28.clipsContent = false;
M["button_group-4"] = n28.id;

const n29 = figma.createText();
n29.name = "text-2";
try { n29.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.fontSize = 14;
M["text-2"] = n29.id;

const n30 = figma.createFrame();
n30.name = "button-1";
n30.layoutMode = "VERTICAL";
n30.itemSpacing = 8;
n30.resize(n30.width, 44);
n30.primaryAxisAlignItems = "CENTER";
n30.counterAxisAlignItems = "CENTER";
n30.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n30.cornerRadius = 8;
n30.clipsContent = false;
M["button-1"] = n30.id;

const n31 = figma.createFrame();
n31.name = "button-2";
n31.layoutMode = "VERTICAL";
n31.itemSpacing = 8;
n31.resize(n31.width, 44);
n31.primaryAxisAlignItems = "CENTER";
n31.counterAxisAlignItems = "CENTER";
n31.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n31.cornerRadius = 8;
n31.clipsContent = false;
M["button-2"] = n31.id;

const n32 = figma.createText();
n32.name = "text-7";
try { n32.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.fontSize = 14;
M["text-7"] = n32.id;

const n33 = figma.createFrame();
n33.name = "button-3";
n33.layoutMode = "VERTICAL";
n33.itemSpacing = 8;
n33.resize(n33.width, 44);
n33.primaryAxisAlignItems = "CENTER";
n33.counterAxisAlignItems = "CENTER";
n33.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n33.cornerRadius = 8;
n33.clipsContent = false;
M["button-3"] = n33.id;

const n34 = figma.createFrame();
n34.name = "button-4";
n34.layoutMode = "VERTICAL";
n34.itemSpacing = 8;
n34.resize(n34.width, 44);
n34.primaryAxisAlignItems = "CENTER";
n34.counterAxisAlignItems = "CENTER";
n34.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n34.cornerRadius = 8;
n34.clipsContent = false;
M["button-4"] = n34.id;

const n35 = figma.createText();
n35.name = "text-12";
try { n35.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.fontSize = 14;
M["text-12"] = n35.id;

const n36 = figma.createFrame();
n36.name = "button-5";
n36.layoutMode = "VERTICAL";
n36.itemSpacing = 8;
n36.resize(n36.width, 44);
n36.primaryAxisAlignItems = "CENTER";
n36.counterAxisAlignItems = "CENTER";
n36.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n36.cornerRadius = 8;
n36.clipsContent = false;
M["button-5"] = n36.id;

const n37 = figma.createFrame();
n37.name = "button-6";
n37.layoutMode = "VERTICAL";
n37.itemSpacing = 8;
n37.resize(n37.width, 44);
n37.primaryAxisAlignItems = "CENTER";
n37.counterAxisAlignItems = "CENTER";
n37.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n37.cornerRadius = 8;
n37.clipsContent = false;
M["button-6"] = n37.id;

const n38 = figma.createText();
n38.name = "text-17";
try { n38.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.fontSize = 14;
M["text-17"] = n38.id;

const n39 = figma.createFrame();
n39.name = "button-7";
n39.layoutMode = "VERTICAL";
n39.itemSpacing = 8;
n39.resize(n39.width, 44);
n39.primaryAxisAlignItems = "CENTER";
n39.counterAxisAlignItems = "CENTER";
n39.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n39.cornerRadius = 8;
n39.clipsContent = false;
M["button-7"] = n39.id;

const n40 = figma.createFrame();
n40.name = "button-8";
n40.layoutMode = "VERTICAL";
n40.itemSpacing = 8;
n40.resize(n40.width, 44);
n40.primaryAxisAlignItems = "CENTER";
n40.counterAxisAlignItems = "CENTER";
n40.fills = [{type: "SOLID", color: {r:0.9451,g:0.9608,b:0.9765}}];
n40.cornerRadius = 8;
n40.clipsContent = false;
M["button-8"] = n40.id;

const n41 = figma.createText();
n41.name = "text-5";
n41.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n41.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.fontSize = 14;
M["text-5"] = n41.id;

const n42 = figma.createText();
n42.name = "text-6";
n42.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n42.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.fontSize = 14;
M["text-6"] = n42.id;

const n43 = figma.createText();
n43.name = "text-10";
n43.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n43.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n43.fontSize = 14;
M["text-10"] = n43.id;

const n44 = figma.createText();
n44.name = "text-11";
n44.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n44.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n44.fontSize = 14;
M["text-11"] = n44.id;

const n45 = figma.createText();
n45.name = "text-15";
n45.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n45.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n45.fontSize = 14;
M["text-15"] = n45.id;

const n46 = figma.createText();
n46.name = "text-16";
n46.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n46.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n46.fontSize = 14;
M["text-16"] = n46.id;

const n47 = figma.createText();
n47.name = "text-20";
n47.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n47.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n47.fontSize = 14;
M["text-20"] = n47.id;

const n48 = figma.createText();
n48.name = "text-21";
n48.fills = [{type: "SOLID", color: {r:0.0588,g:0.0902,b:0.1647}}];
try { n48.fontName = {family: "Inter", style: "Semi Bold"}; } catch (__e) { __errors.push({eid:"text-21", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n48.fontSize = 14;
M["text-21"] = n48.id;


// Phase 2: Compose — wire tree, set layoutSizing
await new Promise(r => setTimeout(r, 0));

n0.appendChild(n1);
n1.layoutSizingHorizontal = "FILL";
n0.appendChild(n2);
n2.layoutSizingHorizontal = "FILL";
n1.appendChild(n3);
try { n3.characters = "Meme Feed"; } catch (__e) { __errors.push({eid:"text-1", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n3.layoutSizingHorizontal = "FILL";
n1.appendChild(n4);
n4.layoutSizingHorizontal = "FIXED";
n4.layoutSizingVertical = "FIXED";
n2.appendChild(n5);
n5.layoutSizingHorizontal = "FILL";
n2.appendChild(n6);
n6.layoutSizingHorizontal = "FILL";
n2.appendChild(n7);
n7.layoutSizingHorizontal = "FILL";
n2.appendChild(n8);
n8.layoutSizingHorizontal = "FILL";
n5.appendChild(n9);
n9.layoutSizingHorizontal = "FIXED";
n9.layoutSizingVertical = "FIXED";
n5.appendChild(n10);
try { n10.characters = "MemeKing92"; } catch (__e) { __errors.push({eid:"text-3", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n10.layoutSizingHorizontal = "FILL";
n5.appendChild(n11);
n5.appendChild(n12);
try { n12.characters = "When you finally understand the assignment"; } catch (__e) { __errors.push({eid:"text-4", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n12.layoutSizingHorizontal = "FILL";
n5.appendChild(n13);
n6.appendChild(n14);
n14.layoutSizingHorizontal = "FIXED";
n14.layoutSizingVertical = "FIXED";
n6.appendChild(n15);
try { n15.characters = "ComedyGold"; } catch (__e) { __errors.push({eid:"text-8", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n15.layoutSizingHorizontal = "FILL";
n6.appendChild(n16);
n6.appendChild(n17);
try { n17.characters = "POV: You're scrolling at 3 AM"; } catch (__e) { __errors.push({eid:"text-9", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n17.layoutSizingHorizontal = "FILL";
n6.appendChild(n18);
n7.appendChild(n19);
n19.layoutSizingHorizontal = "FIXED";
n19.layoutSizingVertical = "FIXED";
n7.appendChild(n20);
try { n20.characters = "LaughTrack"; } catch (__e) { __errors.push({eid:"text-13", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n20.layoutSizingHorizontal = "FILL";
n7.appendChild(n21);
n7.appendChild(n22);
try { n22.characters = "Me pretending to understand what's happening"; } catch (__e) { __errors.push({eid:"text-14", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n22.layoutSizingHorizontal = "FILL";
n7.appendChild(n23);
n8.appendChild(n24);
n24.layoutSizingHorizontal = "FIXED";
n24.layoutSizingVertical = "FIXED";
n8.appendChild(n25);
try { n25.characters = "ViralVibe"; } catch (__e) { __errors.push({eid:"text-18", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n25.layoutSizingHorizontal = "FILL";
n8.appendChild(n26);
n8.appendChild(n27);
try { n27.characters = "This is fine"; } catch (__e) { __errors.push({eid:"text-19", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n27.layoutSizingHorizontal = "FILL";
n8.appendChild(n28);
n9.appendChild(n29);
try { n29.characters = "User"; } catch (__e) { __errors.push({eid:"text-2", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n29.layoutSizingHorizontal = "FILL";
n13.appendChild(n30);
n30.layoutSizingHorizontal = "HUG";
n30.layoutSizingVertical = "FIXED";
n13.appendChild(n31);
n31.layoutSizingHorizontal = "HUG";
n31.layoutSizingVertical = "FIXED";
n14.appendChild(n32);
try { n32.characters = "User"; } catch (__e) { __errors.push({eid:"text-7", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n32.layoutSizingHorizontal = "FILL";
n18.appendChild(n33);
n33.layoutSizingHorizontal = "HUG";
n33.layoutSizingVertical = "FIXED";
n18.appendChild(n34);
n34.layoutSizingHorizontal = "HUG";
n34.layoutSizingVertical = "FIXED";
n19.appendChild(n35);
try { n35.characters = "User"; } catch (__e) { __errors.push({eid:"text-12", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n35.layoutSizingHorizontal = "FILL";
n23.appendChild(n36);
n36.layoutSizingHorizontal = "HUG";
n36.layoutSizingVertical = "FIXED";
n23.appendChild(n37);
n37.layoutSizingHorizontal = "HUG";
n37.layoutSizingVertical = "FIXED";
n24.appendChild(n38);
try { n38.characters = "User"; } catch (__e) { __errors.push({eid:"text-17", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n38.layoutSizingHorizontal = "FILL";
n28.appendChild(n39);
n39.layoutSizingHorizontal = "HUG";
n39.layoutSizingVertical = "FIXED";
n28.appendChild(n40);
n40.layoutSizingHorizontal = "HUG";
n40.layoutSizingVertical = "FIXED";
n30.appendChild(n41);
try { n41.characters = "👍 Upvote"; } catch (__e) { __errors.push({eid:"text-5", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n41.layoutSizingHorizontal = "FILL";
n31.appendChild(n42);
try { n42.characters = "↗️ Share"; } catch (__e) { __errors.push({eid:"text-6", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n42.layoutSizingHorizontal = "FILL";
n33.appendChild(n43);
try { n43.characters = "👍 Upvote"; } catch (__e) { __errors.push({eid:"text-10", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n43.layoutSizingHorizontal = "FILL";
n34.appendChild(n44);
try { n44.characters = "↗️ Share"; } catch (__e) { __errors.push({eid:"text-11", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n44.layoutSizingHorizontal = "FILL";
n36.appendChild(n45);
try { n45.characters = "👍 Upvote"; } catch (__e) { __errors.push({eid:"text-15", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n45.layoutSizingHorizontal = "FILL";
n37.appendChild(n46);
try { n46.characters = "↗️ Share"; } catch (__e) { __errors.push({eid:"text-16", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n46.layoutSizingHorizontal = "FILL";
n39.appendChild(n47);
try { n47.characters = "👍 Upvote"; } catch (__e) { __errors.push({eid:"text-20", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n47.layoutSizingHorizontal = "FILL";
n40.appendChild(n48);
try { n48.characters = "↗️ Share"; } catch (__e) { __errors.push({eid:"text-21", kind:"text_set_failed", error: String(__e && __e.message || __e)}); }
n48.layoutSizingHorizontal = "FILL";
_rootPage.appendChild(n0);
} catch (__thrown) {
  __errors.push({kind: "render_thrown", error: String(__thrown && __thrown.message || __thrown), stack: (__thrown && __thrown.stack) ? String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null});
}
M["__errors"] = __errors;
return M;