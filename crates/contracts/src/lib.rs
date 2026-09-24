//! Stable wire contracts exposed to the web application and asynchronous processors.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sitewatch_domain::{
    AssetRef, CameraId, Detection, DeviationId, DeviationKind, DeviationStatus, EquipmentClass,
    JobId, ObservationId, ObservationSource, ObservationStatus, ProjectId, RuleExpectation,
    Severity, StageId, ZoneId,
};
use utoipa::ToSchema;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct HealthResponse {
    pub status: ServiceStatus,
    pub service: String,
    pub version: String,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ReadinessResponse {
    pub status: ServiceStatus,
    pub dependencies: Vec<DependencyStatus>,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ServiceStatus {
    Up,
    Degraded,
    Down,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct DependencyStatus {
    pub name: String,
    pub status: ServiceStatus,
    pub latency_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct EquipmentClassMetadata {
    pub code: EquipmentClass,
    pub title_ru: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct CreateObservationRequest {
    pub project_id: ProjectId,
    pub camera_id: CameraId,
    pub zone_id: ZoneId,
    pub captured_at: DateTime<Utc>,
    pub source: ObservationSource,
    pub asset: AssetRef,
    /// Client-generated key. Retrying the same request must not duplicate an observation.
    pub idempotency_key: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ObservationAcceptedResponse {
    pub observation_id: ObservationId,
    pub job_id: JobId,
    pub status: ObservationStatus,
    pub queued_at: DateTime<Utc>,
    pub correlation_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ObservationResponse {
    pub id: ObservationId,
    pub project_id: ProjectId,
    pub camera_id: CameraId,
    pub zone_id: ZoneId,
    pub captured_at: DateTime<Utc>,
    pub status: ObservationStatus,
    pub asset: AssetRef,
    pub detections: Vec<Detection>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub analyzed_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct DeviationResponse {
    pub id: DeviationId,
    pub project_id: ProjectId,
    pub stage_id: StageId,
    pub zone_id: ZoneId,
    pub kind: DeviationKind,
    pub severity: Severity,
    pub status: DeviationStatus,
    pub title: String,
    pub explanation: String,
    pub expected: Vec<EquipmentCount>,
    pub observed: Vec<EquipmentCount>,
    pub evidence_observation_ids: Vec<ObservationId>,
    pub detected_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct EquipmentCount {
    pub equipment_class: EquipmentClass,
    pub count: u16,
}

/// Complete replacement of one project's active schedule revision.
#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct WorkStageImportRequest {
    pub timezone: String,
    pub source: String,
    pub stages: Vec<WorkStageInput>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct WorkStageInput {
    pub code: String,
    pub parent_code: Option<String>,
    pub name: String,
    pub zone_code: String,
    pub planned_start: DateTime<Utc>,
    pub planned_end: DateTime<Utc>,
    pub observable_from_camera: bool,
    pub equipment_rules: Vec<EquipmentRuleInput>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EquipmentRuleInput {
    pub equipment_class: EquipmentClass,
    pub expectation: RuleExpectation,
    pub min_count: u16,
    pub max_count: Option<u16>,
    pub min_confidence: f32,
    pub persistence_frames: u16,
    /// Rule-specific document reference; defaults to the import's source when omitted.
    pub source: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ScheduleRevisionResponse {
    pub id: Uuid,
    pub project_id: ProjectId,
    /// Monotonic per-project activation order; consumers ignore older events.
    pub activation_version: i64,
    pub timezone: String,
    pub source: String,
    pub created_at: DateTime<Utc>,
    pub stages: Vec<WorkStageRevisionItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct WorkStageRevisionItem {
    pub id: StageId,
    pub code: String,
    pub parent_code: Option<String>,
    pub name: String,
    pub zone_code: String,
    pub planned_start: DateTime<Utc>,
    pub planned_end: DateTime<Utc>,
    pub observable_from_camera: bool,
    pub equipment_rules: Vec<EquipmentRuleRevisionItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct EquipmentRuleRevisionItem {
    pub equipment_class: EquipmentClass,
    pub expectation: RuleExpectation,
    pub min_count: u16,
    pub max_count: Option<u16>,
    pub min_confidence: f32,
    pub persistence_frames: u16,
    pub source: String,
}

/// RFC 9457-compatible problem details returned by every HTTP error path.
#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ProblemDetails {
    #[serde(rename = "type")]
    pub type_url: String,
    pub title: String,
    pub status: u16,
    pub detail: String,
    pub instance: String,
    pub trace_id: String,
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    pub errors: Vec<FieldViolation>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct FieldViolation {
    pub field: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(bound = "T: Serialize + for<'de2> Deserialize<'de2>")]
pub struct EventEnvelope<T> {
    pub specversion: String,
    pub id: Uuid,
    pub source: String,
    #[serde(rename = "type")]
    pub event_type: String,
    pub subject: String,
    pub time: DateTime<Utc>,
    pub datacontenttype: String,
    pub correlation_id: Uuid,
    pub causation_id: Option<Uuid>,
    pub data: T,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ObservationAcceptedEvent {
    pub observation_id: ObservationId,
    pub project_id: ProjectId,
    pub camera_id: CameraId,
    pub zone_id: ZoneId,
    pub asset: AssetRef,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ObservationAnalyzedEvent {
    pub observation_id: ObservationId,
    pub project_id: ProjectId,
    pub camera_id: CameraId,
    pub zone_id: ZoneId,
    pub captured_at: DateTime<Utc>,
    pub detections: Vec<Detection>,
    pub model_version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct DeviationDetectedEvent {
    pub deviation: DeviationResponse,
}
