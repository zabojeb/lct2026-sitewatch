use std::sync::Arc;

use axum::{Router, routing::get};
use sitewatch_platform::Infrastructure;
use tower_http::{
    cors::{Any, CorsLayer},
    request_id::{MakeRequestUuid, PropagateRequestIdLayer, SetRequestIdLayer},
    trace::TraceLayer,
};
use utoipa::OpenApi;
use utoipa_swagger_ui::SwaggerUi;

pub mod routes;

#[derive(Debug, Clone)]
pub struct AppState {
    pub infrastructure: Arc<Infrastructure>,
}

#[derive(Debug, OpenApi)]
#[openapi(
    info(
        title = "SiteWatch API",
        version = "0.1.0",
        description = "Explainable construction-site monitoring API"
    ),
    paths(
        routes::health::live,
        routes::health::ready,
        routes::meta::equipment_classes
    ),
    components(schemas(
        sitewatch_contracts::HealthResponse,
        sitewatch_contracts::ReadinessResponse,
        sitewatch_contracts::DependencyStatus,
        sitewatch_contracts::ServiceStatus,
        sitewatch_contracts::EquipmentClassMetadata,
        sitewatch_contracts::ProblemDetails,
        sitewatch_contracts::FieldViolation,
        sitewatch_domain::EquipmentClass
    )),
    tags(
        (name = "health", description = "Kubernetes probes"),
        (name = "metadata", description = "Stable product dictionaries")
    )
)]
pub struct ApiDoc;

pub fn build_router(state: AppState) -> Router {
    let request_id_header = axum::http::HeaderName::from_static("x-request-id");

    Router::new()
        .route("/health/live", get(routes::health::live))
        .route("/health/ready", get(routes::health::ready))
        .route(
            "/api/v1/meta/equipment-classes",
            get(routes::meta::equipment_classes),
        )
        .merge(SwaggerUi::new("/docs").url("/api-doc/openapi.json", ApiDoc::openapi()))
        .with_state(state)
        .layer(PropagateRequestIdLayer::new(request_id_header.clone()))
        .layer(SetRequestIdLayer::new(request_id_header, MakeRequestUuid))
        .layer(TraceLayer::new_for_http())
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        )
}
