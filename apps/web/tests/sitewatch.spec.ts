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

test('landing explains the real flow and opens the live workspace', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Вся стройка.В поле зрения.');
  await expect(page.getByText('ИЛЛЮСТРАЦИЯ / НЕ РЕЗУЛЬТАТ АНАЛИЗА')).toBeVisible();
  await page.getByRole('button', { name: 'О демо' }).click();
  await expect(page.getByRole('dialog')).toContainText('детектор и классификатор техники');
  await expect(page.getByRole('dialog')).toContainText('не добавляются в архив');
  await page.getByRole('button', { name: 'Закрыть' }).click();
  await page.getByRole('main').getByRole('link', { name: 'Открыть пульт' }).first().click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Сначала кадр.Затем вывод.');
  await expect(page.getByText('Здесь нет подставленных объектов', { exact: false })).toBeVisible();
  await expect(page.getByText('Северный квартал')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('workspace reports service state from status endpoint, never manufactured observations', async ({
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
  await expect(page.getByRole('article').first().getByText('Работает')).toBeVisible();
  await expect(page.getByRole('article').nth(1).getByText('Нет соединения')).toBeVisible();
  await expect(page.getByRole('article').nth(2).getByText('Не подключён')).toBeVisible();
  await expect(page.getByText('real-version-under-test')).toBeVisible();
  await page.getByRole('button', { name: 'Обновить состояние сервисов' }).click();
  await expect(page.getByText('Проверено в', { exact: false })).toBeVisible();
  await page.getByRole('link', { name: 'Проверить кадр' }).first().click();
  await expect(page.getByRole('heading', { name: 'Загрузите кадр площадки' })).toBeVisible();
});

test('theme persists and 404 offers a route back', async ({ page }) => {
  await page.goto('/app');
  const themeButton = page.getByRole('button', { name: /^(Светлая|Тёмная) тема$/ });
  const initial = await themeButton.getAttribute('aria-label');
  await themeButton.click();
  await page.reload();
  await expect(
    page.getByRole('button', { name: initial === 'Светлая тема' ? 'Тёмная тема' : 'Светлая тема' }),
  ).toBeVisible();
  await page.goto('/unknown-page');
  await expect(page.getByRole('heading', { name: 'Этот участок ещё не найден.' })).toBeVisible();
  await page.getByRole('link', { name: 'Открыть пульт' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Сначала кадр.Затем вывод.');
});
