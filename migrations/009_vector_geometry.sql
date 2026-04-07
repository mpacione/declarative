-- Add vector geometry columns for SVG path data from VECTOR/BOOLEAN_OPERATION nodes.
-- fillGeometry and strokeGeometry store the raw Figma path data as JSON arrays.

ALTER TABLE nodes ADD COLUMN fill_geometry TEXT;
ALTER TABLE nodes ADD COLUMN stroke_geometry TEXT;
