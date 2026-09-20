# Web verification, 2026-09-20

## Follow-up: editable workspace

The Maria-proposal pass adds plan/rule editing, geometry and coverage editing, adjacent stages,
scenario analysis, sourced manual progress, linear completion estimates, a deterministic summary,
local alert drafts and a dataset-job manifest. See `web-masha-scope.md` for the exact boundaries.

Follow-up verification: `pnpm check` (0 errors, 0 warnings), production build, and 36 passing tests
across desktop/mobile Chromium (12.3 seconds). Additional coverage includes JSON import preview/validation, per-site
persistence, source requirements, invalid date/geometry rejection, positive/zero/negative progress
rates, hidden-zone protection, overlap date windows, stale-review invalidation, storage failure,
unexpected-object highlighting and manifest export. New views are checked at 320/390/768/1024/1440px.

The original visual language and components were retained. Desktop analytics and zone editing were
visually inspected in the browser. The in-app browser's viewport override did not resize its rendered
page, so mobile verification for this follow-up uses the automated Chromium mobile/layout tests.
The Lighthouse figures below describe the earlier landing/control-room build, not the added views.

## Automated checks

- `pnpm check`: 0 errors, 0 warnings.
- `pnpm build`: production SvelteKit / adapter-node build succeeds.
- `pnpm test:web`: 12 tests passed, desktop Chromium and mobile Chromium emulation.
  The installed Google Chrome executable was selected with `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`
  because the bundled Playwright browser download timed out. No user browser profile was used.
- `make k8s-validate`: existing dev/prod bootstrap overlays render. This is not validation of a
  deployed microservice system; those service implementations are still pending under ADR 0005.

Tests cover landing navigation, scenario tabs, deep links, review validation/persistence/reset,
counter updates, search/filter/empty states, site switching, local upload validation and preview,
schedule details, theme persistence, JSON report contents, 404 and horizontal bounds at 320, 390,
768, 1024 and 1366 CSS pixels. Tests are wired into the web CI job.

## Browser inspection

Inspected the landing first view, evidence section, control room and review dialog in the browser.
Checked 390x844 mobile and desktop layouts, both themes, normalized detection alignment and image
loading. Three synthetic photographic assets have WebP versions at 768px and 1536px widths. Icons
are decorative to screen readers; control labels remain accessible. Motion respects reduced-motion
preferences, and landing content stays readable without the reveal script.

## Lighthouse

Mobile Lighthouse 13.5.0 against the local production preview at `/`:

| Category | Score |
| --- | --- |
| Performance | 97 |
| Accessibility | 100 |
| Best practices | 100 |
| SEO | 100 |

LCP 2.3s, CLS 0, total blocking time 0ms. This is one local lab run, not production field data or
an accessibility certification. Original JPEG run was 75 performance / 8.3s LCP; responsive WebP,
priority hints and lazy evidence loading addressed the observed image bottleneck.
Machine-readable reports are local-only in `.local/sitewatch-lighthouse*.json`.

The separate `/app` mobile audit scored 99 performance, 100 accessibility and 100 best practices,
with LCP 1.8s. Its `noindex` directive is intentional because it is a demonstration workspace.

## Remaining integration work

The frontend is an interactive demo, not a live construction monitoring deployment. It does not
authenticate, call business APIs, run inference, publish events or send notifications. Images,
confidence values and events are synthetic. Reviews are browser-local only. Real inference and
microservice integration require the implementation gates in ADR 0005; Kubernetes rollout requires
a selected target cluster, secrets, storage and ingress configuration.
