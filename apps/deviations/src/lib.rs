//! Stateless, evidence-gated preview. It never creates a durable deviation or notification.

use std::collections::{BTreeSet, HashSet};

use axum::{
    Json, Router,
    extract::State,
    http::{HeaderMap, StatusCode, header},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use chrono::{DateTime, Duration, Utc};
use serde_json::json;
use sha2::{Digest, Sha256};
use sitewatch_contracts::{
    EquipmentRuleInput, EvaluationPreviewRequest, EvaluationPreviewResponse, PreviewFinding,
    PreviewScheduleResult,
};
use sitewatch_domain::{
    EquipmentClass, EquipmentRule, RuleExpectation,
    evaluation::{
        CountEvidence, ProgressMeasurement, RuleAssessment, compare_equipment_window,
        compare_schedule,
    },
};
use subtle::ConstantTimeEq;
use uuid::Uuid;

#[derive(Debug, Clone)]
pub struct AppState {
    pub internal_token_sha256: [u8; 32],
}

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/health/live", get(live))
        .route("/health/ready", get(live))
        .route("/api/v1/evaluations:preview", post(preview))
        .with_state(state)
}

async fn live() -> Json<serde_json::Value> {
    Json(json!({ "status": "ready", "service": "sitewatch-deviations-preview" }))
}

#[derive(Debug)]
struct ApiError {
    status: StatusCode,
    detail: &'static str,
}

impl ApiError {
    const fn invalid(detail: &'static str) -> Self {
        Self {
            status: StatusCode::UNPROCESSABLE_ENTITY,
            detail,
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (
            self.status,
            [(header::CONTENT_TYPE, "application/problem+json")],
            Json(json!({
                "type": "about:blank",
                "title": self.status.canonical_reason().unwrap_or("Request failed"),
                "status": self.status.as_u16(),
                "detail": self.detail,
                "trace_id": Uuid::now_v7(),
            })),
        )
            .into_response()
    }
}

fn authenticate(headers: &HeaderMap, state: &AppState) -> Result<(), ApiError> {
    let bearer = headers
        .get(header::AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .ok_or(ApiError {
            status: StatusCode::UNAUTHORIZED,
            detail: "bearer token required",
        })?;
    let digest: [u8; 32] = Sha256::digest(bearer.as_bytes()).into();
    if bool::from(digest.ct_eq(&state.internal_token_sha256)) {
        Ok(())
    } else {
        Err(ApiError {
            status: StatusCode::UNAUTHORIZED,
            detail: "invalid bearer token",
        })
    }
}

async fn preview(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<EvaluationPreviewRequest>,
) -> Result<Json<EvaluationPreviewResponse>, ApiError> {
    authenticate(&headers, &state)?;
    evaluate_inner(&request).map(Json)
}

fn valid_score(score: f32) -> bool {
    score.is_finite() && (0.0..=1.0).contains(&score)
}

fn validate_rule(input: &EquipmentRuleInput) -> Result<EquipmentRule, ApiError> {
    let source = input.source.as_deref().unwrap_or_default();
    if source.trim().is_empty() || source.chars().count() > 1000 {
        return Err(ApiError::invalid(
            "У каждого правила должен быть документ-источник.",
        ));
    }
    let rule = EquipmentRule {
        equipment_class: input.equipment_class,
        expectation: input.expectation,
        min_count: input.min_count,
        max_count: input.max_count,
        min_confidence: input.min_confidence,
        persistence_frames: input.persistence_frames,
    };
    rule.validate()
        .map_err(|_| ApiError::invalid("Правило по технике заполнено неверно."))?;
    if (rule.expectation == RuleExpectation::Required && rule.min_count == 0)
        || (rule.expectation != RuleExpectation::Required && rule.min_count != 0)
        || (rule.expectation == RuleExpectation::Unexpected && rule.max_count != Some(0))
        || rule.persistence_frames > 20
    {
        return Err(ApiError::invalid(
            "Правило противоречиво: для обязательной техники минимум не меньше 1, окно не больше 20 кадров.",
        ));
    }
    Ok(rule)
}

// Keep the complete provenance and anti-replay gate together for review.
#[allow(clippy::too_many_lines)]
fn validate(request: &EvaluationPreviewRequest) -> Result<(), ApiError> {
    let stage = &request.stage;
    if stage.name.trim().is_empty()
        || stage.name.chars().count() > 200
        || stage.zone_code.trim().is_empty()
        || stage.zone_code.chars().count() > 80
        || stage.planned_end <= stage.planned_start
        || stage.rules.is_empty()
        || stage.rules.len() > EquipmentClass::ALL.len()
        || request.frames.len() > 20
    {
        return Err(ApiError::invalid(
            "Проверьте этап: название, код зоны, плановые даты, не больше 20 кадров.",
        ));
    }
    if let Some(coverage) = &request.coverage
        && (!valid_score(coverage.percent / 100.0)
            || coverage.source.trim().is_empty()
            || coverage.source.chars().count() > 1000)
    {
        return Err(ApiError::invalid(
            "Для обзора зоны нужны процент 0–100 и источник.",
        ));
    }
    let mut classes = HashSet::new();
    for input in &stage.rules {
        validate_rule(input)?;
        if !classes.insert(input.equipment_class) {
            return Err(ApiError::invalid(
                "Для одного вида техники можно задать только одно правило.",
            ));
        }
    }
    let mut ids = HashSet::new();
    let mut hashes = HashSet::new();
    let mut model_versions = HashSet::new();
    let mut camera_codes = HashSet::new();
    let mut previous: Option<DateTime<Utc>> = None;
    for frame in &request.frames {
        if !ids.insert(frame.id)
            || !hashes.insert(&frame.image_sha256)
            || frame.image_sha256.len() != 64
            || !frame
                .image_sha256
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
            || frame.captured_at_source.trim().is_empty()
            || frame.captured_at_source.chars().count() > 1000
            || frame.camera_code.trim().is_empty()
            || frame.camera_code.chars().count() > 80
            || frame.zone_code != stage.zone_code
            || frame.model_version.trim().is_empty()
            || frame.model_version.len() > 200
            || frame.detections.len() > 100
            || frame.manual_counts.len() > EquipmentClass::ALL.len()
        {
            return Err(ApiError::invalid(
                "Кадр не подходит: повтор, другая камера или зона, либо неверные данные.",
            ));
        }
        model_versions.insert(&frame.model_version);
        camera_codes.insert(&frame.camera_code);
        if let Some(last) = previous {
            let gap = frame.captured_at - last;
            if !(Duration::minutes(1)..=Duration::minutes(60)).contains(&gap) {
                return Err(ApiError::invalid(
                    "Между соседними кадрами окна должно быть от 1 до 60 минут.",
                ));
            }
        }
        previous = Some(frame.captured_at);
        let mut overridden = HashSet::new();
        for manual in &frame.manual_counts {
            if !overridden.insert(manual.equipment_class)
                || manual.source.trim().is_empty()
                || manual.source.chars().count() > 1000
                || manual.count > 100
            {
                return Err(ApiError::invalid(
                    "У ручного уточнения нужны вид техники и источник, по одному на вид.",
                ));
            }
        }
        for detection in &frame.detections {
            if !valid_score(detection.detector_score)
                || !valid_score(detection.classifier_score)
                || detection.bounding_box.validate().is_err()
                || !matches!(
                    detection.mapping_status.as_str(),
                    "mapped" | "other" | "ignored" | "low_confidence"
                )
                || (detection.mapping_status == "mapped") != detection.equipment_class.is_some()
            {
                return Err(ApiError::invalid(
                    "Результат распознавания кадра повреждён.",
                ));
            }
        }
    }
    if model_versions.len() > 1 {
        return Err(ApiError::invalid(
            "Все кадры окна должны быть распознаны в одном режиме.",
        ));
    }
    if camera_codes.len() > 1 {
        return Err(ApiError::invalid(
            "Все кадры окна должны быть с одной камеры.",
        ));
    }
    if let Some(progress) = &request.progress {
        compare_schedule(
            stage.planned_start,
            stage.planned_end,
            &ProgressMeasurement {
                measured_at: progress.measured_at,
                percent: progress.percent,
                source: progress.source.clone(),
            },
        )
        .map_err(|_| ApiError::invalid("Проверьте замер готовности: 0–100 %, время и источник."))?;
    }
    Ok(())
}

/// Evaluate a single stage only. The result is an operator review candidate, not an alert.
///
/// # Errors
/// Returns a validation error for malformed plan, image evidence or provenance.
pub fn evaluate(request: &EvaluationPreviewRequest) -> Result<EvaluationPreviewResponse, String> {
    evaluate_inner(request).map_err(|error| error.detail.to_owned())
}

// The preview deliberately assembles every evidence field before returning a candidate.
#[allow(clippy::too_many_lines)]
fn evaluate_inner(
    request: &EvaluationPreviewRequest,
) -> Result<EvaluationPreviewResponse, ApiError> {
    validate(request)?;
    let mut findings = Vec::new();
    let mut limitations = vec![
        "Это предварительный результат: без проверки оператором замечание не создаётся.".into(),
        "Модель не измеряет движение, фактический этап, расположение в зоне или готовность здания."
            .into(),
        "Уверенность модели — условная оценка, а не вероятность.".into(),
    ];
    if request.coverage.is_none() {
        limitations.push("Обзор рабочей зоны не подтверждён источником.".into());
    }
    if !request.stage.observable_from_camera {
        limitations.push("Этап помечен как ненаблюдаемый этой камерой.".into());
    }
    let within_planned_interval = request.frames.iter().all(|frame| {
        frame.captured_at >= request.stage.planned_start
            && frame.captured_at <= request.stage.planned_end
    });
    if !within_planned_interval {
        limitations.push(
            "Часть кадров вне планового интервала этапа; фактический активный этап требует подтверждения."
                .into(),
        );
    }
    let coverage = request.coverage.as_ref().map_or(0.0, |value| value.percent);
    for input in &request.stage.rules {
        let rule = validate_rule(input)?;
        let source = input.source.as_deref().unwrap_or_default();
        let frames = request
            .frames
            .iter()
            .map(|frame| {
                let observed = frame
                    .manual_counts
                    .iter()
                    .find(|count| count.equipment_class == rule.equipment_class)
                    .map_or_else(
                        || {
                            frame
                                .detections
                                .iter()
                                .filter(|detection| {
                                    detection.equipment_class == Some(rule.equipment_class)
                                        && detection.mapping_status == "mapped"
                                        && detection.classifier_score >= rule.min_confidence
                                })
                                .count()
                        },
                        |manual| usize::from(manual.count),
                    );
                CountEvidence {
                    equipment_class: rule.equipment_class,
                    observed_count: u16::try_from(observed).unwrap_or(u16::MAX),
                    confirmed_frames: 1,
                    evidence_ids: vec![frame.id.to_string()],
                }
            })
            .collect::<Vec<_>>();
        let assessment = if request.stage.observable_from_camera
            && within_planned_interval
            && !frames.is_empty()
        {
            compare_equipment_window(&rule, source, &frames, coverage, 80.0)
                .map_err(|_| ApiError::invalid("Не удалось сопоставить кадры с правилом."))?
                .assessment
        } else {
            RuleAssessment::InsufficientEvidence
        };
        let observed_count = frames.last().map(|evidence| evidence.observed_count);
        let explanation = match assessment {
            RuleAssessment::Missing => "Не видна ни на одном кадре окна. Проверьте площадку и обзор камеры — это ещё не доказанный простой.",
            RuleAssessment::BelowMinimum => "Во всех кадрах число ниже минимума; требуется проверка оператором.",
            RuleAssessment::AboveMaximum => "Во всех кадрах число выше максимума; требуется проверка оператором.",
            RuleAssessment::Unexpected => "На всех кадрах видна техника, не предусмотренная этапом; проверьте соседние работы.",
            RuleAssessment::Consistent => "В этом окне наблюдаемое число согласуется с правилом; это не подтверждает выполнение работ.",
            RuleAssessment::InsufficientEvidence => "Для вывода не хватает данных: мало кадров, количество техники менялось, обзор зоны ниже 80 % или кадры вне плановых дат.",
        }.to_owned();
        let assessment_code = match assessment {
            RuleAssessment::Consistent => "consistent",
            RuleAssessment::Missing => "missing",
            RuleAssessment::BelowMinimum => "below_minimum",
            RuleAssessment::AboveMaximum => "above_maximum",
            RuleAssessment::Unexpected => "unexpected",
            RuleAssessment::InsufficientEvidence => "insufficient_evidence",
        };
        findings.push(PreviewFinding {
            equipment_class: rule.equipment_class,
            assessment: assessment_code.into(),
            expectation: rule.expectation,
            expected_min: rule.min_count,
            expected_max: rule.max_count,
            observed_count,
            rule_source: source.to_owned(),
            evidence_frame_ids: request.frames.iter().map(|frame| frame.id).collect(),
            evidence_sources: request
                .frames
                .iter()
                .map(|frame| {
                    frame
                        .manual_counts
                        .iter()
                        .find(|count| count.equipment_class == rule.equipment_class)
                        .map_or_else(
                            || {
                                format!(
                                    "модель {} · время: {}",
                                    frame.model_version, frame.captured_at_source
                                )
                            },
                            |manual| {
                                format!(
                                    "вручную: {} · время: {}",
                                    manual.source, frame.captured_at_source
                                )
                            },
                        )
                })
                .collect(),
            explanation,
        });
    }
    let status = if findings.iter().any(|finding| {
        matches!(
            finding.assessment.as_str(),
            "missing" | "below_minimum" | "above_maximum" | "unexpected"
        )
    }) {
        "review_required"
    } else if findings
        .iter()
        .all(|finding| finding.assessment == "consistent")
    {
        "observed_consistency"
    } else {
        "insufficient_evidence"
    };
    let configured: HashSet<_> = request
        .stage
        .rules
        .iter()
        .map(|rule| rule.equipment_class)
        .collect();
    let unconfigured_observed = request
        .frames
        .iter()
        .flat_map(|frame| {
            frame
                .detections
                .iter()
                .filter_map(|detection| {
                    (detection.mapping_status == "mapped")
                        .then_some(detection.equipment_class)
                        .flatten()
                })
                .chain(
                    frame
                        .manual_counts
                        .iter()
                        .filter(|manual| manual.count > 0)
                        .map(|manual| manual.equipment_class),
                )
        })
        .filter(|class| !configured.contains(class))
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    let schedule = request
        .progress
        .as_ref()
        .map(|progress| {
            compare_schedule(
                request.stage.planned_start,
                request.stage.planned_end,
                &ProgressMeasurement {
                    measured_at: progress.measured_at,
                    percent: progress.percent,
                    source: progress.source.clone(),
                },
            )
            .map(|comparison| PreviewScheduleResult {
                planned_percent_at_measurement: comparison.planned_percent_at_measurement,
                measured_percent: comparison.measured_percent,
                percentage_point_delta: comparison.percentage_point_delta,
                variance_seconds: comparison.variance_seconds,
                source: comparison.source,
            })
            .map_err(|_| {
                ApiError::invalid("Проверьте замер готовности: 0–100 %, время и источник.")
            })
        })
        .transpose()?;
    Ok(EvaluationPreviewResponse {
        schema: "sitewatch.evaluation.preview.v1".into(),
        status: status.into(),
        stage_name: request.stage.name.clone(),
        findings,
        unconfigured_observed,
        schedule,
        limitations,
    })
}

#[cfg(test)]
mod tests {
    use chrono::TimeZone;
    use sitewatch_contracts::{PreviewCoverage, PreviewDetection, PreviewFrame, PreviewStage};
    use sitewatch_domain::BoundingBox;

    use super::*;

    fn request() -> EvaluationPreviewRequest {
        let start = Utc.with_ymd_and_hms(2026, 9, 19, 0, 0, 0).unwrap();
        EvaluationPreviewRequest {
            stage: PreviewStage {
                name: "Котлован".into(),
                zone_code: "PIT-01".into(),
                planned_start: start,
                planned_end: start + Duration::days(10),
                observable_from_camera: true,
                rules: vec![EquipmentRuleInput {
                    equipment_class: EquipmentClass::Excavator,
                    expectation: RuleExpectation::Required,
                    min_count: 1,
                    max_count: None,
                    min_confidence: 0.5,
                    persistence_frames: 3,
                    source: Some("ППР, пункт 3".into()),
                }],
            },
            coverage: Some(PreviewCoverage {
                percent: 90.0,
                source: "оператор".into(),
            }),
            frames: (0..3)
                .map(|index| PreviewFrame {
                    id: Uuid::from_u128(index + 1),
                    camera_code: "CAM-01".into(),
                    zone_code: "PIT-01".into(),
                    captured_at: start + Duration::minutes(i64::try_from(index).unwrap() * 20),
                    captured_at_source: "оператор".into(),
                    image_sha256: format!("{index:064x}"),
                    model_version: "test-model".into(),
                    detections: vec![],
                    manual_counts: vec![],
                })
                .collect(),
            progress: None,
        }
    }

    #[test]
    fn missing_requires_distinct_temporal_evidence_and_coverage() {
        let mut input = request();
        assert_eq!(evaluate(&input).unwrap().findings[0].assessment, "missing");
        input.frames.truncate(1);
        assert_eq!(evaluate(&input).unwrap().status, "insufficient_evidence");
        input = request();
        input.coverage = None;
        assert_eq!(evaluate(&input).unwrap().status, "insufficient_evidence");
        input = request();
        input.stage.observable_from_camera = false;
        assert_eq!(evaluate(&input).unwrap().status, "insufficient_evidence");
        input = request();
        input.stage.planned_start += Duration::days(1);
        assert_eq!(evaluate(&input).unwrap().status, "insufficient_evidence");
    }

    #[test]
    fn changing_counts_and_low_scores_do_not_create_a_verdict() {
        let mut input = request();
        input.frames[2].detections.push(PreviewDetection {
            equipment_class: Some(EquipmentClass::Excavator),
            mapping_status: "mapped".into(),
            detector_score: 0.9,
            classifier_score: 0.9,
            bounding_box: BoundingBox {
                x_min: 0.1,
                y_min: 0.1,
                x_max: 0.5,
                y_max: 0.5,
            },
        });
        assert_eq!(evaluate(&input).unwrap().status, "insufficient_evidence");
        input.frames[2].detections[0].classifier_score = 0.3;
        assert_eq!(evaluate(&input).unwrap().status, "review_required");
    }

    #[test]
    fn duplicate_image_and_unsourced_manual_counts_are_rejected() {
        let mut input = request();
        input.frames[1].image_sha256 = input.frames[0].image_sha256.clone();
        assert!(evaluate(&input).is_err());
        input = request();
        input.frames[1].camera_code = "CAM-02".into();
        assert!(evaluate(&input).is_err());
        input = request();
        input.frames[0]
            .manual_counts
            .push(sitewatch_contracts::PreviewManualCount {
                equipment_class: EquipmentClass::Excavator,
                count: 1,
                source: " ".into(),
            });
        assert!(evaluate(&input).is_err());
    }
}
