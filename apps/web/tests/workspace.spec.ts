import { expect, test } from '@playwright/test';
import { detectionLabel, rawClassLabels, type ModelDetection } from '../src/lib/model';

test('the live taxonomy exposes all 22 trained classes without pretending all are rule classes', () => {
  expect(Object.keys(rawClassLabels)).toHaveLength(22);
  const detection: ModelDetection = {
    raw_class_id: 7,
    raw_class: 'bucket_loader',
    equipment_class: 'bucket_loader',
    mapping_status: 'mapped',
    detector_score: 0.86,
    classifier_score: 0.78,
    bounding_box: { x_min: 0.1, y_min: 0.2, x_max: 0.6, y_max: 0.7 },
  };
  expect(detectionLabel(detection)).toBe('Ковшовый погрузчик');
  expect(detectionLabel({ ...detection, raw_class: 'new_equipment' })).toBe('new_equipment');
});

test('rule form starts without an invented project, plan or evidence', async ({ page }) => {
  await page.route('**/api/model/status', (route) =>
    route.fulfill({
      json: { status: 'ready', rules_status: 'ready', model_version: 'real-model' },
    }),
  );
  await page.goto('/app/model');
  await expect(page.getByLabel('Название этапа')).toHaveValue('');
  await expect(page.getByLabel('Код зоны')).toHaveValue('');
  await expect(page.getByLabel('Код камеры')).toHaveValue('');
  await expect(page.getByLabel('Плановое начало')).toHaveValue('');
  await expect(page.getByLabel('Плановое завершение')).toHaveValue('');
  await expect(page.getByLabel('Источник правила')).toHaveValue('');
  await expect(page.getByText('00 КАДРОВ В ОКНЕ')).toBeVisible();
  await expect(page.getByText('Демо-методика команды')).toHaveCount(0);
});
