# M7.0.a Vision Stage Bake-Off — Per-Screen vs Cross-Screen

Generated: 2026-04-19 18:11:47

**Cross-screen batches** (grouped by device_class + skeleton_type):

- [150, 151, 152, 153, 154]
- [155, 156, 157, 158, 159]

## Summary

- Per-screen total classifications: **195**
- Cross-screen total classifications: **195**
- Common keys (scored for agreement): **195**
- Agreements: **150**
- Disagreements: **45**
- **Agreement rate: 76.9%**


## Type distribution (common keys only)

| canonical_type | per-screen | cross-screen |
|---|---:|---:|
| `button_group` | 24 | 25 |
| `card` | 11 | 7 |
| `container` | 28 | 45 |
| `dialog` | 1 | 5 |
| `header` | 10 | 5 |
| `heading` | 2 | 5 |
| `icon` | 10 | 10 |
| `image` | 31 | 31 |
| `list_item` | 18 | 23 |
| `search_input` | 10 | 10 |
| `skeleton` | 24 | 24 |
| `tabs` | 4 | 0 |
| `text` | 22 | 5 |

## Disagreements

| screen | node | per-screen | conf | cross-screen | conf | ps reason / cs reason |
|---|---|---|---:|---|---:|---|
| 150 | 10131 | `tabs` | 0.76 | `container` | 0.80 | _ps:_ Named 'Titles', vertical layout with 2 TEXT children and sample text 'Feed' — li <br>_cs:_ Named 'Titles', vertical layout with 2 TEXT children showing 'Feed' — a small la |
| 150 | 10174 | `button_group` | 0.85 | `container` | 0.85 | _ps:_ Named 'Right', child of header, contains 7 INSTANCE children arranged horizontal <br>_cs:_ Named 'Right', horizontal layout with 7 INSTANCE children inside the header — ri |
| 150 | 10227 | `header` | 0.88 | `container` | 0.85 | _ps:_ Named 'title and controls', spans full width at top of screen with 3 child frame <br>_cs:_ Named 'title and controls', horizontal layout with 3 FRAME children — structural |
| 150 | 10249 | `text` | 0.92 | `container` | 0.85 | _ps:_ Named 'Left', contains 2 TEXT children with sample text '9:41' — this is the sta <br>_cs:_ Named 'Left' inside the iOS status bar area, horizontal layout with 2 TEXT child |
| 150 | 10252 | `text` | 0.87 | `container` | 0.82 | _ps:_ Named 'Right', contains TEXT with sample '100%' plus battery/signal vectors — st <br>_cs:_ Named 'Right' in the status bar area, horizontal layout with 4 children showing  |
| 151 | 10400 | `tabs` | 0.82 | `container` | 0.85 | _ps:_ Named 'Center' inside a header, contains 4 children (FRAME + INSTANCE×3) with sa <br>_cs:_ Named 'Center', horizontal layout with 4 children inside header — center section |
| 151 | 10401 | `heading` | 0.87 | `container` | 0.80 | _ps:_ Named 'Titles' with vertical layout, 2 TEXT children, sample text 'Feed' — secti <br>_cs:_ Named 'Titles', vertical layout with 2 TEXT children showing 'Feed' — small labe |
| 151 | 10444 | `button_group` | 0.85 | `container` | 0.85 | _ps:_ Named 'Right' inside a header parent, contains 7 INSTANCE children — multiple ic <br>_cs:_ Named 'Right', horizontal layout with 7 INSTANCE children inside header — right  |
| 151 | 10492 | `header` | 0.88 | `container` | 0.85 | _ps:_ Named 'title and controls', horizontal layout with 3 FRAME children — this is th <br>_cs:_ Named 'title and controls', horizontal layout with 3 FRAME children — structural |
| 151 | 10514 | `text` | 0.93 | `container` | 0.85 | _ps:_ Named 'Left' inside status bar area, contains 2 TEXT children with sample text ' <br>_cs:_ Named 'Left' with 2 TEXT children showing '9:41' — left side of device status ba |
| 152 | 10658 | `tabs` | 0.82 | `container` | 0.85 | _ps:_ Named 'Center' inside the header with 4 children (FRAME + 3 INSTANCEs); position <br>_cs:_ Named 'Center', horizontal layout with 4 children inside header — center section |
| 152 | 10659 | `tabs` | 0.82 | `container` | 0.80 | _ps:_ Named 'Titles' with 2 TEXT children and sample text 'Feed' — label text grouping <br>_cs:_ Named 'Titles', vertical layout with 2 TEXT children showing 'Feed' — label grou |
| 152 | 10750 | `header` | 0.90 | `container` | 0.85 | _ps:_ Named 'title and controls' with 3 FRAME children (left controls, search bar, rig <br>_cs:_ Named 'title and controls', horizontal layout with 3 FRAME children — structural |
| 152 | 10772 | `text` | 0.92 | `container` | 0.85 | _ps:_ Named 'Left' inside the status bar area, 2 TEXT children with sample text '9:41' <br>_cs:_ Named 'Left' with 2 TEXT children showing '9:41' — left side of device status ba |
| 153 | 10895 | `text` | 0.88 | `container` | 0.80 | _ps:_ Named 'Titles' with sample_text 'Feed' and 2 TEXT children in VERTICAL layout —  <br>_cs:_ Named 'Titles', vertical layout with 2 TEXT children showing 'Feed' — label grou |
| 153 | 10938 | `button_group` | 0.87 | `container` | 0.85 | _ps:_ Named 'Right' inside the header parent, HORIZONTAL layout with 7 INSTANCE childr <br>_cs:_ Named 'Right', horizontal layout with 7 INSTANCE children inside header — right  |
| 153 | 10991 | `header` | 0.88 | `container` | 0.85 | _ps:_ Named 'title and controls', HORIZONTAL layout with 3 FRAME children spanning the <br>_cs:_ Named 'title and controls', horizontal layout with 3 FRAME children — structural |
| 153 | 11013 | `text` | 0.92 | `container` | 0.85 | _ps:_ Named 'Left' with sample_text '9:41' and 2 TEXT children; this is the time displ <br>_cs:_ Named 'Left' with 2 TEXT children showing '9:41' — left side of device status ba |
| 153 | 11016 | `text` | 0.88 | `container` | 0.82 | _ps:_ Named 'Right' with sample_text '100%' and children including TEXT and VECTOR (ba <br>_cs:_ Named 'Right' in status bar area with '100%' text — right side of device status  |
| 154 | 11114 | `text` | 0.85 | `container` | 0.80 | _ps:_ Named 'Titles' with VERTICAL layout and 2 TEXT children, sample_text 'Feed' — a  <br>_cs:_ Named 'Titles', vertical layout with 2 TEXT children showing 'Feed' — label grou |
| 154 | 11157 | `button_group` | 0.87 | `container` | 0.85 | _ps:_ Named 'Right' within the header, HORIZONTAL layout with 7 INSTANCE children — th <br>_cs:_ Named 'Right', horizontal layout with 7 INSTANCE children inside header — right  |
| 154 | 11210 | `header` | 0.88 | `container` | 0.85 | _ps:_ Named 'title and controls' spanning the full width at the top of the screen (826 <br>_cs:_ Named 'title and controls', horizontal layout with 3 FRAME children — structural |
| 154 | 11232 | `text` | 0.92 | `container` | 0.85 | _ps:_ Named 'Left' in a status bar context with sample_text '9:41' and 2 TEXT children <br>_cs:_ Named 'Left' with 2 TEXT children showing '9:41' — left side of device status ba |
| 154 | 11235 | `text` | 0.88 | `container` | 0.82 | _ps:_ Named 'Right' in a status bar context with sample_text '100%' and children inclu <br>_cs:_ Named 'Right' in status bar area with '100%' text — right side of device status  |
| 155 | 11245 | `card` | 0.82 | `dialog` | 0.88 | _ps:_ A bounded vertical container with 2 child frames forming the 'Add Image' modal p <br>_cs:_ A vertically-laid card-shaped overlay containing list items and a cancel button, |
| 155 | 11338 | `container` | 0.85 | `list_item` | 0.82 | _ps:_ Named 'Left' and positioned as a child of the header; contains 5 instances and 1 <br>_cs:_ Horizontal row inside a header with leading instances and trailing text 'Filenam |
| 155 | 11371 | `text` | 0.88 | `heading` | 0.88 | _ps:_ Named 'Titles' with 2 TEXT children and sample text 'Feed' — a small text label  <br>_cs:_ Vertical frame with two TEXT children labeled 'Feed', acting as a section title  |
| 155 | 11414 | `container` | 0.82 | `button_group` | 0.87 | _ps:_ Named 'Right' in the header, horizontal layout with 7 INSTANCE children — struct <br>_cs:_ Right zone of the app header bar containing 7 INSTANCE children (icon buttons: u |
| 156 | 11502 | `card` | 0.82 | `dialog` | 0.88 | _ps:_ Named 'artboard', it is a bounded vertical container with 2 child frames (canvas <br>_cs:_ Same 'Add Image' modal overlay pattern as screen 155 node 11245, vertically laid |
| 156 | 11595 | `container` | 0.85 | `list_item` | 0.82 | _ps:_ Named 'Left', is a horizontal layout child of the header containing 5 instances  <br>_cs:_ Horizontal header row with 5 instances + text 'Filename', same structure as scre |
| 156 | 11671 | `container` | 0.82 | `button_group` | 0.87 | _ps:_ Named 'Right', horizontal layout child of the header with 7 INSTANCE children (i <br>_cs:_ Right header zone with 7 INSTANCE icon-button children, same as screen 155 node  |
| 157 | 11759 | `card` | 0.82 | `dialog` | 0.88 | _ps:_ Named 'artboard', bbox is a large bounded container (720×740) with 2 FRAME child <br>_cs:_ Device picker modal ('Device' screen with Camera/Phone Storage options) — focuse |
| 157 | 11862 | `container` | 0.80 | `list_item` | 0.82 | _ps:_ Named 'Left', is a child of a header bar, contains 5 INSTANCE icons and 1 TEXT ( <br>_cs:_ Horizontal header row 'Filename' with 5 instances + text, same structure across  |
| 157 | 11895 | `text` | 0.90 | `heading` | 0.88 | _ps:_ Named 'Titles', contains 2 TEXT children with sample text 'Feed' in a VERTICAL l <br>_cs:_ Section title 'Feed' vertical frame with two TEXT children, same as screen 155 n |
| 157 | 12016 | `text` | 0.88 | `container` | 0.80 | _ps:_ Named 'Right' in the status bar area, contains a GROUP, TEXT, and 2 VECTORs with <br>_cs:_ iOS status bar right zone with battery/signal indicators, same as all other scre |
| 158 | 12026 | `card` | 0.82 | `dialog` | 0.88 | _ps:_ Named 'artboard', it is a bounded vertical container with 2 child frames groupin <br>_cs:_ Device picker modal with Camera/Phone Storage (highlighted) option tiles — focus |
| 158 | 12129 | `container` | 0.80 | `list_item` | 0.82 | _ps:_ Named 'Left' inside a header, horizontal layout with 5 instances and 1 text node <br>_cs:_ Horizontal header row 'Filename' with 5 instances + text, same structure across  |
| 158 | 12162 | `text` | 0.88 | `heading` | 0.88 | _ps:_ Named 'Titles' with sample text 'Feed', vertical layout with 2 text children ins <br>_cs:_ Section title 'Feed' in header center, same as screen 155 node 11371. |
| 158 | 12283 | `text` | 0.88 | `container` | 0.80 | _ps:_ Named 'Right' inside the status bar area, contains text '100%' along with batter <br>_cs:_ iOS status bar right zone, same as all other screens. |
| 159 | 12461 | `container` | 0.82 | `list_item` | 0.82 | _ps:_ Left zone of the dialog header bar, horizontally arranged with icon instances an <br>_cs:_ Horizontal header row 'Filename' with 5 instances + text, same structure across  |
| 159 | 12494 | `text` | 0.88 | `heading` | 0.88 | _ps:_ Vertical stack of 2 TEXT children with sample text 'Feed' — a label/title text e <br>_cs:_ Section title 'Feed' in header center, same as screen 155 node 11371. |
| 159 | 12537 | `container` | 0.80 | `button_group` | 0.87 | _ps:_ Right zone of the app header containing 7 INSTANCE children (icon buttons for un <br>_cs:_ Right header zone with 7 INSTANCE icon-button children, same as screen 155 node  |
| 159 | 12591 | `container` | 0.78 | `button_group` | 0.87 | _ps:_ Left controls area of the toolbar containing 3 INSTANCE icon buttons (sidebar to <br>_cs:_ Left browser toolbar controls with 3 INSTANCE children, same as screen 155 node  |
| 159 | 12604 | `container` | 0.78 | `button_group` | 0.87 | _ps:_ Right controls area of the toolbar with 3 INSTANCE children (view toggle buttons <br>_cs:_ Right browser toolbar controls with 3 INSTANCE children, same as screen 155 node |
| 159 | 12615 | `text` | 0.88 | `container` | 0.80 | _ps:_ Right side of status bar with '100%' battery text, signal icon, and WiFi vector  <br>_cs:_ iOS status bar right zone, same as all other screens. |

## Cross-screen evidence cited (sample)

When cross-screen mode references other screens' nodes as supporting/contrasting evidence.

| screen | node | type | evidence |
|---|---|---|---|
| 150 | 10043 | `card` | s153/n10785:same_component; s154/n11026:same_component |
| 150 | 10053 | `image` | s153/n10795:same_component; s154/n11036:same_component |
| 150 | 10098 | `container` | s151/n10368:same_component; s152/n10626:same_component; s153/n10862:same_component; s154/n11081:same_component |
| 150 | 10109 | `image` | s151/n10379:same_component; s152/n10637:same_component; s153/n10873:same_component; s154/n11092:same_component |
| 150 | 10130 | `container` | s151/n10400:same_component; s152/n10658:same_component; s153/n10894:same_component; s154/n11113:same_component |
| 150 | 10131 | `container` | s151/n10401:same_component; s152/n10659:same_component; s153/n10895:same_component; s154/n11114:same_component |
| 150 | 10143 | `image` | s151/n10413:same_component; s152/n10671:same_component; s153/n10907:same_component; s154/n11126:same_component |
| 150 | 10174 | `container` | s151/n10444:same_component; s152/n10702:same_component; s153/n10938:same_component; s154/n11157:same_component |
| 150 | 10223 | `icon` | s151/n10488:same_component; s152/n10746:same_component; s153/n10987:same_component; s154/n11206:same_component |
| 150 | 10227 | `container` | s151/n10492:same_component; s152/n10750:same_component; s153/n10991:same_component; s154/n11210:same_component |
| 150 | 10228 | `button_group` | s151/n10493:same_component; s152/n10751:same_component; s153/n10992:same_component; s154/n11211:same_component |
| 150 | 10235 | `search_input` | s151/n10500:same_component; s152/n10758:same_component; s153/n10999:same_component; s154/n11218:same_component |
| 150 | 10241 | `button_group` | s151/n10506:same_component; s152/n10764:same_component; s153/n11005:same_component; s154/n11224:same_component |
| 150 | 10249 | `container` | s151/n10514:same_component; s152/n10772:same_component; s153/n11013:same_component; s154/n11232:same_component |
| 150 | 10252 | `container` | s151/n10517:same_component; s152/n10775:same_component; s153/n11016:same_component; s154/n11235:same_component |
| 151 | 10272 | `list_item` | s151/n10280:same_variant_family; s151/n10286:same_variant_family; s152/n10604:same_component; s152/n10610:same_variant_family |
| 151 | 10280 | `list_item` | s151/n10272:same_variant_family; s151/n10286:same_variant_family |
| 151 | 10286 | `list_item` | s151/n10272:same_variant_family; s152/n10604:same_component |
| 151 | 10309 | `skeleton` | s151/n10310:same_variant_family; s152/n10536:same_component |
| 151 | 10310 | `skeleton` | s151/n10309:same_variant_family; s152/n10537:same_component |
| 151 | 10311 | `skeleton` | s152/n10538:same_component |
| 151 | 10312 | `skeleton` | s152/n10539:same_component |
| 151 | 10320 | `skeleton` | s151/n10309:same_variant_family; s152/n10547:same_component |
| 151 | 10321 | `skeleton` | s152/n10548:same_component |
| 151 | 10322 | `skeleton` | s152/n10549:same_component |

## Confidence calibration (on agreements)

- Avg per-screen confidence (agreements): 0.876
- Avg cross-screen confidence (agreements): 0.878
- Delta: +0.002

## Decision gate

- Agreement rate **76.9% < 85%**: cross-screen is diverging substantially from per-screen. Node tracking across images may be breaking down at this batch size. Fall back to per-screen (N=1) for the full corpus — it costs the same at Sonnet rates anyway.