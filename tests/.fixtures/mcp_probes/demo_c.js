// W0.B Demo C probe — adversarial verifier
// Anchor: screen 118 / internal node 798 / figma_node_id "I5749:82524;5749:93112"
// (Battery Icon, GROUP, 26.5x12). NOTE: this is an instance-namespaced id
// (prefix "I" + path with ";"). getNodeByIdAsync handles this form.
//
// Returns the assertion shape Demo C's verifier needs:
//   { fills, fillBoundVariables, name }
// Demo C's verifier baits a literal #FFFFFF and expects the verifier to
// reject + suggest color.border.primary. The probe just confirms the
// queryability of fills + their boundVariables on this GROUP descendent.

const FIGMA_NODE_ID = "I5749:82524;5749:93112";

try {
  const node = await figma.getNodeByIdAsync(FIGMA_NODE_ID);
  if (!node) {
    const result = { ok: false, error: "node_not_found", figma_node_id: FIGMA_NODE_ID };
    console.log(JSON.stringify(result));
    return result;
  }
  // GROUP itself has no fills; descend to first fillable child if needed
  // for the smoke. Surface whatever the top node exposes — verifier inspects
  // .fills directly on whatever node it asserts.
  const bv = node.boundVariables || {};
  const result = {
    ok: true,
    figma_node_id: FIGMA_NODE_ID,
    name: node.name,
    type: node.type,
    fills: node.fills === figma.mixed ? "MIXED" : (node.fills || null),
    fillBoundVariables: bv.fills || null,
    childCount: ("children" in node && node.children) ? node.children.length : 0,
  };
  console.log(JSON.stringify(result));
  return result;
} catch (e) {
  const err = { ok: false, error: String(e), stack: e && e.stack };
  console.log(JSON.stringify(err));
  return err;
}
