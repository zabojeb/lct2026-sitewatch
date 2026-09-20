import { expect, test } from '@playwright/test';
import { observations, parseReviews, filterObservations } from '../src/lib/demo/data';

test('responsive layouts fit small phones, tablets and laptops', async ({ page }) => {
  for (const width of [320, 390, 768, 1024, 1366]) {
    await page.setViewportSize({ width, height: 800 });
    for (const route of ['/', '/app']) {
      await page.goto(route);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
    }
  }
});

test('fixtures and persistence reject malformed data', () => {
  expect(parseReviews('{bad')).toEqual([]);
  expect(parseReviews(JSON.stringify([null, {}, { observationId: 'unknown' }]))).toEqual([]);
  for (const observation of observations) {
    expect(observation.time).toMatch(/Z$/);
    for (const { bbox } of observation.detections) {
      expect(bbox.every((n) => n >= 0 && n <= 1)).toBe(true);
      expect(bbox[0] + bbox[2]).toBeLessThanOrEqual(1);
      expect(bbox[1] + bbox[3]).toBeLessThanOrEqual(1);
    }
  }
  expect(filterObservations(observations, 'самосвал', 'all', []).length).toBe(1);
});

test('landing, tabs and navigation work without page errors', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Вся стройка.В поле зрения.');
  await page.getByRole('button', { name: 'Причина сигнала', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Понимать, что проверить.' })).toBeVisible();
  await page.getByRole('link', { name: 'Открыть пульт', exact: true }).first().click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Северный квартал');
  expect(errors).toEqual([]);
});

test('review validates, persists, updates counters and can be reset', async ({ page }) => {
  await page.goto('/app');
  await page.getByRole('button', { name: 'Разобрать кадр', exact: true }).click();
  await page.getByRole('button', { name: 'Сохранить решение', exact: true }).click();
  await expect(page.getByText('Добавьте комментарий: минимум 3 символа.')).toBeVisible();
  await page
    .getByLabel('Комментарий', { exact: true })
    .fill('Проверить вывоз грунта по дополнительной камере.');
  await page.getByRole('button', { name: 'Сохранить решение', exact: true }).click();
  await expect(page.getByRole('button', { name: /Требуют внимания 01/ })).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: /Журнал/ }).click();
  await expect(
    page.getByText('Проверить вывоз грунта по дополнительной камере.', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Сбросить демо', exact: true }).click();
  await page.getByRole('button', { name: 'Сбросить решения', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Здесь появятся ваши решения' })).toBeVisible();
});

test('search, filters, sites, schedule and local image validation', async ({ page }) => {
  await page.goto('/app');
  await page.getByRole('button', { name: 'Наблюдения', exact: true }).click();
  await page.getByLabel('Поиск по наблюдениям').fill('несуществующая зона');
  await expect(page.getByRole('heading', { name: 'Наблюдений не найдено' })).toBeVisible();
  await page.getByRole('button', { name: 'Сбросить фильтры' }).click();
  await expect(page.locator('.observation-card')).toHaveCount(4);
  await page.getByRole('button', { name: 'Недостаточно данных', exact: true }).click();
  await expect(page.locator('.observation-card')).toHaveCount(1);
  await page.getByLabel('Площадка', { exact: true }).selectOption('river');
  await expect(page.locator('.observation-card')).toHaveCount(2);
  await page.getByRole('button', { name: 'Свой снимок', exact: true }).click();
  await page.getByLabel('Выбрать изображение').setInputFiles({
    name: 'invalid.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('not an image'),
  });
  await expect(page.getByText('Выберите JPEG, PNG или WebP.')).toBeVisible();
  await page.getByLabel('Выбрать изображение').setInputFiles('static/images/excavation.webp');
  await expect(
    page.getByRole('img', { name: 'Локальный предпросмотр выбранного изображения' }),
  ).toBeVisible();
  await expect(page.getByText('Недостаточно данных для оценки', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть загрузку' }).click();
  await page.getByRole('button', { name: 'План работ', exact: true }).click();
  await page.getByRole('button', { name: 'Инженерные сети', exact: true }).click();
  await expect(
    page.locator('.schedule-detail').getByText('Нужен другой источник данных', { exact: true }),
  ).toBeVisible();
});

test('theme, deep link, download and 404', async ({ page }) => {
  await page.goto('/app?observation=OBS-1040');
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByText('Система не делает вывод', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть разбор' }).click();
  const themeButton = page.getByRole('button', { name: /^(Светлая|Тёмная) тема$/ });
  const label = await themeButton.getAttribute('aria-label');
  await themeButton.click();
  await page.reload();
  await expect(
    page.getByRole('button', { name: label === 'Светлая тема' ? 'Тёмная тема' : 'Светлая тема' }),
  ).toBeVisible();
  // The deep link intentionally reopens its observation after a reload.
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть разбор' }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Экспорт отчёта', exact: true }).click();
  const exported = await download;
  expect(exported.suggestedFilename()).toBe('sitewatch-demo-north.json');
  const stream = await exported.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const report = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  expect(report.mode).toBe('synthetic_demo');
  expect(report.site.id).toBe('north');
  expect(report.observations).toHaveLength(4);
  expect(
    report.observations.every(
      (o: { expected: string; observed: string; rule: string }) =>
        o.expected && o.observed && o.rule,
    ),
  ).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.goto('/unknown-page');
  await expect(page.getByRole('heading', { name: 'Этот участок ещё не найден.' })).toBeVisible();
});
