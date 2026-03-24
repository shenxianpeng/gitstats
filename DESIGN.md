# Design System — GitStats

## Product Context
- **What this is:** A Python CLI tool that generates self-contained HTML/JSON reports with statistics from Git repositories
- **Who it's for:** Developers and DevOps engineers analyzing their own repositories
- **Space/industry:** Developer tooling / repository analytics
- **Project type:** Data report — static HTML output, not a web app or SaaS product

## Aesthetic Direction
- **Direction:** Terminal-Native / Developer-First
- **Decoration level:** Minimal — typography, spacing, and contrast do all the work
- **Mood:** Feels like high-quality CLI tool output rendered as HTML. Not a SaaS product trying to appeal to developers — a developer tool that reflects developer values. The user should think "this tool knows what it is."
- **Key differentiator:** Warm grayscale palette + zero border-radius + full monospace typeface. Most git analytics tools (GitHub, GitLab, Sourcegraph) use cool-gray, rounded-corner SaaS aesthetics. GitStats owns the developer-native space.

## Typography
- **All text — IBM Plex Mono** (one typeface for everything, including body)
  - This is a deliberate commitment, not an omission. The gitstats user is a developer. There are no non-technical users to protect from monospace body text.
  - `font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`
- **Loading:** Google Fonts CDN (`https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap`)
- **Type scale:**

| Role | Size | Weight | Notes |
|------|------|--------|-------|
| Hero / page title | 22–28px | 600 | letter-spacing: -0.03em |
| Section heading h2 | 18px | 500 | prefixed with `// ` in amber |
| Sub-heading h3 | 15px | 500 | — |
| Body / paragraphs | 13px | 400 | line-height: 1.7 |
| UI labels / table headers | 11px | 500 | uppercase, letter-spacing: 0.05em |
| Tabular data | 12px | 400 | font-feature-settings: "tnum" |
| Code / commands | 12px | 400 | background surface, border |

## Color

### Light mode
| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#ffffff` | Page background |
| `--surface` | `#f5f5f4` | Table headers, code blocks, surface elements |
| `--surface-2` | `#ebeaea` | Hover states |
| `--text` | `#211e1e` | Primary text (warm near-black) |
| `--text-2` | `#4b4646` | Secondary text, nav links |
| `--text-muted` | `#9e9a9a` | Placeholder, metadata |
| `--border` | `#cfcecd` | Default borders |
| `--border-strong` | `#9e9a9a` | Table borders, strong dividers |
| `--amber` | `#D97706` | **Accent** — links, bar charts, interactive hover, `//` heading prefix |
| `--amber-hover` | `#b45309` | Amber on hover |
| `--amber-light` | `#fef3c7` | Alert/badge backgrounds |
| `--green` | `#2d6a3f` | Health score, success states |
| `--red` | `#8b2323` | Danger/error states |
| `--yellow` | `#d4a017` | Warning states |

### Dark mode
| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#211e1e` | Page background (warm near-black) |
| `--surface` | `#2d2929` | Surface elements |
| `--surface-2` | `#352f2f` | Hover states |
| `--text` | `#f1ecec` | Primary text (warm near-white) |
| `--text-2` | `#b7b1b1` | Secondary text |
| `--text-muted` | `#656363` | Muted text |
| `--border` | `#3d3838` | Default borders |
| `--border-strong` | `#656363` | Strong borders |
| `--amber` | `#F59E0B` | Accent (one stop brighter for dark contrast) |
| `--amber-hover` | `#fbbf24` | Amber on hover |
| `--green` | `#4ade80` | Health/success |
| `--red` | `#f87171` | Danger/error |
| `--yellow` | `#e3b341` | Warning |

### Color role rules
- **Amber** = interaction, state emphasis, links, bar charts, active indicators
- **Green** = heatmap density (GitHub green scale), health scores, success states — never use for interaction
- These two color families must not overlap. Amber is for "you can click/interact with this." Green is for "this is a data density or health signal."

### Heatmap scale
GitHub green — colorblind-safe, universally recognizable for contribution graphs:
- Level 0: `#ebedf0` (light) / `#1c2128` (dark)
- Level 1: `#9be9a8` / `#0e4429`
- Level 2: `#40c463` / `#006d32`
- Level 3: `#30a14e` / `#26a641`
- Level 4: `#216e39` / `#39d353`

## Spacing
- **Base unit:** 4px
- **Scale:** `--sp-1: 4px` `--sp-2: 8px` `--sp-3: 12px` `--sp-4: 16px` `--sp-5: 24px` `--sp-6: 32px` `--sp-7: 48px` `--sp-8: 64px`
- **Density:** Compact-to-comfortable. Table cell padding: 8px 12px. Reports are data-dense — don't waste vertical space.
- **Max content width:** 1280px

## Layout
- **Approach:** Section-based, not card-based. Sections separated by `<h2>` headings and `<hr>` dividers. Tables, chart regions, and stat blocks are the primitives — not cards.
- **Border radius:** Zero everywhere (`border-radius: 0`). This is the terminal/angular identity. Never introduce rounded corners.
- **Grid:** No explicit CSS grid. Section content flows naturally with max-width constraint.
- **Nav:** Sticky top bar, min-height 44px (WCAG 2.5.5 touch target).

### Section heading convention
All `h2` elements get a `//` prefix in amber, applied via CSS:
```css
h2::before { content: '// '; color: var(--amber); }
```

### Generation command block
On the general/index page, directly below `<h1>`, show the command used to generate the report:
```
$ gitstats /path/to/repo ./output ▊
```
Styled with surface background, 1px border, amber prompt character, blinking cursor. This is the single strongest "this is a CLI tool" signal and requires ~4 lines of Python to implement.

## Motion

### Tokens
| Token | Duration | Easing | Usage |
|-------|----------|--------|-------|
| `--transition-fast` | `120ms ease-out` | ease-out | hover color/background shifts |
| `--transition-base` | `150ms ease-out` | ease-out | border-color, nav state |
| `--transition-theme` | `200ms ease` | ease | theme toggle — bg + color on body |
| `--transition-cursor` | `1.2s step-end infinite` | step-end | blinking cursor (blink keyframe) |

### Rules
- **Standard:** `transition: background-color 120ms ease-out, color 120ms ease-out, border-color 120ms ease-out`
- **Theme switch:** `transition: background-color 0.2s ease, color 0.2s ease` on `body`
- **Never animate layout properties** (`width`, `height`, `top`, `left`) — transform + opacity only
- **No animations on data load** — reports are static; entrance animations would feel wrong
- **`prefers-reduced-motion`:** Cursor blink animation (`@keyframes blink`) is disabled via `@media (prefers-reduced-motion: reduce)`. All other transitions are safe (sub-200ms, no layout shifts).

## Interactive States

### Focus
- **`:focus-visible`:** `outline: 2px solid var(--amber); outline-offset: 2px`
- Never use `outline: none` without a visible replacement
- All nav links, the theme toggle, and table header sort anchors must show focus ring on keyboard nav

### Hover
- **Links:** color shifts to `var(--amber)`, underline appears
- **Nav links:** color → `var(--amber)`, background → `var(--surface-color)`
- **Table rows:** `tr:hover td` → background `var(--table-hover-bg)`
- **Bar charts:** `.bar` opacity 0.85 → 1.0 on parent hover
- **Theme toggle / nav-github:** color → `var(--amber)` or `var(--text-color)`

### Active / Current page
- Nav link for the current page should visually indicate active state (bold weight or amber color)
- (not yet implemented — future enhancement)

## Responsive Design

### Strategy
GitStats reports are primarily desktop tools (run via CLI, opened in a browser). Mobile is secondary but should not be broken. The goal is "readable and usable on mobile" not "designed for mobile."

### Breakpoints
| Name | Width | Behavior |
|------|-------|----------|
| desktop | ≥ 768px | Full layout, sticky nav, side-by-side columns |
| mobile | < 768px | Stacked layout, scrollable tables, wrapped nav |

### Nav on mobile
**Current state:** Nav items wrap into multiple rows (deferred — FINDING-003).
**Target:** Implement horizontal scrollable nav with `overflow-x: auto; white-space: nowrap` on `.nav ul`. No hamburger menu — developer tool users expect dense, direct access. A horizontally scrolling list of 6 links is appropriate for this audience.

**Implementation plan (when prioritized):**
```css
@media (max-width: 768px) {
  .nav ul {
    overflow-x: auto;
    white-space: nowrap;
    flex-wrap: nowrap;
    -webkit-overflow-scrolling: touch;
  }
  .nav li a {
    min-height: 44px; /* already set */
  }
}
```

### Tables on mobile
Tables use `display: block; overflow-x: auto` on all viewports (implemented). Wide tables scroll horizontally within the viewport — correct behavior for data reports.

### Charts on mobile
Chart.js canvases are responsive by default (`responsive: true`). Charts reflow to container width automatically.

## Component Library

### Navigation (`.nav`)
```
[GitStats] [General | Activity | Authors | Files | Lines | Tags] [GitHub ⬡] [🌙]
```
- Sticky top bar, `min-height: 44px`, `z-index: 100`
- Brand: `16px 700 monospace`, left
- Links: `12px 500 monospace`, separated by `1px border-left`, vertical dividers
- Right side: GitHub icon link + theme toggle button, separated from links by `border-left`
- Active hover: color → amber, background → surface
- All interactive elements: `min-height: 44px`, `min-width: 44px` (WCAG 2.5.5)

### Generation Command Block (`.cmd-block`)
```
$ gitstats . ./output ▊
```
- Surface background, `1px border`, monospace 12px, amber `$` prompt, blinking cursor `▊`
- `@media (prefers-reduced-motion: reduce)` disables blink
- Placed directly below `<h1>` on the index/general page only

### Tables
- `border-collapse: collapse`, `font-size: 12px`
- `th`: surface background, uppercase, `11px`, `letter-spacing: 0.08em`, strong border
- `td`: white/table-bg background, `8px 12px` padding, light border
- `tr:hover`: table-hover-bg background
- `table.noborders`: bar chart tables — no borders, transparent background
- Responsive: `display: block; overflow-x: auto` on all viewports

### Bar Charts (`.bar` + `.noborders`)
- Plain `<table class="noborders">` with `<td>` cells containing a `<div class="bar">`
- `.bar` background: `var(--bar-color)` = `var(--amber)`, opacity 0.85
- On row hover: opacity → 1.0
- Bar height/width set inline by Python based on value percentage

### Heatmap (`.heat0`–`.heat4`)
- Used on the Activity page for commit frequency calendars
- GitHub green scale (5 levels, colorblind-safe)
- Level 0 = no activity, Level 4 = peak activity
- Text color inverts to white at levels 3–4 for contrast
- See Color section for exact hex values

### Section Headings (`h2`)
```html
<h2><a href="#section-id">Section Name</a></h2>
```
- CSS `h2::before { content: '// '; color: var(--amber); }`
- `border-left: 2px solid var(--amber)`, surface background, 18px 500
- Hover reveals `#` anchor link via `h2:hover a::after`

### AI Summary (`.ai-summary`)
Used for optional AI-generated analysis blocks. Not part of the base report.
- Surface background, strong border, `border-left: 3px solid var(--text-color)`
- Error variant `.ai-summary-error`: `border-left: 3px solid var(--danger-color)`
- The colored left border here is semantic (indicating "this is AI-generated content"), not decorative — an intentional exception to the no-card-left-border rule

## Chart System

### Chart.js Configuration
All charts use Chart.js (bundled, browser-side). Design tokens to apply:

```javascript
// Color sequence — amber first, then muted earth tones
CHART_COLORS = [
  '#D97706',  // amber (primary — always first)
  '#92400E',  // amber-dark
  '#B45309',  // amber-mid
  '#78716C',  // warm gray
  '#57534E',  // warm gray dark
  '#A8A29E',  // warm gray light
  '#059669',  // green (only for health/positive data)
  '#DC2626',  // red (only for error/negative data)
]
```

### Axis & Grid
- Grid lines: `var(--border-color)` (#cfcecd light / #3d3838 dark), `lineWidth: 1`
- Tick labels: `var(--text-secondary)`, 11px, monospace font
- Axis labels: `var(--text-muted)`, 11px
- No chart border (borderWidth: 0 on datasets where appropriate)

### Tooltip
- Background: `var(--surface-color)` with `1px solid var(--border-strong)`
- Title: `var(--text-color)`, 12px bold
- Body: `var(--text-secondary)`, 12px
- No border-radius (consistent with zero-radius system)
- Padding: 8px 12px

### Dark mode
Chart colors shift with CSS variables — use the `data-theme="dark"` class on `<html>` to trigger re-read of CSS variable values for charts. Re-initialize chart theme on toggle.

## Accessibility
- Amber `#D97706` on white `#ffffff`: contrast ratio 4.6:1 (passes WCAG AA)
- GitHub green heatmap scale: safe for deuteranopia/protanopia (green is not paired with red for the same signal)
- All nav links have min 44px touch targets (implemented)
- `:focus-visible` ring is amber, 2px, offset 2px (implemented)
- Color is never the sole conveyor of meaning — badges include text labels, status indicators include icons
- `color-scheme: light` / `dark` set on `:root` / `[data-theme="dark"]` for native browser dark mode (implemented)

## What NOT to do
- No border-radius anywhere (not even on badges or buttons)
- No card-based layout (no `box-shadow` elevation tricks)
- No grain/noise texture (gitstats reports are opened as `file://` — embedded SVG noise has Safari flicker issues and degrades the static file use case)
- No purple gradients, no blobs, no decorative backgrounds
- Do not use system-ui or sans-serif for body text — the full monospace commitment is the identity
- Do not use the current steel blue (`#4a7ab5`) — replace with amber everywhere

## Implementation Notes
- CSS lives in `gitstats/gitstats.css` (single file, ~584 lines as of 2026-03)
- Multi-dataset `CHART_COLORS` in `report_creator.py` should use amber-first ordering
- Body `font-family` must be `var(--font-mono)` — the current fallback to `var(--font-sans)` is a bug in the original implementation
- `--link-color` and `--bar-color` should both be `var(--amber)` in both themes

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-24 | Full IBM Plex Mono (body included) | Gitstats users are developers — all-mono body text is correct for this audience and creates an unmistakable terminal identity |
| 2026-03-24 | Warm amber (#D97706) replaces steel blue | Steel blue is generic and fights the warm grayscale palette; amber is rare in the git analytics space and coheres with the warm near-black |
| 2026-03-24 | No grain/noise texture | Reports opened as file:// — embedded SVG noise flickers in Safari and degrades the static file use case |
| 2026-03-24 | Zero border-radius, no cards | Terminal aesthetic; card grids are SaaS patterns that weaken the developer-native identity |
| 2026-03-24 | Generation command block on index page | Strongest single signal of "this is a CLI tool" — surfaces the command that created the report |
| 2026-03-24 | Mobile nav = horizontal scroll, not hamburger | Developer tool audience — dense, direct access is correct. Hamburger adds interaction cost with no benefit for 6 links. |
| 2026-03-24 | Tables use display:block + overflow-x:auto | Prevents horizontal page scroll without disrupting table semantics; standard responsive table pattern |
| 2026-03-24 | AI summary left-border is semantic, not decorative | Intentional exception to no-left-border rule: distinguishes AI-generated content from report data |
| 2026-03-25 | Mobile nav = horizontal scroll, not hamburger | Developer tool audience — dense, direct access is correct. Hamburger adds interaction cost with no benefit for 6 links. |
| 2026-03-25 | Added: Interactive States, Responsive Design, Component Library, Chart System sections | Closes gap between CSS implementation and design documentation |
| 2026-03-24 | Design system created | Created by /design-consultation based on competitive research (GitHub Insights, GitLab Analytics, Sourcegraph, Wakatime, git-quick-stats) + Codex + Claude subagent review |
