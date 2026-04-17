# Sanity gate — 00d-mode3-v1

**Gate FAILS** — 11 broken / 1 partial / 0 ok (of 12).

> More than half the prompts render as categorically empty. Do not produce a human-rating template until the pipeline regresses this rate below 50%.

| slug | verdict | default_frame_ratio | visible_ratio | vlm |
|---|---|---|---|---|
| 01-login | broken | 0.00 | 0.78 | ok (8) |
| 02-profile-settings | partial | 0.09 | 0.82 | partial (5) |
| 03-meme-feed | broken | 0.18 | 0.52 | broken (2) |
| 04-dashboard | broken | 0.12 | 0.81 | broken (2) |
| 05-paywall | broken | 0.18 | 0.52 | broken (2) |
| 06-spa-minimal | broken | 0.18 | 0.60 | broken (3) |
| 07-search | broken | 0.40 | 0.57 | broken (2) |
| 08-explicit-structure | broken | 0.33 | 0.85 | broken (2) |
| 09-drawer-nav | broken | 0.86 | 0.00 | broken (1) |
| 10-onboarding-carousel | broken | 0.23 | 0.67 | broken (2) |
| 11-vague | broken | 0.41 | 0.68 | broken (2) |
| 12-round-trip-test | broken | 0.33 | 0.50 | broken (2) |
