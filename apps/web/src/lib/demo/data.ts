/** Synthetic UI fixtures. Never use this module as an API fallback or model output. */
export type Assessment = 'needs_attention' | 'consistent' | 'insufficient_evidence';
export type Decision = 'acknowledged' | 'dismissed';
export type Detection = {
  label: string;
  confidence: number;
  bbox: [number, number, number, number];
  unexpected?: boolean;
};
export type Observation = {
  id: string;
  siteId: string;
  camera: string;
  zone: string;
  time: string;
  image: string;
  title: string;
  assessment: Assessment;
  stage: string;
  rule: string;
  expected: string;
  observed: string;
  explanation: string;
  limitation: string;
  detections: Detection[];
};
export type Review = {
  observationId: string;
  decision: Decision;
  note: string;
  createdAt: string;
  context?: string;
};
export const reviewStorageKey = 'sitewatch.demo.reviews.v1';
export const assessmentLabels: Record<Assessment, string> = {
  needs_attention: 'Нужна проверка',
  consistent: 'Согласуется с планом',
  insufficient_evidence: 'Недостаточно данных',
};
export const decisionLabels: Record<Decision, string> = {
  acknowledged: 'Взято в работу',
  dismissed: 'Сигнал отклонён',
};
export const sites = [
  {
    id: 'north',
    name: 'Северный квартал',
    address: 'Москва, участок № 14',
    code: 'SW-014',
    cameras: 3,
  },
  { id: 'river', name: 'Речной парк', address: 'Москва, участок № 08', code: 'SW-008', cameras: 2 },
];
const excavator: Detection = {
  label: 'Экскаватор',
  confidence: 0.94,
  bbox: [0.235, 0.202, 0.462, 0.473],
};
const crane: Detection = {
  label: 'Башенный кран',
  confidence: 0.91,
  bbox: [0.705, 0.022, 0.294, 0.75],
};
export const observations: Observation[] = [
  {
    id: 'OBS-1042',
    siteId: 'north',
    camera: 'Камера 01',
    zone: 'Котлован, секция Б',
    time: '2026-09-19T11:32:00Z',
    image: '/images/excavation.webp',
    title: 'Самосвал не наблюдается',
    assessment: 'needs_attention',
    stage: 'Разработка котлована',
    rule: 'EQ-01 / required_equipment',
    expected: 'Экскаватор ≥ 1, самосвал ≥ 1 в рабочей зоне.',
    observed: 'Экскаватор: 1. Самосвал: 0 в демонстрационном кадре.',
    explanation:
      'Для активного этапа предусмотрен вывоз грунта. В этом наблюдении самосвал не найден. Нужны дополнительные кадры и проверка диспетчером.',
    limitation:
      'Отсутствие объекта в одном кадре не доказывает простой. Самосвал может находиться за границей обзора.',
    detections: [excavator],
  },
  {
    id: 'OBS-1041',
    siteId: 'north',
    camera: 'Камера 02',
    zone: 'Корпус А',
    time: '2026-09-19T11:18:00Z',
    image: '/images/concrete.webp',
    title: 'Кран виден в зоне монтажа',
    assessment: 'consistent',
    stage: 'Монтаж конструкций',
    rule: 'EQ-02 / required_equipment',
    expected: 'Башенный кран ≥ 1 в зоне монтажа.',
    observed: 'Башенный кран: 1 в демонстрационном кадре.',
    explanation:
      'Наблюдаемая техника соответствует потребности этапа. Это не оценка готовности конструкций и не подтверждение соблюдения сроков.',
    limitation: 'По одному изображению нельзя определить загрузку крана и объём выполненных работ.',
    detections: [crane],
  },
  {
    id: 'OBS-1040',
    siteId: 'north',
    camera: 'Камера 03',
    zone: 'Внутренний контур',
    time: '2026-09-19T10:54:00Z',
    image: '/images/concrete.webp',
    title: 'Внутренние работы вне обзора',
    assessment: 'insufficient_evidence',
    stage: 'Инженерные сети',
    rule: 'OBS-01 / visibility_required',
    expected: 'Наблюдаемая зона внутренних работ.',
    observed: 'Наружный ракурс. Рабочая зона внутри здания не видна.',
    explanation:
      'Камера не позволяет оценить этот этап. Система не делает вывод о соответствии или нарушении.',
    limitation: 'Запросите внутренний ракурс или акт выполненных работ.',
    detections: [],
  },
  {
    id: 'OBS-1039',
    siteId: 'north',
    camera: 'Камера 01',
    zone: 'Котлован, секция Б',
    time: '2026-09-19T10:30:00Z',
    image: '/images/excavation.webp',
    title: 'Нужен повторный ракурс',
    assessment: 'needs_attention',
    stage: 'Разработка котлована',
    rule: 'EQ-01 / required_equipment',
    expected: 'Экскаватор ≥ 1, самосвал ≥ 1 в рабочей зоне.',
    observed: 'Экскаватор: 1. Вывоз грунта не наблюдается.',
    explanation:
      'Предыдущий демонстрационный эпизод для проверки рабочего процесса. Изображение-иллюстрация повторно используется, это не временная серия.',
    limitation:
      'Нельзя агрегировать повторно использованную иллюстрацию в доказательство длительного простоя.',
    detections: [excavator],
  },
  {
    id: 'OBS-2081',
    siteId: 'river',
    camera: 'Камера 01',
    zone: 'Корпус В',
    time: '2026-09-19T11:24:00Z',
    image: '/images/concrete.webp',
    title: 'Монтаж обеспечен техникой',
    assessment: 'consistent',
    stage: 'Монтаж конструкций',
    rule: 'EQ-02 / required_equipment',
    expected: 'Башенный кран ≥ 1.',
    observed: 'Башенный кран: 1 в демонстрационном кадре.',
    explanation:
      'Техника наблюдается. Фактическая производительность и готовность этажа требуют дополнительных данных.',
    limitation:
      'Иллюстрация используется для нескольких сценариев и не является снимком реального объекта.',
    detections: [crane],
  },
  {
    id: 'OBS-2080',
    siteId: 'river',
    camera: 'Камера 02',
    zone: 'Подземный паркинг',
    time: '2026-09-19T10:45:00Z',
    image: '/images/site-aerial.webp',
    title: 'Паркинг не виден снаружи',
    assessment: 'insufficient_evidence',
    stage: 'Инженерные сети',
    rule: 'OBS-01 / visibility_required',
    expected: 'Ракурс подземного паркинга.',
    observed: 'Общий вид площадки, подземная зона скрыта.',
    explanation: 'Недостаточно наблюдений, чтобы оценить выполнение внутренних работ.',
    limitation: 'Нужен отдельный источник наблюдений внутри паркинга.',
    detections: [],
  },
];
export const stages = [
  {
    name: 'Разработка котлована',
    dates: '14-22 сентября',
    start: 0,
    span: 9,
    equipment: 'Экскаватор, самосвал',
    observable: true,
  },
  {
    name: 'Монтаж конструкций',
    dates: '18-27 сентября',
    start: 4,
    span: 10,
    equipment: 'Башенный кран',
    observable: true,
  },
  {
    name: 'Инженерные сети',
    dates: '18-30 сентября',
    start: 4,
    span: 13,
    equipment: 'Не оценивается по внешней камере',
    observable: false,
  },
];
export function formatTime(utc: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'Europe/Moscow',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(utc));
}
export function parseReviews(raw: string | null): Review[] {
  if (!raw) return [];
  try {
    const value: unknown = JSON.parse(raw);
    if (!Array.isArray(value)) return [];
    return value
      .filter(
        (r): r is Review =>
          r !== null &&
          typeof r === 'object' &&
          observations.some((o) => o.id === r.observationId) &&
          ['acknowledged', 'dismissed'].includes(r.decision) &&
          typeof r.note === 'string' &&
          r.note.trim().length >= 3 &&
          r.note.length <= 1000 &&
          typeof r.createdAt === 'string' &&
          Number.isFinite(Date.parse(r.createdAt)),
      )
      .filter(
        (r, index, all) =>
          all.findIndex((item) => item.observationId === r.observationId) === index,
      );
  } catch {
    return [];
  }
}
export function filterObservations(
  items: Observation[],
  query: string,
  status: string,
  reviews: Review[],
) {
  const normalized = query.trim().toLocaleLowerCase('ru-RU');
  return items.filter(
    (o) =>
      (!normalized ||
        [o.id, o.title, o.zone, o.camera, o.stage]
          .join(' ')
          .toLocaleLowerCase('ru-RU')
          .includes(normalized)) &&
      (status === 'all' ||
        (status === 'reviewed'
          ? reviews.some((r) => r.observationId === o.id)
          : o.assessment === status)),
  );
}
