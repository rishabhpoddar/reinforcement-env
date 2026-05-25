# Web Design Replication Task: Archiv für Typografische Praxis

You are given screenshots of a **8-page design-archive website** at three viewport sizes
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

- HTML files: `startseite.html`, `sammlung.html`, `objekt-detail.html`, `essays.html`, `essay-detail.html`, `raster-system.html`, `uber-uns.html`, `kontakt.html`
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

- `reference_screenshots/startseite-desktop.png` — startseite page, desktop viewport
- `reference_screenshots/startseite-tablet.png` — startseite page, tablet viewport
- `reference_screenshots/startseite-mobile.png` — startseite page, mobile viewport
- `reference_screenshots/sammlung-desktop.png` — sammlung page, desktop viewport
- `reference_screenshots/sammlung-tablet.png` — sammlung page, tablet viewport
- `reference_screenshots/sammlung-mobile.png` — sammlung page, mobile viewport
- `reference_screenshots/objekt-detail-desktop.png` — objekt-detail page, desktop viewport
- `reference_screenshots/objekt-detail-tablet.png` — objekt-detail page, tablet viewport
- `reference_screenshots/objekt-detail-mobile.png` — objekt-detail page, mobile viewport
- `reference_screenshots/essays-desktop.png` — essays page, desktop viewport
- `reference_screenshots/essays-tablet.png` — essays page, tablet viewport
- `reference_screenshots/essays-mobile.png` — essays page, mobile viewport
- `reference_screenshots/essay-detail-desktop.png` — essay-detail page, desktop viewport
- `reference_screenshots/essay-detail-tablet.png` — essay-detail page, tablet viewport
- `reference_screenshots/essay-detail-mobile.png` — essay-detail page, mobile viewport
- `reference_screenshots/raster-system-desktop.png` — raster-system page, desktop viewport
- `reference_screenshots/raster-system-tablet.png` — raster-system page, tablet viewport
- `reference_screenshots/raster-system-mobile.png` — raster-system page, mobile viewport
- `reference_screenshots/uber-uns-desktop.png` — uber-uns page, desktop viewport
- `reference_screenshots/uber-uns-tablet.png` — uber-uns page, tablet viewport
- `reference_screenshots/uber-uns-mobile.png` — uber-uns page, mobile viewport
- `reference_screenshots/kontakt-desktop.png` — kontakt page, desktop viewport
- `reference_screenshots/kontakt-tablet.png` — kontakt page, tablet viewport
- `reference_screenshots/kontakt-mobile.png` — kontakt page, mobile viewport

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
