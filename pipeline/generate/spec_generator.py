"""LLM-driven website specification generator.

Generates novel website specs by prompting an LLM with seed examples
and previously generated specs to ensure diversity and avoid repetition.
"""

import json
import random
from pathlib import Path

from anthropic import Anthropic

from pipeline.config import (
    BROKEN_WEBSITE_PROBABILITY,
    GENERATED_DIR,
    SEED_SPECS_PATH,
    get_anthropic_key,
    log,
)


SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "site_name": {"type": "string"},
        "category": {"type": "string"},
        "niche": {"type": "string"},
        "language": {
            "type": "string",
            "description": "Primary language code, e.g. 'en', 'es', 'ja', 'ar', 'fr', 'de', 'ko', 'zh', 'hi', 'pt', 'mixed-en-fr'",
        },
        "text_direction": {
            "type": "string",
            "enum": ["ltr", "rtl"],
            "description": "Text direction — 'rtl' for Arabic, Hebrew, etc.",
        },
        "design_style": {
            "type": "string",
            "description": "Visual design style, e.g. 'minimalist', 'brutalist', 'glassmorphism', 'neumorphism', 'retro-90s', 'art-deco', 'corporate', 'editorial', 'playful', 'luxury'",
        },
        "dark_mode": {"type": "boolean"},
        "nav_style": {
            "type": "string",
            "description": "Navigation pattern, e.g. 'top-bar', 'mega-menu', 'side-drawer', 'bottom-tabs', 'hamburger-only', 'breadcrumbs-with-sidebar', 'tab-navigation'",
        },
        "pages": {"type": "array", "items": {"type": "string"}, "minItems": 5},
        "design_system": {
            "type": "object",
            "properties": {
                "color_palette": {
                    "type": "object",
                    "properties": {
                        "primary": {"type": "string"},
                        "secondary": {"type": "string"},
                        "accent": {"type": "string"},
                        "bg": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["primary", "secondary", "accent", "bg", "text"],
                },
                "typography": {
                    "type": "object",
                    "properties": {
                        "heading_font": {"type": "string"},
                        "body_font": {"type": "string"},
                        "scale": {"type": "string"},
                    },
                    "required": ["heading_font", "body_font", "scale"],
                },
                "layout_style": {"type": "string"},
                "mood": {"type": "string"},
            },
            "required": ["color_palette", "typography", "layout_style", "mood"],
        },
        "page_descriptions": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "complexity": {"type": "string", "enum": ["simple", "moderate", "complex"]},
        "special_elements": {"type": "array", "items": {"type": "string"}},
        "image_assets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "prompt": {"type": "string"},
                    "size": {"type": "string", "enum": ["1024x1024", "1024x1536", "1536x1024"]},
                    "used_on": {"type": "string"},
                    "purpose": {"type": "string"},
                },
                "required": ["filename", "prompt", "size", "used_on", "purpose"],
            },
            "minItems": 3,
        },
        "responsive_notes": {"type": "string"},
        "is_broken": {"type": "boolean"},
        "defects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "page": {"type": "string"},
                    "viewport": {"type": "string", "enum": ["desktop", "tablet", "mobile", "all"]},
                    "description": {"type": "string"},
                },
                "required": ["type", "page", "viewport", "description"],
            },
        },
    },
    "required": [
        "site_name",
        "category",
        "niche",
        "language",
        "text_direction",
        "design_style",
        "dark_mode",
        "nav_style",
        "pages",
        "design_system",
        "page_descriptions",
        "complexity",
        "special_elements",
        "image_assets",
        "responsive_notes",
        "is_broken",
    ],
}


def load_seed_specs() -> list[dict]:
    """Load seed example specifications."""
    with open(SEED_SPECS_PATH) as f:
        return json.load(f)


def load_spec_history() -> list[dict]:
    """Load specs from existing generated workspaces."""
    if not GENERATED_DIR.exists():
        return []
    specs = []
    for spec_file in sorted(GENERATED_DIR.glob("*/spec.json")):
        try:
            with open(spec_file) as f:
                specs.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return specs


def _build_generation_prompt(
    seed_specs: list[dict],
    history: list[dict],
    force_broken: bool | None = None,
    force_language: str | None = None,
) -> str:
    """Build the prompt for generating a new website spec."""
    # Show a sample of seed specs (not all, to save tokens)
    sample_seeds = random.sample(seed_specs, min(5, len(seed_specs)))
    seed_text = json.dumps(sample_seeds, indent=2)

    # Show recent history to avoid repetition
    recent_history = history[-10:] if history else []
    history_summary = ""
    if recent_history:
        categories_used = [s.get("category", "unknown") for s in recent_history]
        niches_used = [s.get("niche", "unknown") for s in recent_history]
        languages_used = [s.get("language", "en") for s in recent_history]
        styles_used = [s.get("design_style", "unknown") for s in recent_history]
        history_summary = (
            f"\n\n## Previously Generated (AVOID THESE)\n"
            f"Categories already used: {', '.join(categories_used)}\n"
            f"Niches already used: {', '.join(niches_used)}\n"
            f"Languages already used: {', '.join(languages_used)}\n"
            f"Design styles already used: {', '.join(styles_used)}\n"
            f"Total generated so far: {len(history)}\n"
        )

    # Decide if this should be a broken website
    if force_broken is None:
        should_be_broken = random.random() < BROKEN_WEBSITE_PROBABILITY
    else:
        should_be_broken = force_broken

    broken_instruction = ""
    if should_be_broken:
        broken_instruction = """

## IMPORTANT: This website MUST have intentional defects
Set "is_broken" to true and include a "defects" array with 2-4 defects.
Each defect MUST have these fields:
- "type": one of "broken_responsiveness", "typo", "bad_design", "alignment", "overflow", "inconsistency"
- "page": which page the defect is on (must match a page name from the pages array)
- "viewport": which viewport the defect is most visible at — "desktop", "tablet", "mobile", or "all"
- "description": specific description of the defect

Defect types:
- "broken_responsiveness": A specific element/section that breaks on mobile or tablet (viewport should be "mobile" or "tablet")
- "typo": A misspelled word in a prominent location (viewport is usually "all")
- "bad_design": A specific design choice that clashes — wrong color, bad contrast, etc. (viewport is usually "all")
- "alignment": Elements that are visibly misaligned or inconsistently spaced
- "overflow": Text or elements that overflow their containers
- "inconsistency": A component styled differently than similar components on the site

Make the defects specific and realistic — things a real developer might accidentally ship.
The rest of the site should be well-designed (the defects should stand out against good design)."""
    else:
        broken_instruction = '\n\nSet "is_broken" to false. Do not include a "defects" field.'

    # Randomly pick diversity hints to steer generation
    language_options = {
        "en": "Use English (en, ltr)",
        "es": "Use Spanish (es, ltr) — all content in Spanish",
        "fr": "Use French (fr, ltr) — all content in French",
        "ja": "Use Japanese (ja, ltr) — all content in Japanese",
        "ar": "Use Arabic (ar, rtl) — all content in Arabic with RTL layout",
        "ko": "Use Korean (ko, ltr) — all content in Korean",
        "de": "Use German (de, ltr) — all content in German",
        "pt": "Use Portuguese (pt, ltr) — all content in Portuguese",
        "hi": "Use Hindi (hi, ltr) — all content in Hindi",
        "zh": "Use Chinese (zh, ltr) — all content in Chinese",
        "mixed-en-es": "Use a bilingual mix (mixed-en-es, ltr) — headings and nav in English, body content in Spanish",
        "mixed-en-ja": "Use a bilingual mix (mixed-en-ja, ltr) — Japanese content with English navigation",
    }

    if force_language:
        if force_language not in language_options:
            raise ValueError(f"Unknown language '{force_language}'. Options: {', '.join(language_options.keys())}")
        language_hint = language_options[force_language]
    else:
        language_hint = random.choice([
            language_options["en"],
            language_options["es"],
            language_options["fr"],
            language_options["ja"],
            language_options["ar"],
            language_options["ko"],
            language_options["de"],
            language_options["pt"],
            language_options["hi"],
            language_options["zh"],
            language_options["mixed-en-es"],
            language_options["mixed-en-ja"],
            language_options["en"],
            language_options["en"],
            language_options["en"],
        ])

    style_hint = random.choice([
        "minimalist — lots of whitespace, restrained color, clean lines",
        "brutalist — raw, bold, stark contrasts, unconventional layouts, exposed grid",
        "glassmorphism — frosted glass cards, transparency, blur effects, subtle borders",
        "neumorphism — soft shadows, extruded/inset elements, muted monochrome palette",
        "retro-90s — pixel-ish fonts, bright clashing colors, visible borders, nostalgic web aesthetic",
        "art-deco — geometric patterns, gold/black palette, ornate decorative elements, luxury feel",
        "corporate — clean, professional, blue/gray tones, trustworthy and conventional",
        "editorial — magazine-like, strong typography hierarchy, pull quotes, multi-column text",
        "playful — rounded shapes, bright gradients, bouncy spacing, fun illustrations",
        "luxury — dark backgrounds, gold accents, elegant serif fonts, generous spacing",
        "cyberpunk — neon colors on dark, glitch effects, monospace fonts, tech dystopia aesthetic",
        "organic — natural textures, earthy tones, flowing shapes, hand-drawn feel",
        "swiss/international — grid-based, Helvetica-style, asymmetric layouts, strong alignment",
        "maximalist — dense information, bold colors everywhere, layered elements, visual complexity",
    ])

    dark_hint = random.choice([
        "Use a dark theme (dark_mode: true) — dark backgrounds with light text",
        "Use a light theme (dark_mode: false)",
        "Use a light theme (dark_mode: false)",
        "Use a dark theme (dark_mode: true) — dark backgrounds with light text",
        "Use a light theme (dark_mode: false)",
    ])

    nav_hint = random.choice([
        "top-bar — standard horizontal navigation bar",
        "mega-menu — top bar that expands to show categorized dropdown panels",
        "side-drawer — permanent or collapsible sidebar navigation",
        "bottom-tabs — mobile-app-style bottom tab bar (even on desktop)",
        "hamburger-only — hidden navigation behind hamburger icon at all viewports",
        "tab-navigation — tabbed interface for page sections",
        "top-bar — standard horizontal navigation bar",
        "top-bar — standard horizontal navigation bar",
    ])

    layout_hint = random.choice([
        "Use conventional symmetric layouts",
        "Use asymmetric grid layouts — unequal columns, off-center elements",
        "Use overlapping sections — elements that cross section boundaries",
        "Use a split-screen layout — two distinct halves for content",
        "Use full-width immersive sections alternating with contained content",
        "Use a sticky sidebar with scrolling main content",
        "Use a masonry/pinterest-style grid layout for content",
        "Use conventional symmetric layouts",
    ])

    content_hint = random.choice([
        "Include text-heavy pages with long-form content, pull quotes, and multi-column text",
        "Include data-heavy pages with comparison tables, stat counters, and pricing grids",
        "Include form-heavy pages with multi-section forms, toggles, sliders, and input groups",
        "Include media-heavy pages with photo galleries, video placeholders, and image grids",
        "Include dashboard-like pages with cards, charts placeholder areas, and data tables",
        "Include standard content density",
        "Include standard content density",
    ])

    responsive_hint = random.choice([
        "Standard responsive — desktop layout adapts progressively to tablet and mobile",
        "Mobile-first design — mobile is the primary layout, desktop expands it",
        "Drastically different mobile layout — completely rearranged sections, bottom nav on mobile, hidden elements",
        "Tablet-optimized — tablet gets its own unique layout, not just between desktop and mobile",
        "Standard responsive — desktop layout adapts progressively to tablet and mobile",
    ])

    return f"""Generate a novel, detailed website specification for a multi-page website.

## Seed Examples (for format reference and inspiration)
{seed_text}
{history_summary}

## Requirements
- Generate a UNIQUE website that is DIFFERENT from all examples above
- Be creative with the niche — don't just pick obvious categories
- The site MUST have at least 5 pages (preferably 5-8)
- Include detailed page descriptions that specify exact layout components
- The design system should be cohesive and specific (exact hex colors, clear typography choices)
- Responsive notes should describe specific adaptations per viewport
- Special elements should include 3-5 distinctive design features
- Complexity should match the design (simple sites have fewer components)
{broken_instruction}

## New Required Fields
You MUST include these fields in your spec:
- "language": language code (e.g. "en", "es", "ja", "ar", "mixed-en-fr")
- "text_direction": "ltr" or "rtl" (use "rtl" for Arabic, Hebrew, Urdu, Persian)
- "design_style": the visual design approach (e.g. "minimalist", "brutalist", "glassmorphism", etc.)
- "dark_mode": true or false
- "nav_style": navigation pattern (e.g. "top-bar", "mega-menu", "side-drawer", "bottom-tabs", "hamburger-only")

All text content in page_descriptions should be described in the chosen language.
If using a non-English language, specify that headings, body text, navigation labels, button text, etc. should all be in that language.
If using RTL, note specific RTL layout requirements in responsive_notes.

## Diversity Directives for THIS Spec
Follow these specific directives to ensure variety:
- **Language**: {language_hint}
- **Design style**: {style_hint}
- **Theme**: {dark_hint}
- **Navigation**: {nav_hint}
- **Layout approach**: {layout_hint}
- **Content type**: {content_hint}
- **Responsive strategy**: {responsive_hint}

## Image Assets
Include an "image_assets" array with 3-8 images the site needs. Each entry must have:
- "filename": e.g. "hero-bg.png", "team-photo.png" (must end in .png)
- "prompt": Detailed description for AI image generation — describe subject, style, colors, mood, composition. Reference the site's color palette and mood for visual consistency.
- "size": "1536x1024" for landscape/hero/banner images, "1024x1536" for portrait, "1024x1024" for square
- "used_on": which page(s) will use this image (e.g. "home", "about, team")
- "purpose": how it's used in the layout (e.g. "hero background", "team member photo", "section illustration")

Think about what images would make the site look professional and complete: hero images, section backgrounds, feature illustrations, team photos, product images, etc.

## Diversity Guidelines
- Vary color schemes: dark themes, pastels, vibrant, monochrome, earthy, neon, gradients, high-contrast
- Vary layout styles: minimal, dense, magazine, card-based, full-width, sidebar-heavy, asymmetric, overlapping, split-screen, masonry
- Vary typography: serif/sans-serif/monospace mixing, different scales, display fonts for headings, condensed or wide spacing
- Vary complexity levels across generated specs
- Think beyond obvious categories: consider niche businesses, cultural sites, community platforms, government services, academic departments, hobbyist communities, local organizations
- Vary page content patterns: forms, data tables, timelines, testimonials, FAQs, galleries, dashboards, pricing, schedules
- Include realistic UI details: badges, status indicators, notification counts, progress bars, star ratings, toggle switches, breadcrumbs, announcement banners, cookie consent bars

Return ONLY the JSON spec, nothing else."""


def generate_spec(
    model: str = "claude-sonnet-4-6",
    force_broken: bool | None = None,
    force_language: str | None = None,
) -> dict:
    """Generate a new website specification using an LLM.

    Args:
        model: Anthropic model to use for generation.
        force_broken: If True/False, force broken/clean. If None, random based on probability.
        force_language: If set, force the website to use this language (e.g. 'en', 'ja', 'ar').

    Returns:
        A website specification dict.
    """
    client = Anthropic(api_key=get_anthropic_key())

    seed_specs = load_seed_specs()
    history = load_spec_history()

    prompt = _build_generation_prompt(seed_specs, history, force_broken, force_language)

    response = client.messages.create(
        model=model,
        max_tokens=16384,
        messages=[{"role": "user", "content": prompt}],
    )

    # Parse the response
    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        text = text.strip()

    spec = json.loads(text)

    # Validate minimum requirements
    if len(spec.get("pages", [])) < 5:
        raise ValueError(f"Spec has fewer than 5 pages: {spec.get('pages')}")

    if not spec.get("design_system", {}).get("color_palette"):
        raise ValueError("Spec missing color palette")

    # Backfill defaults for new fields if the LLM missed them
    spec.setdefault("language", "en")
    spec.setdefault("text_direction", "ltr")
    spec.setdefault("design_style", "corporate")
    spec.setdefault("dark_mode", False)
    spec.setdefault("nav_style", "top-bar")

    return spec


def generate_specs_batch(
    count: int,
    model: str = "claude-sonnet-4-6",
    broken_count: int | None = None,
    force_language: str | None = None,
) -> list[dict]:
    """Generate multiple specs, ensuring diversity.

    Args:
        count: Number of specs to generate.
        model: Anthropic model to use.
        broken_count: Exact number of broken specs. If None, uses probability.
        force_language: If set, force all specs to use this language.

    Returns:
        List of website specifications.
    """
    specs = []

    # Determine which indices should be broken
    if broken_count is not None:
        broken_indices = set(random.sample(range(count), min(broken_count, count)))
    else:
        broken_indices = None

    for i in range(count):
        force_broken = None
        if broken_indices is not None:
            force_broken = i in broken_indices

        try:
            spec = generate_spec(model=model, force_broken=force_broken, force_language=force_language)
            specs.append(spec)
            log.info(
                f"  [{i+1}/{count}] Generated: {spec['site_name']} "
                f"({spec['category']}) [{spec.get('language', 'en')}] "
                f"[{spec.get('design_style', '?')}] "
                f"{'[DARK]' if spec.get('dark_mode') else '[LIGHT]'} "
                f"{'[BROKEN]' if spec.get('is_broken') else '[CLEAN]'}"
            )
        except Exception as e:
            log.info(f"  [{i+1}/{count}] Failed: {e}, retrying...")
            try:
                spec = generate_spec(model=model, force_broken=force_broken, force_language=force_language)
                specs.append(spec)
                log.info(
                    f"  [{i+1}/{count}] Retry succeeded: {spec['site_name']}"
                )
            except Exception as e2:
                log.info(f"  [{i+1}/{count}] Retry also failed: {e2}, skipping")

    return specs
