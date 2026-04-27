-- Migration 019: add compositional_role to screen_component_instances.
--
-- M7.0.d — Alexander's "forces" guard. A classifier tells us WHAT a
-- node is (a button, a card); forces labeling tells us WHAT IT IS
-- DOING THERE (main-cta in login-form, avatar in list-item).
--
-- The same pattern applied with different forces produces different
-- concrete forms, so synthesis needs the forces label to pick a
-- donor that matches the target *role*, not just the type. This
-- column feeds M7.6 S4 composition: "I need a main-cta" retrieves
-- instances with matching compositional_role, not every button ever.
--
-- Format: flat string, canonical shape `<role> in <context>`
-- (e.g. "main-cta in login-form"). Nullable; unset means not yet
-- labeled. The labeling is intentionally incremental — we don't
-- label 49K rows up front; we label the subset of interesting
-- canonical_types on demand.
--
-- Run: sqlite3 your.declarative.db < migrations/019_forces_compositional_role.sql

ALTER TABLE screen_component_instances
    ADD COLUMN compositional_role TEXT;
