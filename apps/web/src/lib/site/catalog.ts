/** The 14 classes the stage methodology reasons about (8 from the task + 6 added by the team). */
export const EQUIPMENT = [
  'dump-truck',
  'excavator',
  'roller',
  'manipulator',
  'mixer',
  'bulldozer',
  'truck',
  'mobile-crane',
  'tower-crane',
  'drill',
  'pump',
  'loader',
  'grader',
  'paver',
] as const;

const NAMES: Record<string, string> = {
  'dump-truck': 'Самосвал',
  excavator: 'Экскаватор',
  roller: 'Каток',
  manipulator: 'Кран-манипулятор',
  mixer: 'Автобетоносмеситель',
  bulldozer: 'Бульдозер',
  truck: 'Грузовик',
  'mobile-crane': 'Автокран',
  'tower-crane': 'Башенный кран',
  drill: 'Буровая установка',
  pump: 'Бетононасос',
  loader: 'Погрузчик',
  grader: 'Автогрейдер',
  paver: 'Асфальтоукладчик',
  person: 'Человек',
  helmet: 'Каска',
  'mini-loader': 'Мини-погрузчик',
  tractor: 'Трактор',
  'mini-bulldozer': 'Мини-бульдозер',
  forklift: 'Вилочный погрузчик',
  'garbage-truck': 'Мусоровоз',
  lift: 'Подъёмник',
};

export const equipmentName = (slug: string) => NAMES[slug] ?? slug;
export const isEquipment = (slug: string) => (EQUIPMENT as readonly string[]).includes(slug);
/** People and helmets are shown but never counted as machinery. */
export const isMachine = (slug: string) => slug !== 'person' && slug !== 'helmet';

export const SOURCE_LABELS = {
  annotation: 'разметка датасета',
  model: 'модель',
  synthetic: 'синтетические кадры',
} as const;
