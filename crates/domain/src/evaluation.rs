//! Pure comparisons: detector output is evidence, never a schedule verdict by itself.

use chrono::{DateTime, Duration, Utc};

use crate::{DomainValidationError, EquipmentClass, EquipmentRule, RuleExpectation};

/// Operator measurement or a separately validated estimator output with provenance.
#[derive(Debug, Clone, PartialEq)]
pub struct ProgressMeasurement {
    pub measured_at: DateTime<Utc>,
    pub percent: f64,
    pub source: String,
}

/// Positive variance means the measured completion happened late; negative means early.
#[derive(Debug, Clone, PartialEq)]
pub struct ScheduleComparison {
    pub planned_percent_at_measurement: f64,
    pub measured_percent: f64,
    pub percentage_point_delta: f64,
    pub variance_seconds: i64,
    pub planned_duration_seconds: i64,
    pub source: String,
}

/// Compare sourced completion with an explicit linear plan, not machinery presence.
///
/// # Errors
/// Rejects invalid dates, percentages or missing provenance.
pub fn compare_schedule(
    planned_start: DateTime<Utc>,
    planned_end: DateTime<Utc>,
    measurement: &ProgressMeasurement,
) -> Result<ScheduleComparison, DomainValidationError> {
    let duration = (planned_end - planned_start).num_seconds();
    if duration <= 0 {
        return Err(DomainValidationError::InvalidSchedule);
    }
    let planned_span = (planned_end - planned_start)
        .to_std()
        .map_err(|_| DomainValidationError::InvalidSchedule)?;
    if !measurement.percent.is_finite()
        || !(0.0..=100.0).contains(&measurement.percent)
        || measurement.source.trim().is_empty()
    {
        return Err(DomainValidationError::InvalidProgressMeasurement);
    }
    let elapsed = (measurement.measured_at - planned_start).num_seconds();
    let planned_percent = if elapsed <= 0 {
        0.0
    } else if elapsed >= duration {
        100.0
    } else {
        (measurement.measured_at - planned_start)
            .to_std()
            .map_err(|_| DomainValidationError::InvalidSchedule)?
            .as_secs_f64()
            / planned_span.as_secs_f64()
            * 100.0
    };
    let milestone = Duration::from_std(planned_span.mul_f64(measurement.percent / 100.0))
        .map_err(|_| DomainValidationError::InvalidSchedule)?;
    let planned_milestone = planned_start
        .checked_add_signed(milestone)
        .ok_or(DomainValidationError::InvalidSchedule)?;
    Ok(ScheduleComparison {
        planned_percent_at_measurement: planned_percent,
        measured_percent: measurement.percent,
        percentage_point_delta: measurement.percent - planned_percent,
        variance_seconds: (measurement.measured_at - planned_milestone).num_seconds(),
        planned_duration_seconds: duration,
        source: measurement.source.clone(),
    })
}

#[derive(Debug, Clone, PartialEq)]
pub struct CountEvidence {
    pub equipment_class: EquipmentClass,
    /// Deduplicated tracked objects, not the sum of boxes across frames.
    pub observed_count: u16,
    pub confirmed_frames: u16,
    pub evidence_ids: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RuleAssessment {
    Consistent,
    Missing,
    BelowMinimum,
    AboveMaximum,
    Unexpected,
    InsufficientEvidence,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EquipmentComparison {
    pub equipment_class: EquipmentClass,
    pub expectation: RuleExpectation,
    pub expected_min: u16,
    pub expected_max: Option<u16>,
    pub observed_count: u16,
    pub assessment: RuleAssessment,
    pub rule_source: String,
    pub evidence_ids: Vec<String>,
}

/// Apply one sourced rule. Blind spots and incomplete persistence cannot yield a verdict.
///
/// # Errors
/// Rejects invalid rule, mismatched class, coverage or missing rule provenance.
pub fn compare_equipment(
    rule: &EquipmentRule,
    rule_source: &str,
    evidence: &CountEvidence,
    coverage_percent: f32,
    minimum_coverage_percent: f32,
) -> Result<EquipmentComparison, DomainValidationError> {
    rule.validate()?;
    if rule.equipment_class != evidence.equipment_class
        || rule_source.trim().is_empty()
        || !coverage_percent.is_finite()
        || !minimum_coverage_percent.is_finite()
        || !(0.0..=100.0).contains(&coverage_percent)
        || !(0.0..=100.0).contains(&minimum_coverage_percent)
    {
        return Err(DomainValidationError::InvalidEvidence);
    }
    let assessment = if coverage_percent < minimum_coverage_percent
        || evidence.confirmed_frames < rule.persistence_frames
        || (evidence.observed_count > 0 && evidence.evidence_ids.is_empty())
    {
        RuleAssessment::InsufficientEvidence
    } else if rule.expectation == RuleExpectation::Unexpected && evidence.observed_count > 0 {
        RuleAssessment::Unexpected
    } else if rule.expectation == RuleExpectation::Required
        && evidence.observed_count < rule.min_count
    {
        if evidence.observed_count == 0 {
            RuleAssessment::Missing
        } else {
            RuleAssessment::BelowMinimum
        }
    } else if rule
        .max_count
        .is_some_and(|maximum| evidence.observed_count > maximum)
    {
        RuleAssessment::AboveMaximum
    } else {
        RuleAssessment::Consistent
    };
    Ok(EquipmentComparison {
        equipment_class: rule.equipment_class,
        expectation: rule.expectation,
        expected_min: rule.min_count,
        expected_max: rule.max_count,
        observed_count: evidence.observed_count,
        assessment,
        rule_source: rule_source.to_owned(),
        evidence_ids: evidence.evidence_ids.clone(),
    })
}

#[cfg(test)]
mod tests {
    use chrono::{Duration, TimeZone};

    use super::*;

    #[test]
    fn schedule_expresses_delay_and_lead_in_hours() {
        let start = Utc.with_ymd_and_hms(2026, 9, 1, 0, 0, 0).unwrap();
        let end = start + Duration::days(10);
        let measured_at = start + Duration::days(5);
        let late = compare_schedule(
            start,
            end,
            &ProgressMeasurement {
                measured_at,
                percent: 40.0,
                source: "Акт КС-2".into(),
            },
        )
        .unwrap();
        assert_eq!(late.variance_seconds, 86_400);
        assert!((late.percentage_point_delta + 10.0).abs() < 1e-9);
        assert_eq!(late.planned_duration_seconds, 864_000);
        let early = compare_schedule(
            start,
            end,
            &ProgressMeasurement {
                measured_at,
                percent: 55.0,
                source: "Замер инженера".into(),
            },
        )
        .unwrap();
        assert_eq!(early.variance_seconds, -43_200);
    }

    #[test]
    fn rejects_unsourced_measurement() {
        let now = Utc::now();
        assert_eq!(
            compare_schedule(
                now,
                now + Duration::days(1),
                &ProgressMeasurement {
                    measured_at: now,
                    percent: 50.0,
                    source: " ".into(),
                }
            ),
            Err(DomainValidationError::InvalidProgressMeasurement)
        );
    }

    #[test]
    fn quantity_shortage_and_blind_spot_are_distinct() {
        let rule = EquipmentRule {
            equipment_class: EquipmentClass::Excavator,
            expectation: RuleExpectation::Required,
            min_count: 2,
            max_count: Some(3),
            min_confidence: 0.7,
            persistence_frames: 2,
        };
        let evidence = CountEvidence {
            equipment_class: EquipmentClass::Excavator,
            observed_count: 1,
            confirmed_frames: 2,
            evidence_ids: vec!["observation-1".into()],
        };
        assert_eq!(
            compare_equipment(&rule, "Ведомость техники, п. 3", &evidence, 95.0, 80.0)
                .unwrap()
                .assessment,
            RuleAssessment::BelowMinimum
        );
        assert_eq!(
            compare_equipment(&rule, "Ведомость техники, п. 3", &evidence, 60.0, 80.0)
                .unwrap()
                .assessment,
            RuleAssessment::InsufficientEvidence
        );
        let mut over = evidence.clone();
        over.observed_count = 4;
        assert_eq!(
            compare_equipment(&rule, "Ведомость техники, п. 3", &over, 95.0, 80.0)
                .unwrap()
                .assessment,
            RuleAssessment::AboveMaximum
        );
        let unexpected = EquipmentRule {
            expectation: RuleExpectation::Unexpected,
            min_count: 0,
            max_count: Some(0),
            ..rule
        };
        assert_eq!(
            compare_equipment(&unexpected, "ППР", &evidence, 95.0, 80.0)
                .unwrap()
                .assessment,
            RuleAssessment::Unexpected
        );
    }
}
