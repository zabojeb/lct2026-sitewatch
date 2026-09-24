//! Schedule service: immutable revisions, sourced equipment rules and a transactional outbox.

use std::{
    collections::{HashMap, HashSet},
    time::Instant,
};

pub mod outbox;

use axum::{
    Json, Router,
    extract::{Path, State},
    http::{HeaderMap, StatusCode, header},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use chrono::Utc;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use sitewatch_contracts::{
    DependencyStatus, EquipmentRuleInput, EquipmentRuleRevisionItem, HealthResponse,
    ReadinessResponse, ScheduleRevisionResponse, ServiceStatus, WorkStageImportRequest,
    WorkStageRevisionItem,
};
use sitewatch_domain::{EquipmentRule, ProjectId, RuleExpectation, StageId};
use sqlx::{PgPool, Postgres, Row, Transaction};
use subtle::ConstantTimeEq;
use uuid::Uuid;

#[derive(Debug, Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub jetstream: async_nats::jetstream::Context,
    /// SHA-256 of a gateway-to-service bearer secret, never logged or returned.
    pub internal_token_sha256: [u8; 32],
}

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/health/live", get(live))
        .route("/health/ready", get(ready))
        .route(
            "/api/v1/projects/{project_id}/stages:import",
            post(import_schedule),
        )
        .route(
            "/api/v1/projects/{project_id}/stages",
            get(get_active_schedule),
        )
        .route(
            "/api/v1/projects/{project_id}/stages/revisions/{revision_id}",
            get(get_schedule_revision),
        )
        .with_state(state)
}

async fn live() -> Json<HealthResponse> {
    Json(HealthResponse {
        status: ServiceStatus::Up,
        service: "sitewatch-schedule".into(),
        version: env!("CARGO_PKG_VERSION").into(),
        timestamp: Utc::now(),
    })
}

async fn ready(State(state): State<AppState>) -> (StatusCode, Json<ReadinessResponse>) {
    let postgres_started = Instant::now();
    let postgres_ok = sqlx::query("SELECT 1").execute(&state.pool).await.is_ok();
    let postgres_latency =
        u64::try_from(postgres_started.elapsed().as_millis()).unwrap_or(u64::MAX);
    let nats_started = Instant::now();
    let nats_ok = state.jetstream.get_stream("SITEWATCH_EVENTS").await.is_ok();
    let nats_latency = u64::try_from(nats_started.elapsed().as_millis()).unwrap_or(u64::MAX);
    let healthy = postgres_ok && nats_ok;
    let status = if healthy {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };
    (
        status,
        Json(ReadinessResponse {
            status: if healthy {
                ServiceStatus::Up
            } else {
                ServiceStatus::Down
            },
            dependencies: vec![
                DependencyStatus {
                    name: "postgres".into(),
                    status: if postgres_ok {
                        ServiceStatus::Up
                    } else {
                        ServiceStatus::Down
                    },
                    latency_ms: postgres_latency,
                    detail: None,
                },
                DependencyStatus {
                    name: "jetstream".into(),
                    status: if nats_ok {
                        ServiceStatus::Up
                    } else {
                        ServiceStatus::Down
                    },
                    latency_ms: nats_latency,
                    detail: None,
                },
            ],
            timestamp: Utc::now(),
        }),
    )
}

#[derive(Debug)]
struct ApiError {
    status: StatusCode,
    detail: &'static str,
}

impl ApiError {
    const fn bad_request(detail: &'static str) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            detail,
        }
    }

    const fn unprocessable(detail: &'static str) -> Self {
        Self {
            status: StatusCode::UNPROCESSABLE_ENTITY,
            detail,
        }
    }

    const fn internal() -> Self {
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            detail: "internal service error",
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
                "instance": "",
                "trace_id": Uuid::now_v7().to_string(),
                "errors": [],
            })),
        )
            .into_response()
    }
}

fn authenticate(headers: &HeaderMap, state: &AppState) -> Result<(), ApiError> {
    let bearer = headers
        .get(axum::http::header::AUTHORIZATION)
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

fn validate_import(request: &WorkStageImportRequest) -> Result<(), ApiError> {
    if request.stages.is_empty() || request.stages.len() > 1_000 {
        return Err(ApiError::unprocessable("schedule must have 1-1000 stages"));
    }
    if request.timezone.trim().is_empty()
        || request.timezone.len() > 100
        || request.source.trim().is_empty()
        || request.source.len() > 1_000
    {
        return Err(ApiError::unprocessable("timezone and source are required"));
    }
    let mut codes = HashSet::new();
    for stage in &request.stages {
        if !valid_wbs_code(&stage.code)
            || stage.name.trim().is_empty()
            || stage.name.len() > 200
            || stage.zone_code.trim().is_empty()
            || stage.zone_code.len() > 80
            || stage.planned_end <= stage.planned_start
            || stage
                .parent_code
                .as_ref()
                .is_some_and(|code| !valid_wbs_code(code) || code == &stage.code)
        {
            return Err(ApiError::unprocessable(
                "invalid stage code, name, zone or dates",
            ));
        }
        if !codes.insert((stage.zone_code.clone(), stage.code.clone())) {
            return Err(ApiError::unprocessable("duplicate stage code within zone"));
        }
        let mut classes = HashSet::new();
        for rule in &stage.equipment_rules {
            if !classes.insert(rule.equipment_class) || !valid_rule(rule, &request.source) {
                return Err(ApiError::unprocessable(
                    "invalid or contradictory equipment rules",
                ));
            }
        }
    }
    Ok(())
}

fn valid_wbs_code(code: &str) -> bool {
    let code = code.strip_suffix('.').unwrap_or(code);
    !code.is_empty()
        && code.len() <= 64
        && code
            .split('.')
            .all(|part| !part.is_empty() && part.bytes().all(|c| c.is_ascii_digit()))
}

fn valid_rule(rule: &EquipmentRuleInput, fallback_source: &str) -> bool {
    let source = rule.source.as_deref().unwrap_or(fallback_source);
    if source.trim().is_empty() || source.len() > 1_000 {
        return false;
    }
    let domain_rule = EquipmentRule {
        equipment_class: rule.equipment_class,
        expectation: rule.expectation,
        min_count: rule.min_count,
        max_count: rule.max_count,
        min_confidence: rule.min_confidence,
        persistence_frames: rule.persistence_frames,
    };
    domain_rule.validate().is_ok()
        && match rule.expectation {
            RuleExpectation::Required => rule.min_count > 0,
            RuleExpectation::Optional => rule.min_count == 0,
            RuleExpectation::Unexpected => rule.min_count == 0 && rule.max_count == Some(0),
        }
}

// Keep the revision, its stages, rules, active pointer and outbox event visibly in one transaction.
#[allow(clippy::too_many_lines)]
async fn import_schedule(
    State(state): State<AppState>,
    Path(project_id): Path<Uuid>,
    headers: HeaderMap,
    Json(request): Json<WorkStageImportRequest>,
) -> Result<(StatusCode, Json<ScheduleRevisionResponse>), ApiError> {
    authenticate(&headers, &state)?;
    validate_import(&request)?;
    let key = headers
        .get("idempotency-key")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| Uuid::parse_str(value).ok())
        .ok_or(ApiError::bad_request("Idempotency-Key must be a UUID"))?;
    let timezone_known: bool =
        sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name = $1)")
            .bind(&request.timezone)
            .fetch_one(&state.pool)
            .await
            .map_err(|_| ApiError::internal())?;
    if !timezone_known {
        return Err(ApiError::unprocessable("unknown IANA timezone"));
    }
    let canonical = serde_json::to_vec(&request).map_err(|_| ApiError::internal())?;
    let request_hash = format!("{:x}", Sha256::digest(&canonical));
    let revision_id = Uuid::now_v7();
    let created_at = Utc::now();
    let mut tx = state.pool.begin().await.map_err(|_| ApiError::internal())?;
    let inserted: Option<Uuid> = sqlx::query_scalar(
        "INSERT INTO schedule_revisions (id, project_id, idempotency_key, request_sha256, timezone, source, created_at) \
         VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (project_id, idempotency_key) DO NOTHING RETURNING id",
    )
    .bind(revision_id)
    .bind(project_id)
    .bind(key)
    .bind(&request_hash)
    .bind(&request.timezone)
    .bind(&request.source)
    .bind(created_at)
    .fetch_optional(&mut *tx)
    .await
    .map_err(|_| ApiError::internal())?;
    if inserted.is_none() {
        let row = sqlx::query(
            "SELECT id, request_sha256 FROM schedule_revisions WHERE project_id = $1 AND idempotency_key = $2",
        )
        .bind(project_id)
        .bind(key)
        .fetch_one(&mut *tx)
        .await
        .map_err(|_| ApiError::internal())?;
        let original_hash: String = row
            .try_get("request_sha256")
            .map_err(|_| ApiError::internal())?;
        if original_hash.trim() != request_hash {
            return Err(ApiError {
                status: StatusCode::CONFLICT,
                detail: "idempotency key reused with different schedule",
            });
        }
        let original_id: Uuid = row.try_get("id").map_err(|_| ApiError::internal())?;
        tx.rollback().await.map_err(|_| ApiError::internal())?;
        let response = read_revision(&state.pool, project_id, original_id).await?;
        return Ok((StatusCode::OK, Json(response)));
    }
    let mut response_stages = Vec::with_capacity(request.stages.len());
    for stage in &request.stages {
        let stage_id = Uuid::now_v7();
        sqlx::query(
            "INSERT INTO work_stages (id, revision_id, code, parent_code, name, zone_code, planned_start, planned_end, observable_from_camera) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        )
        .bind(stage_id)
        .bind(revision_id)
        .bind(&stage.code)
        .bind(&stage.parent_code)
        .bind(&stage.name)
        .bind(&stage.zone_code)
        .bind(stage.planned_start)
        .bind(stage.planned_end)
        .bind(stage.observable_from_camera)
        .execute(&mut *tx)
        .await
        .map_err(|_| ApiError::internal())?;
        let mut response_rules = Vec::with_capacity(stage.equipment_rules.len());
        for rule in &stage.equipment_rules {
            let source = rule.source.as_deref().unwrap_or(&request.source);
            let class = rule.equipment_class.as_str();
            let expectation = expectation_code(rule.expectation);
            sqlx::query(
                "INSERT INTO equipment_rules (stage_id, equipment_class, expectation, min_count, max_count, min_confidence, persistence_frames, source) \
                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            )
            .bind(stage_id)
            .bind(class)
            .bind(expectation)
            .bind(i32::from(rule.min_count))
            .bind(rule.max_count.map(i32::from))
            .bind(rule.min_confidence)
            .bind(i32::from(rule.persistence_frames))
            .bind(source)
            .execute(&mut *tx)
            .await
            .map_err(|_| ApiError::internal())?;
            response_rules.push(EquipmentRuleRevisionItem {
                equipment_class: rule.equipment_class,
                expectation: rule.expectation,
                min_count: rule.min_count,
                max_count: rule.max_count,
                min_confidence: rule.min_confidence,
                persistence_frames: rule.persistence_frames,
                source: source.to_owned(),
            });
        }
        response_stages.push(WorkStageRevisionItem {
            id: StageId(stage_id),
            code: stage.code.clone(),
            parent_code: stage.parent_code.clone(),
            name: stage.name.clone(),
            zone_code: stage.zone_code.clone(),
            planned_start: stage.planned_start,
            planned_end: stage.planned_end,
            observable_from_camera: stage.observable_from_camera,
            equipment_rules: response_rules,
        });
    }
    let activation_version: i64 = sqlx::query_scalar(
        "INSERT INTO active_schedule_revisions (project_id, revision_id, version) VALUES ($1, $2, 1) \
         ON CONFLICT (project_id) DO UPDATE SET revision_id = EXCLUDED.revision_id, \
         version = active_schedule_revisions.version + 1, updated_at = now() RETURNING version",
    )
    .bind(project_id)
    .bind(revision_id)
    .fetch_one(&mut *tx)
    .await
    .map_err(|_| ApiError::internal())?;
    sqlx::query("UPDATE schedule_revisions SET activation_version = $2 WHERE id = $1")
        .bind(revision_id)
        .bind(activation_version)
        .execute(&mut *tx)
        .await
        .map_err(|_| ApiError::internal())?;
    let response = ScheduleRevisionResponse {
        id: revision_id,
        project_id: ProjectId(project_id),
        activation_version,
        timezone: request.timezone,
        source: request.source,
        created_at,
        stages: response_stages,
    };
    enqueue_revision_event(&mut tx, &response).await?;
    tx.commit().await.map_err(|_| ApiError::internal())?;
    Ok((StatusCode::CREATED, Json(response)))
}

async fn enqueue_revision_event(
    tx: &mut Transaction<'_, Postgres>,
    revision: &ScheduleRevisionResponse,
) -> Result<(), ApiError> {
    let event_id = Uuid::now_v7();
    let payload = json!({
        "specversion": "1.0",
        "id": event_id,
        "source": "sitewatch-schedule",
        "type": "schedule.revision_activated.v1",
        "subject": revision.project_id.to_string(),
        "time": Utc::now(),
        "datacontenttype": "application/json",
        "correlation_id": Uuid::now_v7(),
        "data": {"project_id": revision.project_id, "revision_id": revision.id, "activation_version": revision.activation_version},
    });
    sqlx::query("INSERT INTO outbox_events (id, subject, payload) VALUES ($1, $2, $3)")
        .bind(event_id)
        .bind("lct.schedule.revision_activated.v1")
        .bind(payload)
        .execute(&mut **tx)
        .await
        .map_err(|_| ApiError::internal())?;
    Ok(())
}

async fn get_active_schedule(
    State(state): State<AppState>,
    Path(project_id): Path<Uuid>,
    headers: HeaderMap,
) -> Result<Json<ScheduleRevisionResponse>, ApiError> {
    authenticate(&headers, &state)?;
    let revision_id: Option<Uuid> = sqlx::query_scalar(
        "SELECT revision_id FROM active_schedule_revisions WHERE project_id = $1",
    )
    .bind(project_id)
    .fetch_optional(&state.pool)
    .await
    .map_err(|_| ApiError::internal())?;
    let revision_id = revision_id.ok_or(ApiError {
        status: StatusCode::NOT_FOUND,
        detail: "active schedule not found",
    })?;
    Ok(Json(
        read_revision(&state.pool, project_id, revision_id).await?,
    ))
}

async fn get_schedule_revision(
    State(state): State<AppState>,
    Path((project_id, revision_id)): Path<(Uuid, Uuid)>,
    headers: HeaderMap,
) -> Result<Json<ScheduleRevisionResponse>, ApiError> {
    authenticate(&headers, &state)?;
    Ok(Json(
        read_revision(&state.pool, project_id, revision_id).await?,
    ))
}

// Fetch the revision, stages and all rules in three queries rather than one query per stage.
#[allow(clippy::too_many_lines)]
async fn read_revision(
    pool: &PgPool,
    project_id: Uuid,
    revision_id: Uuid,
) -> Result<ScheduleRevisionResponse, ApiError> {
    let revision = sqlx::query(
        "SELECT timezone, source, created_at, activation_version FROM schedule_revisions WHERE id = $1 AND project_id = $2",
    )
    .bind(revision_id)
    .bind(project_id)
    .fetch_optional(pool)
    .await
    .map_err(|_| ApiError::internal())?;
    let revision = revision.ok_or(ApiError {
        status: StatusCode::NOT_FOUND,
        detail: "schedule revision not found",
    })?;
    let rows = sqlx::query(
        "SELECT id, code, parent_code, name, zone_code, planned_start, planned_end, observable_from_camera \
         FROM work_stages WHERE revision_id = $1 ORDER BY zone_code, code",
    )
    .bind(revision_id)
    .fetch_all(pool)
    .await
    .map_err(|_| ApiError::internal())?;
    let rules = sqlx::query(
        "SELECT r.stage_id, r.equipment_class, r.expectation, r.min_count, r.max_count, \
         r.min_confidence, r.persistence_frames, r.source FROM equipment_rules AS r \
         JOIN work_stages AS s ON s.id = r.stage_id WHERE s.revision_id = $1 \
         ORDER BY r.stage_id, r.equipment_class",
    )
    .bind(revision_id)
    .fetch_all(pool)
    .await
    .map_err(|_| ApiError::internal())?;
    let mut rules_by_stage: HashMap<Uuid, Vec<EquipmentRuleRevisionItem>> = HashMap::new();
    for rule in rules {
        let stage_id: Uuid = rule.try_get("stage_id").map_err(|_| ApiError::internal())?;
        let class: String = rule
            .try_get("equipment_class")
            .map_err(|_| ApiError::internal())?;
        let expectation: String = rule
            .try_get("expectation")
            .map_err(|_| ApiError::internal())?;
        rules_by_stage
            .entry(stage_id)
            .or_default()
            .push(EquipmentRuleRevisionItem {
                equipment_class: enum_from_code(&class)?,
                expectation: enum_from_code(&expectation)?,
                min_count: decode_u16(&rule, "min_count")?,
                max_count: rule
                    .try_get::<Option<i32>, _>("max_count")
                    .map_err(|_| ApiError::internal())?
                    .map(u16::try_from)
                    .transpose()
                    .map_err(|_| ApiError::internal())?,
                min_confidence: rule
                    .try_get("min_confidence")
                    .map_err(|_| ApiError::internal())?,
                persistence_frames: decode_u16(&rule, "persistence_frames")?,
                source: rule.try_get("source").map_err(|_| ApiError::internal())?,
            });
    }
    let mut stages = Vec::with_capacity(rows.len());
    for row in rows {
        let stage_id: Uuid = row.try_get("id").map_err(|_| ApiError::internal())?;
        stages.push(WorkStageRevisionItem {
            id: StageId(stage_id),
            code: row.try_get("code").map_err(|_| ApiError::internal())?,
            parent_code: row
                .try_get("parent_code")
                .map_err(|_| ApiError::internal())?,
            name: row.try_get("name").map_err(|_| ApiError::internal())?,
            zone_code: row.try_get("zone_code").map_err(|_| ApiError::internal())?,
            planned_start: row
                .try_get("planned_start")
                .map_err(|_| ApiError::internal())?,
            planned_end: row
                .try_get("planned_end")
                .map_err(|_| ApiError::internal())?,
            observable_from_camera: row
                .try_get("observable_from_camera")
                .map_err(|_| ApiError::internal())?,
            equipment_rules: rules_by_stage.remove(&stage_id).unwrap_or_default(),
        });
    }
    Ok(ScheduleRevisionResponse {
        id: revision_id,
        project_id: ProjectId(project_id),
        activation_version: revision
            .try_get("activation_version")
            .map_err(|_| ApiError::internal())?,
        timezone: revision
            .try_get("timezone")
            .map_err(|_| ApiError::internal())?,
        source: revision
            .try_get("source")
            .map_err(|_| ApiError::internal())?,
        created_at: revision
            .try_get("created_at")
            .map_err(|_| ApiError::internal())?,
        stages,
    })
}

fn decode_u16(row: &sqlx::postgres::PgRow, field: &str) -> Result<u16, ApiError> {
    let value: i32 = row.try_get(field).map_err(|_| ApiError::internal())?;
    u16::try_from(value).map_err(|_| ApiError::internal())
}

fn enum_from_code<T: serde::de::DeserializeOwned>(code: &str) -> Result<T, ApiError> {
    serde_json::from_value(Value::String(code.to_owned())).map_err(|_| ApiError::internal())
}

const fn expectation_code(value: RuleExpectation) -> &'static str {
    match value {
        RuleExpectation::Required => "required",
        RuleExpectation::Optional => "optional",
        RuleExpectation::Unexpected => "unexpected",
    }
}

#[cfg(test)]
mod tests {
    use chrono::TimeZone;
    use sitewatch_contracts::WorkStageInput;
    use sitewatch_domain::EquipmentClass;

    use super::*;

    fn request() -> WorkStageImportRequest {
        WorkStageImportRequest {
            timezone: "Europe/Moscow".into(),
            source: "ППР, редакция 2, пункт 4".into(),
            stages: vec![WorkStageInput {
                code: "12.3.7".into(),
                parent_code: Some("12.3".into()),
                name: "Земляные работы".into(),
                zone_code: "PIT-01".into(),
                planned_start: Utc.with_ymd_and_hms(2026, 9, 19, 5, 0, 0).unwrap(),
                planned_end: Utc.with_ymd_and_hms(2026, 9, 26, 15, 0, 0).unwrap(),
                observable_from_camera: true,
                equipment_rules: vec![EquipmentRuleInput {
                    equipment_class: EquipmentClass::Excavator,
                    expectation: RuleExpectation::Required,
                    min_count: 1,
                    max_count: Some(2),
                    min_confidence: 0.6,
                    persistence_frames: 3,
                    source: None,
                }],
            }],
        }
    }

    #[test]
    fn import_rejects_unsourced_and_contradictory_rules() {
        let mut input = request();
        assert!(validate_import(&input).is_ok());
        input.stages[0].equipment_rules[0].min_count = 0;
        assert!(validate_import(&input).is_err());
        input = request();
        input.stages[0].equipment_rules[0].source = Some(" ".into());
        assert!(validate_import(&input).is_err());
    }

    #[test]
    fn import_rejects_duplicate_codes_and_bad_dates() {
        let mut input = request();
        input.stages.push(input.stages[0].clone());
        assert!(validate_import(&input).is_err());
        input = request();
        input.stages[0].planned_end = input.stages[0].planned_start;
        assert!(validate_import(&input).is_err());
    }

    #[test]
    fn import_wire_rejects_unknown_properties() {
        let mut value = serde_json::to_value(request()).unwrap();
        value["stages"][0]["equipment_rules"][0]["source_typo"] = json!("untrusted");
        assert!(serde_json::from_value::<WorkStageImportRequest>(value).is_err());
    }
}
