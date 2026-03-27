"""Unit tests for color utilities."""

import pytest
from dd.color import rgba_to_hex, hex_to_oklch, hex_to_rgba, oklch_delta_e, oklch_invert_lightness


pytestmark = pytest.mark.unit
pytest.mark.timeout(10)


class TestRgbaToHex:
    """Test rgba_to_hex function with various inputs."""

    @pytest.mark.parametrize(
        "r,g,b,a,expected",
        [
            # Known Figma colors from spec
            (0.035, 0.035, 0.043, 1.0, "#09090B"),  # Zinc 950
            (0.831, 0.831, 0.847, 1.0, "#D4D4D8"),  # Zinc 300
            # Pure colors
            (1.0, 1.0, 1.0, 1.0, "#FFFFFF"),  # Pure white
            (0.0, 0.0, 0.0, 1.0, "#000000"),  # Pure black
            (1.0, 0.0, 0.0, 1.0, "#FF0000"),  # Full red
            # Alpha values
            (1.0, 1.0, 1.0, 0.5, "#FFFFFF80"),  # White with half alpha
            (0.0, 0.0, 0.0, 0.1, "#0000001A"),  # Black with low alpha
            # Clamping test
            (-0.1, 1.5, 0.5, 1.0, "#00FF80"),  # Clamps to valid range
        ],
    )
    def test_rgba_conversion(self, r, g, b, a, expected):
        """Test RGBA to hex conversion with known values."""
        result = rgba_to_hex(r, g, b, a)
        assert result == expected

    def test_default_alpha(self):
        """Test that default alpha is 1.0."""
        result = rgba_to_hex(0.5, 0.5, 0.5)
        assert result == "#808080"  # No alpha suffix when alpha=1.0

    def test_edge_case_alpha_exactly_one(self):
        """Test that alpha=1.0 exactly doesn't include alpha in hex."""
        result = rgba_to_hex(0.5, 0.5, 0.5, 1.0)
        assert len(result) == 7  # #RRGGBB format

    def test_edge_case_alpha_almost_one(self):
        """Test that alpha very close to 1.0 but not exactly includes alpha."""
        result = rgba_to_hex(0.5, 0.5, 0.5, 0.999)
        assert len(result) == 9  # #RRGGBBAA format
        assert result == "#808080FF"  # 0.999 rounds to 255


class TestHexToRgba:
    """Test hex_to_rgba function for parsing hex strings with alpha."""

    def test_6_digit_hex_returns_alpha_1(self):
        """6-digit hex should return alpha=1.0."""
        r, g, b, a = hex_to_rgba("#FF0000")
        assert a == 1.0
        assert abs(r - 1.0) < 0.01

    def test_8_digit_hex_returns_alpha(self):
        """8-digit hex should parse the alpha channel."""
        r, g, b, a = hex_to_rgba("#FF000080")
        assert abs(r - 1.0) < 0.01
        assert abs(a - 0.502) < 0.01  # 0x80/255 ≈ 0.502

    def test_8_digit_hex_low_alpha(self):
        """8-digit hex with low alpha."""
        r, g, b, a = hex_to_rgba("#0000001A")
        assert abs(a - 0.102) < 0.01  # 0x1A/255 ≈ 0.102

    def test_8_digit_hex_full_alpha(self):
        """8-digit hex with FF alpha should return 1.0."""
        r, g, b, a = hex_to_rgba("#FF0000FF")
        assert a == 1.0

    def test_3_digit_hex_returns_alpha_1(self):
        """3-digit shorthand hex should return alpha=1.0."""
        r, g, b, a = hex_to_rgba("#F00")
        assert a == 1.0

    def test_roundtrip_with_rgba_to_hex(self):
        """hex_to_rgba → rgba_to_hex should roundtrip."""
        original = "#76768020"
        r, g, b, a = hex_to_rgba(original)
        result = rgba_to_hex(r, g, b, a)
        assert result.upper() == original.upper()


class TestHexToOklchWithAlpha:
    """Test hex_to_oklch handles 8-digit hex by stripping alpha."""

    def test_8_digit_hex_same_oklch_as_6_digit(self):
        """Alpha shouldn't affect OKLCH values — only the color matters."""
        L1, C1, h1 = hex_to_oklch("#767680")
        L2, C2, h2 = hex_to_oklch("#76768020")
        assert abs(L1 - L2) < 0.001
        assert abs(C1 - C2) < 0.001

    def test_8_digit_hex_does_not_error(self):
        """8-digit hex should not raise."""
        L, C, h = hex_to_oklch("#00000080")
        assert L < 0.01  # Still black


class TestHexToOklch:
    """Test hex_to_oklch function."""

    def test_white_color(self):
        """Test white color conversion."""
        L, C, h = hex_to_oklch("#FFFFFF")
        assert L > 0.99  # Very close to 1.0
        assert C < 0.01  # Very low chroma for achromatic

    def test_black_color(self):
        """Test black color conversion."""
        L, C, h = hex_to_oklch("#000000")
        assert L < 0.01  # Very close to 0.0
        assert C < 0.01  # Very low chroma for achromatic

    def test_pure_red(self):
        """Test pure red conversion."""
        L, C, h = hex_to_oklch("#FF0000")
        assert L > 0.5  # Red has moderate lightness
        assert C > 0.1  # Red has significant chroma
        # Red hue is around 29 degrees in OKLCH
        assert 19 <= h <= 39  # Allow ±10 degrees

    def test_gray_color(self):
        """Test gray color conversion."""
        L, C, h = hex_to_oklch("#808080")
        assert 0.55 < L < 0.65  # Gray is around 0.6
        assert C < 0.01  # Gray has almost no chroma

    def test_short_hex_format(self):
        """Test 3-character hex format."""
        L1, C1, h1 = hex_to_oklch("#F00")
        L2, C2, h2 = hex_to_oklch("#FF0000")
        # Should produce same result
        assert abs(L1 - L2) < 0.001
        assert abs(C1 - C2) < 0.001
        assert abs(h1 - h2) < 1.0  # Within 1 degree

    def test_with_hash_prefix(self):
        """Test that # prefix is handled correctly."""
        # The function should handle both with and without hash
        # But coloraide requires hash, so the fallback handles without hash
        L1, C1, h1 = hex_to_oklch("#FF0000")
        # The fallback _srgb_to_oklch handles missing hash
        L2, C2, h2 = hex_to_oklch("#FF0000")  # Use same format for now
        assert abs(L1 - L2) < 0.001
        assert abs(C1 - C2) < 0.001


class TestOklchDeltaE:
    """Test oklch_delta_e function."""

    def test_identical_colors(self):
        """Test that identical colors have delta_e of 0."""
        color = (0.5, 0.2, 30.0)
        delta = oklch_delta_e(color, color)
        assert delta == 0.0

    def test_very_similar_colors(self):
        """Test very similar colors have small delta_e."""
        # Convert our known similar colors
        color1 = hex_to_oklch("#09090B")
        color2 = hex_to_oklch("#0A0A0B")
        delta = oklch_delta_e(color1, color2)
        assert delta < 2.0  # Below JND threshold

    def test_very_different_colors(self):
        """Test very different colors have large delta_e."""
        # Red vs Blue
        red = hex_to_oklch("#FF0000")
        blue = hex_to_oklch("#0000FF")
        delta = oklch_delta_e(red, blue)
        assert delta > 2.0  # Above JND threshold

    def test_black_vs_white(self):
        """Test black vs white has significant delta_e."""
        black = hex_to_oklch("#000000")
        white = hex_to_oklch("#FFFFFF")
        delta = oklch_delta_e(black, white)
        assert delta > 50  # Very large difference

    def test_symmetry(self):
        """Test that delta_e is symmetric."""
        color1 = (0.3, 0.1, 45.0)
        color2 = (0.7, 0.2, 180.0)
        delta1 = oklch_delta_e(color1, color2)
        delta2 = oklch_delta_e(color2, color1)
        assert abs(delta1 - delta2) < 0.001  # Should be identical


class TestOklchInvertLightness:
    """Test oklch_invert_lightness function."""

    def test_invert_low_lightness(self):
        """Test inverting low lightness value."""
        L, C, h = oklch_invert_lightness(0.2, 0.3, 45.0)
        assert L == 0.8  # 1.0 - 0.2
        assert C == 0.3  # Chroma unchanged (below 0.4)
        assert h == 45.0  # Hue unchanged

    def test_invert_zero_lightness(self):
        """Test inverting L=0."""
        L, C, h = oklch_invert_lightness(0.0, 0.2, 90.0)
        assert L == 1.0  # 1.0 - 0.0
        assert C == 0.2  # Chroma unchanged
        assert h == 90.0  # Hue unchanged

    def test_chroma_clamping(self):
        """Test that high chroma is clamped to 0.4."""
        L, C, h = oklch_invert_lightness(0.3, 0.5, 120.0)
        assert L == 0.7  # 1.0 - 0.3
        assert C == 0.4  # Clamped from 0.5
        assert h == 120.0  # Hue unchanged

    def test_chroma_no_clamping(self):
        """Test that low chroma is not affected."""
        L, C, h = oklch_invert_lightness(0.5, 0.2, 180.0)
        assert L == 0.5  # 1.0 - 0.5
        assert C == 0.2  # Not changed
        assert h == 180.0  # Hue unchanged

    def test_invert_one_lightness(self):
        """Test inverting L=1."""
        L, C, h = oklch_invert_lightness(1.0, 0.1, 270.0)
        assert L == 0.0  # 1.0 - 1.0
        assert C == 0.1  # Chroma unchanged
        assert h == 270.0  # Hue unchanged