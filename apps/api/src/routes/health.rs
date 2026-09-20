use std::time::SystemTime;

use axum::{Json, extract::State, http::StatusCode, response::IntoResponse};
use chrono::Utc;
use sitewatch_contracts::{DependencyStatus, HealthResponse, ReadinessResponse, ServiceStatus};

use crate::AppState;

#[utoipa::path(
    get,
    path = "/health/live",
    tag = "health",
    responses((status = 200, description = "Process is alive", body = HealthResponse))
)]
pub async fn live() -> Json<HealthResponse> {
    Json(HealthResponse {
        status: ServiceStatus::Up,
        service: "sitewatch-api".to_owned(),
        version: env!("CARGO_PKG_VERSION").to_owned(),
        timestamp: Utc::now(),
    })
}

#[utoipa::path(
    get,
    path = "/health/ready",
    tag = "health",
    responses(
        (status = 200, description = "All required dependencies are available", body = ReadinessResponse),
        (status = 503, description = "One or more dependencies are unavailable", body = ReadinessResponse)
    )
)]
pub async fn ready(State(state): State<AppState>) -> impl IntoResponse {
    let dependencies = state.infrastructure.readiness().await;
    let healthy = dependencies.iter().all(|dependency| dependency.healthy);
    let response = ReadinessResponse {
        status: if healthy {
            ServiceStatus::Up
        } else {
            ServiceStatus::Down
        },
        dependencies: dependencies
            .into_iter()
            .map(|probe| DependencyStatus {
                name: probe.name.to_owned(),
                status: if probe.healthy {
                    ServiceStatus::Up
                } else {
                    ServiceStatus::Down
                },
                latency_ms: probe.latency_ms,
                detail: probe.detail,
            })
            .collect(),
        timestamp: SystemTime::now().into(),
    };
    let status = if healthy {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };
    (status, Json(response))
}
