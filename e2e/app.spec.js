const { test, expect } = require('@playwright/test');

const MAIN_PAGES = [
  '/app',
  '/app/generate',
  '/app/rewrite',
  '/app/products',
  '/app/templates',
  '/app/history',
  '/app/import',
  '/app/search',
  '/app/ai-config',
];

test('all main pages render without console errors', async ({ page }) => {
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));

  for (const path of MAIN_PAGES) {
    const response = await page.goto(path, { waitUntil: 'domcontentloaded' });
    expect(response && response.ok(), `${path} should return 2xx`).toBeTruthy();
    await page.waitForTimeout(150);
  }

  expect(errors).toEqual([]);
});

test('mobile AI work opens with chat visible, drawer closed and composer on screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app', { waitUntil: 'domcontentloaded' });

  const state = await page.evaluate(() => {
    const side = document.querySelector('.inspiration-side');
    const composer = document.querySelector('.inspiration-composer');
    const rect = composer.getBoundingClientRect();
    const fabs = Array.from(document.querySelectorAll('.ai-config-fab,.data-import-fab'));
    return {
      drawerOpen: side.classList.contains('is-open'),
      composerTop: rect.top,
      composerBottom: rect.bottom,
      viewportHeight: window.innerHeight,
      fabsHidden: fabs.every(item => getComputedStyle(item).display === 'none'),
      mobileUtilityCount: document.querySelectorAll('.nav-mobile-utility').length,
    };
  });

  expect(state.drawerOpen).toBe(false);
  expect(state.composerTop).toBeGreaterThanOrEqual(0);
  expect(state.composerBottom).toBeLessThanOrEqual(state.viewportHeight + 1);
  expect(state.fabsHidden).toBe(true);
  expect(state.mobileUtilityCount).toBe(2);

  await page.locator('#historyDrawerToggle').click();
  await expect(page.locator('.inspiration-side')).toHaveClass(/is-open/);
  await expect(page.locator('#historyDrawerBackdrop')).toHaveClass(/is-open/);
});

test('desktop AI work keeps the two-column layout', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/app', { waitUntil: 'domcontentloaded' });

  const columns = await page.locator('.inspiration-shell').evaluate(
    element => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length,
  );
  await expect(page.locator('.inspiration-side')).toBeVisible();
  await expect(page.locator('.inspiration-composer')).toBeVisible();
  expect(columns).toBe(2);
});
