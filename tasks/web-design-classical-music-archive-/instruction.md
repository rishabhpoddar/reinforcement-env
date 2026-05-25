# Web Design Replication Task: ध्रुपद धरोहर

You are given screenshots of a **8-page classical-music-archive website** at three viewport sizes
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

- HTML files: `मुख्य-पृष्ठ.html`, `घराने.html`, `राग-कोश.html`, `गुरु-शिष्य.html`, `अभिलेखागार.html`, `लेख.html`, `कार्यशालाएं.html`, `संपर्क.html`
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

- `reference_screenshots/मुख्य-पृष्ठ-desktop.png` — मुख्य-पृष्ठ page, desktop viewport
- `reference_screenshots/मुख्य-पृष्ठ-tablet.png` — मुख्य-पृष्ठ page, tablet viewport
- `reference_screenshots/मुख्य-पृष्ठ-mobile.png` — मुख्य-पृष्ठ page, mobile viewport
- `reference_screenshots/घराने-desktop.png` — घराने page, desktop viewport
- `reference_screenshots/घराने-tablet.png` — घराने page, tablet viewport
- `reference_screenshots/घराने-mobile.png` — घराने page, mobile viewport
- `reference_screenshots/राग-कोश-desktop.png` — राग-कोश page, desktop viewport
- `reference_screenshots/राग-कोश-tablet.png` — राग-कोश page, tablet viewport
- `reference_screenshots/राग-कोश-mobile.png` — राग-कोश page, mobile viewport
- `reference_screenshots/गुरु-शिष्य-desktop.png` — गुरु-शिष्य page, desktop viewport
- `reference_screenshots/गुरु-शिष्य-tablet.png` — गुरु-शिष्य page, tablet viewport
- `reference_screenshots/गुरु-शिष्य-mobile.png` — गुरु-शिष्य page, mobile viewport
- `reference_screenshots/अभिलेखागार-desktop.png` — अभिलेखागार page, desktop viewport
- `reference_screenshots/अभिलेखागार-tablet.png` — अभिलेखागार page, tablet viewport
- `reference_screenshots/अभिलेखागार-mobile.png` — अभिलेखागार page, mobile viewport
- `reference_screenshots/लेख-desktop.png` — लेख page, desktop viewport
- `reference_screenshots/लेख-tablet.png` — लेख page, tablet viewport
- `reference_screenshots/लेख-mobile.png` — लेख page, mobile viewport
- `reference_screenshots/कार्यशालाएं-desktop.png` — कार्यशालाएं page, desktop viewport
- `reference_screenshots/कार्यशालाएं-tablet.png` — कार्यशालाएं page, tablet viewport
- `reference_screenshots/कार्यशालाएं-mobile.png` — कार्यशालाएं page, mobile viewport
- `reference_screenshots/संपर्क-desktop.png` — संपर्क page, desktop viewport
- `reference_screenshots/संपर्क-tablet.png` — संपर्क page, tablet viewport
- `reference_screenshots/संपर्क-mobile.png` — संपर्क page, mobile viewport

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
