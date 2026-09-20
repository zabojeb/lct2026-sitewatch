use axum::Json;
use sitewatch_contracts::EquipmentClassMetadata;
use sitewatch_domain::EquipmentClass;

#[utoipa::path(
    get,
    path = "/api/v1/meta/equipment-classes",
    tag = "metadata",
    responses(
        (status = 200, description = "Supported equipment taxonomy", body = [EquipmentClassMetadata])
    )
)]
pub async fn equipment_classes() -> Json<Vec<EquipmentClassMetadata>> {
    Json(
        EquipmentClass::ALL
            .into_iter()
            .map(|equipment_class| EquipmentClassMetadata {
                code: equipment_class,
                title_ru: equipment_class.title_ru().to_owned(),
            })
            .collect(),
    )
}
