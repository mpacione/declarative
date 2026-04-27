# M7.0.a Vision Stage Bake-Off — Per-Screen vs Cross-Screen

Generated: 2026-04-19 17:36:20

**Cross-screen batches** (grouped by device_class + skeleton_type):

- [150, 151, 152, 153, 154]
- [155, 156, 157, 158, 159]

## Summary

- Per-screen total classifications: **195**
- Cross-screen total classifications: **195**
- Common keys (scored for agreement): **195**
- Agreements: **145**
- Disagreements: **50**
- **Agreement rate: 74.4%**


## Type distribution (common keys only)

| canonical_type | per-screen | cross-screen |
|---|---:|---:|
| `button` | 0 | 1 |
| `button_group` | 5 | 0 |
| `card` | 11 | 4 |
| `container` | 55 | 73 |
| `dialog` | 1 | 0 |
| `header` | 8 | 10 |
| `heading` | 2 | 5 |
| `icon` | 5 | 0 |
| `image` | 43 | 31 |
| `list_item` | 18 | 22 |
| `search_input` | 10 | 10 |
| `skeleton` | 12 | 24 |
| `tabs` | 4 | 5 |
| `text` | 21 | 10 |

## Disagreements

| screen | node | per-screen | conf | cross-screen | conf | ps reason / cs reason |
|---|---|---|---:|---|---:|---|
| 150 | 10043 | `card` | 0.72 | `container` | 0.85 | _ps:_ Named 'artboard', large bounded vertical container (720×740) with 2 child frames <br>_cs:_ Named 'artboard' with VERTICAL layout and 2 FRAME children — a structural canvas |
| 150 | 10131 | `text` | 0.85 | `tabs` | 0.78 | _ps:_ Named 'Titles' with sample text 'Feed', vertical layout with 2 text children — a <br>_cs:_ Named 'Titles' with sample_text 'Feed', VERTICAL layout with 2 TEXT children ins |
| 151 | 10286 | `list_item` | 0.82 | `button` | 0.78 | _ps:_ Named 'Frame 268', same structure as Frame 266/267 — horizontal layout with FRAM <br>_cs:_ Named 'Frame 268', horizontal layout with 2 children (FRAME + INSTANCE), parent= |
| 151 | 10444 | `button_group` | 0.80 | `container` | 0.80 | _ps:_ Named 'Right' inside a header with 7 INSTANCE children in a horizontal layout —  <br>_cs:_ Named 'Right' inside a header with 7 INSTANCE children — structural grouping of  |
| 151 | 10488 | `icon` | 0.82 | `container` | 0.75 | _ps:_ Named 'grabber' with 3 ellipse children in a horizontal layout — classic iOS sta <br>_cs:_ Named 'grabber' with 3 ELLIPSE children — the three-dot status bar indicator (el |
| 151 | 10492 | `container` | 0.80 | `header` | 0.88 | _ps:_ Named 'title and controls', horizontal layout with 3 FRAME children spanning the <br>_cs:_ Named 'title and controls', horizontal layout with 3 FRAME children — the Safari |
| 151 | 10493 | `button_group` | 0.78 | `container` | 0.82 | _ps:_ Named 'left controls' with horizontal layout and 3 INSTANCE children — a cluster <br>_cs:_ Named 'left controls' with 3 INSTANCE children — structural grouping of the left |
| 151 | 10506 | `button_group` | 0.78 | `container` | 0.82 | _ps:_ Named 'right controls', horizontal layout with 3 INSTANCE children — a cluster o <br>_cs:_ Named 'right controls' with 3 INSTANCE children — structural grouping of the rig |
| 151 | 10517 | `text` | 0.85 | `container` | 0.80 | _ps:_ Named 'Right' in the status bar area with sample text '100%', children include G <br>_cs:_ Named 'Right' in the status bar with sample_text '100%' — battery/signal groupin |
| 152 | 10536 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 350', child of a container, no described children beyond its boundi <br>_cs:_ Named 'Frame 350', 200×140, parent=container — placeholder tile in a content gri |
| 152 | 10537 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 351', same dimensions (200×140) and container parent as Frame 350 s <br>_cs:_ Named 'Frame 351', 200×140, parent=container — placeholder tile in content grid. |
| 152 | 10538 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 352', same 200×140 dimensions and grid container parent as other Fr <br>_cs:_ Named 'Frame 352', 200×140, parent=container — placeholder tile in content grid. |
| 152 | 10539 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 353', same 200×140 dimensions and grid container parent as other Fr <br>_cs:_ Named 'Frame 353', 200×140, parent=container — placeholder tile in content grid. |
| 152 | 10547 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 350', identical size and parent type as node 10536 — same repeating <br>_cs:_ Named 'Frame 350', 200×140, parent=container — placeholder tile in a content gri |
| 152 | 10548 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 351', same repeating grid pattern of 200×140 thumbnail frames. <br>_cs:_ Named 'Frame 351', 200×140, parent=container — placeholder tile in content grid. |
| 152 | 10549 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 352', repeating 200×140 thumbnail frame in grid layout. <br>_cs:_ Named 'Frame 352', 200×140, parent=container — placeholder tile in content grid. |
| 152 | 10550 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 353', repeating 200×140 thumbnail frame in grid layout. <br>_cs:_ Named 'Frame 353', 200×140, parent=container — placeholder tile in content grid. |
| 152 | 10558 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 350', identical size and parent type — third in a column of same-si <br>_cs:_ Named 'Frame 350', 200×140, parent=container — placeholder tile in a content gri |
| 152 | 10559 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 351', third in the column of same-sized thumbnail frames. <br>_cs:_ Named 'Frame 351', 200×140, parent=container — placeholder tile in content grid. |
| 152 | 10560 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 352', third in the column — same repeating grid thumbnail pattern. <br>_cs:_ Named 'Frame 352', 200×140, parent=container — placeholder tile in content grid. |
| 152 | 10561 | `image` | 0.75 | `skeleton` | 0.85 | _ps:_ Named 'Frame 353', third in the column — same repeating grid thumbnail pattern. <br>_cs:_ Named 'Frame 353', 200×140, parent=container — placeholder tile in content grid. |
| 152 | 10658 | `tabs` | 0.78 | `container` | 0.80 | _ps:_ Named 'Center' in a header parent, horizontal layout with 4 children (1 FRAME +  <br>_cs:_ Named 'Center' inside a header, horizontal layout — structural grouping for the  |
| 152 | 10659 | `text` | 0.85 | `tabs` | 0.78 | _ps:_ Named 'Titles', vertical layout with 2 TEXT children and sample text 'Feed' — a  <br>_cs:_ Named 'Titles' with sample_text 'Feed', VERTICAL layout with 2 TEXT children in  |
| 152 | 10751 | `button_group` | 0.75 | `container` | 0.82 | _ps:_ Named 'left controls', horizontal layout with 3 INSTANCE children — a grouped se <br>_cs:_ Named 'left controls' with 3 INSTANCE children — structural grouping of left bro |
| 152 | 10764 | `button_group` | 0.75 | `container` | 0.82 | _ps:_ Named 'right controls', horizontal layout with 3 INSTANCE children on the right  <br>_cs:_ Named 'right controls' with 3 INSTANCE children — structural grouping of right b |
| 153 | 10785 | `card` | 0.72 | `container` | 0.85 | _ps:_ Named 'artboard', VERTICAL layout with 2 FRAME children, bounded container group <br>_cs:_ Named 'artboard' with VERTICAL layout and 2 FRAME children — structural canvas/e |
| 153 | 11016 | `text` | 0.85 | `container` | 0.80 | _ps:_ Named 'Right', contains GROUP, TEXT, and VECTOR children with sample text '100%' <br>_cs:_ Named 'Right' in status bar with sample_text '100%' — iOS status bar right group |
| 154 | 11026 | `card` | 0.72 | `container` | 0.85 | _ps:_ Named 'artboard' with a VERTICAL layout containing 2 FRAME children inside a scr <br>_cs:_ Named 'artboard' with VERTICAL layout and 2 FRAME children — structural canvas/e |
| 154 | 11206 | `icon` | 0.85 | `container` | 0.75 | _ps:_ Named 'grabber' with 3 ELLIPSE children arranged horizontally (classic three-dot <br>_cs:_ Named 'grabber' with 3 ELLIPSE children — three-dot status bar indicator. |
| 154 | 11235 | `text` | 0.87 | `container` | 0.80 | _ps:_ Named 'Right' in the status bar region with sample text '100%' (battery percenta <br>_cs:_ Named 'Right' in status bar with sample_text '100%' — iOS status bar right group |
| 155 | 11245 | `card` | 0.82 | `container` | 0.85 | _ps:_ Named 'artboard' with VERTICAL layout containing 2 child FRAMEs; positioned as a <br>_cs:_ Named 'artboard', vertical layout frame with 2 child frames — a structural canva |
| 155 | 11338 | `container` | 0.85 | `list_item` | 0.75 | _ps:_ Named 'Left' inside a header parent, HORIZONTAL layout with 5 INSTANCE children  <br>_cs:_ Named 'Left', horizontal layout with 5 instances and a TEXT child reading 'Filen |
| 155 | 11463 | `icon` | 0.88 | `container` | 0.72 | _ps:_ Named 'grabber' with 3 ELLIPSE children arranged horizontally — a classic three- <br>_cs:_ Named 'grabber', horizontal layout with 3 ellipses — the three-dot grabber/drag  |
| 156 | 11502 | `card` | 0.82 | `container` | 0.85 | _ps:_ Named 'artboard', it is a bounded vertical container with 2 child frames sitting <br>_cs:_ Named 'artboard', vertical layout frame with 2 child frames — same structural ca |
| 156 | 11595 | `container` | 0.85 | `list_item` | 0.75 | _ps:_ Named 'Left', it is a horizontal layout group inside a header containing 5 insta <br>_cs:_ Named 'Left' with sample_text 'Filename', horizontal layout with 5 INSTANCEs and |
| 157 | 11759 | `card` | 0.72 | `container` | 0.85 | _ps:_ Named 'artboard' with VERTICAL layout and 2 child FRAMEs; bounded container grou <br>_cs:_ Named 'artboard', vertical layout with 2 child frames — structural meme canvas c |
| 157 | 11862 | `container` | 0.80 | `list_item` | 0.75 | _ps:_ Named 'Left' as a child of a header bar, HORIZONTAL layout with 5 INSTANCEs and  <br>_cs:_ Named 'Left' with 'Filename' text in header — file breadcrumb row, same as scree |
| 157 | 11895 | `text` | 0.88 | `heading` | 0.80 | _ps:_ Named 'Titles' with VERTICAL layout, 2 TEXT children, and sample text 'Feed' — a <br>_cs:_ Named 'Titles' with sample_text 'Feed', 2 TEXT children — page title in header c |
| 157 | 11987 | `icon` | 0.82 | `container` | 0.72 | _ps:_ Named 'grabber' with 3 ELLIPSE children in a HORIZONTAL layout — classic three-d <br>_cs:_ Named 'grabber' with 3 ellipses — three-dot drag handle, same pattern as screens |
| 157 | 11991 | `container` | 0.82 | `header` | 0.85 | _ps:_ Named 'title and controls', HORIZONTAL layout with 3 FRAMEs — a structural group <br>_cs:_ Named 'title and controls', horizontal with 3 FRAMEs — browser toolbar row, same |
| 157 | 12016 | `text` | 0.85 | `container` | 0.80 | _ps:_ Named 'Right' in the status bar area with sample text '100%' and children includ <br>_cs:_ Named 'Right' with '100%' text — iOS status bar battery/signal zone, same as scr |
| 158 | 12026 | `card` | 0.82 | `container` | 0.85 | _ps:_ Bounded vertical container (720×740) with 2 child frames, positioned in the cont <br>_cs:_ Named 'artboard', vertical layout with 2 child frames — structural meme canvas c |
| 158 | 12129 | `container` | 0.80 | `list_item` | 0.75 | _ps:_ Horizontal layout labeled 'Left' with 6 children (5 instances + 1 text 'Filename <br>_cs:_ Named 'Left' with 'Filename' text in header — file breadcrumb row, same as previ |
| 158 | 12162 | `text` | 0.88 | `heading` | 0.80 | _ps:_ Vertical layout named 'Titles' with 2 text children and sample text 'Feed' — a s <br>_cs:_ Named 'Titles' with sample_text 'Feed', 2 TEXT children — page title in header c |
| 158 | 12283 | `text` | 0.88 | `container` | 0.80 | _ps:_ Horizontal frame labeled 'Right' in the status bar area with group, text '100%', <br>_cs:_ Named 'Right' with '100%' text — iOS status bar right zone, same as previous scr |
| 159 | 12293 | `dialog` | 0.88 | `container` | 0.85 | _ps:_ A large vertical-layout frame (720×740) labeled 'artboard' containing a file pic <br>_cs:_ Named 'artboard', vertical layout with 2 child frames — structural meme canvas c |
| 159 | 12461 | `container` | 0.82 | `list_item` | 0.75 | _ps:_ Labeled 'Left' with horizontal layout inside a header, containing 5 instances an <br>_cs:_ Named 'Left' with 'Filename' text in header — file breadcrumb row, same as previ |
| 159 | 12494 | `text` | 0.88 | `heading` | 0.80 | _ps:_ Named 'Titles', vertical layout with 2 TEXT children, sample text 'Feed' — a sma <br>_cs:_ Named 'Titles' with sample_text 'Feed', 2 TEXT children — page title in header c |
| 159 | 12586 | `icon` | 0.85 | `container` | 0.72 | _ps:_ Named 'grabber' with 3 ELLIPSE children in a horizontal layout — a classic three <br>_cs:_ Named 'grabber' with 3 ellipses — three-dot drag handle, same pattern as previou |
| 159 | 12615 | `text` | 0.88 | `container` | 0.80 | _ps:_ Named 'Right' in status bar area, contains GROUP, TEXT, and VECTOR children with <br>_cs:_ Named 'Right' with '100%' text — iOS status bar right zone, same as previous scr |

## Cross-screen evidence cited (sample)

When cross-screen mode references other screens' nodes as supporting/contrasting evidence.

| screen | node | type | evidence |
|---|---|---|---|
| 150 | 10043 | `container` | s153/n10785:same_component; s154/n11026:same_component |
| 150 | 10053 | `image` | s153/n10795:same_component; s154/n11036:same_component |
| 150 | 10098 | `container` | s151/n10368:same_component; s152/n10626:same_component; s153/n10862:same_component; s154/n11081:same_component |
| 150 | 10109 | `image` | s151/n10379:same_component; s152/n10637:same_component; s153/n10873:same_component; s154/n11092:same_component |
| 150 | 10130 | `container` | s151/n10400:same_component; s152/n10658:same_component; s153/n10894:same_component; s154/n11113:same_component |
| 150 | 10131 | `tabs` | s151/n10401:same_component; s152/n10659:same_component; s153/n10895:same_component; s154/n11114:same_component |
| 150 | 10143 | `image` | s151/n10413:same_component; s152/n10671:same_component; s153/n10907:same_component; s154/n11126:same_component |
| 150 | 10174 | `container` | s151/n10444:same_component; s152/n10702:same_component; s153/n10938:same_component; s154/n11157:same_component |
| 150 | 10223 | `container` | s151/n10488:same_component; s152/n10746:same_component; s153/n10987:same_component; s154/n11206:same_component |
| 150 | 10227 | `header` | s151/n10492:same_component; s152/n10750:same_component; s153/n10991:same_component; s154/n11210:same_component |
| 150 | 10228 | `container` | s151/n10493:same_component; s152/n10751:same_component; s153/n10992:same_component; s154/n11211:same_component |
| 150 | 10235 | `search_input` | s151/n10500:same_component; s152/n10758:same_component; s153/n10999:same_component; s154/n11218:same_component |
| 150 | 10241 | `container` | s151/n10506:same_component; s152/n10764:same_component; s153/n11005:same_component; s154/n11224:same_component |
| 150 | 10249 | `text` | s151/n10514:same_component; s152/n10772:same_component; s153/n11013:same_component; s154/n11232:same_component |
| 150 | 10252 | `container` | s151/n10517:same_component; s152/n10775:same_component; s153/n11016:same_component; s154/n11235:same_component |
| 151 | 10272 | `list_item` | s151/n10280:same_variant_family; s151/n10286:same_variant_family |
| 151 | 10280 | `list_item` | s151/n10272:same_variant_family; s151/n10286:same_variant_family |
| 151 | 10286 | `button` | s151/n10272:same_variant_family |
| 151 | 10309 | `skeleton` | s151/n10310:same_variant_family; s151/n10311:same_variant_family; s151/n10312:same_variant_family |
| 151 | 10310 | `skeleton` | s151/n10309:same_variant_family |
| 151 | 10311 | `skeleton` | s151/n10309:same_variant_family |
| 151 | 10312 | `skeleton` | s151/n10309:same_variant_family |
| 151 | 10320 | `skeleton` | s151/n10309:same_variant_family |
| 151 | 10321 | `skeleton` | s151/n10309:same_variant_family |
| 151 | 10322 | `skeleton` | s151/n10309:same_variant_family |

## Confidence calibration (on agreements)

- Avg per-screen confidence (agreements): 0.844
- Avg cross-screen confidence (agreements): 0.832
- Delta: -0.012

## Decision gate

- Agreement rate **74.4% < 85%**: cross-screen is diverging substantially from per-screen. Node tracking across images may be breaking down at this batch size. Fall back to per-screen (N=1) for the full corpus — it costs the same at Sonnet rates anyway.