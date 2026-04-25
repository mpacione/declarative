// W0.B Demo B probe — token-mutation propagation
// Anchor: screen 333, ANY node bound to color.border.tertiary (#047AFF).
// DB query (run beforehand against Dank-EXP-02.declarative.db) found
// these stroke-bound candidates: 82120 / 82121 / 82122 (Frame 366/361/362).
// We use 5749:101820 (internal id 82120) as the canonical Demo B anchor;
// the demo asserts presence of a stroke boundVariables entry, so any of
// the candidates works as long as boundVariables.strokes / fills resolves.
//
// Returns the assertion shape Demo B's verifier needs:
//   { fillBoundVariableId, strokeBoundVariableId }
// (plus name + raw boundVariables for diagnostic visibility).

const FIGMA_NODE_ID = "5749:101820";

try {
  const node = await figma.getNodeByIdAsync(FIGMA_NODE_ID);
  if (!node) {
    const result = { ok: false, error: "node_not_found", figma_node_id: FIGMA_NODE_ID };
    console.log(JSON.stringify(result));
    return result;
  }
  // boundVariables shape on shape nodes:
  //   { fills: [ { id, type } | null, ... ], strokes: [ ... ], cornerRadius: { id, type }, ... }
  const bv = node.boundVariables || {};
  const firstId = (arr) => Array.isArray(arr) && arr.length > 0 && arr[0] && arr[0].id ? arr[0].id : null;
  const result = {
    ok: true,
    figma_node_id: FIGMA_NODE_ID,
    name: node.name,
    type: node.type,
    fillBoundVariableId: firstId(bv.fills),
    strokeBoundVariableId: firstId(bv.strokes),
    boundVariables: bv,
  };
  console.log(JSON.stringify(result));
  return result;
} catch (e) {
  const err = { ok: false, error: String(e), stack: e && e.stack };
  console.log(JSON.stringify(err));
  return err;
}
