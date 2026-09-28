export type BoundingBox = {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
};

export type ModelDetection = {
  raw_class_id: number;
  raw_class: string;
  equipment_class: string | null;
  mapping_status: 'mapped' | 'other' | 'ignored' | 'low_confidence';
  detector_score: number;
  classifier_score: number;
  bounding_box: BoundingBox;
};

export type ModelPrediction = {
  schema: 'sitewatch.inference.v1';
  model_version: string;
  image_width: number;
  image_height: number;
  detections: ModelDetection[];
  note: string;
};

export const rawClassLabels: Record<string, string> = {
  dump_truck: 'Самосвал',
  excavator: 'Экскаватор',
  motor_grader: 'Автогрейдер',
  roller: 'Каток',
  crane_manipulator: 'Кран-манипулятор',
  light_commercial_vehicle: 'Лёгкий коммерческий автомобиль',
  forklift: 'Вилочный погрузчик',
  bucket_loader: 'Ковшовый погрузчик',
  concrete_mixer: 'Автобетоносмеситель',
  tanker: 'Автоцистерна',
  bulldozer: 'Бульдозер',
  cleaning_equipment: 'Уборочная техника',
  truck: 'Грузовик',
  trailer: 'Прицеп',
  mobile_crane: 'Автокран',
  tower_crane: 'Башенный кран',
  tractor: 'Трактор',
  concrete_pump: 'Бетононасос',
  drilling_rig: 'Буровая установка',
  pile_driver: 'Сваебойная установка',
  person: 'Человек',
  other_vehicle: 'Прочий транспорт',
};

export function detectionLabel(detection: ModelDetection): string {
  return rawClassLabels[detection.raw_class] ?? detection.raw_class;
}
