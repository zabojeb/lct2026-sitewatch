/** Browser-only scenario simulator, NOT the production domain/rules service.
 * Inputs are authored fixtures or explicit operator input. Never use as an API fallback.
 */
import type { Assessment, Detection, Observation } from './data';

export const equipment = {
  excavator: 'Экскаватор',
  truck: 'Самосвал',
  crane: 'Башенный кран',
  mixer: 'Автобетоносмеситель',
  pump: 'Бетононасос',
  loader: 'Погрузчик',
} as const;
export type Equipment = keyof typeof equipment;
export type Stage = {
  id: string;
  name: string;
  start: string;
  end: string;
  required: Equipment[];
  possible: Equipment[];
  requiredCounts: Partial<Record<Equipment, number>>;
  maxCounts: Partial<Record<Equipment, number>>;
  ruleSources: Partial<Record<Equipment, string>>;
  source: string;
  observable: boolean;
  progress: number | null;
  previousProgress: number | null;
  progressDate: string;
  previousDate: string;
  progressSource: string;
  progressTime: string;
  previousTime: string;
  actualStart: string;
  actualEnd: string;
};
export type Zone = {
  id: string;
  name: string;
  camera: string;
  stageId: string;
  adjacent: string[];
  coverage: number;
  bounds: [number, number, number, number];
};
export type ManualObservation = {
  counts: Partial<Record<Equipment, number>>;
  equipmentZones: Partial<Record<Equipment, string>>;
  stationaryMinutes: Partial<Record<Equipment, number>>;
  source: string;
};
export type Workspace = {
  version: 2;
  interval: number;
  stages: Stage[];
  zones: Zone[];
  manualObservations: Record<string, ManualObservation>;
};
export const workspaceKey = 'sitewatch.demo.workspace.v1';
export const asOf = '2026-09-19';
export const scenarios = [
  {
    id: 'original',
    name: 'Исходный кадр',
    detail: 'Ручная разметка иллюстрации. Без временных выводов.',
  },
  {
    id: 'extra',
    name: 'Неожиданная техника',
    detail: 'Вход симулятора: экскаватор и автобетоносмеситель.',
  },
  {
    id: 'overlap',
    name: 'Соседние этапы',
    detail: 'Вход симулятора: экскаватор и кран. Соседство задаётся в зонах.',
  },
  {
    id: 'hidden',
    name: 'Неполный обзор',
    detail: 'Вход симулятора: видна только треть рабочей зоны.',
  },
  {
    id: 'stationary',
    name: 'Без перемещения',
    detail: 'Две условные позиции одного объекта через 20 минут.',
  },
  { id: 'jump', name: 'Скачок готовности', detail: 'Условные отметки: 40% → 80% за одну минуту.' },
  {
    id: 'wrong_zone',
    name: 'За границей зоны',
    detail: 'Условная позиция объекта на схеме вне назначенной зоны.',
  },
] as const;
export type Scenario = (typeof scenarios)[number]['id'];
export type Finding = {
  code: string;
  title: string;
  expected: string;
  observed: string;
  level: 'warning' | 'unknown' | 'info';
};
export type Analysis = {
  assessment: Assessment;
  findings: Finding[];
  missing: string[];
  extra: string[];
  alternatives: string[];
  overlap: string[];
  required: string[];
  possible: string[];
  detected: string[];
  observedCounts: Partial<Record<Equipment, number>>;
  likelyAlternative: string | null;
  manualOverride: boolean;
  manualSource: string | null;
  coverage: number;
  stage: Stage;
  zone: Zone;
};
const emptyProgress = {
  progress: null,
  previousProgress: null,
  progressDate: asOf,
  previousDate: '2026-09-16',
  progressSource: '',
  progressTime: '23:59',
  previousTime: '23:59',
  actualStart: '',
  actualEnd: '',
};
export function defaults(siteId: string): Workspace {
  return {
    version: 2,
    interval: 20,
    manualObservations: {},
    stages: [
      {
        id: 'excavation',
        name: 'Разработка котлована',
        start: '2026-09-14',
        end: '2026-09-22',
        required: ['excavator', 'truck'],
        possible: ['loader'],
        requiredCounts: { excavator: 1, truck: 1 },
        maxCounts: {},
        ruleSources: {},
        source: 'Демо-методика команды. Сопоставление с ГЭСН требует проверки и точной ссылки.',
        observable: true,
        ...emptyProgress,
      },
      {
        id: 'assembly',
        name: 'Монтаж конструкций',
        start: '2026-09-18',
        end: '2026-09-27',
        required: ['crane'],
        possible: ['truck', 'mixer', 'pump'],
        requiredCounts: { crane: 1 },
        maxCounts: {},
        ruleSources: {},
        source: 'Демо-методика команды. Не утверждённый норматив.',
        observable: true,
        ...emptyProgress,
      },
      {
        id: 'utilities',
        name: 'Инженерные сети',
        start: '2026-09-18',
        end: '2026-09-30',
        required: [],
        possible: [],
        requiredCounts: {},
        maxCounts: {},
        ruleSources: {},
        source: 'Перечень не установлен. Требуются внутренний ракурс или документы.',
        observable: false,
        ...emptyProgress,
      },
    ],
    zones:
      siteId === 'north'
        ? [
            {
              id: 'pit',
              name: 'Котлован, секция Б',
              camera: 'Камера 01',
              stageId: 'excavation',
              adjacent: [],
              coverage: 90,
              bounds: [0.06, 0.42, 0.43, 0.48],
            },
            {
              id: 'building',
              name: 'Корпус А',
              camera: 'Камера 02',
              stageId: 'assembly',
              adjacent: [],
              coverage: 95,
              bounds: [0.51, 0.17, 0.43, 0.53],
            },
            {
              id: 'inside',
              name: 'Внутренний контур',
              camera: 'Камера 03',
              stageId: 'utilities',
              adjacent: [],
              coverage: 0,
              bounds: [0.57, 0.74, 0.31, 0.19],
            },
          ]
        : [
            {
              id: 'building',
              name: 'Корпус В',
              camera: 'Камера 01',
              stageId: 'assembly',
              adjacent: [],
              coverage: 95,
              bounds: [0.32, 0.15, 0.57, 0.53],
            },
            {
              id: 'inside',
              name: 'Подземный паркинг',
              camera: 'Камера 02',
              stageId: 'utilities',
              adjacent: [],
              coverage: 0,
              bounds: [0.08, 0.71, 0.6, 0.2],
            },
          ],
  };
}
export function validDate(value: string): boolean {
  return (
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value
  );
}
const validTime = (value: string) => /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
const validLocalDateTime = (value: string) =>
  /^\d{4}-\d{2}-\d{2}T([01]\d|2[0-3]):[0-5]\d$/.test(value) && validDate(value.slice(0, 10));
export function validateWorkspace(w: Workspace): string {
  if (!w || w.version !== 2 || !Number.isInteger(w.interval) || w.interval < 1 || w.interval > 1440)
    return 'Интервал должен быть целым числом от 1 до 1440 минут.';
  if (
    !Array.isArray(w.stages) ||
    w.stages.length !== 3 ||
    !Array.isArray(w.zones) ||
    !w.zones.length
  )
    return 'Некорректный состав плана.';
  if (
    new Set(w.stages.map((s) => s.id)).size !== w.stages.length ||
    new Set(w.zones.map((z) => z.id)).size !== w.zones.length
  )
    return 'Идентификаторы должны быть уникальны.';
  for (const s of w.stages) {
    if (
      !s.name?.trim() ||
      s.name.length > 120 ||
      !validDate(s.start) ||
      !validDate(s.end) ||
      s.end < s.start
    )
      return 'Укажите корректные даты: окончание не раньше начала.';
    if (
      typeof s.observable !== 'boolean' ||
      typeof s.source !== 'string' ||
      !s.source.trim() ||
      s.source.length > 1000
    )
      return 'Укажите основание правил (до 1000 символов).';
    if (
      ![s.required, s.possible].every(
        (a) =>
          Array.isArray(a) &&
          new Set(a).size === a.length &&
          a.every((e) => Object.hasOwn(equipment, e)),
      ) ||
      s.required.some((e) => s.possible.includes(e))
    )
      return 'Техника не может быть одновременно обязательной и возможной.';
    if (
      !s.requiredCounts ||
      typeof s.requiredCounts !== 'object' ||
      Object.entries(s.requiredCounts).some(
        ([key, count]) =>
          !s.required.includes(key as Equipment) ||
          !Number.isInteger(count) ||
          count < 1 ||
          count > 99,
      ) ||
      s.required.some((e) => !Number.isInteger(s.requiredCounts[e]))
    )
      return 'Для обязательной техники укажите количество от 1 до 99.';
    if (
      !s.ruleSources ||
      typeof s.ruleSources !== 'object' ||
      Object.entries(s.ruleSources).some(
        ([key, source]) =>
          !Object.hasOwn(equipment, key) || typeof source !== 'string' || source.length > 500,
      )
    )
      return 'Проверьте ссылки на источники требований к технике.';
    if (
      !s.maxCounts ||
      typeof s.maxCounts !== 'object' ||
      Object.entries(s.maxCounts).some(
        ([key, count]) =>
          ![...s.required, ...s.possible].includes(key as Equipment) ||
          !Number.isInteger(count) ||
          count < (s.requiredCounts[key as Equipment] ?? 1) ||
          count > 99,
      )
    )
      return 'Максимальное количество должно быть не меньше минимума и не больше 99.';
    if (
      ![s.progress, s.previousProgress].every(
        (p) => p === null || (typeof p === 'number' && Number.isFinite(p) && p >= 0 && p <= 100),
      )
    )
      return 'Готовность должна быть от 0 до 100%.';
    if (
      !validDate(s.progressDate) ||
      !validDate(s.previousDate) ||
      !validTime(s.progressTime) ||
      !validTime(s.previousTime) ||
      `${s.previousDate}T${s.previousTime}` >= `${s.progressDate}T${s.progressTime}`
    )
      return 'Предыдущий замер должен быть раньше текущего.';
    if (
      (s.actualStart && !validLocalDateTime(s.actualStart)) ||
      (s.actualEnd && (!validLocalDateTime(s.actualEnd) || !s.actualStart)) ||
      (s.actualEnd && s.actualEnd < s.actualStart)
    )
      return 'Проверьте фактическое начало и окончание этапа.';
    if (
      typeof s.progressSource !== 'string' ||
      s.progressSource.length > 500 ||
      ((s.progress !== null || s.previousProgress !== null || s.actualStart || s.actualEnd) &&
        !s.progressSource.trim())
    )
      return 'Для готовности укажите источник: акт, замер или демо-ввод.';
  }
  for (const z of w.zones) {
    if (
      !z.name?.trim() ||
      z.name.length > 120 ||
      !z.camera?.trim() ||
      z.camera.length > 120 ||
      !w.stages.some((s) => s.id === z.stageId) ||
      !Array.isArray(z.adjacent) ||
      z.adjacent.some((id) => id === z.stageId || !w.stages.some((s) => s.id === id))
    )
      return 'Проверьте название зоны и назначенные этапы.';
    if (!Number.isFinite(z.coverage) || z.coverage < 0 || z.coverage > 100)
      return 'Обзор должен быть от 0 до 100%.';
    if (
      !Array.isArray(z.bounds) ||
      z.bounds.length !== 4 ||
      !z.bounds.every((n) => Number.isFinite(n) && n >= 0 && n <= 1) ||
      z.bounds[2] < 0.05 ||
      z.bounds[3] < 0.05 ||
      z.bounds[0] + z.bounds[2] > 1.000001 ||
      z.bounds[1] + z.bounds[3] > 1.000001
    )
      return 'Границы зоны должны помещаться в схеме (минимум 5% по каждой стороне).';
  }
  if (!w.manualObservations || typeof w.manualObservations !== 'object')
    return 'Некорректные ручные наблюдения.';
  for (const [id, observation] of Object.entries(w.manualObservations)) {
    if (
      !id ||
      id.length > 120 ||
      !observation ||
      typeof observation.source !== 'string' ||
      !observation.source.trim() ||
      observation.source.length > 500 ||
      !observation.counts ||
      !observation.equipmentZones ||
      !observation.stationaryMinutes
    )
      return 'Для ручного наблюдения укажите источник и корректные данные.';
    if (
      Object.entries(observation.counts).some(
        ([key, count]) =>
          !Object.hasOwn(equipment, key) || !Number.isInteger(count) || count < 0 || count > 99,
      )
    )
      return 'Ручное количество техники должно быть от 0 до 99.';
    if (
      Object.entries(observation.equipmentZones).some(
        ([key, zoneId]) =>
          !Object.hasOwn(equipment, key) || !w.zones.some((zone) => zone.id === zoneId),
      )
    )
      return 'Проверьте ручную привязку техники к зоне.';
    if (
      Object.entries(observation.stationaryMinutes).some(
        ([key, minutes]) =>
          !Object.hasOwn(equipment, key) ||
          !Number.isInteger(minutes) ||
          minutes < 0 ||
          minutes > 1440,
      )
    )
      return 'Период без перемещения должен быть от 0 до 1440 минут.';
  }
  return '';
}
export function upgradeWorkspace(value: unknown): Workspace {
  const w = value as Omit<Workspace, 'version'> & { version: number };
  if (!w || (w.version !== 1 && w.version !== 2) || !Array.isArray(w.stages))
    throw new Error('Некорректная версия плана.');
  if (w.version === 2)
    return {
      ...w,
      manualObservations: w.manualObservations ?? {},
      stages: w.stages.map((stage) => ({ ...stage, maxCounts: stage.maxCounts ?? {} })),
    } as Workspace;
  return {
    ...w,
    version: 2,
    manualObservations: {},
    stages: w.stages.map((stage) => ({
      ...stage,
      requiredCounts: Object.fromEntries((stage.required || []).map((key) => [key, 1])),
      maxCounts: {},
      ruleSources: {},
      progressTime: '23:59',
      previousTime: '23:59',
      actualStart: '',
      actualEnd: '',
    })),
  };
}
export function parseWorkspace(raw: string | null, siteId: string): Workspace {
  try {
    const w = upgradeWorkspace(JSON.parse(raw || 'null'));
    const baseline = defaults(siteId);
    if (
      !w ||
      validateWorkspace(w) ||
      w.stages.some((s) => !baseline.stages.some((b) => b.id === s.id)) ||
      w.zones.length !== baseline.zones.length ||
      w.zones.some((z) => !baseline.zones.some((b) => b.id === z.id))
    )
      return baseline;
    return w;
  } catch {
    return defaults(siteId);
  }
}
export function stageFor(w: Workspace, o: Observation): { stage: Stage; zone: Zone } {
  const zone = w.zones.find((z) => z.camera === o.camera) || w.zones[0];
  return { zone, stage: w.stages.find((s) => s.id === zone.stageId)! };
}
export function scenarioEquipment(o: Observation, scenario: Scenario): Equipment[] {
  if (scenario === 'extra') return ['excavator', 'mixer'];
  if (scenario === 'overlap') return ['excavator', 'crane'];
  return o.detections.flatMap((d) =>
    (Object.keys(equipment) as Equipment[]).filter((k) => equipment[k] === d.label),
  );
}
export function analyze(o: Observation, w: Workspace, scenario: Scenario = 'original'): Analysis {
  const { stage, zone } = stageFor(w, o);
  const manual = scenario === 'original' ? w.manualObservations[o.id] : undefined;
  const detected = manual
    ? (Object.keys(equipment) as Equipment[]).flatMap((key) =>
        Array.from({ length: manual.counts[key] ?? 0 }, () => key),
      )
    : scenarioEquipment(o, scenario);
  const observedCounts = Object.fromEntries(
    (Object.keys(equipment) as Equipment[]).map((key) => [
      key,
      detected.filter((item) => item === key).length,
    ]),
  ) as Record<Equipment, number>;
  const date = o.time.slice(0, 10);
  const active = w.stages.filter((s) => s.id !== stage.id && s.start <= date && s.end >= date);
  const neighbors = active.filter((s) => zone.adjacent.includes(s.id));
  const allowed = [...stage.required, ...stage.possible];
  const neighborEquipment = neighbors.flatMap((s) => [...s.required, ...s.possible]);
  const missing = stage.required.filter((e) => !detected.includes(e)).map((e) => equipment[e]);
  const shortages = stage.required.filter(
    (e) => observedCounts[e] > 0 && observedCounts[e] < (stage.requiredCounts[e] ?? 1),
  );
  const excess = [...stage.required, ...stage.possible].filter(
    (key) => stage.maxCounts[key] !== undefined && observedCounts[key] > stage.maxCounts[key],
  );
  const extra = [...new Set(detected)]
    .filter((e) => !allowed.includes(e) && !neighborEquipment.includes(e))
    .map((e) => equipment[e]);
  const overlap = neighbors
    .filter((s) =>
      detected.some((e) => !allowed.includes(e) && [...s.required, ...s.possible].includes(e)),
    )
    .map((s) => s.name);
  const alternatives = w.stages
    .filter(
      (s) =>
        s.id !== stage.id &&
        s.observable &&
        detected.some((e) => !allowed.includes(e) && [...s.required, ...s.possible].includes(e)),
    )
    .map((s) => s.name);
  const fit = (s: Stage) => {
    const expected = [...s.required, ...s.possible];
    return (
      s.required.reduce(
        (score, key) => score + Math.min(1, observedCounts[key] / (s.requiredCounts[key] ?? 1)),
        0,
      ) -
      s.required.filter((key) => !observedCounts[key]).length -
      [...new Set(detected)].filter((key) => !expected.includes(key)).length
    );
  };
  const likelyAlternative =
    w.stages
      .filter(
        (candidate) =>
          candidate.id !== stage.id && candidate.observable && candidate.required.length,
      )
      .map((candidate) => ({ candidate, score: fit(candidate) }))
      .filter(({ score }) => score > fit(stage) && score > 0)
      .sort((a, b) => b.score - a.score)[0]?.candidate.name ?? null;
  const coverage = scenario === 'hidden' ? 30 : zone.coverage;
  const findings: Finding[] = [];
  const add = (
    code: string,
    title: string,
    expected: string,
    observed: string,
    level: Finding['level'] = 'warning',
  ) => findings.push({ code, title, expected, observed, level });
  const unknown =
    !stage.observable || coverage < 80 || (!stage.required.length && !stage.possible.length);
  if (!stage.observable)
    add(
      'visibility_required',
      'Этап вне визуального контроля',
      'Наблюдаемая рабочая зона',
      'Система не делает вывод о соответствии или нарушении.',
      'unknown',
    );
  else if (coverage < 80)
    add(
      'coverage_required',
      'Неполный обзор площадки',
      'Минимум 80% по демо-правилу',
      `Видно ${coverage}%. Запросите дополнительный ракурс.`,
      'unknown',
    );
  else if (!stage.required.length && !stage.possible.length)
    add(
      'rule_missing',
      'Перечень техники не установлен',
      'Проверенная методика этапа',
      'Отсутствие требований не означает соответствие.',
      'unknown',
    );
  else {
    if (missing.length)
      add(
        'required_equipment',
        'Обязательная техника не наблюдается',
        stage.required.map((e) => `${equipment[e]} ≥ ${stage.requiredCounts[e] ?? 1}`).join(', '),
        missing.join(', ') + '. Это сигнал для проверки, не доказательство отсутствия.',
      );
    for (const key of shortages)
      add(
        'equipment_shortage',
        'Техники меньше плана',
        `${equipment[key]} ≥ ${stage.requiredCounts[key] ?? 1}; основание: ${stage.ruleSources[key] || stage.source}`,
        `${equipment[key]}: ${observedCounts[key]} в демонстрационном кадре. Нужна повторная проверка.`,
      );
    for (const key of excess)
      add(
        'equipment_excess',
        'Техники больше допустимого количества',
        `${equipment[key]} ≤ ${stage.maxCounts[key]}; основание: ${stage.ruleSources[key] || stage.source}`,
        `${equipment[key]}: ${observedCounts[key]} в демонстрационном кадре.`,
      );
    if (extra.length)
      add(
        'unexpected_equipment',
        'Техника вне перечня этапа',
        allowed.map((e) => equipment[e]).join(', '),
        extra.join(', '),
      );
    if (overlap.length)
      add(
        'adjacent_stage',
        'Учтены соседние этапы',
        'Явно разрешённые пересекающиеся этапы',
        overlap.join(', '),
        'info',
      );
  }
  if (date < stage.start || date > stage.end)
    add('schedule_window', 'Снимок вне сроков этапа', `${stage.start} — ${stage.end}`, date);
  if (!unknown && likelyAlternative)
    add(
      'alternate_stage_candidate',
      'Возможен другой этап работ',
      `По графику и зоне: ${stage.name}`,
      `Набор техники лучше совпадает с этапом «${likelyAlternative}». Гипотеза, оператор должен проверить по актам и кадрам.`,
      'info',
    );
  if (scenario === 'wrong_zone')
    add(
      'equipment_zone',
      'Объект за границей рабочей зоны',
      zone.name,
      'Условная позиция вне назначенной зоны. Нужна проверка геопривязки.',
    );
  if (manual && !unknown) {
    for (const key of Object.keys(equipment) as Equipment[]) {
      const actualZone = manual.equipmentZones[key];
      if (observedCounts[key] > 0 && actualZone && actualZone !== zone.id)
        add(
          'equipment_zone',
          'Техника находится не в назначенной зоне',
          `${equipment[key]}: ${zone.name}`,
          `Оператор указал зону «${w.zones.find((item) => item.id === actualZone)?.name}»; источник: ${manual.source}.`,
        );
      const stationary = manual.stationaryMinutes[key];
      if (observedCounts[key] > 0 && stationary !== undefined && stationary >= 60)
        add(
          'possible_idle_equipment',
          'Возможный застой техники',
          `Подтверждённая работа ${equipment[key]} в зоне`,
          `По ручному наблюдению нет перемещения ${stationary} мин; источник: ${manual.source}. Не доказывает простой: возможна работа на месте.`,
        );
    }
  }
  if (scenario === 'stationary')
    add(
      'position_unchanged',
      'Положение не изменилось',
      'Сопоставимые кадры одного объекта',
      'Демо-трек: 0 смещения за 20 минут. Неподвижность не доказывает простой.',
      'info',
    );
  if (scenario === 'jump')
    add(
      'temporal_consistency',
      'Неправдоподобное изменение',
      'Согласованные замеры готовности во времени',
      'Демо: +40 п.п. за 1 минуту. Проверьте время и источник оценки.',
    );
  return {
    assessment: unknown
      ? 'insufficient_evidence'
      : findings.some((f) => f.level === 'warning')
        ? 'needs_attention'
        : 'consistent',
    findings,
    missing,
    extra,
    overlap,
    alternatives,
    coverage,
    stage,
    zone,
    detected: detected.map((e) => equipment[e]),
    observedCounts,
    likelyAlternative: unknown ? null : likelyAlternative,
    manualOverride: Boolean(manual),
    manualSource: manual?.source ?? null,
    required: stage.required.map(
      (e) =>
        `${equipment[e]} ≥ ${stage.requiredCounts[e] ?? 1}${stage.maxCounts[e] === undefined ? '' : `, ≤ ${stage.maxCounts[e]}`}`,
    ),
    possible: stage.possible.map(
      (e) => `${equipment[e]}${stage.maxCounts[e] === undefined ? '' : ` ≤ ${stage.maxCounts[e]}`}`,
    ),
  };
}
export function projectObservation(o: Observation, w: Workspace): Observation {
  const a = analyze(o, w);
  return {
    ...o,
    assessment: a.assessment,
    stage: a.stage.name,
    zone: a.zone.name,
    title:
      a.assessment === 'insufficient_evidence'
        ? a.findings.find((f) => f.level === 'unknown')?.title || 'Недостаточно данных для оценки'
        : a.missing.length
          ? `${a.missing.join(', ')} не наблюдается`
          : a.findings.find((f) => f.level === 'warning')?.title ||
            'Техника согласуется с правилами',
    detections: markedDetections(o, a),
    rule: a.findings.map((f) => f.code).join(' / ') || 'equipment_matches',
    expected: a.required.length
      ? `Обязательная: ${a.required.join(', ')}. Возможная: ${a.possible.join(', ') || 'не задана'}.`
      : 'Обязательный перечень не задан.',
    observed: a.detected.join(', ') || 'Техника не наблюдается.',
    explanation:
      a.findings.map((f) => `${f.title}: ${f.observed}`).join(' ') ||
      'Набор техники согласуется с локально заданными правилами. Это не подтверждение сроков или объёма работ.',
  };
}
export function markedDetections(o: Observation, a: Analysis): Detection[] {
  return o.detections.map((d) => ({
    ...d,
    unexpected:
      !a.manualOverride && a.assessment !== 'insufficient_evidence' && a.extra.includes(d.label),
  }));
}
export function progressEstimate(s: Stage) {
  const day = 86400000;
  const start = Date.parse(`${s.start}T00:00:00+03:00`);
  const endExclusive = Date.parse(`${s.end}T00:00:00+03:00`) + day;
  const measuredAt = Date.parse(`${s.progressDate}T${s.progressTime}:00+03:00`);
  const previousAt = Date.parse(`${s.previousDate}T${s.previousTime}:00+03:00`);
  const duration = (endExclusive - start) / day;
  const elapsed = (measuredAt - start) / day;
  const planned = Math.round(Math.max(0, Math.min(100, (elapsed / duration) * 100)));
  const delta = s.progress === null ? null : Math.round((s.progress - planned) * 10) / 10;
  const varianceHours =
    s.progress === null
      ? null
      : Math.round(((measuredAt - (start + (s.progress / 100) * duration * day)) / 3600000) * 10) /
        10;
  const days = (measuredAt - previousAt) / day;
  const rate =
    s.progress !== null && s.previousProgress !== null && days > 0
      ? (s.progress - s.previousProgress) / days
      : null;
  const remaining =
    rate !== null && rate > 0 && s.progress !== null ? Math.ceil((100 - s.progress) / rate) : null;
  const finish =
    remaining !== null && remaining <= 36500
      ? new Date(measuredAt + remaining * day).toISOString().slice(0, 10)
      : null;
  const delay = finish ? Math.round((Date.parse(finish) - Date.parse(s.end)) / day) : null;
  const actualDurationHours =
    s.actualStart && s.actualEnd
      ? Math.round(
          ((Date.parse(`${s.actualEnd}:00+03:00`) - Date.parse(`${s.actualStart}:00+03:00`)) /
            3600000) *
            10,
        ) / 10
      : null;
  const actualFinishVarianceHours = s.actualEnd
    ? Math.round(((Date.parse(`${s.actualEnd}:00+03:00`) - endExclusive) / 3600000) * 10) / 10
    : null;
  return {
    planned,
    delta,
    varianceHours,
    plannedDurationHours: duration * 24,
    actualDurationHours,
    actualFinishVarianceHours,
    rate,
    finish,
    delay,
  };
}
export function formatVariance(hours: number | null): string {
  if (hours === null) return 'Не оценивается без замера готовности';
  if (Math.abs(hours) < 0.05) return 'В срок по линейному плану';
  const magnitude = Math.abs(hours);
  const days = Math.floor(magnitude / 24);
  const remainder = Math.round((magnitude - days * 24) * 10) / 10;
  return `${hours > 0 ? 'Отставание' : 'Опережение'} на ${days ? `${days} дн. ` : ''}${remainder ? `${remainder} ч` : ''}`.trim();
}
export function summary(o: Observation, a: Analysis, scenario: Scenario): string {
  const p = progressEstimate(a.stage);
  return [
    `SiteWatch · ДЕМО · ${o.id} · ${o.time}`,
    `Сценарий: ${scenarios.find((s) => s.id === scenario)?.name}. Иллюстрации и разметка синтетические.`,
    `${a.zone.name} / ${a.stage.name}. Обзор: ${a.coverage}%.`,
    `Правило: ${a.stage.source}`,
    `Ожидается: ${a.required.join(', ') || 'перечень не установлен'}. Обнаружено: ${a.detected.join(', ') || 'нет объектов'}.`,
    ...(a.manualSource
      ? [`Количество, зоны и движение уточнены вручную. Источник: ${a.manualSource}.`]
      : []),
    ...a.findings.map((f) => `[${f.code}] ${f.title}. ${f.observed}`),
    ...(a.alternatives.length
      ? [`Альтернативный контекст: ${a.alternatives.join(', ')}. Это не классификация этапа.`]
      : []),
    `Готовность: ${a.stage.progress === null ? 'нет замеров' : `${a.stage.progress}% (${a.stage.progressSource})`}.`,
    `Расхождение по времени: ${formatVariance(p.varianceHours)}. Плановая длительность: ${p.plannedDurationHours} ч.`,
    ...(p.actualDurationHours !== null
      ? [
          `Фактическая длительность: ${p.actualDurationHours} ч; отклонение окончания: ${formatVariance(p.actualFinishVarianceHours)}.`,
        ]
      : []),
    ...(p.finish ? [`Линейный сценарий завершения: ${p.finish}. Не ML-прогноз.`] : []),
    'Следующий шаг: проверить дополнительные кадры, график и основание правил. Один кадр не доказывает нарушение.',
    'Сводка составлена шаблоном по указанным данным. LLM/VLM не подключены. Уведомление не отправлено.',
  ].join('\n');
}
