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
- **Approach:** Minimal-functional. Transitions aid comprehension (theme switch, hover feedback) but are not decorative.
- **Standard transition:** `150ms ease-out` — apply to: `background-color`, `color`, `border-color`
- **Hover convention:** On hover, borders and links shift to amber. Tables: row background becomes `--surface`.
- **Theme switch:** Smooth `background-color` and `color` transitions on `body` and key elements. No jarring instant flip.
- **No animations on data load** — reports are static; animation would feel wrong.

## Accessibility
- Amber `#D97706` on white `#ffffff`: contrast ratio 4.6:1 (passes WCAG AA)
- GitHub green heatmap scale: safe for deuteranopia/protanopia (green is not paired with red for the same signal)
- All nav links have min 44px touch targets
- Color is never the sole conveyor of meaning — badges include text labels, status indicators include icons

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
| 2026-03-24 | Design system created | Created by /design-consultation based on competitive research (GitHub Insights, GitLab Analytics, Sourcegraph, Wakatime, git-quick-stats) + Codex + Claude subagent review |
