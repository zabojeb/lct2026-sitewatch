import { expect, test } from '@playwright/test';

test('live-model screen keeps synthetic data separate and shows detector evidence', async ({
  page,
}) => {
  await page.route('**/api/model/status', (route) =>
    route.fulfill({
      json: {
        status: 'ready',
        rules_status: 'ready',
        model_version: 'test-detector+test-classifier',
      },
    }),
  );
  await page.route('**/api/model/predict', (route) =>
    route.fulfill({
      json: {
        schema: 'sitewatch.inference.v1',
        model_version: 'test-detector+test-classifier',
        image_width: 768,
        image_height: 512,
        detections: [
          {
            raw_class_id: 1,
            raw_class: 'excavator',
            equipment_class: 'excavator',
            mapping_status: 'mapped',
            detector_score: 0.91,
            classifier_score: 0.97,
            bounding_box: { x_min: 0.2, y_min: 0.2, x_max: 0.6, y_max: 0.7 },
          },
        ],
        note: 'Model evidence only',
      },
    }),
  );
  await page.goto('/app/model');
  await expect(page.getByText('МОДЕЛЬ ГОТОВА')).toBeVisible();
  await page.locator('input[type=file]').setInputFiles('static/images/excavation-768.webp');
  await page.getByRole('button', { name: 'Запустить анализ' }).click();
  await expect(page.locator('.box')).toHaveCount(1);
  await expect(page.getByText('excavator · excavator')).toBeVisible();
  await expect(
    page.getByText('Это результат моделей, а не вердикт о стройке.', { exact: false }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('live-model screen cannot upload when the sandbox is disabled', async ({ page }) => {
  await page.route('**/api/model/status', (route) =>
    route.fulfill({ json: { status: 'disabled', rules_status: 'disabled' } }),
  );
  await page.goto('/app/model');
  await page.locator('input[type=file]').setInputFiles('static/images/excavation-768.webp');
  await expect(page.getByRole('button', { name: 'Запустить анализ' })).toBeDisabled();
  await expect(page.getByText('Живой режим выключен в конфигурации')).toBeVisible();
});

test('invalid image is rejected before it reaches the model', async ({ page }) => {
  await page.route('**/api/model/status', (route) =>
    route.fulfill({
      json: { status: 'ready', rules_status: 'ready', model_version: 'model-test' },
    }),
  );
  let uploaded = false;
  await page.route('**/api/model/predict', (route) => {
    uploaded = true;
    return route.abort();
  });
  await page.goto('/app/model');
  await page.locator('input[type=file]').setInputFiles({
    name: 'invalid.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('not an image'),
  });
  await expect(page.getByRole('alert')).toHaveText('Выберите JPEG, PNG или WebP.');
  await expect(page.getByRole('button', { name: 'Запустить анализ' })).toBeDisabled();
  expect(uploaded).toBe(false);
});

test('real-frame rule preview carries model provenance and never promotes one frame to an alert', async ({
  page,
}) => {
  await page.route('**/api/model/status', (route) =>
    route.fulfill({
      json: { status: 'ready', rules_status: 'ready', model_version: 'model-test' },
    }),
  );
  await page.route('**/api/model/predict', (route) =>
    route.fulfill({
      json: {
        schema: 'sitewatch.inference.v1',
        model_version: 'model-test',
        image_width: 768,
        image_height: 512,
        detections: [
          {
            raw_class_id: 1,
            raw_class: 'excavator',
            equipment_class: 'excavator',
            mapping_status: 'mapped',
            detector_score: 0.9,
            classifier_score: 0.8,
            bounding_box: { x_min: 0.1, y_min: 0.1, x_max: 0.4, y_max: 0.5 },
          },
        ],
        note: 'Model evidence only',
      },
    }),
  );
  await page.route('**/api/model/evaluate', async (route) => {
    const request = route.request().postDataJSON();
    expect(request.stage.rules).toHaveLength(1);
    expect(request.stage.zone_code).toBe('PIT-01');
    expect(request.coverage).toEqual({ percent: 90, source: 'Схема камеры' });
    expect(request.frames).toHaveLength(1);
    expect(request.frames[0].image_sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(request.frames[0].detections[0].equipment_class).toBe('excavator');
    expect(request.frames[0].captured_at_source).toBe('Метка камеры');
    expect(request.frames[0].camera_code).toBe('CAM-01');
    await route.fulfill({
      json: {
        schema: 'sitewatch.evaluation.preview.v1',
        status: 'insufficient_evidence',
        stage_name: 'Разработка котлована',
        schedule: null,
        unconfigured_observed: [],
        findings: [
          {
            equipment_class: 'excavator',
            assessment: 'insufficient_evidence',
            expectation: 'required',
            expected_min: 1,
            expected_max: null,
            observed_count: 1,
            rule_source: 'ППР, раздел 4',
            evidence_frame_ids: [request.frames[0].id],
            evidence_sources: ['model model-test'],
            explanation: 'Нужны ещё независимые кадры.',
          },
        ],
        limitations: ['Предпросмотр не создаёт алерт.'],
      },
    });
  });
  await page.goto('/app/model');
  await page.getByLabel('Название этапа').fill('Разработка котлована');
  await page.getByLabel('Код зоны').fill('PIT-01');
  await page.getByLabel('Код камеры').fill('CAM-01');
  await page.getByLabel('Плановое начало').fill('2026-09-27T06:00');
  await page.getByLabel('Плановое завершение').fill('2026-10-04T06:00');
  await page.getByLabel('Зона видна с этой камеры').check();
  await page.getByLabel('Класс').selectOption('excavator');
  await page.getByLabel('Источник правила').fill('ППР, раздел 4');
  await page.getByLabel('Время текущего кадра').fill('2026-09-27T07:00');
  await page.getByLabel('Источник времени').fill('Метка камеры');
  await page.locator('input[type=file]').setInputFiles('static/images/excavation-768.webp');
  await page.getByRole('button', { name: 'Запустить анализ' }).click();
  await page.getByRole('button', { name: 'Добавить результат модели в окно' }).click();
  await expect(page.locator('.frame-row')).toHaveCount(1);
  await page.getByLabel('Обзор зоны, %').fill('90');
  await page.getByLabel('Источник оценки обзора').fill('Схема камеры');
  await page.getByRole('button', { name: 'Сравнить с графиком' }).click();
  await expect(page.getByText('Нужны ещё независимые кадры.')).toBeVisible();
  await expect(page.getByText('Предпросмотр не создаёт алерт.')).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Экспортировать проверку в JSON' }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^sitewatch-preview-\d{4}-\d{2}-\d{2}\.json$/);
  const stream = await file.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const report = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  expect(report.schema).toBe('sitewatch.operator-preview.v1');
  expect(report.input.frames[0].image_sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(report.result.status).toBe('insufficient_evidence');
  expect(JSON.stringify(report)).not.toContain('data:image');
  await page.getByRole('button', { name: 'Добавить результат модели в окно' }).click();
  await expect(page.getByText('Этот файл уже добавлен.', { exact: false })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
