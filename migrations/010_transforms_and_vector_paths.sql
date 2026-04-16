-- Add relativeTransform, local width/height override, OpenType features,
-- and vectorPaths columns for Plugin API-only fields that the initial
-- REST extraction cannot capture with round-trip fidelity.
--
-- relative_transform: [[a,b,e],[c,d,f]] 2x3 affine matrix in parent-local coords.
-- Rotation, skew, and parent-relative translation in one value. Required for
-- nested rotation preservation — absolute rotation from REST doesn't round-trip.
--
-- opentype_features: JSON array of 4-char OpenType feature tags, e.g. ["ss01","liga"].
-- REST only exposes the styled-range feature map under an API-specific key; this
-- column stores the Plugin API's authoritative list.
--
-- vector_paths: JSON array of {path, windingRule} — the authoring primitive
-- for VECTOR nodes. REST gives you fill/stroke geometries that are derived;
-- vectorPaths is the original. Required for SVG round-trip without resampling.

ALTER TABLE nodes ADD COLUMN relative_transform TEXT;
ALTER TABLE nodes ADD COLUMN opentype_features TEXT;
ALTER TABLE nodes ADD COLUMN vector_paths TEXT;
