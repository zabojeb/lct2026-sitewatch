import { expect, test } from '@playwright/test';
import { observations } from '../src/lib/demo/data';
import {
  defaults,
  analyze,
  validateWorkspace,
  parseWorkspace,
  progressEstimate,
  summary,
  projectObservation,
  workspaceKey,
} from '../src/lib/demo/workspace';

test('demo rules retain evidence, handle overlaps and never judge invisible stages', () => {
  const w = defaults('north');
  expect(validateWorkspace(w)).toBe('');
  const missing = analyze(observations[0], w);
  expect(missing.missing).toEqual(['Самосвал']);
  expect(missing.assessment).toBe('needs_attention');
  expect(missing.findings.every((f) => f.code && f.expected && f.observed)).toBe(true);
  expect(analyze(observations[0], w, 'hidden').assessment).toBe('insufficient_evidence');
  expect(analyze(observations[2], w).assessment).toBe('insufficient_evidence');
  expect(analyze(observations[0], w, 'extra').extra).toEqual(['Автобетоносмеситель']);
  expect(analyze(observations[0], w, 'overlap').extra).toEqual(['Башенный кран']);
  w.zones[0].adjacent = ['assembly'];
  const overlapping = analyze(observations[0], w, 'overlap');
  expect(overlapping.extra).toEqual([]);
  expect(overlapping.overlap).toEqual(['Монтаж конструкций']);
  w.stages[1].start = '2026-09-20';
  expect(analyze(observations[0], w, 'overlap').extra).toEqual(['Башенный кран']);
  w.stages[0].required = [];
  w.stages[0].possible = [];
  expect(analyze(observations[0], w).assessment).toBe('insufficient_evidence');
});

test('validation rejects corrupt persistence, bounds, dates and conflicting requirements', () => {
  for (const raw of ['{bad', 'null', '{}', '{"version":1}', '[]'])
    expect(parseWorkspace(raw, 'north')).toEqual(defaults('north'));
  const w = defaults('north');
  w.stages[0].possible.push('excavator');
  expect(validateWorkspace(w)).toContain('одновременно');
  w.stages[0].possible = [];
  w.stages[0].end = '2026-02-30';
  expect(validateWorkspace(w)).toContain('даты');
  w.stages[0].end = '2026-09-22';
  w.zones[0].bounds = [0.9, 0, 0.5, 0.5];
  expect(validateWorkspace(w)).toContain('Границы');
  expect(parseWorkspace(JSON.stringify(w), 'north')).toEqual(defaults('north'));
  expect(parseWorkspace(JSON.stringify(defaults('river')), 'north')).toEqual(defaults('north'));
});

test('progress is sourced manual input and forecasts require positive measured change', () => {
  const w = defaults('north');
  const s = w.stages[0];
  expect(progressEstimate(s).delta).toBeNull();
  expect(progressEstimate(s).finish).toBeNull();
  s.progress = 50;
  s.previousProgress = 20;
  expect(validateWorkspace(w)).toContain('источник');
  s.progressSource = 'Демонстрационный акт';
  expect(progressEstimate(s)).toMatchObject({
    planned: 67,
    delta: -17,
    rate: 10,
    finish: '2026-09-24',
    delay: 2,
  });
  s.progress = 80;
  expect(progressEstimate(s).delta).toBe(13);
  s.previousProgress = 80;
  expect(progressEstimate(s).finish).toBeNull();
  s.previousProgress = 90;
  expect(progressEstimate(s).finish).toBeNull();
  const report = summary(observations[0], analyze(observations[0], w), 'original');
  expect(report).toContain('LLM/VLM не подключены');
  expect(report).toContain('Уведомление не отправлено');
});

test('plan edits recalculate observations, persist and stay isolated by site', async ({ page }) => {
  await page.goto('/app?view=schedule');
  await page.getByLabel('Самосвал: требование').selectOption('possible');
  await page.getByLabel('Интервал снимков, мин').fill('30');
  await page.getByRole('button', { name: 'Применить план', exact: true }).click();
  await expect(page.getByText('План применён. Разбор наблюдений пересчитан.')).toBeVisible();
  await page.getByRole('button', { name: 'Обзор', exact: true }).click();
  await expect(page.getByRole('button', { name: /Требуют внимания 00/ })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Самосвал: требование')).toHaveValue('possible');
  await expect(page.getByLabel('Интервал снимков, мин')).toHaveValue('30');
  await page.getByLabel('Площадка', { exact: true }).selectOption('river');
  await expect(page.getByLabel('Интервал снимков, мин')).toHaveValue('20');
  await expect(page.getByLabel('Самосвал: требование')).toHaveValue('required');
});

test('manual progress, summary, provenance and local alert work', async ({ page }) => {
  await page.goto('/app?view=schedule');
  await page.getByText('Замеры готовности и сценарий завершения', { exact: true }).click();
  await page.getByLabel('Предыдущая готовность, %', { exact: true }).fill('20');
  await page.getByLabel('Текущая готовность, %', { exact: true }).fill('50');
  await page.getByLabel('Источник готовности', { exact: true }).fill('Демонстрационный акт');
  await page.getByRole('button', { name: 'Применить план', exact: true }).click();
  await page.getByRole('button', { name: 'Аналитика', exact: true }).click();
  await expect(page.getByText('Отставание 17 п.п.', { exact: true })).toBeVisible();
  await expect(page.getByText('2026-09-24', { exact: true })).toBeVisible();
  await page.getByText('Источник правил и показателей', { exact: true }).click();
  await expect(page.locator('.method-detail').getByText(/ГЭСН требует проверки/)).toBeVisible();
  await page.getByText('Итоговая сводка и черновик алерта', { exact: true }).click();
  await page.getByRole('button', { name: 'Подготовить алерт', exact: true }).click();
  await expect(page.getByText('Черновик для прораба · не отправлен')).toBeVisible();
  await expect(page.locator('.summary-panel pre')).toContainText('Не ML-прогноз');
});

test('zones change visibility, stage and overlap rules with validated bounds', async ({ page }) => {
  await page.goto('/app?view=zones');
  await page.getByLabel('Видимость зоны, %').fill('30');
  await page.getByRole('button', { name: 'Сохранить зону' }).click();
  await page.getByRole('button', { name: 'Аналитика', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Неполный обзор площадки' })).toBeVisible();
  await page.getByRole('button', { name: 'Зоны', exact: true }).click();
  await page.getByLabel('Видимость зоны, %').fill('90');
  await page.getByLabel('Монтаж конструкций', { exact: true }).check();
  await page.getByLabel('Слева', { exact: true }).fill('90');
  await page.getByRole('button', { name: 'Сохранить зону' }).click();
  await expect(page.getByRole('alert')).toContainText('Границы');
  await page.getByLabel('Слева', { exact: true }).fill('6');
  await page.getByRole('button', { name: 'Сохранить зону' }).click();
  await page.getByRole('button', { name: 'Сценарии', exact: true }).click();
  await page.getByRole('button', { name: /Соседние этапы Вход/ }).click();
  await expect(page.getByRole('heading', { name: 'Учтены соседние этапы' })).toBeVisible();
});

test('all scenarios show authored inputs; repeated images never become real motion evidence', async ({
  page,
}) => {
  await page.goto('/app?view=scenarios');
  await page.getByRole('button', { name: /Неожиданная техника Вход/ }).click();
  await expect(page.locator('.signal-red')).toHaveText('Автобетоносмеситель');
  await page.getByRole('button', { name: /Неполный обзор Вход/ }).click();
  await expect(page.getByRole('heading', { name: 'Неполный обзор площадки' })).toBeVisible();
  await page.getByRole('button', { name: /Без перемещения Две/ }).click();
  await expect(
    page.locator('.finding').getByText(/Неподвижность не доказывает простой/),
  ).toBeVisible();
  await page.getByRole('button', { name: /Скачок готовности Условные/ }).click();
  await expect(page.getByRole('heading', { name: 'Неправдоподобное изменение' })).toBeVisible();
  await page.getByRole('button', { name: /За границей зоны Условная/ }).click();
  await expect(
    page.getByRole('heading', { name: 'Объект за границей рабочей зоны' }),
  ).toBeVisible();
});

test('plan JSON preview/import and report export include configuration and evidence', async ({
  page,
}) => {
  await page.goto('/app?view=schedule');
  await page.getByRole('button', { name: 'Импорт JSON' }).click();
  await page.getByLabel('План JSON').fill('{bad');
  await page.getByRole('button', { name: 'Проверить и загрузить' }).click();
  await expect(page.getByRole('alert')).not.toBeEmpty();
  const workspace = defaults('north');
  workspace.interval = 40;
  await page.getByLabel('План JSON').fill(JSON.stringify(workspace));
  await page.getByRole('button', { name: 'Проверить и загрузить' }).click();
  expect(
    await page.evaluate((key) => localStorage.getItem(key), `${workspaceKey}.north`),
  ).toBeNull();
  await page.getByRole('button', { name: 'Применить план' }).click();
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Экспорт отчёта' }).click();
  const stream = await (await downloaded).createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const report = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  expect(report.workspace.interval).toBe(40);
  expect(report.analyses[0].findings[0].code).toBe('required_equipment');
  expect(report.modelStatus.notifications).toBe('draft_only');
});

test('expanded workspace stays within mobile bounds and emits no runtime errors', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 850 });
    for (const view of ['schedule', 'zones', 'analysis', 'scenarios']) {
      await page.goto(`/app?view=${view}`);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `${width} ${view}`,
      ).toBe(true);
    }
  }
  expect(errors).toEqual([]);
});

test('finding titles and red boxes follow changed requirements rather than stale fixtures', () => {
  const w = defaults('north');
  w.stages[0].required = ['mixer'];
  w.stages[0].possible = [];
  const o = projectObservation(observations[0], w);
  expect(o.title).toBe('Автобетоносмеситель не наблюдается');
  expect(o.detections[0].unexpected).toBe(true);
  w.zones[0].coverage = 30;
  expect(projectObservation(observations[0], w).detections[0].unexpected).toBe(false);
});

test('prior decisions do not suppress signals under a new rule configuration', async ({ page }) => {
  await page.goto('/app');
  await page.getByRole('button', { name: 'Разобрать кадр', exact: true }).click();
  await page.getByLabel('Комментарий', { exact: true }).fill('Проверено по демо-правилу');
  await page.getByRole('button', { name: 'Сохранить решение', exact: true }).click();
  await expect(page.getByRole('button', { name: /Требуют внимания 01/ })).toBeVisible();
  await page.getByRole('button', { name: 'План работ', exact: true }).click();
  await page.getByLabel('Бетононасос: требование').selectOption('required');
  await page.getByRole('button', { name: 'Применить план', exact: true }).click();
  await page.getByRole('button', { name: 'Обзор', exact: true }).click();
  await expect(page.getByRole('button', { name: /Требуют внимания 02/ })).toBeVisible();
  await page.getByRole('button', { name: /Журнал/ }).click();
  await expect(
    page.getByText('Правила изменились после этого решения. Нужна повторная проверка.'),
  ).toBeVisible();
});

test('storage failure is explicit and dataset manifest never claims generated images', async ({
  page,
}) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new Error('storage blocked');
    };
  });
  await page.goto('/app?view=schedule');
  await page.getByLabel('Интервал снимков, мин').fill('25');
  await page.getByRole('button', { name: 'Применить план', exact: true }).click();
  await expect(
    page.getByText('Настройки применены в памяти, но браузер запретил сохранение.'),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Сценарии', exact: true }).click();
  await page.getByText('Разнообразие синтетических данных', { exact: true }).click();
  await page.getByRole('combobox', { name: 'Сезон', exact: true }).selectOption('winter');
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Экспорт задания для датасета' }).click();
  const stream = await (await pending).createReadStream();
  const chunks = [];
  for await (const c of stream) chunks.push(c);
  const manifest = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  expect(manifest.season).toBe('winter');
  expect(manifest.status).toBe('planned_not_generated');
  expect(manifest.scenarios).toHaveLength(7);
});
