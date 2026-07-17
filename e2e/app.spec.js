const { test, expect } = require('@playwright/test');

const MAIN_PAGES = [
  '/app',
  '/app/generate',
  '/app/rewrite',
  '/app/products',
  '/app/creators',
  '/app/templates',
  '/app/history',
  '/app/import',
  '/app/search',
  '/app/ai-config',
  '/app/operations',
  '/app/api-connections',
];

const TOOL_PAGES = MAIN_PAGES;

test('all main pages render without console errors', async ({ page }) => {
  await page.route('**/api/integrations/providers', route => route.fulfill({
    json: { providers: [] },
  }));
  await page.route(/\/api\/integrations\/connections(?:\?.*)?$/, route => route.fulfill({
    json: { connections: [] },
  }));
  await page.route(/\/api\/integrations\/sync-runs(?:\?.*)?$/, route => route.fulfill({
    json: { items: [], total: 0, page: 1, per_page: 50, total_pages: 1 },
  }));

  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') {
      const location = message.location();
      errors.push(`${message.text()} @ ${location.url || 'unknown'}`);
    }
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
    const launcher = document.querySelector('.facai-tools-launcher');
    return {
      drawerOpen: side.classList.contains('is-open'),
      composerTop: rect.top,
      composerBottom: rect.bottom,
      viewportHeight: window.innerHeight,
      launcherHidden: launcher && getComputedStyle(launcher).display === 'none',
      mobileUtilityCount: document.querySelectorAll('.nav-mobile-utility').length,
    };
  });

  expect(state.drawerOpen).toBe(false);
  expect(state.composerTop).toBeGreaterThanOrEqual(0);
  expect(state.composerBottom).toBeLessThanOrEqual(state.viewportHeight + 1);
  expect(state.launcherHidden).toBe(true);
  expect(state.mobileUtilityCount).toBe(3);

  await page.locator('#historyDrawerToggle').click();
  await expect(page.locator('.inspiration-side')).toHaveClass(/is-open/);
  await expect(page.locator('#historyDrawerBackdrop')).toHaveClass(/is-open/);
});

test('tools launcher is one accessible disclosure and filters the current tool', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });

  for (const path of TOOL_PAGES) {
    await page.goto(path, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.facai-tools-launcher'), `${path} should render tools`).toHaveCount(1);
    await expect(page.locator('#facaiToolsToggle'), `${path} tools should be visible`).toBeVisible();
  }

  await page.goto('/app/generate', { waitUntil: 'domcontentloaded' });

  await expect(page.locator('.facai-tools-launcher')).toHaveCount(1);
  const toggle = page.locator('#facaiToolsToggle');
  const menu = page.locator('#facaiToolsMenu');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(menu).toBeVisible();
  await expect(menu.locator('a')).toHaveCount(3);
  await expect(page.locator('body')).toHaveClass(/facai-tools-open/);

  await page.keyboard.press('Escape');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(toggle).toBeFocused();

  await toggle.click();
  await page.locator('main').click({ position: { x: 5, y: 5 } });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');

  await page.goto('/app/import', { waitUntil: 'domcontentloaded' });
  await page.locator('#facaiToolsToggle').click();
  await expect(page.locator('#facaiToolsMenu a')).toHaveCount(2);
  await expect(page.locator('#facaiToolsMenu a[href="/app/import"]')).toHaveCount(0);
});

test('generate scroll top stays clear of tools and hides while disclosure is open', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/app/generate', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(100);

  const positions = await page.evaluate(() => {
    const scroll = document.querySelector('.scroll-top-btn').getBoundingClientRect();
    const launcher = document.querySelector('.facai-tools-launcher').getBoundingClientRect();
    return { scrollBottom: scroll.bottom, launcherTop: launcher.top };
  });
  expect(positions.scrollBottom).toBeLessThanOrEqual(positions.launcherTop);

  await page.locator('#facaiToolsToggle').click();
  await expect(page.locator('.scroll-top-btn')).toHaveCSS('visibility', 'hidden');
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

test('API connections opens directly without a login session', async ({ page }) => {
  await page.goto('/app/api-connections', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: '电商 API 接入中心' })).toBeVisible();
  await expect(page.locator('.provider-connection-row')).toHaveCount(4);
  await expect(page.locator('#integrationLogout')).toHaveCount(0);
  await expect(page.getByText('功能框架已就绪，连接器尚未配置')).toBeVisible();
  await expect(page.locator('#facaiToolsToggle')).toBeVisible();
});
