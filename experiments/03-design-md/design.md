# design.md — Dank (Experimental)

Auto-generated from `/Users/mattpacione/declarative-build/Dank-EXP-02.declarative.db` on 2026-04-16T22:53:49Z.

- File key: `drxXOUOdYEBBQ09mrXJeYu`
- Screens: 338
- Nodes: 86766
- CKR size (distinct component keys): 129
- Generator: `experiments/03-design-md/generator.py` (pre-dd/ v0.1)

This file is an auto-extractable subset of the design system. Sections marked TODO require a human designer. The rest is mined directly from the MLIR database.

## Component inventory

Auto-extracted from `component_key_registry`. Each row is one shared component used at least once in the corpus. The "typically ..." clause is mined from parent / sibling adjacencies. Where multiple CKR rows share a display name (distinct `component_key` values with the same Figma name), the short key suffix disambiguates them.

- `button/large/translucent` — used 3891 times. Commonly parented by button/toolbar (3884), (screen root) (7). Most frequent siblings: button/large/translucent (16851), Frame 419 (112), nav/top-nav (7).
- `icon/back` — used 3808 times. Commonly parented by button/small/translucent (1981), button/large/translucent (1826), button/large/solid (1). Most frequent siblings: Skip (1981), Buy Trophy (1827), icon/new (643).
- `button/small/translucent` — used 2604 times. Commonly parented by Right [FRAME] (1248), Left [FRAME] (832), Center [FRAME] (208). Most frequent siblings: button/small/translucent (9054), icon/more (1248), logo/dank (1040).
- `icon/chevron-down` — used 1181 times. Commonly parented by button/large/translucent (840), button/small/translucent (341). Most frequent siblings: Buy Trophy (825), Skip (341), icon/font (338).
- `icon/new` — used 849 times. Commonly parented by button/small/translucent (849). Most frequent siblings: Skip (849), icon/back (643), icon/panel-left (202).
- `button/small/solid` — used 837 times. Commonly parented by nav/tabs (836), field [FRAME] (1). Most frequent siblings: button/small/solid (2508), icon/qr-code (1), 0x59E17174D32...3Bef22 (1).
- `icon/wallet` — used 837 times. Commonly parented by button/small/solid (836), button/small/translucent (1). Most frequent siblings: Skip (837), icon/power (209), icon/mint (209).
- `icon/close` — used 799 times. Commonly parented by button/large/translucent (419), button/small/translucent (372), button/white (4). Most frequent siblings: Buy Trophy (424), Skip (374), icon/menu (279).
- `icon/font` — used 790 times. Commonly parented by button/large/translucent (742), Frame 399 [FRAME] (48). Most frequent siblings: Buy Trophy (727), icon/chevron-down (338), icon/close (265).
- `New Folder` — used 690 times. Commonly parented by right controls [FRAME] (414), left controls [FRAME] (276). Most frequent siblings: View Mode (552), Next (276), New Folder (276).
- `icon/delete` — used 685 times. Commonly parented by button/large/translucent (681), button/white (4). Most frequent siblings: Buy Trophy (685), icon/delete (306), icon/close (153).
- `icon/check` — used 616 times. Commonly parented by button/large/translucent (446), button/small/translucent (148), Frame 412 [FRAME] (18). Most frequent siblings: Buy Trophy (446), icon/check (306), Skip (150).
- `icon/checkbox-empty` — used 480 times. Commonly parented by Frame 292 [FRAME] (145), Frame 293 [FRAME] (145), Frame 398 [FRAME] (58). Most frequent siblings: message (432), Frame 399 (366), button/slider (66).
- `logo/dank` — used 417 times. Commonly parented by Center [FRAME] (208), Left [FRAME] (208), Frame 430 [FRAME] (1). Most frequent siblings: button/small/translucent (1040), nav/tabs (208), Titles (208).
- `icon/menu` — used 416 times. Commonly parented by button/small/translucent (416). Most frequent siblings: Skip (416), icon/close (279), icon/chevron-down (137).
- `_Key · bf9678a0` — used 319 times. Commonly parented by Top Row [FRAME] (110), Middle Row [FRAME] (99), Keys [FRAME] (77). Most frequent siblings: _Key (2310).
- `_KeyContainer · 72270805` — used 297 times. Commonly parented by _Key (297). Most frequent siblings: Letter (297).
- `a` — used 260 times. Commonly parented by Row 1 [FRAME] (100), Row 2 [FRAME] (90), Row 3 [FRAME] (70). Most frequent siblings: y (90), w (90), u (90).
- `icon/checkbox-filled` — used 257 times. Commonly parented by Frame 289 [FRAME] (219), Frame 271 [FRAME] (16), Frame 276 [FRAME] (9). Most frequent siblings: Frame 375 (34), Frame 289 (18), icon/brush-soft-square (10).
- `icon/folder` — used 242 times. Commonly parented by button/small/solid (209), Frame 267 [FRAME] (15), Frame 271 [FRAME] (9). Most frequent siblings: icon/wallet (209), Skip (209), Frame 375 (24).
- `icon/more · 21ade1ac` — used 238 times. Commonly parented by Frame 367 [FRAME] (200), Frame 271 [FRAME] (14), Frame 273 [FRAME] (9). Most frequent siblings: field title (200), Frame 375 (38), icon/tablet (20).
- `icon/mint` — used 217 times. Commonly parented by button/small/solid (209), button/large/translucent (7), Frame 426 [FRAME] (1). Most frequent siblings: icon/wallet (209), Skip (209), icon/forward (7).
- `icon/undo` — used 211 times. Commonly parented by button/small/translucent (204), Frame 357 [FRAME] (7). Most frequent siblings: icon/back (204), Skip (204), field title (14).
- `icon/fill` — used 210 times. Commonly parented by button/small/solid (209), Frame 425 [FRAME] (1). Most frequent siblings: icon/wallet (209), Skip (209), Workshop (1).
- `icon/power` — used 210 times. Commonly parented by button/small/solid (209), Frame 423 [FRAME] (1). Most frequent siblings: icon/wallet (209), Skip (209), Gym (1).
- `icon/edit · a32b9443` — used 208 times. Commonly parented by button/small/translucent (208). Most frequent siblings: Skip (208), icon/share (200), icon/switch (4).
- `icon/more · 4895e251` — used 208 times. Commonly parented by Right [FRAME] (208). Most frequent siblings: button/small/translucent (1248).
- `nav/tabs` — used 208 times. Commonly parented by Center [FRAME] (208). Most frequent siblings: logo/dank (208), button/small/translucent (208), Titles (208).
- `nav/top-nav` — used 207 times. Commonly parented by (screen root) (12). Most frequent siblings: button/toolbar (883), Overlay (166), ios/status-bar (137).
- `icon/text-style` — used 206 times. Commonly parented by button/large/translucent (206). Most frequent siblings: Buy Trophy (206), icon/text-style (116), icon/stroke (37).
- `icon/panel-left` — used 203 times. Commonly parented by button/small/translucent (203). Most frequent siblings: Skip (203), icon/new (202), icon/back (1).
- `icon/share` — used 203 times. Commonly parented by button/small/translucent (200), button/large/translucent (3). Most frequent siblings: icon/edit (200), Skip (200), icon/chevron-down (3).
- `icon/redo` — used 200 times. Commonly parented by button/small/translucent (200). Most frequent siblings: icon/back (200), Skip (200).
- `icon/send-forward` — used 189 times. Commonly parented by button/large/translucent (182), Frame 399 [FRAME] (7). Most frequent siblings: Buy Trophy (182), icon/delete (111), icon/back (71).
- `icon/rotate` — used 182 times. Commonly parented by button/large/translucent (182). Most frequent siblings: Buy Trophy (182), icon/delete (111), icon/back (71).
- `icon/ai` — used 164 times. Commonly parented by button/large/translucent (149), Frame 266 [FRAME] (15). Most frequent siblings: icon/back (149), Buy Trophy (149), Frame 375 (15).
- `icon/char` — used 158 times. Commonly parented by button/large/translucent (158). Most frequent siblings: icon/back (158), Buy Trophy (158).
- `icon/image` — used 158 times. Commonly parented by button/large/translucent (158). Most frequent siblings: icon/back (158), Buy Trophy (158).
- `icon/pencil` — used 158 times. Commonly parented by button/large/translucent (158). Most frequent siblings: icon/back (158), Buy Trophy (158).
- `icon/shape` — used 158 times. Commonly parented by button/large/translucent (158). Most frequent siblings: icon/back (158), Buy Trophy (158).
- `icon/text` — used 158 times. Commonly parented by button/large/translucent (158). Most frequent siblings: icon/back (158), Buy Trophy (158).
- `icon/smooth` — used 156 times. Commonly parented by button/large/translucent (99), Frame 399 [FRAME] (57). Most frequent siblings: icon/chevron-down (99), Buy Trophy (99).
- `Next` — used 138 times. Commonly parented by left controls [FRAME] (138). Most frequent siblings: Sidebar (138), Previous (138).
- `Home Indicator · 64e2079e` — used 137 times. Commonly parented by (screen root) (12). Most frequent siblings: button/toolbar (755), nav/top-nav (137), ios/status-bar (137).
- `ios/safari-nav` — used 137 times. Commonly parented by (screen root) (12). Most frequent siblings: button/toolbar (755), nav/top-nav (137), ios/status-bar (137).
- `ios/status-bar` — used 137 times. Commonly parented by (screen root) (12). Most frequent siblings: button/toolbar (755), nav/top-nav (137), ios/safari-nav (137).
- `icon/mirror-horiz` — used 125 times. Commonly parented by button/large/translucent (87), Frame 399 [FRAME] (38). Most frequent siblings: Buy Trophy (87), icon/back (71), icon/text-style (16).
- `Button 1` — used 120 times. Commonly parented by Button Set - Leading [INSTANCE] (60), Button Set - Trailing [INSTANCE] (60). Most frequent siblings: Button 6 (100), Button 5 (100), Button 4 (100).
- `icon/threshold` — used 101 times. Commonly parented by button/large/translucent (101). Most frequent siblings: icon/chevron-down (101), Buy Trophy (101).
- `icon/color-fill` — used 96 times. Commonly parented by button/large/translucent (96). Most frequent siblings: Buy Trophy (96), icon/back (95), icon/check (1).
- `icon/erase` — used 96 times. Commonly parented by button/large/translucent (96). Most frequent siblings: icon/back (96), Buy Trophy (96).
- `button/white` — used 91 times. Commonly parented by Frame 395 [FRAME] (46), card/sheet/success (20), card/modal (12). Most frequent siblings: button/white (58), Frame 265 (23), Frame 268 (19).
- `icon/shape-square` — used 88 times. Commonly parented by button/large/translucent (80), Frame 268 [FRAME] (4), Frame 399 [FRAME] (4). Most frequent siblings: icon/chevron-down (80), Buy Trophy (80), Frame 375 (4).
- `icon/comment-sml` — used 87 times. Commonly parented by button/white (87). Most frequent siblings: Buy Trophy (87), icon/forward (83), icon/delete (4).
- `icon/crop` — used 87 times. Commonly parented by button/large/translucent (87). Most frequent siblings: icon/back (87), Buy Trophy (87).
- `icon/forward · 6add5052` — used 87 times. Commonly parented by button/white (87). Most frequent siblings: Buy Trophy (87), icon/comment-sml (83), icon/close (4).
- `icon/remove-bg` — used 87 times. Commonly parented by button/large/translucent (87). Most frequent siblings: icon/back (87), Buy Trophy (87).
- `icon/lasso` — used 80 times. Commonly parented by button/large/translucent (80). Most frequent siblings: icon/back (80), Buy Trophy (80).
- `.icons/safari/lock` — used 71 times. Commonly parented by address [FRAME] (71). Most frequent siblings: apple.com (71).
- `icon/levels` — used 71 times. Commonly parented by button/large/translucent (71). Most frequent siblings: icon/back (71), Buy Trophy (71).
- `icon/pixel` — used 71 times. Commonly parented by Frame 399 [FRAME] (57), Frame 271 [FRAME] (14). Most frequent siblings: Frame 375 (14), icon/checkbox-empty (8), icon/checkbox-filled (6).
- `iOS/HomeIndicator` — used 70 times. Commonly parented by (screen root) (12). Most frequent siblings: button/toolbar (128), nav/top-nav (70), iOS/StatusBar (70).
- `iOS/StatusBar` — used 70 times. Commonly parented by (screen root) (12). Most frequent siblings: button/toolbar (128), nav/top-nav (70), iOS/HomeIndicator (70).
- `Safari - Bottom · 4986744d` — used 67 times. Commonly parented by (screen root) (12). Most frequent siblings: button/toolbar (128), nav/top-nav (67), iOS/StatusBar (67).
- `icon/chevron-right` — used 62 times. Commonly parented by Frame 271 [FRAME] (18), Frame 274 [FRAME] (13), Frame 273 [FRAME] (4). Most frequent siblings: Frame 375 (59), Frame 289 (32), icon/tablet (9).
- `icon/text-align-left` — used 62 times. Commonly parented by button/large/translucent (58), Frame 399 [FRAME] (4). Most frequent siblings: icon/back (58), Buy Trophy (58).
- `icon/tablet` — used 61 times. Commonly parented by Frame 271 [FRAME] (14), Frame 275 [FRAME] (9), Frame 382 [FRAME] (8). Most frequent siblings: message (32), Frame 375 (29), icon/more (20).
- `icon/stroke` — used 60 times. Commonly parented by button/large/translucent (60). Most frequent siblings: Buy Trophy (60), icon/text-style (37), icon/chevron-down (23).
- `icon/text-size` — used 58 times. Commonly parented by button/large/translucent (58). Most frequent siblings: icon/chevron-down (58), Buy Trophy (58).
- `.?123 · 4ae03351` — used 50 times. Commonly parented by Emoji and Numbers [FRAME] (20), Caps Lock [FRAME] (10), Shift [FRAME] (10). Most frequent siblings: Emoji (10), .?123 (10).
- `icon/shape-circle` — used 47 times. Commonly parented by button/large/translucent (43), Frame 399 [FRAME] (4). Most frequent siblings: icon/chevron-down (43), Buy Trophy (43).
- `icon/shape-prism` — used 47 times. Commonly parented by button/large/translucent (43), Frame 399 [FRAME] (4). Most frequent siblings: icon/chevron-down (43), Buy Trophy (43).
- `icon/wand` — used 46 times. Commonly parented by button/large/translucent (46). Most frequent siblings: icon/back (46), Buy Trophy (46).
- `_KeyContainer · a43dade2` — used 44 times. Commonly parented by _Key (44). Most frequent siblings: Letter (22), Union (11), Shift Inactive (11).
- `icon/brush-solid-round` — used 44 times. Commonly parented by Frame 399 [FRAME] (40), Frame 285 [FRAME] (4). Most frequent siblings: message (4), icon/checkbox-empty (4).
- `icon/phone` — used 40 times. Commonly parented by Frame 268 [FRAME] (15), Frame 274 [FRAME] (9), Frame 276 [FRAME] (8). Most frequent siblings: Frame 375 (32), icon/chevron-right (9), message (8).
- `icon/mirror-vert` — used 38 times. Commonly parented by Frame 399 [FRAME] (38).
- `icon/color-stroke` — used 37 times. Commonly parented by button/large/translucent (37). Most frequent siblings: icon/back (37), Buy Trophy (37).
- `icon/radius` — used 37 times. Commonly parented by button/large/translucent (37). Most frequent siblings: icon/text-style (37), Buy Trophy (37).
- `.?123 · b17883a5` — used 30 times. Commonly parented by Delete [FRAME] (10), Dictation + Space + Numbers [FRAME] (10), Shift [FRAME] (10). Most frequent siblings: Space (10), Dictation (10).
- `icon/opacity` — used 23 times. Commonly parented by button/large/translucent (23). Most frequent siblings: icon/chevron-down (23), Buy Trophy (23).
- `icon/spray` — used 23 times. Commonly parented by button/large/translucent (23). Most frequent siblings: icon/chevron-down (23), Buy Trophy (23).
- `!,` — used 20 times. Commonly parented by Row 3 [FRAME] (20). Most frequent siblings: z (20), x (20), v (20).
- `icon/picker` — used 19 times. Commonly parented by button/small/translucent (19). Most frequent siblings: icon/back (19), Skip (19).
- `icon/brush-soft-square` — used 18 times. Commonly parented by Frame 271 [FRAME] (14), Frame 286 [FRAME] (4). Most frequent siblings: Frame 375 (14), icon/checkbox-filled (10), icon/checkbox-empty (8).
- `icon/file-image` — used 17 times. Commonly parented by Frame 271 [FRAME] (9), Frame 396 [FRAME] (8). Most frequent siblings: icon/more (9), Frame 375 (9), message (8).
- `icon/decap` — used 16 times. Commonly parented by button/large/translucent (16). Most frequent siblings: icon/back (16), Buy Trophy (16).
- `icon/list` — used 16 times. Commonly parented by button/small/translucent (16). Most frequent siblings: icon/back (16), Skip (16).
- `icon/options` — used 15 times. Commonly parented by button/small/translucent (15). Most frequent siblings: icon/back (15), Skip (15).
- `icon/grid-view` — used 13 times. Commonly parented by button/small/translucent (13). Most frequent siblings: icon/back (13), Skip (13).
- `HomeIndicator` — used 11 times. Commonly parented by ios/alpha-keyboard (11). Most frequent siblings: Keys (11), Emoji & Dictation (11), Bottom Row (11).
- `_Key · 3c65d9a8` — used 11 times. Commonly parented by Bottom Row [FRAME] (11). Most frequent siblings: _Key (11), Keys (11).
- `_Key · 88018dba` — used 11 times. Commonly parented by Bottom Row [FRAME] (11). Most frequent siblings: _Key (11), Keys (11).
- `Button Set - Leading` — used 10 times. Commonly parented by ios/keyboard-ipad-landscape (5), ios/keyboard-ipad-portrait (5). Most frequent siblings: Keyboard Layout (10), Home Indicator (10), Enter (10).
- `Button Set - Trailing` — used 10 times. Commonly parented by ios/keyboard-ipad-landscape (5), ios/keyboard-ipad-portrait (5). Most frequent siblings: Keyboard Layout (10), Home Indicator (10), Enter (10).
- `Dictation` — used 10 times. Commonly parented by Dictation + Space + Numbers [FRAME] (10). Most frequent siblings: Space (10), .?123 (10).
- `Enter` — used 10 times. Commonly parented by Enter [FRAME] (10).
- `Home Indicator · 2b31f453` — used 10 times. Commonly parented by ios/keyboard-ipad-landscape (5), ios/keyboard-ipad-portrait (5). Most frequent siblings: Keyboard Layout (10), Enter (10), Button Set - Trailing (10).
- `Keyboard Close` — used 10 times. Commonly parented by Keyboard Close [FRAME] (10).
- `Keyboard Layout` — used 10 times. Commonly parented by ios/keyboard-ipad-landscape (5), ios/keyboard-ipad-portrait (5). Most frequent siblings: Home Indicator (10), Enter (10), Button Set - Trailing (10).
- `icon/save` — used 10 times. Commonly parented by Frame 357 [FRAME] (7), button/large/translucent (3). Most frequent siblings: field title (14), icon/chevron-down (3), Buy Trophy (3).
- `ios/alpha-keyboard` — used 10 times. Commonly parented by (screen root) (10). Most frequent siblings: button/toolbar (20), nav/top-nav (10), iOS/StatusBar (10).
- `space` — used 10 times. Commonly parented by Space [FRAME] (10).
- `icon/camera` — used 8 times. Commonly parented by Frame 275 [FRAME] (8). Most frequent siblings: Frame 375 (8).
- `icon/search` — used 8 times. Commonly parented by button/small/translucent (8). Most frequent siblings: icon/back (8), Skip (8).
- `icon/stroke-1` — used 8 times. Commonly parented by Frame 399 [FRAME] (8).
- `icon/stroke-2` — used 8 times. Commonly parented by Frame 399 [FRAME] (8).
- `icon/stroke-3` — used 8 times. Commonly parented by Frame 399 [FRAME] (8).
- `icon/stroke-4` — used 8 times. Commonly parented by Frame 399 [FRAME] (8).
- `icon/forward · 8da5540e` — used 7 times. Commonly parented by button/large/translucent (7). Most frequent siblings: icon/mint (7), Buy Trophy (7).
- `icon/profile` — used 7 times. Commonly parented by button/small/translucent (7). Most frequent siblings: icon/back (7), Skip (7).
- `icon/send-back` — used 7 times. Commonly parented by Frame 399 [FRAME] (7).
- `icon/store` — used 7 times. Commonly parented by Frame 357 [FRAME] (7). Most frequent siblings: field title (14).
- `icon/edit · 6882038d` — used 5 times. Commonly parented by button/small/translucent (5). Most frequent siblings: icon/back (5), Skip (5).
- `icon/bottom` — used 4 times. Commonly parented by Frame 399 [FRAME] (4).
- `icon/brush-soft-round` — used 4 times. Commonly parented by Frame 275 [FRAME] (4). Most frequent siblings: message (4), icon/checkbox-empty (4).
- `icon/brush-solid-square` — used 4 times. Commonly parented by Frame 287 [FRAME] (4). Most frequent siblings: message (4), icon/checkbox-empty (4).
- `icon/middle` — used 4 times. Commonly parented by Frame 399 [FRAME] (4).
- `icon/switch` — used 4 times. Commonly parented by button/small/translucent (4). Most frequent siblings: icon/edit (4), Skip (4).
- `icon/template` — used 4 times. Commonly parented by Frame 267 [FRAME] (4). Most frequent siblings: Frame 375 (4).
- `icon/text-align-center` — used 4 times. Commonly parented by Frame 399 [FRAME] (4).
- `icon/text-align-justify` — used 4 times. Commonly parented by Frame 399 [FRAME] (4).
- `icon/text-align-right` — used 4 times. Commonly parented by Frame 399 [FRAME] (4).
- `icon/top` — used 4 times. Commonly parented by Frame 399 [FRAME] (4).
- `ios/keyboard-ipad-landscape` — used 4 times. Commonly parented by (screen root) (4). Most frequent siblings: button/toolbar (24), nav/top-nav (4), ios/status-bar (4).
- `ios/keyboard-ipad-portrait` — used 4 times. Commonly parented by (screen root) (4). Most frequent siblings: button/toolbar (24), nav/top-nav (4), ios/status-bar (4).
- `Safari - Bottom · 615ca5ae` — used 3 times. Commonly parented by (screen root) (3). Most frequent siblings: swimlane (3), nav/top-nav (3), iOS/StatusBar (3).
- `icon/expand` — used 3 times. Commonly parented by button/large/translucent (3). Most frequent siblings: icon/chevron-down (3), Buy Trophy (3).
- `icon/qr-code` — used 1 times. Commonly parented by field [FRAME] (1). Most frequent siblings: button/small/solid (1), 0x59E17174D32...3Bef22 (1).

## Token palette

Canonical `tokens` table is empty — clustering has not been run since the last restore. Palette pending `dd cluster`. Below is the observed raw-value census from `node_token_bindings` grouped by property class; treat it as a dry-run of what clustering will surface.

### Color

- `#000000` — used 33026 times
- `#FFFFFF` — used 7754 times
- `#09090B` — used 5870 times
- `#047AFF` — used 2227 times
- `#9EFF85` — used 1566 times
- `#D9FF40` — used 1566 times
- `#0000000D` — used 1106 times
- `#FF0000` — used 747 times
- `#007AFF` — used 690 times
- `#09090B80` — used 638 times
- `#00000005` — used 626 times
- `#3C3C4399` — used 552 times
- `#00000080` — used 422 times
- `#FFFFFF66` — used 414 times
- `#DADADA` — used 374 times
- _+61 more values omitted (long tail)_

### Spacing

- `0.7064197659492493 [itemSpacing]` — used 10 times
- `1.0 [itemSpacing]` — used 138 times
- `1.1518691778182983 [itemSpacing]` — used 10 times
- `2.0 [padding.top]` — used 144 times
- `2.0 [padding.bottom]` — used 138 times
- `2.0 [padding.right]` — used 30 times
- `2.0 [padding.left]` — used 30 times
- `3.0 [itemSpacing]` — used 276 times
- `4.0 [padding.left]` — used 1403 times
- `4.0 [padding.right]` — used 1299 times
- `4.0 [padding.top]` — used 1146 times
- `4.0 [padding.bottom]` — used 1146 times
- `4.0 [itemSpacing]` — used 565 times
- `4.178328037261963 [padding.top]` — used 2 times
- `4.178328037261963 [padding.right]` — used 2 times
- `4.178328037261963 [padding.left]` — used 2 times
- `4.178328037261963 [padding.bottom]` — used 2 times
- `4.178328037261963 [itemSpacing]` — used 1 times
- `4.458666801452637 [itemSpacing]` — used 71 times
- `5.0 [padding.top]` — used 138 times
- `5.0 [padding.bottom]` — used 138 times
- `6.0 [padding.bottom]` — used 182 times
- `6.0 [itemSpacing]` — used 93 times
- `6.0 [padding.right]` — used 11 times
- `6.0 [padding.left]` — used 10 times
- _+73 more values omitted (long tail)_

### Radius

- `10` — used 7595 times
- `1` — used 7225 times
- `2.5` — used 3992 times
- `3` — used 3621 times
- `2` — used 1901 times
- `16` — used 1781 times
- `0.1` — used 573 times
- `8` — used 498 times
- `100` — used 419 times
- `4.6` — used 341 times
- `4` — used 300 times
- `9.21495` — used 200 times
- `5.65136` — used 200 times
- `28` — used 169 times
- `7` — used 159 times
- _+23 more values omitted (long tail)_

### Effects

- `0 [effect.0.spread]` — used 812 times
- `0.0 [effect.0.offsetX]` — used 812 times
- `0.0 [effect.0.radius]` — used 812 times
- `30.0 [effect.2.radius]` — used 616 times
- `#00000059 [effect.0.color]` — used 400 times
- `#0000004D [effect.0.color]` — used 341 times
- `1.0 [effect.0.offsetY]` — used 341 times
- `0.0 [effect.1.offsetX]` — used 338 times
- `0.0 [effect.1.radius]` — used 338 times
- `20.0 [effect.0.radius]` — used 211 times
- `15.0 [effect.0.radius]` — used 209 times
- `#0000000D [effect.1.color]` — used 200 times
- `0.0 [effect.1.offsetY]` — used 200 times
- `0.7064197659492493 [effect.0.offsetY]` — used 200 times
- `1.1518691778182983 [effect.0.offsetY]` — used 200 times
- _+19 more values omitted (long tail)_

### Opacity (non-default)

- `0.20` — used 621 times
- `0.40` — used 347 times
- `0.30` — used 208 times
- `0.35` — used 71 times

## Typography scale

Each row is a distinct (family, weight, size, line-height) combo observed on TEXT nodes (13279 text nodes across 53 combos). Top 25 shown; long tail collapsed.

| Family | Weight | Size (px) | Line height | Count |
| --- | --- | --- | --- | --- |
| Inter Variable | 600 | 16 | auto | 6584 |
| SF Pro | 400 | 17 | 22 | 1380 |
| Inter Variable | 600 | 18 | auto | 894 |
| Inter Variable | 600 | 14 | auto | 536 |
| Inter Variable | 500 | 12 | auto | 398 |
| SF Pro Display | 300 | 26 | 34 | 286 |
| SF Pro | 510 | 12 | auto | 276 |
| Inter Variable | 600 | 18 | 24 | 212 |
| Inter Variable | 600 | 28 | auto | 209 |
| Inter | 500 | 18 | 22 | 208 |
| Inter Variable | 500 | 14 | 22 | 208 |
| Inter Variable | 600 | 18 | 22 | 208 |
| Inter Variable | 400 | 18 | 24 | 184 |
| SF Pro | 510 | 12 | 14 | 138 |
| SF Pro | 400 | 12.0091 | 15.5412 | 135 |
| SF Pro | 400 | 19.5818 | 25.3411 | 135 |
| SF Pro | 400 | 21.899 | auto | 135 |
| SF Pro | 400 | 35.7079 | auto | 135 |
| Inter Variable | 600 | 12 | auto | 130 |
| Inter Variable | 600 | 17 | auto | 114 |
| Inter Variable | 500 | 14 | 24 | 96 |
| Inter Variable | 500 | 12 | 24 | 80 |
| SF Pro Display | 400 | 14.3314 | auto | 71 |
| SF Pro Text | 600 | 16 | 21 | 71 |
| SF Pro | 400 | 13.7752 | auto | 45 |
| _+28 more combos_ | | | | 411 |

## Spacing rhythm

Observed 43303 numeric spacing values across 41 distinct magnitudes. **No strict grid detected** — the modal magnitudes (10 / 14) don't align with a conventional 4/8/16 px rhythm. Closest loose fit: **2px**. (coverage: 4px multiples = 24.1%, 8px multiples = 8.1%, 2px multiples = 91.1%).

### Most common spacing magnitudes

| Value (px) | Count | % of total |
| --- | --- | --- |
| 10 | 18633 | 43.0% |
| 14 | 8800 | 20.3% |
| 4 | 5559 | 12.8% |
| 16 | 1944 | 4.5% |
| 9 | 1328 | 3.1% |
| 12 | 1002 | 2.3% |
| 8 | 838 | 1.9% |
| 15 | 692 | 1.6% |
| 24 | 591 | 1.4% |
| 9.5 | 552 | 1.3% |
| 22 | 419 | 1.0% |
| 2 | 342 | 0.8% |
| 6 | 296 | 0.7% |
| 7 | 276 | 0.6% |
| 5 | 276 | 0.6% |
| 3 | 276 | 0.6% |
| 190 | 199 | 0.5% |
| 28 | 163 | 0.4% |
| 20 | 158 | 0.4% |
| 1 | 138 | 0.3% |

### Off-grid anomalies

Values that don't divide cleanly by the detected base grid. Could be intentional (nudged dividers, odd-pixel borders) or drift.

| Value (px) | Count |
| --- | --- |
| 9 | 1328 |
| 15 | 692 |
| 9.5 | 552 |
| 7 | 276 |
| 5 | 276 |
| 3 | 276 |
| 1 | 138 |
| 4.45867 | 71 |
| 16.1262 | 65 |
| 9.88988 | 65 |
| 19 | 32 |
| 23 | 11 |
| 1.15187 | 10 |
| 0.70642 | 10 |
| 4.17833 | 9 |
| _+8 more_ | — |

## Adjacencies

For each frequently-used container (parent that holds other shared components), the top internal child-type sequences are listed. Container titles use the CKR display name where available; child sequences use each node's `component_key` display name if it has one, otherwise a `<TYPE:name>` shorthand.

### `button/large/translucent` — 3907 instances

1. [icon/font, <TEXT:Buy Trophy>, icon/chevron-down] — 8% (323 / 3907)
2. [icon/font, <TEXT:Buy Trophy>, icon/close] — 7% (265 / 3907)
3. [icon/back, <TEXT:Buy Trophy>, icon/image] — 4% (158 / 3907)
4. [icon/back, <TEXT:Buy Trophy>, icon/shape] — 4% (158 / 3907)
5. [icon/back, <TEXT:Buy Trophy>, icon/text] — 4% (158 / 3907)

### `button/small/translucent` — 2605 instances

1. [icon/back, <TEXT:Skip>, icon/new] — 25% (643 / 2605)
2. [icon/menu, <TEXT:Skip>, icon/close] — 11% (279 / 2605)
3. [icon/back, <TEXT:Skip>, icon/chevron-down] — 8% (204 / 2605)
4. [icon/back, <TEXT:Skip>, icon/undo] — 8% (204 / 2605)
5. [icon/panel-left, <TEXT:Skip>, icon/new] — 8% (202 / 2605)

### `button/toolbar` — 926 instances

1. [button/large/translucent, button/large/translucent, button/large/translucent] — 39% (361 / 926)
2. [button/large/translucent, button/large/translucent] — 24% (225 / 926)
3. [button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent] — 16% (149 / 926)
4. [button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent] — 13% (117 / 926)
5. [button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent, button/large/translucent] — 5% (43 / 926)

### `button/small/solid` — 838 instances

1. [icon/mint, <TEXT:Skip>, icon/wallet] — 25% (209 / 838)
2. [icon/fill, <TEXT:Skip>, icon/wallet] — 25% (209 / 838)
3. [icon/folder, <TEXT:Skip>, icon/wallet] — 25% (209 / 838)
4. [icon/power, <TEXT:Skip>, icon/wallet] — 25% (209 / 838)
5. [icon/check, <TEXT:Skip>, icon/close] — 0% (2 / 838)

### `nav/tabs` — 209 instances

1. [button/small/solid, button/small/solid, button/small/solid, button/small/solid] — 100% (209 / 209)

### `Left` — 208 instances

1. [button/small/translucent, logo/dank, button/small/translucent, button/small/translucent, <TEXT:Title>, button/small/translucent] — 100% (208 / 208)

### `Center` — 208 instances

1. [<FRAME:Titles>, button/small/translucent, logo/dank, nav/tabs] — 100% (208 / 208)

### `Right` — 208 instances

1. [icon/more, button/small/translucent, button/small/translucent, button/small/translucent, button/small/translucent, button/small/translucent, button/small/translucent] — 100% (208 / 208)

### `left controls` — 138 instances

1. [Sidebar, Previous, Next] — 100% (138 / 138)

### `right controls` — 138 instances

1. [New Folder, View Mode, View Mode] — 100% (138 / 138)

### `button/white` — 91 instances

1. [icon/comment-sml, <TEXT:Buy Trophy>, icon/forward] — 91% (83 / 91)
2. [icon/close, <TEXT:Buy Trophy>, icon/forward] — 4% (4 / 91)
3. [icon/comment-sml, <TEXT:Buy Trophy>, icon/delete] — 4% (4 / 91)

### `Frame 271` — 60 instances

1. [icon/brush-soft-square, <FRAME:Frame 375>, icon/checkbox-filled] — 17% (10 / 60)
2. [icon/tablet, <FRAME:Frame 375>, icon/chevron-right] — 15% (9 / 60)
3. [icon/folder, <FRAME:Frame 375>, icon/chevron-right] — 15% (9 / 60)
4. [icon/file-image, <FRAME:Frame 375>, icon/more] — 15% (9 / 60)
5. [icon/pixel, <FRAME:Frame 375>, icon/checkbox-empty] — 13% (8 / 60)

## Screen archetypes

Screens clustered by their top-level structural fingerprint: the sequence of direct children of the screen root, with anonymous `FRAME`/`RECTANGLE` runs collapsed (`FRAME×3` means three contiguous unnamed frames). Named components are kept verbatim. `screen_component_instances` is empty in this DB, so this is a raw structural fingerprint, not a semantic-role one.

### 35 screens

Fingerprint (top-to-bottom z-order):

```
- FRAME x2
- RECTANGLE
- FRAME x6
- nav/top-nav
- Home Indicator
- ios/safari-nav
- ios/status-bar
```

Examples: `iPad Pro 11" - 12`, `iPad Pro 11" - 13`, `iPad Pro 11" - 14`, `iPad Pro 11" - 15`, `iPad Pro 11" - 16`, `iPad Pro 11" - 17` _and 29 more_

### 25 screens

Fingerprint (top-to-bottom z-order):

```
- FRAME x2
- RECTANGLE
- FRAME x7
- nav/top-nav
- Home Indicator
- ios/safari-nav
- ios/status-bar
```

Examples: `iPad Pro 12.9" - 19`, `iPad Pro 12.9" - 20`, `iPad Pro 12.9" - 21`, `iPad Pro 12.9" - 22`, `iPad Pro 12.9" - 23`, `iPad Pro 12.9" - 24` _and 19 more_

### 24 screens

Fingerprint (top-to-bottom z-order):

```
- FRAME
- RECTANGLE
- FRAME x8
- nav/top-nav
- Home Indicator
- ios/safari-nav
- ios/status-bar
```

Examples: `iPad Pro 12.9" - 18`, `iPad Pro 12.9" - 48`, `iPad Pro 12.9" - 50`, `iPad Pro 12.9" - 51`, `iPad Pro 12.9" - 52`, `iPad Pro 12.9" - 53` _and 18 more_

### 16 screens

Fingerprint (top-to-bottom z-order):

```
- FRAME
- RECTANGLE
- FRAME x6
- nav/top-nav
- Home Indicator
- ios/safari-nav
- ios/status-bar
```

Examples: `iPad Pro 12.9" - 7`, `iPad Pro 12.9" - 8`, `iPad Pro 12.9" - 9`, `iPad Pro 12.9" - 10`, `iPad Pro 12.9" - 11`, `iPad Pro 12.9" - 12` _and 10 more_

### 14 screens

Fingerprint (top-to-bottom z-order):

```
- FRAME x5
- Safari - Bottom
- iOS/HomeIndicator
- nav/top-nav
- iOS/StatusBar
```

Examples: `iPhone 13 Pro Max - 103`, `iPhone 13 Pro Max - 111`, `iPhone 13 Pro Max - 112`, `iPhone 13 Pro Max - 117`, `iPhone 13 Pro Max - 84`, `iPhone 13 Pro Max - 85` _and 8 more_

### 10 screens

Fingerprint (top-to-bottom z-order):

```
- FRAME
- RECTANGLE
- FRAME x7
- nav/top-nav
- Home Indicator
- ios/safari-nav
- ios/status-bar
```

Examples: `iPad Pro 12.9" - 69`, `iPad Pro 12.9" - 17`, `iPad Pro 12.9" - 31`, `iPad Pro 12.9" - 30`, `iPad Pro 12.9" - 32`, `iPad Pro 12.9" - 35` _and 4 more_

### 8 screens

Fingerprint (top-to-bottom z-order):

```
- FRAME x2
- RECTANGLE
- FRAME
- nav/top-nav
- Home Indicator
- ios/safari-nav
- ios/status-bar
```

Examples: `iPad Pro 11" - 4`, `iPad Pro 11" - 5`, `iPad Pro 11" - 6`, `iPad Pro 11" - 7`, `iPad Pro 11" - 8`, `iPad Pro 11" - 9` _and 2 more_

## Missing / gaps

Canonical component types from the 48-type catalog (`dd/catalog.py`) that have **no matching Figma Component** (CKR entry) in this file. The "loose" column also scans raw node names — entries that exist as bare frames but have not been componentised. The synthesis LLM should treat *missing-in-CKR* as "compose from primitives" and *present-as-name-only* as "copy from these frames".

- Catalog size: **48**
- Present as shared component (CKR): **9**
- Absent from CKR but present as raw node name: **3**
- Fully absent (not in CKR, not in raw names): **36**

| Canonical type | Category | In CKR? | In raw names? |
| --- | --- | --- | --- |
| `accordion` | navigation | — | — |
| `alert` | feedback_and_status | — | — |
| `avatar` | content_and_display | — | — |
| `badge` | content_and_display | — | — |
| `bottom_nav` | navigation | — | — |
| `breadcrumbs` | navigation | — | — |
| `button` | actions | yes | yes |
| `button_group` | actions | — | — |
| `card` | content_and_display | — | yes |
| `checkbox` | selection_and_input | yes | yes |
| `combobox` | selection_and_input | — | — |
| `context_menu` | actions | — | — |
| `date_picker` | selection_and_input | — | — |
| `dialog` | containment_and_overlay | — | — |
| `drawer` | navigation | — | — |
| `empty_state` | content_and_display | — | — |
| `fab` | actions | — | — |
| `file_upload` | selection_and_input | — | — |
| `header` | navigation | — | — |
| `heading` | content_and_display | — | — |
| `icon` | content_and_display | yes | yes |
| `icon_button` | actions | — | — |
| `image` | content_and_display | yes | yes |
| `link` | content_and_display | — | — |
| `list` | content_and_display | yes | yes |
| `list_item` | content_and_display | — | — |
| `menu` | actions | yes | yes |
| `navigation_row` | navigation | — | — |
| `pagination` | navigation | — | — |
| `popover` | containment_and_overlay | — | — |
| `radio` | selection_and_input | — | — |
| `radio_group` | selection_and_input | — | — |
| `search_input` | selection_and_input | — | — |
| `segmented_control` | selection_and_input | — | — |
| `select` | selection_and_input | — | — |
| `sheet` | containment_and_overlay | — | yes |
| `skeleton` | content_and_display | — | — |
| `slider` | selection_and_input | — | yes |
| `stepper` | navigation | — | — |
| `table` | content_and_display | yes | yes |
| `tabs` | navigation | yes | yes |
| `text` | content_and_display | yes | yes |
| `text_input` | selection_and_input | — | — |
| `textarea` | selection_and_input | — | — |
| `toast` | feedback_and_status | — | — |
| `toggle` | selection_and_input | — | — |
| `toggle_group` | selection_and_input | — | — |
| `tooltip` | feedback_and_status | — | — |

## Designer-authored sections (TODO)

### Voice
TODO: describe the design system's voice (playful, minimal, corporate, ...).

### Intent conventions
TODO: when to use `button/primary` vs `button/white`. Why.

### Exclusions
TODO: things the design system deliberately doesn't do (e.g., no dark mode yet).

### Style lineage
TODO: reference points and influences.
