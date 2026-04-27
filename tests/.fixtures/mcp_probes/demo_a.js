// W0.B Demo A probe — DS-correct edit
// Anchor: screen 333 / internal node 82169 / figma_node_id "5749:101869"
// (button/large/translucent INSTANCE, CKR 689e60bd3db9ef304a9304eb585566a888a18237)
//
// Verifies that the assertion shape Demo A's verifier needs is queryable
// through figma-console-mcp (NOT just plugin API in isolation):
//   { componentKey, cornerRadius, boundVariables }
//
// Send through mcp__figma-console__figma_execute. Top-level await is
// supported in this environment (see render_batch/screen_*.js for idiom).

const FIGMA_NODE_ID = "5749:101869";

try {
  const node = await figma.getNodeByIdAsync(FIGMA_NODE_ID);
  if (!node) {
    const result = { ok: false, error: "node_not_found", figma_node_id: FIGMA_NODE_ID };
    console.log(JSON.stringify(result));
    return result;
  }
  // INSTANCE-only: componentKey lives on the main component.
  let componentKey = null;
  if (node.type === "INSTANCE") {
    const main = await node.getMainComponentAsync();
    componentKey = main && main.key ? main.key : null;
  }
  const result = {
    ok: true,
    figma_node_id: FIGMA_NODE_ID,
    name: node.name,
    type: node.type,
    componentKey: componentKey,
    cornerRadius: node.cornerRadius,
    boundVariables: node.boundVariables || null,
  };
  console.log(JSON.stringify(result));
  return result;
} catch (e) {
  const err = { ok: false, error: String(e), stack: e && e.stack };
  console.log(JSON.stringify(err));
  return err;
}
