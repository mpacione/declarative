# UI Format Comparison: Settings Screen

All 8 formats express the identical screen: a 428x926 mobile settings screen with
a nav bar, two cards containing toggle rows, and a save button.

---

## 1. HTML/CSS

```html
<!DOCTYPE html>
<html>
<head>
<style>
  .screen { width: 428px; height: 926px; background: #F2F2F7; display: flex; flex-direction: column; font-family: -apple-system, sans-serif; }
  .nav { height: 56px; padding: 0 16px; display: flex; align-items: center; background: #FFFFFF; }
  .nav h1 { font-size: 20px; font-weight: 600; color: #000000; }
  .content { flex: 1; padding: 16px; display: flex; flex-direction: column; gap: 16px; overflow-y: auto; }
  .card { background: #FFFFFF; border-radius: 12px; padding: 16px; display: flex; flex-direction: column; gap: 0; }
  .card-heading { font-size: 16px; font-weight: 600; color: #000000; margin-bottom: 12px; }
  .toggle-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-top: 1px solid #E5E5EA; }
  .toggle-row:first-of-type { border-top: none; }
  .toggle-row span { font-size: 16px; color: #000000; }
  .toggle { width: 51px; height: 31px; border-radius: 16px; background: #34C759; }
  .save-btn { height: 50px; background: #007AFF; color: #FFFFFF; border: none; border-radius: 12px; font-size: 17px; font-weight: 600; margin: 16px; cursor: pointer; }
</style>
</head>
<body>
<div class="screen">
  <nav class="nav">
    <h1>Settings</h1>
  </nav>
  <div class="content">
    <div class="card">
      <div class="card-heading">Notifications</div>
      <div class="toggle-row">
        <span>Push Notifications</span>
        <div class="toggle"></div>
      </div>
      <div class="toggle-row">
        <span>Email Alerts</span>
        <div class="toggle"></div>
      </div>
      <div class="toggle-row">
        <span>Weekly Digest</span>
        <div class="toggle"></div>
      </div>
    </div>
    <div class="card">
      <div class="card-heading">Appearance</div>
      <div class="toggle-row">
        <span>Dark Mode</span>
        <div class="toggle"></div>
      </div>
    </div>
  </div>
  <button class="save-btn">Save</button>
</div>
</body>
</html>
```

**Lines: 43 (HTML) + 16 (CSS) = 59 total**
**Characters: ~2,580**

---

## 2. JSX (React)

```jsx
function SettingsScreen() {
  return (
    <Screen width={428} height={926} background="#F2F2F7">
      <NavBar>
        <Title>Settings</Title>
      </NavBar>
      <ScrollView padding={16} gap={16}>
        <Card>
          <CardHeading>Notifications</CardHeading>
          <ToggleRow label="Push Notifications" value={true} />
          <ToggleRow label="Email Alerts" value={true} />
          <ToggleRow label="Weekly Digest" value={false} />
        </Card>
        <Card>
          <CardHeading>Appearance</CardHeading>
          <ToggleRow label="Dark Mode" value={false} />
        </Card>
      </ScrollView>
      <Button variant="primary" fullWidth>Save</Button>
    </Screen>
  );
}
```

**Lines: 22**
**Characters: ~660**

---

## 3. SwiftUI

```swift
struct SettingsScreen: View {
    @State private var pushNotifications = true
    @State private var emailAlerts = true
    @State private var weeklyDigest = false
    @State private var darkMode = false

    var body: some View {
        VStack(spacing: 0) {
            NavigationBar(title: "Settings")

            ScrollView {
                VStack(spacing: 16) {
                    GroupBox(label: Text("Notifications").font(.headline)) {
                        Toggle("Push Notifications", isOn: $pushNotifications)
                        Toggle("Email Alerts", isOn: $emailAlerts)
                        Toggle("Weekly Digest", isOn: $weeklyDigest)
                    }
                    GroupBox(label: Text("Appearance").font(.headline)) {
                        Toggle("Dark Mode", isOn: $darkMode)
                    }
                }
                .padding(16)
            }

            Button(action: save) {
                Text("Save")
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(12)
            }
            .padding(16)
        }
        .frame(width: 428, height: 926)
        .background(Color(.systemGroupedBackground))
    }
}
```

**Lines: 36**
**Characters: ~1,120**

---

## 4. YAML

```yaml
screen:
  width: 428
  height: 926
  background: "{color.bg.secondary}"
  layout: column

  children:
    - nav-bar:
        title: "Settings"

    - scroll-view:
        padding: "{space.md}"
        gap: "{space.md}"
        flex: 1
        children:
          - card:
              children:
                - heading: "Notifications"
                - toggle-row:
                    label: "Push Notifications"
                    value: true
                - toggle-row:
                    label: "Email Alerts"
                    value: true
                - toggle-row:
                    label: "Weekly Digest"
                    value: false

          - card:
              children:
                - heading: "Appearance"
                - toggle-row:
                    label: "Dark Mode"
                    value: false

    - button:
        label: "Save"
        variant: primary
        full-width: true
        margin: "{space.md}"
```

**Lines: 40**
**Characters: ~850**

---

## 5. Pug/Jade

```pug
screen(width=428 height=926 background="#F2F2F7")
  nav-bar
    title Settings
  scroll-view(padding=16 gap=16 flex=1)
    card
      heading Notifications
      toggle-row(label="Push Notifications" value=true)
      toggle-row(label="Email Alerts" value=true)
      toggle-row(label="Weekly Digest" value=false)
    card
      heading Appearance
      toggle-row(label="Dark Mode" value=false)
  button(variant="primary" full-width) Save
```

**Lines: 14**
**Characters: ~430**

---

## 6. S-expression (Lisp-like)

```lisp
(screen :width 428 :height 926 :background "{color.bg.secondary}"
  (nav-bar
    (title "Settings"))
  (scroll-view :padding "{space.md}" :gap "{space.md}" :flex 1
    (card
      (heading "Notifications")
      (toggle-row :label "Push Notifications" :value true)
      (toggle-row :label "Email Alerts" :value true)
      (toggle-row :label "Weekly Digest" :value false))
    (card
      (heading "Appearance")
      (toggle-row :label "Dark Mode" :value false)))
  (button :variant primary :full-width true "Save"))
```

**Lines: 14**
**Characters: ~530**

---

## 7. Custom Indentation DSL

```
Screen 428x926 bg:{color.bg.secondary}
  NavBar
    Title "Settings"
  ScrollView flex:1 pad:{space.md} gap:{space.md}
    Card
      Heading "Notifications"
      ToggleRow "Push Notifications" on
      ToggleRow "Email Alerts" on
      ToggleRow "Weekly Digest" off
    Card
      Heading "Appearance"
      ToggleRow "Dark Mode" off
  Button "Save" variant:primary width:fill
```

**Lines: 14**
**Characters: ~370**

---

## 8. JSON

```json
{
  "type": "screen",
  "width": 428,
  "height": 926,
  "background": "{color.bg.secondary}",
  "layout": "column",
  "children": [
    {
      "type": "nav-bar",
      "children": [
        {
          "type": "title",
          "text": "Settings"
        }
      ]
    },
    {
      "type": "scroll-view",
      "padding": "{space.md}",
      "gap": "{space.md}",
      "flex": 1,
      "children": [
        {
          "type": "card",
          "children": [
            {
              "type": "heading",
              "text": "Notifications"
            },
            {
              "type": "toggle-row",
              "label": "Push Notifications",
              "value": true
            },
            {
              "type": "toggle-row",
              "label": "Email Alerts",
              "value": true
            },
            {
              "type": "toggle-row",
              "label": "Weekly Digest",
              "value": false
            }
          ]
        },
        {
          "type": "card",
          "children": [
            {
              "type": "heading",
              "text": "Appearance"
            },
            {
              "type": "toggle-row",
              "label": "Dark Mode",
              "value": false
            }
          ]
        }
      ]
    },
    {
      "type": "button",
      "text": "Save",
      "variant": "primary",
      "fullWidth": true,
      "margin": "{space.md}"
    }
  ]
}
```

**Lines: 72**
**Characters: ~1,680**

---

## Metrics Comparison

| Format              | Lines | Chars | Noise Ratio | Notes                                  |
|---------------------|-------|-------|-------------|----------------------------------------|
| HTML/CSS            |    59 | 2,580 | ~55%        | Tags, classes, style rules             |
| JSX (React)         |    22 |   660 | ~35%        | Angle brackets, JSX syntax             |
| SwiftUI             |    36 | 1,120 | ~40%        | Modifiers, property wrappers, keywords |
| YAML                |    40 |   850 | ~20%        | Quotes on strings, `children:` keys    |
| Pug/Jade            |    14 |   430 | ~18%        | Parens for attributes                  |
| S-expression        |    14 |   530 | ~25%        | Parens everywhere, keyword prefixes    |
| Custom DSL          |    14 |   370 | ~10%        | Minimal: type + inline props           |
| JSON                |    72 | 1,680 | ~50%        | Braces, brackets, quotes, commas       |

**Noise ratio** = approximate percentage of characters that are structural syntax
(brackets, tags, quotes, colons, commas, `children:` keys) rather than semantic
content (component names, property values, text content).

---

## Analysis and Recommendations

### (a) Human Readability and Editability

**Winner: Custom DSL**

The custom indentation DSL wins on every readability axis:
- 14 lines, 370 characters -- 4.5x shorter than JSON, 7x shorter than HTML
- Component type is always the first word -- instant visual scanning
- Properties inline where simple (`variant:primary`), no ceremony
- Text content in quotes immediately after type (`ToggleRow "Push Notifications" on`)
- Indentation conveys hierarchy without any brackets or closing tags
- Boolean values as `on`/`off` rather than `true`/`false`
- Token references are natural inline: `bg:{color.bg.secondary}`

Pug is a close second but carries parens for attributes. YAML is readable but
verbose due to `children:` keys and quoting requirements.

### (b) LLM Generation Reliability

**Winner: YAML, with JSON as a safe fallback**

LLMs generate YAML and JSON extremely reliably because:
- Both are universal formats in every LLM's training data
- JSON has zero ambiguity -- every LLM can produce valid JSON
- YAML is nearly as reliable, and 2x more compact than JSON
- Both have battle-tested parsers in every language

The custom DSL would be the best *if* the LLM were fine-tuned or few-shot prompted
on it. Without training data, LLMs will hallucinate syntax variants. S-expressions
are also reliable (simple grammar, LLMs know Lisp) but less common in training data.

**Risk ranking (most to least reliable for zero-shot LLM generation):**
1. JSON -- every LLM generates valid JSON
2. YAML -- nearly as reliable, much more compact
3. JSX -- well-represented in training data
4. HTML -- universal but verbose
5. S-expression -- simple grammar but less common
6. SwiftUI -- common but complex modifier chains
7. Pug -- niche, less training data
8. Custom DSL -- zero training data, needs examples

### (c) Parsability (Unambiguous, Easy to Write a Parser)

**Winner: JSON, then S-expressions**

JSON is unambiguously the easiest to parse: the grammar is tiny, parsers exist in
every language, and there is zero context-sensitivity.

S-expressions are second: the grammar is `(type props... children...)` with
exactly one rule. A recursive descent parser is ~50 lines.

The custom DSL is third: indentation-based parsing is well-understood (Python does it)
but requires tracking indent levels. The grammar is:
```
line = INDENT type [inline-props...] [quoted-text] [inline-props...]
```
This is a two-pass parse: (1) tokenize by indent level, (2) parse each line.
Simple but not trivial -- whitespace sensitivity adds edge cases.

YAML is deceptively hard to parse correctly (the full YAML spec is enormous), but
using a subset keeps it tractable.

HTML and JSX require real parsers with tag matching. SwiftUI requires a Swift parser.

**Parsability ranking (easiest to hardest):**
1. JSON -- trivial grammar, universal parsers
2. S-expression -- one rule, recursive descent
3. Custom DSL -- indent-based, small grammar, ~200 lines
4. YAML (subset) -- well-known libraries, but full spec is complex
5. Pug -- indent-based but more grammar rules
6. JSX -- needs tag matching, expression parsing
7. HTML -- forgiving parser needed, closing tags
8. SwiftUI -- full language parser required

### (d) Expressiveness (All 6 Spatial Mechanisms)

The 6 mechanisms: **position, size, padding, gap, constraints, z-order**

| Format         | Position | Size   | Padding | Gap    | Constraints | Z-order |
|----------------|----------|--------|---------|--------|-------------|---------|
| HTML/CSS       | yes      | yes    | yes     | yes    | yes         | yes     |
| JSX            | yes      | yes    | yes     | yes    | yes         | yes     |
| SwiftUI        | yes      | yes    | yes     | yes    | yes         | yes     |
| YAML           | yes      | yes    | yes     | yes    | yes*        | yes*    |
| Pug            | yes      | yes    | yes     | yes    | yes*        | yes*    |
| S-expression   | yes      | yes    | yes     | yes    | yes*        | yes*    |
| Custom DSL     | yes      | yes    | yes     | yes    | yes*        | yes*    |
| JSON           | yes      | yes    | yes     | yes    | yes*        | yes*    |

*All data formats (YAML, JSON, S-expr, Custom DSL, Pug) can express any property
as a key:value pair, so expressiveness is equal. The question is whether the format
has natural idioms for each mechanism.*

**Winner: Tie.** All formats can represent all 6 mechanisms as properties. The real
differentiator is whether the format makes common patterns *ergonomic*:

- HTML/CSS: gap via `gap:`, position via flexbox/grid/absolute, z-order via `z-index`
- SwiftUI: gap via `spacing:`, constraints via `.frame(min/max)`, z-order via `zIndex`
- Custom DSL: `gap:{space.md}`, `pos:0,56`, `z:2`, `min-w:200`, `pad:16` -- all inline

The custom DSL is most *ergonomic* for spatial properties because they're terse and
inline, but no format is more *capable* than another.

---

## Overall Recommendation

| Goal                       | Best Format      | Runner-up     |
|----------------------------|------------------|---------------|
| Human readability          | Custom DSL       | Pug           |
| LLM generation (zero-shot) | YAML            | JSON          |
| LLM generation (trained)   | Custom DSL      | YAML          |
| Parsability                | JSON             | S-expression  |
| Expressiveness             | Tie (all equal)  | --            |
| **Best overall balance**   | **YAML**         | Custom DSL    |

**Pragmatic recommendation:** Use YAML as the serialization format with a custom
vocabulary of component types and property names. This gives you:
- LLM generation reliability (YAML is in every training set)
- Human readability (2x more compact than JSON, no brackets)
- Parsability (battle-tested libraries everywhere)
- The semantic expressiveness of the custom DSL vocabulary
- A migration path: if you later build a custom parser, the vocabulary transfers

**If you invest in a custom parser:** The custom indentation DSL is the clear winner.
It is 2.3x more compact than YAML, nearly zero noise, and trivially convertible
to/from YAML or JSON. The parser is ~200 lines of TypeScript. The cost is training
LLMs to produce it reliably (solvable with few-shot prompting or a grammar constraint).

**The worst options are HTML and JSON** -- both carry enormous noise for this use case.
HTML requires tag matching and CSS; JSON doubles the line count with structural braces.
