import { expect, test, type Page } from '@playwright/test';

async function open(page: Page, route: string) {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(route);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  return errors;
}

test('archive project labels provenance without asserting a construction stage', async ({ page }) => {
  const errors = await open(page, '/app/site');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Обзор проекта');
  await expect(page.getByText('Рамки: разметка датасета.')).toBeVisible();
  await expect(page.getByRole('link', { name: /const-video-v2i-yolo26/ })).toBeVisible();
  await expect(page.getByText('Архивный проект', { exact: true })).toBeVisible();
  await page.getByLabel('Камера', { exact: true }).selectOption('cam-8');
  await expect(page.getByText('Этап работ по технике не определяется')).toBeVisible();
  await expect(page.getByText(/^Срез площадки на \d/)).toBeVisible();
  await expect(page.getByText('Визуальное сопоставление без процента готовности')).toBeVisible();
  expect(errors).toEqual([]);
});

test('plan: a stage from the works list joins the calendar without inferring completion', async ({
  page,
}) => {
  const errors = await open(page, '/app/site/plan');
  await expect(page.getByText('Для вывода нужны видимые признаки работ', { exact: false })).toBeVisible();
  const before = await page.locator('.plan-item').count();
  await page.getByPlaceholder('Например: котлован, сваи, асфальт…').fill('асфальт');
  await page
    .getByRole('button', { name: /Асфальтобетонное покрытие|асфальтобетонного покрытия/ })
    .first()
    .click();
  await expect(page.locator('.plan-item')).toHaveCount(before + 1);
  await expect(page.getByText('строка 354 перечня')).toBeVisible();
  expect(errors).toEqual([]);
});

test('zones: the example rule flags the excavator and a new zone can be drawn', async ({
  page,
}) => {
  const errors = await open(page, '/app/site/zones');
  await page.getByLabel('Камера', { exact: true }).selectOption('cam-9');
  await expect(page.getByText('Склад материалов · пример правила')).toBeVisible();
  await expect(page.getByText('1 объект в зоне')).toBeVisible();
  await page.getByLabel('Камера', { exact: true }).selectOption('cam-4');
  await page.getByRole('button', { name: 'Начать разметку' }).click();
  await page.getByRole('button', { name: 'Перейти к обводу' }).click();
  await page.locator('.frame').first().scrollIntoViewIfNeeded();
  const frame = await page.locator('.frame').first().boundingBox();
  if (!frame) throw new Error('frame not rendered');
  for (const [x, y] of [
    [0.2, 0.2],
    [0.5, 0.25],
    [0.4, 0.6],
  ])
    await page.mouse.click(frame.x + frame.width * x, frame.y + frame.height * y);
  await page.getByRole('button', { name: 'Завершить зону' }).click();
  await expect(page.getByRole('heading', { name: '1 зона' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('history summarises control dates of a long-term project', async ({ page }) => {
  const errors = await open(page, '/app/site/history');
  await page.getByLabel('Проект').selectOption('torre-h');
  await expect(page.getByText('Контрольные даты')).toBeVisible();
  await expect(page.locator('.dates .row:not(.head)')).toHaveCount(5);
  await expect(page.getByText('Рамки: разметка датасета.')).toBeVisible();
  expect(errors).toEqual([]);
});
