//! Domain language shared by the API, processor and rule engine.
//!
//! These types deliberately avoid database- or transport-specific details. They define what the
//! product means by an observation, an equipment rule and a deviation.

use std::{fmt, str::FromStr};

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use utoipa::ToSchema;
use uuid::Uuid;

pub mod evaluation;

macro_rules! entity_id {
    ($name:ident) => {
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
        #[serde(transparent)]
        #[schema(value_type = String, format = Uuid)]
        pub struct $name(pub Uuid);

        impl $name {
            pub fn new() -> Self {
                Self(Uuid::now_v7())
            }
        }

        impl Default for $name {
            fn default() -> Self {
                Self::new()
            }
        }

        impl fmt::Display for $name {
            fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                self.0.fmt(formatter)
            }
        }

        impl FromStr for $name {
            type Err = uuid::Error;

            fn from_str(value: &str) -> Result<Self, Self::Err> {
                Uuid::parse_str(value).map(Self)
            }
        }
    };
}

entity_id!(ProjectId);
entity_id!(ZoneId);
entity_id!(CameraId);
entity_id!(StageId);
entity_id!(ObservationId);
entity_id!(DetectionId);
entity_id!(DeviationId);
entity_id!(JobId);

#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, ToSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum EquipmentClass {
    DumpTruck,
    Excavator,
    RoadRoller,
    LoaderCrane,
    ConcreteMixer,
    Bulldozer,
    Truck,
    MobileCrane,
    TowerCrane,
    PilingRig,
}

impl EquipmentClass {
    pub const ALL: [Self; 10] = [
        Self::DumpTruck,
        Self::Excavator,
        Self::RoadRoller,
        Self::LoaderCrane,
        Self::ConcreteMixer,
        Self::Bulldozer,
        Self::Truck,
        Self::MobileCrane,
        Self::TowerCrane,
        Self::PilingRig,
    ];

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::DumpTruck => "dump_truck",
            Self::Excavator => "excavator",
            Self::RoadRoller => "road_roller",
            Self::LoaderCrane => "loader_crane",
            Self::ConcreteMixer => "concrete_mixer",
            Self::Bulldozer => "bulldozer",
            Self::Truck => "truck",
            Self::MobileCrane => "mobile_crane",
            Self::TowerCrane => "tower_crane",
            Self::PilingRig => "piling_rig",
        }
    }

    pub const fn title_ru(self) -> &'static str {
        match self {
            Self::DumpTruck => "Самосвал",
            Self::Excavator => "Экскаватор",
            Self::RoadRoller => "Каток",
            Self::LoaderCrane => "Кран-манипулятор",
            Self::ConcreteMixer => "Автобетоносмеситель",
            Self::Bulldozer => "Бульдозер",
            Self::Truck => "Грузовик",
            Self::MobileCrane => "Автокран",
            Self::TowerCrane => "Башенный кран",
            Self::PilingRig => "Буровая или сваебойная установка",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ObservationSource {
    Upload,
    CameraSnapshot,
    RtspFrame,
    Synthetic,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ObservationStatus {
    Queued,
    Processing,
    Analyzed,
    Rejected,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum RuleExpectation {
    Required,
    Optional,
    Unexpected,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum DeviationKind {
    MissingRequiredEquipment,
    UnexpectedEquipment,
    CountOutsideRange,
    InsufficientEvidence,
    ScheduleConflict,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Info,
    Warning,
    Critical,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum DeviationStatus {
    Open,
    Acknowledged,
    Resolved,
    Dismissed,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct BoundingBox {
    /// Normalized left coordinate in the `[0, 1]` interval.
    pub x_min: f32,
    /// Normalized top coordinate in the `[0, 1]` interval.
    pub y_min: f32,
    /// Normalized right coordinate in the `[0, 1]` interval.
    pub x_max: f32,
    /// Normalized bottom coordinate in the `[0, 1]` interval.
    pub y_max: f32,
}

impl BoundingBox {
    /// Checks that every coordinate is normalized and that the box has positive area.
    ///
    /// # Errors
    ///
    /// Returns [`DomainValidationError::InvalidBoundingBox`] for non-finite, out-of-range or
    /// inverted coordinates.
    pub fn validate(&self) -> Result<(), DomainValidationError> {
        let coordinates = [self.x_min, self.y_min, self.x_max, self.y_max];
        if coordinates
            .iter()
            .any(|value| !value.is_finite() || !(0.0..=1.0).contains(value))
        {
            return Err(DomainValidationError::InvalidBoundingBox);
        }
        if self.x_min >= self.x_max || self.y_min >= self.y_max {
            return Err(DomainValidationError::InvalidBoundingBox);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Detection {
    pub id: DetectionId,
    pub equipment_class: EquipmentClass,
    pub confidence: f32,
    pub bounding_box: BoundingBox,
    pub model_version: String,
}

impl Detection {
    /// Validates detector confidence and normalized geometry.
    ///
    /// # Errors
    ///
    /// Returns a domain validation error when confidence or the bounding box is invalid.
    pub fn validate(&self) -> Result<(), DomainValidationError> {
        if !self.confidence.is_finite() || !(0.0..=1.0).contains(&self.confidence) {
            return Err(DomainValidationError::InvalidConfidence);
        }
        self.bounding_box.validate()
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct EquipmentRule {
    pub equipment_class: EquipmentClass,
    pub expectation: RuleExpectation,
    pub min_count: u16,
    pub max_count: Option<u16>,
    pub min_confidence: f32,
    pub persistence_frames: u16,
}

impl EquipmentRule {
    /// Validates count bounds, confidence and temporal persistence.
    ///
    /// # Errors
    ///
    /// Returns a domain validation error for contradictory counts, an invalid confidence or an
    /// empty persistence window.
    pub fn validate(&self) -> Result<(), DomainValidationError> {
        if let Some(max_count) = self.max_count
            && max_count < self.min_count
        {
            return Err(DomainValidationError::InvalidCountRange);
        }
        if !self.min_confidence.is_finite() || !(0.0..=1.0).contains(&self.min_confidence) {
            return Err(DomainValidationError::InvalidConfidence);
        }
        if self.persistence_frames == 0 {
            return Err(DomainValidationError::ZeroPersistenceWindow);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct AssetRef {
    /// S3-compatible object key. The API never exposes bucket credentials.
    pub object_key: String,
    /// Lowercase hexadecimal SHA-256 digest used for idempotency and audit.
    pub sha256: String,
    pub media_type: String,
    pub size_bytes: u64,
    pub width_px: u32,
    pub height_px: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct WorkStage {
    pub id: StageId,
    pub project_id: ProjectId,
    pub parent_id: Option<StageId>,
    /// Stable WBS code stored as text, e.g. `12.3.7`.
    pub code: String,
    pub name: String,
    pub zone_id: ZoneId,
    pub planned_start: DateTime<Utc>,
    pub planned_end: DateTime<Utc>,
    pub observable_from_camera: bool,
    pub rules: Vec<EquipmentRule>,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum DomainValidationError {
    #[error("bounding-box coordinates must be finite, normalized and ordered")]
    InvalidBoundingBox,
    #[error("confidence must be a finite value in the [0, 1] interval")]
    InvalidConfidence,
    #[error("maximum equipment count cannot be lower than minimum count")]
    InvalidCountRange,
    #[error("persistence window must contain at least one frame")]
    ZeroPersistenceWindow,
    #[error("planned end must be after planned start")]
    InvalidSchedule,
    #[error("completion must be in [0, 100] and have a source")]
    InvalidProgressMeasurement,
    #[error("evidence must match the rule and coverage/provenance must be valid")]
    InvalidEvidence,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bounding_box_rejects_inverted_coordinates() {
        let bounding_box = BoundingBox {
            x_min: 0.8,
            y_min: 0.1,
            x_max: 0.2,
            y_max: 0.9,
        };

        assert_eq!(
            bounding_box.validate(),
            Err(DomainValidationError::InvalidBoundingBox)
        );
    }

    #[test]
    fn equipment_rule_rejects_an_empty_persistence_window() {
        let rule = EquipmentRule {
            equipment_class: EquipmentClass::Excavator,
            expectation: RuleExpectation::Required,
            min_count: 1,
            max_count: None,
            min_confidence: 0.6,
            persistence_frames: 0,
        };

        assert_eq!(
            rule.validate(),
            Err(DomainValidationError::ZeroPersistenceWindow)
        );
    }
}
