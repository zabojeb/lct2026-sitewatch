# Two-stage model serving

The supplied artifacts are a class-agnostic YOLO26x detector (`item`) and a 22-class ConvNeXt-Small
crop classifier. The private `apps/inference` service loads both at startup, checks exact weight
hashes and class order, detects proposals, crops each box, applies the supplied 224×224
aspect-preserving / 114-pad / ImageNet-normalized preprocessing, and returns raw and canonical
labels with separate scores. Boxes are normalized to `[0, 1]`. No schedule decision is made here.

## Artifact identity

| Local ignored path | SHA-256 |
|---|---|
| `models/sitewatch-v1/detector.pt` | `1740e491176042786976a8e291ac2b81623eec16b895d7ccd187d4fbb48b97b7` |
| `models/sitewatch-v1/classifier.pth` | `c3fb36540f7368d164cecd53f243024bd4344c899b5062ea717ab8060162ba07` |

Copy the supplied files into those paths; `models/` is Git-ignored. Startup rejects other weights
until their adapter, tests and release identity are reviewed. PyTorch checkpoints are executable
deserialization artifacts: deploy only weights from a trusted source. The classifier uses
`weights_only=True`; Ultralytics' detector loader still requires trusting its checkpoint.

## Class adapter

Raw labels are never discarded. The stable taxonomy maps `roller→road_roller`,
`crane_manipulator→loader_crane`, and both `drilling_rig` and `pile_driver→piling_rig`; exact
matches retain their code. `concrete_pump` and `bucket_loader` are also first-class rule codes by
team decision. Unmapped equipment is returned as `other`, and `person` as `ignored`. A classifier
score below 0.5 yields
`low_confidence` even for a known type. These statuses have `equipment_class: null` and cannot
directly trigger equipment rules. This mapping is provisional until the team confirms the
definitive business taxonomy. Scores are **not calibrated probabilities**.

## Run locally

With the two private model files already in the ignored `models/sitewatch-v1/` directory,
`make demo-live` starts inference, the independent rules service and the web UI at
`http://127.0.0.1:5174/app/model`. It creates a fresh internal token in memory for each run and
stops its child processes on Ctrl+C. Run `make inference-check` and `pnpm install` once if the
local dependencies are not installed.

### Share the Mac-hosted demo with teammates

`make demo-share` builds the production web server and starts a temporary HTTPS tunnel through
[Pinggy](https://pinggy.io/), using the macOS SSH client with no account or VPN.
It prints one HTTPS link with a random 256-bit access token; teammates only need that link, not
an account or VPN. The link first sets a secure, HttpOnly, SameSite cookie and redirects to a URL
without the token. Other page and API requests without the cookie receive 403. The model and
rules services listen only on `127.0.0.1`; the web server also listens only there, and only its
web endpoint is relayed. Run `make demo-share-status` to retrieve the current link and
`make demo-share-stop` to revoke it. The link changes on every start. The ignored
`.local/demo-share/run.log` contains the link and is restricted to the current macOS user.
Pinggy may show a one-time caution page in a browser; a teammate must choose **Enter site** to
continue. It is not a SiteWatch login.

This is a **capability link**, not individual user authentication: anyone who gets it can use the
demo until sharing stops, and there are no per-user logs or revocation. Keep the Mac awake and
online. Uploaded frames traverse Pinggy before reaching the Mac; do not use confidential site
photos without approval for that data path. The free tunnel expires after 60 minutes; run
`make demo-share-stop` and `make demo-share` to obtain a new link. Use a managed tunnel or private
access for longer-lived deployment.

Use a random internal token of at least 32 bytes in the ignored `.env`, and set
`INFERENCE_DEMO_ENABLED=true` only on a trusted/local demo. For Compose:

```bash
mkdir -p models/sitewatch-v1
cp /path/to/best.pt models/sitewatch-v1/detector.pt
cp /path/to/convnext_small_aug_best.pth models/sitewatch-v1/classifier.pth
chmod 644 models/sitewatch-v1/detector.pt models/sitewatch-v1/classifier.pth
docker compose -f deploy/compose.yaml --profile live up --build inference deviations web
```

Set `WEB_ORIGIN` to the exact browser-facing origin if it is not `http://localhost:3000`
(including a custom `WEB_PORT`); SvelteKit requires this for production CSRF checks.

`/app/model` is the live-model screen. `/app` now shows the actual readiness of the model and
rules service, with no synthetic sites, detections or alerts. The browser upload route is disabled
by default; it is **not** an authenticated,
rate-limited production ingestion API. It sends an image through SvelteKit's server-side proxy to
the token-protected inference service, which does not persist the file.

The same screen offers a **local preview against a plan**. Enter the real stage, dates, zone,
camera and source of each rule; none is filled with a demonstration project. Add several different
modelled frames with sourced capture times, edit the equipment rules, and enter a sourced
manual coverage estimate (and optional manual progress/count corrections). A separate Rust
`apps/deviations` service evaluates this packet with the shared domain rules. It requires a stable
count over the rule's configured number of distinct frames, 1–60 minutes between frames, a single
model version and at least 80% sourced coverage. Unknown or low coverage, an invisible stage,
mixed counts or too few frames all yield `insufficient_evidence`. Even `review_required` is an
**operator candidate**, never a persisted deviation or notification. The 80% cutoff and linear
progress comparison are local-demo assumptions, not measured construction standards.
The operator can export the input and preview response as JSON, including source labels and frame
hashes but not image bytes. Export is local to the browser and does not create a server-side record.

For a lighter local run without Docker, `cd apps/inference && uv sync --frozen --group dev --extra serve`, then
start `uv run uvicorn sitewatch_inference.app:create_app --factory --host 127.0.0.1 --port 8083`
with `SITEWATCH_INTERNAL_TOKEN`, `DETECTOR_WEIGHTS` and `CLASSIFIER_WEIGHTS` set. Start SvelteKit
with the same token, `INFERENCE_URL=http://127.0.0.1:8083` and
`INFERENCE_DEMO_ENABLED=true`. Start `cargo run -p sitewatch-deviations` with the same token and
`DEVIATIONS_HTTP_ADDR=127.0.0.1:8084`; set `DEVIATIONS_URL=http://127.0.0.1:8084` for SvelteKit.
Run `make inference-check` and `cargo test -p sitewatch-deviations` for focused tests.

## Kubernetes

The base Kustomize deployment exposes only a ClusterIP service. Its init container downloads
the two immutable files from `MODEL_S3_BUCKET/sitewatch-v1/` into an ephemeral model volume; the
main container verifies their hashes before readiness turns green. Populate the private S3 bucket
and replace `MODEL_S3_ENDPOINT`, `MODEL_S3_ACCESS_KEY`, `MODEL_S3_SECRET_KEY`, and
`SITEWATCH_INTERNAL_TOKEN` in cluster secret/config management before applying. The example
Secret contains placeholders and is not deployable as-is. The `gpu` overlay requests one NVIDIA
GPU; it requires a CUDA-capable image/node and NVIDIA device plugin. The default runs on CPU. The
web upload route remains disabled in Kubernetes until operator authentication and quotas exist.
The ingress sends `/api/model` to the web proxy, while other `/api` requests go to the API
service. Keep the web `ORIGIN` setting aligned with the ingress host and scheme.

## Integration boundary

The production `observations` service does not exist yet. Consequently this release does not
consume `lct.observation.accepted.v1`, persist detections, publish
`lct.observation.analyzed.v1`, or create durable deviations. The preview service only compares
client-supplied evidence and never changes business state. When observations is implemented, it must own
image references and inference job state, use its database/outbox for result events, and deduplicate
JetStream redeliveries. The detector output is evidence; a rule engine must also verify stage,
zone, observability, thresholds and persistence before raising an alert. Zero boxes are **not**
proof of absent equipment.

Independent scene-disjoint validation and score calibration are still needed before claiming
accuracy or using this model for automatic business alerts. Training metrics in a checkpoint are
not a substitute for held-out product-level evaluation.
