# Web Design Replication Task: Atelier Papier Buvard

You are given screenshots of a **7-page artisan-stationery website** at three viewport sizes
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

- HTML files: `accueil.html`, `collections.html`, `atelier.html`, `savoir-faire.html`, `journal.html`, `commander.html`, `contact.html`
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

- `reference_screenshots/accueil-desktop.png` — accueil page, desktop viewport
- `reference_screenshots/accueil-tablet.png` — accueil page, tablet viewport
- `reference_screenshots/accueil-mobile.png` — accueil page, mobile viewport
- `reference_screenshots/collections-desktop.png` — collections page, desktop viewport
- `reference_screenshots/collections-tablet.png` — collections page, tablet viewport
- `reference_screenshots/collections-mobile.png` — collections page, mobile viewport
- `reference_screenshots/atelier-desktop.png` — atelier page, desktop viewport
- `reference_screenshots/atelier-tablet.png` — atelier page, tablet viewport
- `reference_screenshots/atelier-mobile.png` — atelier page, mobile viewport
- `reference_screenshots/savoir-faire-desktop.png` — savoir-faire page, desktop viewport
- `reference_screenshots/savoir-faire-tablet.png` — savoir-faire page, tablet viewport
- `reference_screenshots/savoir-faire-mobile.png` — savoir-faire page, mobile viewport
- `reference_screenshots/journal-desktop.png` — journal page, desktop viewport
- `reference_screenshots/journal-tablet.png` — journal page, tablet viewport
- `reference_screenshots/journal-mobile.png` — journal page, mobile viewport
- `reference_screenshots/commander-desktop.png` — commander page, desktop viewport
- `reference_screenshots/commander-tablet.png` — commander page, tablet viewport
- `reference_screenshots/commander-mobile.png` — commander page, mobile viewport
- `reference_screenshots/contact-desktop.png` — contact page, desktop viewport
- `reference_screenshots/contact-tablet.png` — contact page, tablet viewport
- `reference_screenshots/contact-mobile.png` — contact page, mobile viewport

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

## Important: This Website Has Intentional Design Defects

This website contains **intentional design defects**. You must **replicate the design EXACTLY as shown** in the screenshots, including any defects you notice. Do NOT fix or improve the design — reproduce it faithfully.
