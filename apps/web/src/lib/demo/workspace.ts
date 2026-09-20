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
  source: string;
  observable: boolean;
  progress: number | null;
  previousProgress: number | null;
  progressDate: string;
  previousDate: string;
  progressSource: string;
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
export type Workspace = { version: 1; interval: number; stages: Stage[]; zones: Zone[] };
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
};
export function defaults(siteId: string): Workspace {
  return {
    version: 1,
    interval: 20,
    stages: [
      {
        id: 'excavation',
        name: 'Разработка котлована',
        start: '2026-09-14',
        end: '2026-09-22',
        required: ['excavator', 'truck'],
        possible: ['loader'],
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
export function validateWorkspace(w: Workspace): string {
  if (w.version !== 1 || !Number.isInteger(w.interval) || w.interval < 1 || w.interval > 1440)
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
      ![s.progress, s.previousProgress].every(
        (p) => p === null || (typeof p === 'number' && Number.isFinite(p) && p >= 0 && p <= 100),
      )
    )
      return 'Готовность должна быть от 0 до 100%.';
    if (
      !validDate(s.progressDate) ||
      !validDate(s.previousDate) ||
      s.previousDate >= s.progressDate
    )
      return 'Предыдущий замер должен быть раньше текущего.';
    if (
      typeof s.progressSource !== 'string' ||
      s.progressSource.length > 500 ||
      ((s.progress !== null || s.previousProgress !== null) && !s.progressSource.trim())
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
  return '';
}
export function parseWorkspace(raw: string | null, siteId: string): Workspace {
  try {
    const w = JSON.parse(raw || 'null') as Workspace;
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
  const detected = scenarioEquipment(o, scenario);
  const date = o.time.slice(0, 10);
  const active = w.stages.filter((s) => s.id !== stage.id && s.start <= date && s.end >= date);
  const neighbors = active.filter((s) => zone.adjacent.includes(s.id));
  const allowed = [...stage.required, ...stage.possible];
  const neighborEquipment = neighbors.flatMap((s) => [...s.required, ...s.possible]);
  const missing = stage.required.filter((e) => !detected.includes(e)).map((e) => equipment[e]);
  const extra = detected
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
        stage.required.map((e) => equipment[e]).join(', '),
        missing.join(', ') + '. Это сигнал для проверки, не доказательство отсутствия.',
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
  if (scenario === 'wrong_zone')
    add(
      'equipment_zone',
      'Объект за границей рабочей зоны',
      zone.name,
      'Условная позиция вне назначенной зоны. Нужна проверка геопривязки.',
    );
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
    required: stage.required.map((e) => equipment[e]),
    possible: stage.possible.map((e) => equipment[e]),
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
    unexpected: a.assessment !== 'insufficient_evidence' && a.extra.includes(d.label),
  }));
}
export function progressEstimate(s: Stage) {
  const day = 86400000;
  const duration = (Date.parse(s.end) - Date.parse(s.start)) / day + 1;
  const elapsed = (Date.parse(s.progressDate) - Date.parse(s.start)) / day + 1;
  const planned = Math.round(Math.max(0, Math.min(100, (elapsed / duration) * 100)));
  const delta = s.progress === null ? null : Math.round((s.progress - planned) * 10) / 10;
  const days = (Date.parse(s.progressDate) - Date.parse(s.previousDate)) / day;
  const rate =
    s.progress !== null && s.previousProgress !== null && days > 0
      ? (s.progress - s.previousProgress) / days
      : null;
  const remaining =
    rate !== null && rate > 0 && s.progress !== null ? Math.ceil((100 - s.progress) / rate) : null;
  const finish =
    remaining !== null && remaining <= 36500
      ? new Date(Date.parse(s.progressDate) + remaining * day).toISOString().slice(0, 10)
      : null;
  const delay = finish ? Math.round((Date.parse(finish) - Date.parse(s.end)) / day) : null;
  return { planned, delta, rate, finish, delay };
}
export function summary(o: Observation, a: Analysis, scenario: Scenario): string {
  const p = progressEstimate(a.stage);
  return [
    `SiteWatch · ДЕМО · ${o.id} · ${o.time}`,
    `Сценарий: ${scenarios.find((s) => s.id === scenario)?.name}. Иллюстрации и разметка синтетические.`,
    `${a.zone.name} / ${a.stage.name}. Обзор: ${a.coverage}%.`,
    `Правило: ${a.stage.source}`,
    `Ожидается: ${a.required.join(', ') || 'перечень не установлен'}. Обнаружено: ${a.detected.join(', ') || 'нет объектов'}.`,
    ...a.findings.map((f) => `[${f.code}] ${f.title}. ${f.observed}`),
    ...(a.alternatives.length
      ? [`Альтернативный контекст: ${a.alternatives.join(', ')}. Это не классификация этапа.`]
      : []),
    `Готовность: ${a.stage.progress === null ? 'нет замеров' : `${a.stage.progress}% (${a.stage.progressSource})`}.`,
    ...(p.finish ? [`Линейный сценарий завершения: ${p.finish}. Не ML-прогноз.`] : []),
    'Следующий шаг: проверить дополнительные кадры, график и основание правил. Один кадр не доказывает нарушение.',
    'Сводка составлена шаблоном по указанным данным. LLM/VLM не подключены. Уведомление не отправлено.',
  ].join('\n');
}
