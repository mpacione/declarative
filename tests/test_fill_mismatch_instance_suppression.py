"""Phase E #2 fix — fill_mismatch suppression for Mode-1 INSTANCE
heads with token-bound gradient IR + solid rendered.

Phase E re-run sweep on Nouns identified 3 fill_mismatch errors,
all on `chip-1` across screens 24, 25, 44 (same chip variant
"Chip/Activity Succeeded" rendered into different screens):

  IR visual.fills = [{type: "gradient-linear", stops: [
                      {color: "{color.surface.14}", ...},
                      {color: "{color.surface.33}", ...}]}]
  Rendered fills  = [{type: "solid", color: "#3BC98D"}]
  Verifier: solid fill count: IR=0, rendered=1 → KIND_FILL_MISMATCH

Root cause: Mode-1 INSTANCE heads delegate fill rendering to the
master. The renderer (dd/render_figma_ast.py:823-836) emits
createInstance() and skips visual writes — the master's fill is
what renders. The IR's visual.fills for an instance is a
SNAPSHOT of what extraction observed (a gradient with token-ref
colors here), but the rendered tree shows the master's defaults
(a flat solid).

That divergence is NOT a renderer failure. The verifier was
comparing an extraction snapshot against a runtime master default.

Codex 2026-04-26 (gpt-5.5 high reasoning) recommended a narrow
suppression rule:

  Skip fill_mismatch IFF:
    rendered.type == "INSTANCE"
    AND no solid fills in IR
    AND all IR fills are gradient-* with token-ref colors

This preserves the signal for:
- non-instance nodes (regular fill check applies)
- INSTANCE nodes with concrete solid IR fills (override-replay
  failures still flag)
- solid-vs-solid color mismatches
- explicit override failures that materialize as solid IR
  expectations

Longer-term: tag extraction with override-vs-snapshot provenance
so legitimate instance overrides still enforce. Without that
provenance, a broad "INSTANCE fills must match" check produces
false positives like these 3 chip cases.

Phase E impact:
- 3 fill_mismatch errors cleared on screens 24, 25, 44
- Screen 24 specifically goes from parity_ratio=0.9946 errs=1 to
  parity_ratio=1.0000 errs=0 (fully clean post-fix)
"""

from __future__ import annotations

from dd.boundary import KIND_FILL_MISMATCH
from dd.verify_figma import FigmaRenderVerifier


class TestInstanceTokenGradientSuppression:
    """The headline contract — INSTANCE heads with token-bound
    gradient IR fills + solid rendered fills should NOT report
    fill_mismatch."""

    def test_chip_1_token_gradient_vs_solid_no_error(self):
        """Reproduction of the actual Phase E #2 case."""
        ir = {
            "elements": {
                "chip-1": {
                    "type": "instance",
                    "visual": {
                        "fills": [
                            {
                                "type": "gradient-linear",
                                "stops": [
                                    {
                                        "color": "{color.surface.14}",
                                        "position": 0.0,
                                    },
                                    {
                                        "color": "{color.surface.33}",
                                        "position": 1.0,
                                    },
                                ],
                            }
                        ]
                    },
                }
            }
        }
        rendered_ref = {
            "eid_map": {
                "chip-1": {
                    "type": "INSTANCE",
                    "name": "Chip/Activity Succeeded",
                    "fills": [{"type": "solid", "color": "#3BC98D"}],
                }
            },
            "errors": [],
        }
        report = FigmaRenderVerifier().verify(ir, rendered_ref)
        fill_errs = [
            e for e in report.errors if e.kind == KIND_FILL_MISMATCH
        ]
        assert not fill_errs, (
            f"Phase E #2 fix: chip-1 (INSTANCE head with token-bound "
            f"gradient IR + solid rendered) should NOT trigger "
            f"fill_mismatch. Got: {fill_errs}"
        )


class TestInstanceFillCheckPreservesOtherSignals:
    """Defensive — the suppression must NOT swallow legitimate
    fill_mismatch errors."""

    def test_instance_with_solid_ir_fill_still_checks(self):
        """If the IR has a SOLID fill (extraction captured an
        explicit color override), the fill check should still
        compare against rendered."""
        ir = {
            "elements": {
                "btn": {
                    "type": "instance",
                    "visual": {
                        "fills": [{"type": "solid", "color": "#FF0000"}]
                    },
                }
            }
        }
        rendered_ref = {
            "eid_map": {
                "btn": {
                    "type": "INSTANCE",
                    "fills": [{"type": "solid", "color": "#0000FF"}],
                }
            },
            "errors": [],
        }
        report = FigmaRenderVerifier().verify(ir, rendered_ref)
        fill_errs = [
            e for e in report.errors if e.kind == KIND_FILL_MISMATCH
        ]
        assert fill_errs, (
            "Defensive: INSTANCE with explicit solid IR fill should "
            "still flag a color mismatch (the suppression only "
            "covers token-bound gradient → solid divergence)."
        )

    def test_non_instance_with_gradient_ir_still_checks_count(self):
        """Non-instance node (e.g. plain rectangle) with gradient
        IR + solid rendered should still flag — the suppression is
        instance-specific."""
        ir = {
            "elements": {
                "rect": {
                    "type": "rectangle",
                    "visual": {
                        "fills": [
                            {
                                "type": "gradient-linear",
                                "stops": [
                                    {
                                        "color": "{color.fg}",
                                        "position": 0.0,
                                    }
                                ],
                            }
                        ]
                    },
                }
            }
        }
        rendered_ref = {
            "eid_map": {
                "rect": {
                    "type": "RECTANGLE",
                    "fills": [{"type": "solid", "color": "#FF0000"}],
                }
            },
            "errors": [],
        }
        report = FigmaRenderVerifier().verify(ir, rendered_ref)
        fill_errs = [
            e for e in report.errors if e.kind == KIND_FILL_MISMATCH
        ]
        assert fill_errs, (
            "Defensive: non-instance with token-gradient IR + solid "
            "rendered should still flag — the renderer is supposed "
            "to write fills explicitly for non-instance nodes."
        )

    def test_instance_with_multiple_ir_fills_one_solid_still_checks(self):
        """If IR has MIXED fills (some solid, some gradient), the
        presence of any solid means the suppression doesn't fire."""
        ir = {
            "elements": {
                "card": {
                    "type": "instance",
                    "visual": {
                        "fills": [
                            {"type": "solid", "color": "#FFFFFF"},
                            {
                                "type": "gradient-linear",
                                "stops": [
                                    {
                                        "color": "{color.tint}",
                                        "position": 0.0,
                                    }
                                ],
                            },
                        ]
                    },
                }
            }
        }
        rendered_ref = {
            "eid_map": {
                "card": {
                    "type": "INSTANCE",
                    "fills": [{"type": "solid", "color": "#000000"}],
                }
            },
            "errors": [],
        }
        report = FigmaRenderVerifier().verify(ir, rendered_ref)
        fill_errs = [
            e for e in report.errors if e.kind == KIND_FILL_MISMATCH
        ]
        # IR solids = 1 (the white solid), rendered solids = 1 (black).
        # The count matches, but the COLOR differs (white vs black) →
        # color-mismatch entry.
        assert fill_errs, (
            "Defensive: INSTANCE with mixed IR fills (one solid + one "
            "gradient) should still flag the solid color mismatch."
        )


class TestInstanceFillCheckSpecificity:
    """Document the exact suppression triggers — these are the
    boundary conditions Codex's review specified."""

    def test_only_instance_rendered_type_triggers_suppression(self):
        """The suppression keys on rendered.type == 'INSTANCE'.
        A non-instance IR type with token-bound gradient fills and
        a solid rendered (rendered as FRAME) should NOT be
        suppressed — the renderer was supposed to write the fill
        explicitly. This boundary test uses ir.type='frame' (not
        instance) so type_substitution doesn't pre-empt the fill
        check."""
        ir = {
            "elements": {
                "x": {
                    # frame, not instance — no type_substitution fires.
                    "type": "frame",
                    "visual": {
                        "fills": [
                            {
                                "type": "gradient-linear",
                                "stops": [
                                    {"color": "{token}", "position": 0.0}
                                ],
                            }
                        ]
                    },
                }
            }
        }
        # rendered.type = "FRAME" (not INSTANCE) — suppression should NOT fire.
        rendered_ref = {
            "eid_map": {
                "x": {
                    "type": "FRAME",
                    "fills": [{"type": "solid", "color": "#FF0000"}],
                }
            },
            "errors": [],
        }
        report = FigmaRenderVerifier().verify(ir, rendered_ref)
        fill_errs = [
            e for e in report.errors if e.kind == KIND_FILL_MISMATCH
        ]
        assert fill_errs, (
            "Suppression boundary: rendered.type='FRAME' should NOT "
            "trigger the suppression. Only INSTANCE delegates to "
            "master."
        )

    def test_non_token_gradient_color_still_checks(self):
        """Suppression requires gradient stops to have token-ref
        colors (start with '{'). A literal hex gradient with
        rendered solid is still a real mismatch."""
        ir = {
            "elements": {
                "y": {
                    "type": "instance",
                    "visual": {
                        "fills": [
                            {
                                "type": "gradient-linear",
                                "stops": [
                                    {"color": "#ABC123", "position": 0.0}
                                ],
                            }
                        ]
                    },
                }
            }
        }
        rendered_ref = {
            "eid_map": {
                "y": {
                    "type": "INSTANCE",
                    "fills": [{"type": "solid", "color": "#FF0000"}],
                }
            },
            "errors": [],
        }
        report = FigmaRenderVerifier().verify(ir, rendered_ref)
        fill_errs = [
            e for e in report.errors if e.kind == KIND_FILL_MISMATCH
        ]
        assert fill_errs, (
            "Suppression boundary: gradient with literal hex color "
            "(not token ref) is NOT a snapshot — it's a concrete "
            "expectation. Should still flag mismatch."
        )
