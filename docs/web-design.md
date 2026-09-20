# SiteWatch web experience

## Design read

A Russian-language construction intelligence product for operators and hackathon judges. The landing
page is architectural, photographic and deliberately spare. The separate control room is precise,
evidence-led and useful at laptop size. SvelteKit and native CSS remain the foundation.

## Audit and direction

The original page contained a wordmark, a bootstrap status, a technology strip and a four-step
explanation. It had no product navigation or working product flows. Preserve SiteWatch and the
observation / schedule / explanation story; replace the bootstrap presentation with a product.

Landing dials: DESIGN_VARIANCE 8, MOTION_INTENSITY 5, VISUAL_DENSITY 3. Product density 7.
Typography: self-hosted Manrope, Cyrillic and Latin, tabular data. Palette: graphite #171a16,
off-white #efefe8, muted lime #c6dc91. Light mode uses the same hierarchy. Four-pixel control radii;
flat information sections. Layer scale: content 0, sticky navigation 10, dialog 20, notification 30.

Generated references were inspected before implementation. The hero establishes a two-line title
over darkened architectural imagery, 48-64px desktop gutters, ~70px navigation and a single lime CTA.
The evidence reference establishes a 2:1 photo/detail split, thin separators, and a 48-64px title.
The closing reference contributes the open workflow and facade composition; its accidental light
theme and fabricated wall slogan are not adopted. The control-room reference contributes the top
navigation, flat statistics and 2:1 workspace. Its fabricated safety violations/live status are not
adopted. The implementation uses only explicitly synthetic scenarios within the actual task scope.

## Functional boundary

`/` is the public product story. `/app` is an explicitly marked browser-local demonstration.
Generated photographs and manually authored detections are illustrations, not organizer data or
model output. Reviews are validated and saved locally; PostgreSQL remains the future authoritative
backend. No real operational records are written from the demo. Uploaded images stay in memory and
are previewed only; they are never assigned fabricated detections.

Backend business endpoints exist in the contract but are not yet implemented. Do not silently
fall back from a future authenticated API to demo fixtures. Replace the demo data boundary with
the generated API client only when those routes are available.

## Assets

Built-in image generation produced three project-local editorial illustrations:
`apps/web/static/images/site-aerial.webp`, `excavation.webp`, `concrete.webp`.
The final generation prompts are recorded in `docs/web-image-prompts.md`.
These are synthetic marketing/demo assets, never training data or genuine evidence.
