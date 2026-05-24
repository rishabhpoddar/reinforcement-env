# Scalable RL Environment for Web Design Replication
## Presentation Outline

---

## Slide 1: Title

**Scalable RL Environment for Web Design Replication**

One-liner: A pipeline that generates diverse website tasks, evaluates coding agents on visual fidelity, and produces calibrated reward signals for RL training.

---

## Slide 2: System Overview (Architecture Diagram)

The pipeline in one visual:

```
Spec → Build+Judge Loop → Screenshot → Package → Eval (Modal)
```

- **Spec**: LLM generates website specification with randomized diversity directives
- **Build+Judge**: Coding agent builds HTML/CSS, judges score iteratively until 10/10
- **Screenshot**: Playwright captures at 3 viewports (desktop/tablet/mobile)
- **Package**: Self-contained Harbor task with Dockerfile, grader, reference screenshots
- **Eval**: Runs on Modal cloud — 10 tasks × 10 trials in parallel, zero local resources

---

## Slide 3: Build + Judge Loop — Iterating to Quality

How each reference website gets built:

```
Builder (OpenCode agent + Playwright MCP)
  ↓ writes HTML/CSS to disk
Judge(s) (one per model, parallel)
  ↓ reads source, takes screenshots, scores 0-10
  ↓ writes actionable feedback
All 10/10? → Done. Otherwise → feedback fed back to builder → next iteration
```

- **Builder**: OpenCode agent with a randomly chosen model (Claude/GPT), has Playwright MCP for self-checking at 3 viewports, generates AI images via GPT image-2 plugin
- **Judges**: Multiple models run in parallel, each takes its own screenshots, scores against the spec, writes structured feedback
- **Session continuity**: Builder and judges reuse sessions across iterations — judges remember what they've already flagged, enables stuck detection
- **Stuck detection**: Built into the judge prompt — "if you've raised the same issues 3+ times, signal stuck" — eliminates a separate LLM call
- Converges when all judges give 10/10 or max iterations reached (typically 3-5 iterations)

---

## Slide 4: Website Diversity — By Design, Not By Chance

7 randomized dimensions steer every spec generation. Without this, the LLM gravitates toward the same patterns (English, light theme, corporate, top-bar nav).

| Dimension | Examples |
|-----------|----------|
| Language | en, fr, de, ar (RTL), hi, ja, ko, zh, mixed bilingual |
| Design style | minimalist, brutalist, glassmorphism, neumorphism, retro-90s, cyberpunk, swiss, maximalist, art-deco... (14 total) |
| Theme | Dark / Light |
| Navigation | top-bar, mega-menu, side-drawer, bottom-tabs, hamburger-only, tab-navigation |
| Layout | symmetric, asymmetric, split-screen, masonry, sticky sidebar |
| Content type | text-heavy, data-heavy, form-heavy, media-heavy, dashboard-like |
| Responsive | standard, mobile-first, drastically different mobile, tablet-optimized |

Every site has 5-8 pages, a shared stylesheet, and AI-generated image assets (GPT image-2).

**The 10 generated sites in this demo:**

| Site | Language | Style | Theme | Nav |
|------|----------|-------|-------|-----|
| Atelier Papier Buvard | French | minimalist | light | bottom-tabs |
| Tactile Sound Lab | English | neumorphism | dark | tab-navigation |
| NeonPulse Bioware | English/Spanish | cyberpunk | light | top-bar |
| Childcare Enrollment | Arabic (RTL) | playful | light | top-bar |
| Classical Music Archive | Hindi | neumorphism | light | mega-menu |
| Archiv für Typografische Praxis | German | swiss/international | light | side-drawer |
| The Pickle Periodical | English | maximalist | light | top-bar |
| Meridian Freight Index | English | swiss/international | dark | top-bar |
| रेडियो तरंग 90 | Hindi | retro-90s | light | tab-navigation |
| PixelMétéo 95 | French | retro-90s | dark | top-bar |

---

## Slide 5: Website Diversity — Visual Examples

*[Show 6 home-desktop.png screenshots side by side from the generated folder]*

Screenshots to include:
- `generated/artisan-stationery-atelier-papier-buvard/screenshots/accueil-desktop.png` — French minimalist, light, bottom-tabs
- `generated/audio-equipment-review-tactile-sound-lab/screenshots/home-desktop.png` — English neumorphism, dark
- `generated/biohacker-community-neonpulse-bioware-collective/screenshots/home-desktop.png` — Bilingual cyberpunk
- `generated/childcare-enrollment/screenshots/home-desktop.png` — Arabic RTL, playful
- `generated/design-archive-archiv-fr-typografische-praxis/screenshots/home-desktop.png` — German swiss/international
- `generated/retro-radio-fanclub-90/screenshots/home-desktop.png` — Hindi retro-90s

Point out: RTL layout, non-Latin scripts, dark vs light, wildly different design systems — all from the same pipeline.

---

## Slide 6: Broken Website Tasks — Testing Deeper Understanding

~25% of generated tasks have intentional design defects. The agent must replicate them faithfully AND identify them.

**Types of defects:**
- Broken responsiveness — elements overflow on mobile/tablet
- Typos — misspelled text in prominent locations
- Bad design — clashing colors, poor contrast
- Alignment issues — misaligned grid items
- Overflow — text breaking container boundaries
- Inconsistency — components styled differently from siblings

Each defect specifies which page and viewport it's visible at.

**What the agent must do:**
- Replicate the design exactly — including the defects. Don't "fix" them.
- This tests whether the agent faithfully reproduces what it sees vs. "correcting" what it thinks is wrong.

**Grading formula for broken sites:**
```
overall = 0.75 × visual_fidelity + 0.25 × defect_replication
```

- Defect replication: for each known defect, an LLM visually compares reference and submission screenshots to check if the defect is faithfully reproduced.

---

## Slide 7: The Grading System — Three Signals

**80% Dual LLM Judges** (Claude Opus 4.7 + GPT-5.5, averaged)
- 5 criteria: layout, color, typography, spacing, components (0-10 each)
- Structured tool_use forces integer outputs, no hedging
- Explicit score anchors prevent drift (0=absent, 5-6=correct structure but issues, 10=indistinguishable)

**15% Pixel Metrics** (deterministic)
- SSIM + color histogram similarity — anchors the score, reduces LLM variance

**5% Structural Checks** (deterministic)
- Files exist, nav links work, viewport meta, semantic HTML, media queries

**Anti-hack detection**: LLM analyzes source code to catch screenshot-embedding tricks — catches ANY technique (img tags, canvas, CSS background-image, hidden HTML + overlay), not just pattern-matched ones.

---

## Slide 9: Calibration — Proving the Grader Works

6 tiers of programmatic degradation tested across 4 sites (24 submissions):

| Tier | Description | Mean Score | Expected |
|------|-------------|-----------|----------|
| 0 | Perfect copy | 0.983 | ~1.0 |
| 1 | Minor CSS tweaks (±15 RGB, ±10% spacing) | 0.812 | ~0.8 |
| 2 | Wrong fonts + 60pt color shift + 1.8x spacing | 0.504 | ~0.5 |
| 3 | HTML only, CSS stripped to reset | 0.283 | ~0.2 |
| 4 | Screenshot hack (embedded ref image) | 0.000 | 0.0 |
| 5 | Empty stub | 0.024 | 0.0 |

**Ranking accuracy (ρ) = 0.943** (1.0 = perfect ordering of tiers) | **Run-to-run variance: ±0.002** | **Hack rejection: 100%**

---

## Slide 10: Post-Hoc Validation — Consistency + Monotonicity

Two experiments on a real Harbor job output (not synthetic degradation):

**Experiment 1: Consistency** — Graded same submission 4 times, changed nothing
- Overall score range: **0.012** (1.2 percentage points) — acceptable noise for RL

**Experiment 2: Monotonicity** — Made real CSS improvements, retook screenshots, regraded

| Round | Change | Score | Delta |
|-------|--------|-------|-------|
| Base | Original agent submission | 0.572 | — |
| 1 | Small: accent color orange→peach | 0.569 | -0.003 (noise) |
| 2 | **Large: palette navy→charcoal + neumorphic shadows** | **0.646** | **+0.077** |
| 3 | Small: typography serif→sans-serif | 0.680 | +0.034 |
| 4 | Medium: tighter spacing, neumorphic buttons | 0.678 | -0.002 (noise) |

- Real improvements produce jumps 6x larger than noise floor
- Typography fix → llm_typography jumped 0.517→0.702, other dims flat
- **Two properties critical for RL confirmed: low noise + correct ordering**

---

## Slide 11: Running at Scale — Modal Cloud Execution

Everything runs in the cloud — orchestrator, agents, and sandboxes. Local machine only streams logs.

```
Your Mac (streams logs only)
  └── modal run remote_eval.py
        └── Modal: 10 machines in parallel (one per task)
              ├── Machine 1: Harbor orchestrator → 10 child Modal sandboxes
              ├── Machine 2: Harbor orchestrator → 10 child Modal sandboxes
              └── ...
```

- 10 tasks × 10 trials = **100 trials**, all parallel
- Total wall-clock time: **~20 minutes**
- Results auto-downloaded to local machine
- Cost: ~$50 in API calls (agent + grader LLM judges)

---

## Slide 12: Results — 10 Tasks × 10 Trials

| Task | Lang | Style | Overall | Layout | Color | Typography | Spacing | Components |
|------|------|-------|---------|--------|-------|------------|---------|------------|
| Childcare Enrollment | ar | playful | **0.640** | 0.598 | 0.672 | 0.649 | 0.539 | 0.567 |
| Archiv für Typografische Praxis | de | swiss | **0.619** | 0.630 | 0.719 | 0.613 | 0.558 | 0.597 |
| NeonPulse Bioware | en/es | cyberpunk | **0.609** | 0.628 | 0.685 | 0.658 | 0.574 | 0.585 |
| Pickle Periodical | en | maximalist | **0.593** | 0.616 | 0.659 | 0.620 | 0.553 | 0.542 |
| Tactile Sound Lab | en | neumorphism | **0.582** | 0.590 | 0.658 | 0.557 | 0.525 | 0.553 |
| PixelMétéo 95 | fr | retro-90s | **0.575** | 0.574 | 0.693 | 0.584 | 0.521 | 0.562 |
| Classical Music Archive | hi | neumorphism | **0.571** | 0.667 | 0.669 | 0.651 | 0.602 | 0.610 |
| रेडियो तरंग 90 | hi | retro-90s | **0.547** | 0.565 | 0.559 | 0.542 | 0.503 | 0.513 |
| Meridian Freight Index | en | swiss | **0.532** | 0.667 | 0.765 | 0.666 | 0.585 | 0.630 |
| Atelier Papier Buvard | fr | minimalist | **0.482** | 0.632 | 0.753 | 0.701 | 0.578 | 0.611 |

96/100 trials completed successfully (4 agent timeouts).

**Patterns**: Color is consistently the strongest dimension (~0.68). Spacing is the weakest (~0.55). Structural score is ~1.0 across the board.

---

## Slide 13: Good vs Bad — What the Scores Actually Mean

### High score example: Archiv für Typografische Praxis (0.709, best single trial)

*[Show side-by-side: reference screenshot vs agent submission screenshot]*
- Reference: `generated/design-archive-archiv-fr-typografische-praxis/screenshots/home-desktop.png`
- Submission: `remote-jobs/jobs/remote-web-design-design-archive-archiv-fr-typografische-praxis-20260524-154031/web-design-design-archive-archiv__oJ3vNjB/verifier/screenshots/home-desktop.png`

What the agent got right: correct color palette, layout structure matches, typography hierarchy preserved, components (cards, nav) are recognizable.

### Low score example: Tactile Sound Lab (0.397, worst single trial)

*[Show side-by-side: reference screenshot vs agent submission screenshot]*
- Reference: `generated/audio-equipment-review-tactile-sound-lab/screenshots/home-desktop.png`
- Submission: `remote-jobs/jobs/remote-web-design-audio-equipment-review-tactile-sound-lab-20260524-154029/web-design-audio-equipment-revie__2VNpNje/verifier/screenshots/home-desktop.png`

What the agent got wrong: wrong background palette (navy vs charcoal), missing neumorphic shadows, typography mismatch (serif vs sans-serif), spacing proportions off.

**The grader correctly assigns higher scores to submissions that more closely match the reference — confirmed both by calibration and by visual inspection.**

---

## Slide 14: Observations & Learnings from Agent Behavior

- Scores range **0.48–0.64** across tasks — agents get the structure right but miss finer details
- **Color is the strongest dimension** (~0.68) — agents extract palettes well from screenshots
- **Spacing is the weakest** (~0.55) — margins/padding are hard to judge from pixels alone
- **Desktop >> Mobile** — responsive design is consistently the biggest gap
- **Structural score is nearly always 1.0** — agents reliably create all required files and navigation

Common failure patterns observed:
- Subtle intentional defects not replicated (typos, broken responsive behavior)
- Exact layout matching issues (wrong column counts, card proportions)
- High variance between reruns of same task (same task can score 0.40 or 0.70)
- Non-Latin scripts (Hindi, Arabic) are harder — lower scores on average

---

## Slide 15: Future Work

**Near-term:**
- Copy/text verification in grader (check exact text matches per page)
- Config-driven pipeline (easy to add website types, swap models, tweak prompts)
- Codebase refactor for production quality

**Medium-term:**
- **Animation support** — spec describes animations, Playwright screencast captures video, grade with frame-delta heuristic + LLM frame comparison
- **Multi-tech-stack** — React+Tailwind, Vue, Svelte alongside HTML+CSS via tech stack profile configs
- Agent trajectory analysis for additional hack detection signal
