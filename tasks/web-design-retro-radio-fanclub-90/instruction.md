# Web Design Replication Task: रेडियो तरंग 90

You are given screenshots of a **8-page retro-radio-fanclub website** at three viewport sizes
(desktop 1280px, tablet 768px, mobile 375px).

Your task is to create a **pixel-perfect replication** of this website using HTML and CSS.

## CRITICAL: What "pixel-perfect" means

This is NOT about creating a "similar looking" website. You must reproduce the EXACT layout, structure, and visual design shown in the screenshots:

- **Study each screenshot carefully** before writing any code
- **Count the exact number of columns, cards, sections** on each page
- **Match the precise layout structure** — if the hero has a 2-column split with text left and image right, yours must too
- **Reproduce specific design elements** — drop caps, sidebars, decorative dividers, card styles, badges, overlays
- **Match the color palette exactly** — extract colors from the screenshots and use them
- **Match the typography hierarchy** — heading sizes, font weights, italic vs regular, serif vs sans-serif
- **Match spacing and proportions** — margins, padding, gaps between elements
- **Match the responsive behavior** — compare desktop vs tablet vs mobile screenshots to understand how the layout adapts

Do NOT take creative liberties. Do NOT simplify the design. Do NOT substitute your own layout ideas. Your output should look identical to the screenshots when rendered in a browser.

## Files to Create

- HTML files: `mukhya-prishth.html`, `kaaryakram-suchi.html`, `jingle-sangrah.html`, `redio-natak.html`, `shrota-patra.html`, `tasveer-deergha.html`, `sadasyata.html`, `sampark.html`
- Shared stylesheet: `styles.css`
- Place all files in `/app/`

## Constraints

- Navigation between pages must work via relative links (e.g., `href="about.html"`)
- No external dependencies — no CDN links, no JavaScript libraries, no external fonts
- Use system font stacks that match the visual style (serif, sans-serif, monospace as appropriate)
- Focus entirely on visual fidelity — functionality is not required

## Image Assets

The required media files for the website are provided in the `/app/assets/` folder. Use these images in your HTML with relative paths like `<img src="assets/filename.png">`. Do NOT generate or create new images — use only the provided assets.


## Reference Screenshots

- `reference_screenshots/mukhya-prishth-desktop.png` — mukhya-prishth page, desktop viewport
- `reference_screenshots/mukhya-prishth-tablet.png` — mukhya-prishth page, tablet viewport
- `reference_screenshots/mukhya-prishth-mobile.png` — mukhya-prishth page, mobile viewport
- `reference_screenshots/kaaryakram-suchi-desktop.png` — kaaryakram-suchi page, desktop viewport
- `reference_screenshots/kaaryakram-suchi-tablet.png` — kaaryakram-suchi page, tablet viewport
- `reference_screenshots/kaaryakram-suchi-mobile.png` — kaaryakram-suchi page, mobile viewport
- `reference_screenshots/jingle-sangrah-desktop.png` — jingle-sangrah page, desktop viewport
- `reference_screenshots/jingle-sangrah-tablet.png` — jingle-sangrah page, tablet viewport
- `reference_screenshots/jingle-sangrah-mobile.png` — jingle-sangrah page, mobile viewport
- `reference_screenshots/redio-natak-desktop.png` — redio-natak page, desktop viewport
- `reference_screenshots/redio-natak-tablet.png` — redio-natak page, tablet viewport
- `reference_screenshots/redio-natak-mobile.png` — redio-natak page, mobile viewport
- `reference_screenshots/shrota-patra-desktop.png` — shrota-patra page, desktop viewport
- `reference_screenshots/shrota-patra-tablet.png` — shrota-patra page, tablet viewport
- `reference_screenshots/shrota-patra-mobile.png` — shrota-patra page, mobile viewport
- `reference_screenshots/tasveer-deergha-desktop.png` — tasveer-deergha page, desktop viewport
- `reference_screenshots/tasveer-deergha-tablet.png` — tasveer-deergha page, tablet viewport
- `reference_screenshots/tasveer-deergha-mobile.png` — tasveer-deergha page, mobile viewport
- `reference_screenshots/sadasyata-desktop.png` — sadasyata page, desktop viewport
- `reference_screenshots/sadasyata-tablet.png` — sadasyata page, tablet viewport
- `reference_screenshots/sadasyata-mobile.png` — sadasyata page, mobile viewport
- `reference_screenshots/sampark-desktop.png` — sampark page, desktop viewport
- `reference_screenshots/sampark-tablet.png` — sampark page, tablet viewport
- `reference_screenshots/sampark-mobile.png` — sampark page, mobile viewport

## How to Approach This

1. **Start by examining ALL screenshots** — understand the full site design before writing code
2. **Identify the design system** — colors, fonts, spacing scale, shared components (nav, footer)
3. **Build the shared CSS first** — variables, resets, typography, layout utilities, component styles
4. **Build each page** — match the exact structure shown in the desktop screenshot
5. **Add responsive styles** — compare tablet and mobile screenshots to understand breakpoint behavior
6. **Review your work** — compare your output against each screenshot and fix discrepancies

## Grading

You will be graded by an LLM judge that compares your rendered pages against the reference screenshots side by side. The judge scores:
- **Layout** (0-10) — are sections, columns, and elements positioned exactly as shown?
- **Color** (0-10) — does the color scheme match precisely?
- **Typography** (0-10) — are font sizes, weights, and styles correct?
- **Spacing** (0-10) — are margins, padding, and whitespace proportions right?
- **Components** (0-10) — are UI elements (cards, buttons, nav, badges, dividers) visually accurate?

A score of 10 means your page is visually indistinguishable from the reference. Aim for 10/10 on every criterion.
