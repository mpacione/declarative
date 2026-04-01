# T5 Component Vocabulary Research — Library Taxonomy Comparison

Compiled 2026-04-01. Full comparison of how 10 major component libraries organize their components, with cross-library analysis of the universal core, categorization patterns, and implications for the canonical component vocabulary.

---

## Library Summary

| Library | Total | Categories | Headless? | Layout Components? | Philosophy |
|---------|-------|-----------|-----------|-------------------|------------|
| Headless UI | 16 | 0 (flat) | Yes | No | Minimal behavioral primitives |
| M3 (Google) | ~28 | 6 | No | Implicit | Mobile-first, user intent |
| Radix Primitives | ~30 | 0 (flat) | Yes | No | Accessibility primitives |
| Bootstrap | ~24 (+8 forms) | 1 (+sections) | No | Separate grid | Traditional, conservative |
| Apple HIG | ~41 | 7 | No | Implicit | Platform-native, user task |
| MUI | ~50 (+lab) | 8 | No | Yes (5) | Technical function |
| shadcn/ui | 59 | 0 (flat) | Styled headless | No | Radix + Tailwind |
| Ant Design | ~67 | 6 | No | Yes (7) | Enterprise, data-heavy |
| Mantine | ~108 | 10 | No | Yes (10) | Full-featured web |
| Chakra UI | ~112 | 12 | No | Yes (16) | Most granular taxonomy |

---

## The Universal Core (~12-15 Components)

These appear in ALL or nearly all 10 libraries:

| Component | Appears in | Notes |
|-----------|-----------|-------|
| **Button** | 10/10 | Universal. Every library. |
| **Checkbox** | 10/10 | Universal |
| **Dialog/Modal** | 10/10 | Called Dialog, Modal, Alert Dialog, Alerts, or Sheet |
| **Select/Dropdown** | 10/10 | Select, Listbox, Dropdown, Picker, Combo Box |
| **Tabs** | 10/10 | Universal |
| **Switch/Toggle** | 10/10 | Toggle in Apple/component.gallery, Switch in most web libs |
| **Radio Group** | 10/10 | Universal |
| **Text Input** | 10/10 | TextField, Input, TextInput |
| **Progress Indicator** | 10/10 | Progress, Spinner, Loader, Activity Indicator |
| **Alert/Notification** | 10/10 | Alert, Notification, Snackbar, Banner |
| **Tooltip** | 9/10 | All except Headless UI |
| **Slider** | 9/10 | All except Bootstrap |
| **Accordion/Collapse** | 9/10 | All except Headless UI |
| **Badge** | 8/10 | Most full libraries |
| **Popover** | 8/10 | Most libraries |
| **Menu/Dropdown Menu** | 9/10 | Most libraries |

### Near-Universal (~7-9 of 10)

| Component | Count | Notes |
|-----------|-------|-------|
| Avatar | 7/10 | Not in Headless, Bootstrap, M3 |
| Breadcrumb | 8/10 | Most libraries |
| Card | 8/10 | Not in Headless or Radix (headless libs) |
| Pagination | 8/10 | Most libraries |
| Separator/Divider | 8/10 | Most libraries |
| Skeleton | 7/10 | Loading placeholder |
| Toast/Snackbar | 8/10 | Most libraries |
| Textarea | 8/10 | Most libraries |

---

## Categorization Philosophies

### Technical Function (Web Libraries)

Used by: MUI, Ant Design, Chakra, Mantine

```
Inputs / Data Entry      → form controls users interact with
Data Display             → read-only presentation
Feedback / Communication → status and alerts
Navigation               → moving between screens/sections
Layout                   → structural arrangement
Surfaces / Containment   → container elements
```

### User Intent (Platform Design Systems)

Used by: Apple HIG, Google M3

```
Actions                  → things users DO (buttons, menus)
Selection and Input      → things users CHOOSE (pickers, toggles)
Content                  → things users SEE (text, images)
Navigation and Search    → things users GO TO
Presentation             → how content APPEARS (modals, sheets)
Status / Communication   → what the system TELLS users
```

### Key Insight

The user-intent model is more natural for composition. When a designer thinks "I need the user to select a date," they think in terms of intent, not "I need a Data Entry component." The canonical vocabulary should organize by **what the component DOES for the user**, not by its technical classification.

---

## Layout vs. Content Distinction

Libraries split into two camps:

**Layout as components** (MUI, Ant, Chakra, Mantine): Box, Stack, Grid, Flex, Container, Center, etc. are first-class components.

**Layout as utility** (shadcn, Radix, Headless UI, Bootstrap): Layout handled by CSS utilities (Tailwind, grid system). Components only handle interactive behavior.

For our Pattern Language, layout primitives (stack, row, grid, overlay, scroll) are STRUCTURAL — they're the grammar that connects components. They should be separate from the 60 canonical component types, which are the NOUNS.

---

## Primitive vs. Composite

| Layer | What | Examples | Libraries |
|-------|------|---------|-----------|
| **Primitives** | Behavioral/accessibility atoms | Focus trap, Portal, Slot, Visually Hidden | Radix, Headless UI |
| **Components** | Styled, composable units | Button, Card, Dialog, Select | All full libraries |
| **Patterns** | Multi-component compositions | App Shell, Command Palette, Data Table | Mantine, Chakra, MUI X |

Radix and Headless UI ARE the primitive layer. shadcn/ui builds styled components on Radix primitives. This layering maps to our architecture:

```
Our layout primitives (stack, row, grid)  ≈  Radix structural utilities
Our 60 canonical types                    ≈  shadcn/ui components (Radix + styling)
Our screen skeletons                      ≈  Mantine AppShell / full compositions
```

---

## Full Component Lists by Library

### shadcn/ui (59 components, flat)

Accordion, Alert, Alert Dialog, Aspect Ratio, Avatar, Badge, Breadcrumb, Button, Button Group, Calendar, Card, Carousel, Chart, Checkbox, Collapsible, Combobox, Command, Context Menu, Data Table, Date Picker, Dialog, Direction, Drawer, Dropdown Menu, Empty, Field, Hover Card, Input, Input Group, Input OTP, Item, Kbd, Label, Menubar, Native Select, Navigation Menu, Pagination, Popover, Progress, Radio Group, Resizable, Scroll Area, Select, Separator, Sheet, Sidebar, Skeleton, Slider, Sonner (toast), Spinner, Switch, Table, Tabs, Textarea, Toast, Toggle, Toggle Group, Tooltip, Typography

### MUI (8 categories)

**Inputs (13):** Autocomplete, Button, Button Group, Checkbox, FAB, Number Field, Radio Group, Rating, Select, Slider, Switch, Text Field, Toggle Button

**Data Display (10):** Avatar, Badge, Chip, Divider, Icons, List, Table, Tooltip, Typography, Material Icons

**Feedback (6):** Alert, Backdrop, Dialog, Progress, Skeleton, Snackbar

**Surfaces (4):** Accordion, App Bar, Card, Paper

**Navigation (10):** Bottom Navigation, Breadcrumbs, Drawer, Link, Menu, Pagination, Speed Dial, Stepper, Tabs, Transfer List

**Layout (5):** Box, Container, Grid (v1+v2), Stack, Image List

**Utils:** CSS Baseline, Modal, Transitions, Popper, Textarea Autosize, Click Away Listener, No SSR, Portal

**Lab:** Masonry, Timeline, Tree View, Loading Button

### Ant Design (6 categories, ~67 components)

**General (4):** Button, FloatButton, Icon, Typography

**Layout (7):** Divider, Flex, Grid, Layout, Masonry, Space, Splitter

**Navigation (7):** Anchor, Breadcrumb, Dropdown, Menu, Pagination, Steps, Tabs

**Data Entry (18):** AutoComplete, Cascader, Checkbox, ColorPicker, DatePicker, Form, Input, InputNumber, Mentions, Radio, Rate, Select, Slider, Switch, TimePicker, Transfer, TreeSelect, Upload

**Data Display (20):** Avatar, Badge, Calendar, Card, Carousel, Collapse, Descriptions, Empty, Image, List, Popover, QRCode, Segmented, Statistic, Table, Tag, Timeline, Tooltip, Tour, Tree

**Feedback (11):** Alert, Drawer, Message, Modal, Notification, Popconfirm, Progress, Result, Skeleton, Spin, Watermark

### Radix Primitives (~30 user-facing)

Accessible Icon, Accordion, Alert Dialog, Aspect Ratio, Avatar, Checkbox, Collapsible, Context Menu, Dialog, Dropdown Menu, Form, Hover Card, Label, Menu, Menubar, Navigation Menu, OTP Field, Password Toggle, Popover, Progress, Radio Group, Scroll Area, Select, Separator, Slider, Switch, Tabs, Toast, Toggle, Toggle Group, Toolbar, Tooltip, Visually Hidden

### Bootstrap (24 components + forms)

**Components:** Accordion, Alerts, Badge, Breadcrumb, Buttons, Button Group, Card, Carousel, Close Button, Collapse, Dropdowns, List Group, Modal, Navbar, Navs & Tabs, Offcanvas, Pagination, Placeholders, Popovers, Progress, Scrollspy, Spinners, Toasts, Tooltips

**Forms:** Form Controls, Select, Checks & Radios, Range, Input Group, Floating Labels, Layout, Validation

### Chakra UI (12 categories, ~112 components)

**Layout (16):** Aspect Ratio, Bleed, Box, Center (Absolute), Center, Container, Flex, Float, Grid, Group, Scroll Area, Separator, SimpleGrid, Splitter, Stack, Wrap

**Typography (14):** Blockquote, Code, Code Block, Em, Heading, Highlight, Kbd, Link, Link Overlay, List, Mark, Prose, Rich Text Editor, Text

**Buttons (4):** Button, Close Button, Icon Button, Download Trigger

**Date and Time (2):** Date Picker, Calendar

**Forms (21):** Checkbox, Checkbox Card, Color Picker, Color Swatch, Editable, Field, Fieldset, File Upload, Input, Number Input, Password Input, Pin Input, Radio Card, Radio, Rating, Segmented Control, Select (Native), Switch, Slider, Textarea, Tags Input

**Collections (4):** Combobox, Listbox, Select, Tree View

**Overlays (9):** Action Bar, Dialog, Drawer, Hover Card, Menu, Overlay Manager, Popover, Toggle Tip, Tooltip

**Disclosure (7):** Accordion, Breadcrumb, Carousel, Collapsible, Pagination, Steps, Tabs

**Feedback (8):** Alert, Empty State, Progress Circle, Progress, Skeleton, Spinner, Status, Toast

**Data Display (13):** Avatar, Badge, Card, Clipboard, Image, Data List, Icon, Marquee, QR Code, Stat, Table, Tag, Timeline

**Internationalization (3):** LocaleProvider, FormatNumber, FormatByte

**Utilities (11):** Checkmark, ClientOnly, EnvironmentProvider, For, Presence, Portal, Radiomark, Show, Skip Nav, Visually Hidden, Theme

### Mantine (10 categories, ~108 components)

**Layout (10):** AppShell, AspectRatio, Center, Container, Flex, Grid, Group, SimpleGrid, Space, Stack

**Inputs (23):** AlphaSlider, AngleSlider, Checkbox, Chip, ColorInput, ColorPicker, Fieldset, FileInput, HueSlider, Input, JsonInput, NativeSelect, NumberInput, PasswordInput, PinInput, Radio, RangeSlider, Rating, SegmentedControl, Slider, Switch, Textarea, TextInput

**Combobox (7):** Autocomplete, Combobox, MultiSelect, Pill, PillsInput, Select, TagsInput

**Buttons (6):** ActionIcon, Button, CloseButton, CopyButton, FileButton, UnstyledButton

**Navigation (9):** Anchor, Breadcrumbs, Burger, NavLink, Pagination, Stepper, TableOfContents, Tabs, Tree

**Feedback (7):** Alert, Loader, Notification, Progress, RingProgress, SemiCircleProgress, Skeleton

**Overlays (12):** Affix, Dialog, Drawer, FloatingIndicator, FloatingWindow, HoverCard, LoadingOverlay, Menu, Modal, Overlay, Popover, Tooltip

**Data Display (14):** Accordion, Avatar, BackgroundImage, Badge, Card, ColorSwatch, Image, Indicator, Kbd, NumberFormatter, OverflowList, Spoiler, ThemeIcon, Timeline

**Typography (9):** Blockquote, Code, Highlight, List, Mark, Table, Text, Title, Typography

**Miscellaneous (11):** Box, Collapse, Divider, FocusTrap, Marquee, Paper, Portal, ScrollArea, Scroller, Transition, VisuallyHidden

### Apple HIG (7 categories, ~41 components)

**Content:** Images, Text Views, Web Views

**Layout and Organization:** Boxes, Collections, Column Views, Disclosure Groups, Forms, Labels, Lists and Tables, Outline Views, Split Views, Tab Views

**Menus and Actions:** Buttons, Context Menus, Dock Menus, Edit Menus, Menus, Pull-Down Buttons

**Navigation and Search:** Navigation Bars, Ornaments, Path Controls, Search Fields, Sidebars, Tab Bars, Token Fields, Toolbars

**Presentation:** Alerts, Page Controls, Popovers, Sheets

**Selection and Input:** Color Wells, Combo Boxes, Date Pickers, Disclosure Controls, Pickers, Segmented Controls, Sliders, Steppers, Text Fields, Toggles

**Status:** Activity Views, Gauges, Progress Indicators

### Google Material Design 3 (6 categories, ~28 components)

**Actions:** Common Buttons, FAB, Extended FAB, Icon Buttons, Segmented Buttons

**Communication:** Badges, Progress Indicators, Snackbars

**Containment:** Bottom Sheets, Cards, Carousels, Dialogs, Dividers, Lists, Side Sheets, Tooltips

**Navigation:** Bottom App Bar, Navigation Bar, Navigation Drawer, Tabs, Top App Bar

**Selection:** Checkboxes, Chips, Date Pickers, Radio Buttons, Sliders, Switches, Time Pickers

**Text Inputs:** Text Fields, Search

---

## Components Unique to Specific Libraries

| Component | Library | Notes |
|-----------|---------|-------|
| Cascader | Ant Design | Hierarchical selection |
| Transfer | Ant Design | Dual-list transfer |
| Mentions | Ant Design | @-mention input |
| Tour | Ant Design | Product tours |
| QR Code | Ant Design, Chakra | |
| Watermark | Ant Design | Document watermarking |
| Result | Ant Design | Success/error result pages |
| Descriptions | Ant Design | Key-value detail display |
| Speed Dial | MUI | FAB sub-actions |
| AppShell | Mantine | Full app layout scaffold |
| Spotlight | Mantine | Command palette |
| JsonInput | Mantine | JSON editor |
| Rich Text Editor | Chakra | WYSIWYG |
| Clipboard | Chakra | Copy to clipboard |
| Gauges | Apple HIG | Analog indicators |
| Ornaments | Apple HIG | visionOS specific |
| Command | shadcn | Command palette (cmdk) |
| Resizable | shadcn | Resizable panels |
| Side Sheets | M3 | Panel from edge |

---

## Implications for the Canonical Component Vocabulary

### 1. The Universal Core Should Be Our Foundation

The ~15 components that appear in every library are non-negotiable. These are the Platonic forms that every design system independently converges on. They should be the first components we define with full slot decomposition and recognition heuristics.

### 2. User-Intent Categorization for the Pattern Language

Apple and Google organize by what the component DOES FOR THE USER, not its technical type. This is the right model for the Pattern Language — when composing a screen, the designer thinks "I need the user to select an option" not "I need a Data Entry component."

Proposed categories inspired by Apple HIG + M3:
- **Actions** — things users DO (Button, FAB, Menu)
- **Selection & Input** — things users CHOOSE or TYPE (Toggle, Select, Input, Slider, Checkbox, Radio, DatePicker)
- **Content & Display** — things users SEE (Card, Avatar, Badge, Image, Table, List, Typography)
- **Navigation** — things users GO TO (Tabs, Breadcrumb, Nav Bar, Sidebar, Pagination)
- **Feedback & Status** — what the system TELLS users (Alert, Toast, Progress, Skeleton, Spinner)
- **Containment & Overlay** — HOW content APPEARS (Dialog, Drawer, Sheet, Popover, Accordion, Tooltip)

### 3. Layout Primitives Are Separate

Layout components (Stack, Grid, Flex, etc.) should NOT be in the 60 canonical types. They're structural grammar — the verbs that connect nouns. Keep them as the ~7 layout primitives in the Pattern Language, separate from the component vocabulary.

### 4. ~45-55 Types Is the Right Size

Component.gallery has 60. The universal core is ~15. Near-universal adds ~10 more. Common-but-not-universal adds ~15-20. That puts us at ~40-45 truly useful canonical types, plus maybe 5-10 mobile-specific or enterprise-specific extensions.

### 5. The Headless/Primitive Layer Matters

Radix's approach — behavioral primitives separate from styling — maps to our architecture. Our canonical types are BEHAVIORAL concepts (a Toggle is "a binary choice control"), not visual implementations. The same Toggle maps to shadcn `<Switch>`, MUI `<Switch>`, SwiftUI `Toggle`, Figma component instance, etc.

---

## Cross-Reference: component.gallery's 60 vs. Library Consensus

component.gallery types NOT well-represented in major libraries:
- File (6 examples) — niche
- Quote (11 examples) — niche
- Rich text editor (5 examples) — niche
- Skip link (14 examples) — accessibility utility
- Visually hidden (11 examples) — accessibility utility
- Video (15 examples) — media player
- Color picker (16 examples) — specialized input

component.gallery types well-represented everywhere:
- Button (118), Alert (108), Badge (122), Checkbox (84), Radio (86), Select (82), Modal (82), Tabs (81), Card (79), Table (74), Tooltip (74), Text input (72), List (69), Spinner (66), Link (64), Toggle (59), Breadcrumbs (55), Textarea (51), Popover (50), Pagination (49)

The high-example-count types are the universal core. The low-count types are candidates for exclusion or demotion to "optional extensions."
