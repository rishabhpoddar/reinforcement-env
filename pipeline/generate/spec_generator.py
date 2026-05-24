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
    SEED_SPECS_PATH,
    SPEC_HISTORY_PATH,
    get_anthropic_key,
    log,
)


SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "site_name": {"type": "string"},
        "category": {"type": "string"},
        "niche": {"type": "string"},
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
    """Load previously generated specifications."""
    if not SPEC_HISTORY_PATH.exists():
        return []
    with open(SPEC_HISTORY_PATH) as f:
        return json.load(f)


def save_spec_to_history(spec: dict) -> None:
    """Append a spec to the history file."""
    history = load_spec_history()
    history.append(spec)
    with open(SPEC_HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


def _build_generation_prompt(
    seed_specs: list[dict],
    history: list[dict],
    force_broken: bool | None = None,
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
        history_summary = (
            f"\n\n## Previously Generated (AVOID THESE)\n"
            f"Categories already used: {', '.join(categories_used)}\n"
            f"Niches already used: {', '.join(niches_used)}\n"
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

    return f"""Generate a novel, detailed website specification for a multi-page website.

## Seed Examples (for format reference and inspiration)
{seed_text}
{history_summary}

## Requirements
- Generate a UNIQUE website that is DIFFERENT from all examples above
- Be creative with the niche — don't just pick obvious categories
- The site MUST have at least 5 pages (preferably 5-7)
- Include detailed page descriptions that specify exact layout components
- The design system should be cohesive and specific (exact hex colors, clear typography choices)
- Responsive notes should describe specific adaptations per viewport
- Special elements should include 3-5 distinctive design features
- Complexity should match the design (simple sites have fewer components)
{broken_instruction}

## Image Assets
Include an "image_assets" array with 3-8 images the site needs. Each entry must have:
- "filename": e.g. "hero-bg.png", "team-photo.png" (must end in .png)
- "prompt": Detailed description for AI image generation — describe subject, style, colors, mood, composition. Reference the site's color palette and mood for visual consistency.
- "size": "1536x1024" for landscape/hero/banner images, "1024x1536" for portrait, "1024x1024" for square
- "used_on": which page(s) will use this image (e.g. "home", "about, team")
- "purpose": how it's used in the layout (e.g. "hero background", "team member photo", "section illustration")

Think about what images would make the site look professional and complete: hero images, section backgrounds, feature illustrations, team photos, product images, etc.

## Diversity Guidelines
- Vary color schemes: try dark themes, pastels, vibrant, monochrome, earthy, neon
- Vary layout styles: minimal, dense, magazine, card-based, full-width, sidebar-heavy
- Vary typography: serif/sans-serif/monospace mixing, different scales
- Vary complexity levels across generated specs
- Think beyond obvious categories: consider niche businesses, cultural sites, community platforms

Return ONLY the JSON spec, nothing else."""


def generate_spec(
    model: str = "claude-sonnet-4-6",
    force_broken: bool | None = None,
) -> dict:
    """Generate a new website specification using an LLM.

    Args:
        model: Anthropic model to use for generation.
        force_broken: If True/False, force broken/clean. If None, random based on probability.

    Returns:
        A website specification dict.
    """
    client = Anthropic(api_key=get_anthropic_key())

    seed_specs = load_seed_specs()
    history = load_spec_history()

    prompt = _build_generation_prompt(seed_specs, history, force_broken)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
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

    # Save to history
    save_spec_to_history(spec)

    return spec


def generate_specs_batch(
    count: int,
    model: str = "claude-sonnet-4-6",
    broken_count: int | None = None,
) -> list[dict]:
    """Generate multiple specs, ensuring diversity.

    Args:
        count: Number of specs to generate.
        model: Anthropic model to use.
        broken_count: Exact number of broken specs. If None, uses probability.

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
            spec = generate_spec(model=model, force_broken=force_broken)
            specs.append(spec)
            log.info(
                f"  [{i+1}/{count}] Generated: {spec['site_name']} "
                f"({spec['category']}) "
                f"{'[BROKEN]' if spec.get('is_broken') else '[CLEAN]'}"
            )
        except Exception as e:
            log.info(f"  [{i+1}/{count}] Failed: {e}, retrying...")
            try:
                spec = generate_spec(model=model, force_broken=force_broken)
                specs.append(spec)
                log.info(
                    f"  [{i+1}/{count}] Retry succeeded: {spec['site_name']}"
                )
            except Exception as e2:
                log.info(f"  [{i+1}/{count}] Retry also failed: {e2}, skipping")

    return specs
