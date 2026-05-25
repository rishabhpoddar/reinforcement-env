# Web Design Replication Task: NEONPULSE // Bioware Collective

You are given screenshots of a **8-page biohacker-community website** at three viewport sizes
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

- HTML files: `home.html`, `implant-registry.html`, `guides.html`, `submit-procedure.html`, `members.html`, `events.html`, `manifesto.html`, `contact.html`
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
- `reference_screenshots/implant-registry-desktop.png` — implant-registry page, desktop viewport
- `reference_screenshots/implant-registry-tablet.png` — implant-registry page, tablet viewport
- `reference_screenshots/implant-registry-mobile.png` — implant-registry page, mobile viewport
- `reference_screenshots/guides-desktop.png` — guides page, desktop viewport
- `reference_screenshots/guides-tablet.png` — guides page, tablet viewport
- `reference_screenshots/guides-mobile.png` — guides page, mobile viewport
- `reference_screenshots/submit-procedure-desktop.png` — submit-procedure page, desktop viewport
- `reference_screenshots/submit-procedure-tablet.png` — submit-procedure page, tablet viewport
- `reference_screenshots/submit-procedure-mobile.png` — submit-procedure page, mobile viewport
- `reference_screenshots/members-desktop.png` — members page, desktop viewport
- `reference_screenshots/members-tablet.png` — members page, tablet viewport
- `reference_screenshots/members-mobile.png` — members page, mobile viewport
- `reference_screenshots/events-desktop.png` — events page, desktop viewport
- `reference_screenshots/events-tablet.png` — events page, tablet viewport
- `reference_screenshots/events-mobile.png` — events page, mobile viewport
- `reference_screenshots/manifesto-desktop.png` — manifesto page, desktop viewport
- `reference_screenshots/manifesto-tablet.png` — manifesto page, tablet viewport
- `reference_screenshots/manifesto-mobile.png` — manifesto page, mobile viewport
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
