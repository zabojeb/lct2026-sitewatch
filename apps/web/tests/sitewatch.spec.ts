import { expect, test } from '@playwright/test';

test('all public routes fit mobile, tablet and desktop without horizontal scrolling', async ({
  page,
}) => {
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 850 });
    for (const route of [
      '/',
      '/app',
      '/app/model',
      '/app/site',
      '/app/site/plan',
      '/app/site/zones',
      '/app/site/history',
    ]) {
      await page.goto(route);
      // the site console renders on the client after loading its project
      if (route.startsWith('/app/site')) await page.getByRole('heading', { level: 1 }).waitFor();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `${route} at ${width}px`,
      ).toBe(true);
    }
  }
});

test('landing opens the scene workspace without an intermediate page', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Вся стройка.В поле зрения.');
  await page.getByRole('main').getByRole('link', { name: 'Начать анализ' }).first().click();
  await expect(page).toHaveURL(/\/app\/model$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Анализ сцен');
  await page.goto('/app');
  await expect(page).toHaveURL(/\/app\/model$/);
  expect(errors).toEqual([]);
});

test('workspace keeps technical model status out of the main layout', async ({
  page,
}) => {
  await page.route('**/api/model/status', (route) =>
    route.fulfill({
      json: {
        status: 'ready',
        rules_status: 'unavailable',
        model_version: 'real-version-under-test',
      },
    }),
  );
  await page.goto('/app');
  await expect(page.getByText('МОДЕЛЬ ГОТОВА')).toHaveCount(0);
  await expect(page.getByText('real-version-under-test')).toHaveCount(0);
  await expect(page.getByText('Северный квартал')).toHaveCount(0);
});

test('theme persists and 404 offers a route back', async ({ page }) => {
  await page.goto('/app');
  await page.locator('.scene-card').first().waitFor(); // redirected to /app/model and hydrated
  const themeButton = page.getByRole('button', { name: /^(Светлая|Тёмная) тема$/ });
  const initial = await themeButton.getAttribute('aria-label');
  await themeButton.click();
  await page.reload();
  await page.locator('.scene-card').first().waitFor();
  await expect(
    page.getByRole('button', { name: initial === 'Светлая тема' ? 'Тёмная тема' : 'Светлая тема' }),
  ).toBeVisible();
  await page.goto('/unknown-page');
  await expect(page.getByRole('heading', { name: 'Этот участок ещё не найден.' })).toBeVisible();
  await page.getByRole('link', { name: 'К анализу сцен' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Анализ сцен');
});
