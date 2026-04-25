// W0.B Demo D probe — compose with real components
// Anchor: screen 311 / internal node 72405 / figma_node_id "5749:99599"
// (button/toolbar FRAME, VERTICAL auto-layout, 8 INSTANCE children
//  — all button/large/translucent today; demo appends a 9th =
//  button/small/translucent to flip the size axis visibly).
//
// Anchor was updated 2026-04-25 from screen 243 (which is in the
// iPad-translucent-cluster drift set per
// feedback_ipad_component_frame_inlining.md) to screen 311 (clean,
// not in any known drift set). Same component family inventory
// (24 large + 12 small + 4 solid translucent buttons + 6 toolbars).
//
// Returns the assertion shape Demo D's verifier needs:
//   { childCount, layoutMode, lastChildName }
// Verifier checks that an emit_append landed an 8th child with the right
// variant axis. This probe just confirms the container is queryable and
// reports its current child count + layoutMode.

const FIGMA_NODE_ID = "5749:99599";

try {
  const node = await figma.getNodeByIdAsync(FIGMA_NODE_ID);
  if (!node) {
    const result = { ok: false, error: "node_not_found", figma_node_id: FIGMA_NODE_ID };
    console.log(JSON.stringify(result));
    return result;
  }
  const children = ("children" in node && node.children) ? node.children : [];
  const lastChild = children.length > 0 ? children[children.length - 1] : null;
  const result = {
    ok: true,
    figma_node_id: FIGMA_NODE_ID,
    name: node.name,
    type: node.type,
    childCount: children.length,
    layoutMode: ("layoutMode" in node) ? node.layoutMode : null,
    primaryAxisSizingMode: ("primaryAxisSizingMode" in node) ? node.primaryAxisSizingMode : null,
    counterAxisSizingMode: ("counterAxisSizingMode" in node) ? node.counterAxisSizingMode : null,
    lastChildName: lastChild ? lastChild.name : null,
    lastChildType: lastChild ? lastChild.type : null,
  };
  console.log(JSON.stringify(result));
  return result;
} catch (e) {
  const err = { ok: false, error: String(e), stack: e && e.stack };
  console.log(JSON.stringify(err));
  return err;
}
