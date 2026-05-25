# Web Design Replication Task: Tactile Sound Lab

You are given screenshots of a **7-page audio-equipment-review website** at three viewport sizes
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

- HTML files: `home.html`, `reviews.html`, `gear-database.html`, `lab-tests.html`, `comparisons.html`, `community.html`, `about.html`
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

- `reference_screenshots/home-desktop.png` — home page, desktop viewport
- `reference_screenshots/home-tablet.png` — home page, tablet viewport
- `reference_screenshots/home-mobile.png` — home page, mobile viewport
- `reference_screenshots/reviews-desktop.png` — reviews page, desktop viewport
- `reference_screenshots/reviews-tablet.png` — reviews page, tablet viewport
- `reference_screenshots/reviews-mobile.png` — reviews page, mobile viewport
- `reference_screenshots/gear-database-desktop.png` — gear-database page, desktop viewport
- `reference_screenshots/gear-database-tablet.png` — gear-database page, tablet viewport
- `reference_screenshots/gear-database-mobile.png` — gear-database page, mobile viewport
- `reference_screenshots/lab-tests-desktop.png` — lab-tests page, desktop viewport
- `reference_screenshots/lab-tests-tablet.png` — lab-tests page, tablet viewport
- `reference_screenshots/lab-tests-mobile.png` — lab-tests page, mobile viewport
- `reference_screenshots/comparisons-desktop.png` — comparisons page, desktop viewport
- `reference_screenshots/comparisons-tablet.png` — comparisons page, tablet viewport
- `reference_screenshots/comparisons-mobile.png` — comparisons page, mobile viewport
- `reference_screenshots/community-desktop.png` — community page, desktop viewport
- `reference_screenshots/community-tablet.png` — community page, tablet viewport
- `reference_screenshots/community-mobile.png` — community page, mobile viewport
- `reference_screenshots/about-desktop.png` — about page, desktop viewport
- `reference_screenshots/about-tablet.png` — about page, tablet viewport
- `reference_screenshots/about-mobile.png` — about page, mobile viewport

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
