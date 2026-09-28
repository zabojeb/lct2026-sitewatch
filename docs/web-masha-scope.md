# Frontend follow-through on Maria's proposals

> Historical design record. On 2026-09-27 the synthetic `/app` scenario was removed from the
> user-facing site. The following table describes the earlier browser-only prototype, not current
> live functionality. The current `/app` shows service readiness, and `/app/model` offers real
> inference plus a stateless Rust rules preview. Camera ingestion, persisted observations,
> reviewed alerts and most scenario controls listed below remain to be connected to live data.

Implemented on 2026-09-20, based on the discussion starting with message 618 on 2026-09-19.
This is a frontend deliverable, not an assertion that the ML/backend system is complete.

## Shipped UI and local workflows

| Proposal | Implementation | Boundary |
| --- | --- | --- |
| Required vs possible equipment, not stage probability | Plan editor and deterministic scenario analysis | Browser-only simulator; production domain stays in Rust |
| Missing equipment, unexpected equipment highlighted red | Recalculated findings, red unexpected bounding boxes and equipment text | Authored detections, not inference; missing does not mean physically absent |
| Alternative stage context | Named alternative stages based on equipment matches | No probability or asserted stage classification |
| Official methodology / GESN | Editable rule-source field included in analysis and export | No claim of verified GESN mapping; needs a checked source and edition |
| Stages without established rules | Explicit insufficient-evidence result and observable toggle | Empty requirements do not establish compliance |
| Manual assignment and editing | Per-stage equipment requirements, per-zone primary stage | Per-site local storage, not PostgreSQL |
| Overlapping stages | Explicit adjacent-stage selection, filtered by observation date | Equipment for unrelated zones is not automatically permitted |
| Stage deadlines | Editable dates, responsive timeline, JSON import with preview and validation | Imports the supported workspace schema, not arbitrary PDF/Excel schedules |
| Periodic photos, 20-minute default | Configurable cadence, frame and next scheduled time, archival labels | No timer pretending a live stream exists |
| Work vs stationary equipment | Stationary-position scenario with limitation | Does not classify actual operation or infer downtime from reused images |
| Implausible changes | Temporal-jump test scenario | Authored scenario, not a calibrated anomaly model |
| Incomplete camera coverage | Coverage editor, warning, hatched zones, insufficient-evidence guard | Coverage is manually entered; threshold 80% is a demo assumption |
| Equipment in wrong zone | Zone-map editor and wrong-zone scenario | Manual rectangular sketch, not calibrated geospatial reconstruction |
| Map and user-assigned zones | Select zones on image or keyboard-accessible select; edit bounds, stage, coverage | Existing synthetic aerial image; no reconstruction from multiple cameras |
| Visual state and readiness | Explicit manual progress fields with dated source | VLM not connected; no automatic percentage from a photograph |
| Ahead/behind schedule | Percentage-point delta against an explicitly linear baseline | Linear schedule is a simplifying assumption, not an accepted construction model |
| Finish/delay forecast | Positive change between two dated measurements gives linear finish scenario | No forecast for missing/flat/decreasing data; not an ML prediction |
| LLM conclusion | Expandable, copyable evidence-linked summary | Deterministic template, clearly labelled; LLM not connected |
| Foreman alerts | In-app findings and a copyable local draft with observation deep link | No Telegram/email/push delivery from the website |
| Synthetic-data diversity | Season/weather/background/position controls and downloadable dataset-job manifest | Planned configuration only; no new dataset or generated images |
| Diverse demonstration examples | Seven selectable inputs with documented limitations | No fabricated claims of benchmark performance |
| Explain side-panel metrics | Rule sources, manual coverage and linear calculations exposed in UI | Model confidence remains identified as authored demo data |
| Business logic focus | Expected / observed / rule / limitation throughout analysis and report | No bare detector result is treated as a proven business violation |

## Persistence and review semantics

Each site's workspace uses its own versioned localStorage key. Settings are validated on load and
invalid data falls back to safe defaults. JSON import validates before loading an editable draft;
applying it is a separate action. Numeric, date, geometry and mutually exclusive equipment checks
also run before saving. Storage failure is shown explicitly; in-memory edits can still be exported.

Review records carry a snapshot of the workspace configuration used at decision time. A changed
configuration does not hide a new signal under an old acknowledgement. Old decisions remain in
the journal and are labelled as requiring reassessment when the configuration has changed.

Reports contain the site, workspace, observations, source-bearing findings, review context, summary
and explicit model/delivery integration status. User-uploaded photos still remain in memory and are
not assigned synthetic detections. Neither the frontend nor its test data is a production rules
service or an API fallback.

## Walkthrough

1. Open `/app?view=schedule`. Change the truck requirement from required to possible; apply.
   Return to Overview: the missing-truck signal disappears. Refresh: settings persist.
2. Open Zones. Lower visibility to 30%, save, then inspect Analytics. The result becomes
   insufficient evidence, not compliant/violating.
3. In Zones, permit the assembly stage alongside excavation and restore visibility. In Scenarios,
   select the overlapping-stage case. The crane is explained by the active adjacent stage.
4. In the plan, enter 20% on September 16 and 50% on September 19, citing a demo measurement.
   Analytics shows 17 percentage points behind the linear plan and a September 24 finish scenario.
5. Expand the summary, prepare a local alert draft, and export the JSON report.

## Not represented as implemented

Live ingestion, authentic camera streams, real detector/tracker/VLM/LLM inference, verified
construction norms, production forecasting, actual dataset generation, business microservices,
authentication, server persistence and outbound operational alerts still require integration.
The existing Rust microservices / separate PostgreSQL databases / NATS / Kubernetes decision is
unchanged. No backend handler, contract, migration or Kubernetes configuration changed in this pass.

## Дополнение 2026-09-27

Переданные командой YOLO26x и ConvNeXt-Small теперь работают в отдельном приватном сервисе и
на экране `/app/model`, который принимает реальный кадр и показывает рамки и сырые классы.
Синтетические наблюдения этого пульта не подменены результатами модели: сервис наблюдений,
история, правила и алерты ещё не соединены с live-инференсом. См. [model serving](model-serving.md).

Теперь отдельный локальный контур после инференса позволяет собрать несколько разных кадров
и передать их в Rust-сервис предпросмотра правил: выбрать технику, количество, источник,
обзор и ручной процент готовности. Он не создаёт алертов в БД и не подменяет существующие
синтетические наблюдения. Один кадр, неполный обзор и нестабильные количества возвращают
`insufficient_evidence`; сравнение сроков возможно только по ручному замеру с источником.

## Дополнение 2026-09-24

Редактор теперь принимает минимальное количество и источник для каждого обязательного типа
техники; в аналитике можно отдельно от исходного снимка вручную уточнить количество, зону и
период без перемещения с обязательным источником. Есть предупреждения о недоборе и возможном
застое, а более подходящий по набору техники этап выводится только как проверяемая гипотеза.
Ручные замеры времени позволяют показать отставание/опережение в часах и фактическую
длительность. Старые локальные планы v1 мигрируют в v2. Это по-прежнему демо, не живой
детектор или подтверждённый простой. Полная граница реализованного и следующего этапа —
[`schedule-and-evidence-requirements.md`](schedule-and-evidence-requirements.md).
