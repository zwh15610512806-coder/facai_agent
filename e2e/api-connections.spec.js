const { test, expect } = require('@playwright/test');

const providerPayload = {
  providers: [
    { provider: 'qianchuan', configured: true, live_verified: false, app_config: { app_id: 'qc-app', secret_configured: true, secret_mask: '••••9138' } },
    { provider: 'doudian', configured: false, live_verified: false },
    { provider: 'taobao', configured: false, live_verified: false },
    { provider: 'pdd', configured: false, live_verified: false },
  ],
};

const connectionPayload = {
  connections: [{
    id: 1,
    provider: 'qianchuan',
    display_name: '千川测试账户',
    status: 'active',
    authorization_id: 101,
    external_account_id: 'account-safe-01',
    capabilities: { status: 'verified', verified_resources: ['orders'] },
    last_successful_sync_at: '2026-07-14T02:00:00Z',
    authorization: { id: 101, scopes: ['ad.read'], access_expires_at: '2026-07-31T00:00:00Z', access_token_mask: '••••9138' },
  }],
};

async function mockConnectionApis(page, options = {}) {
  await page.route('**/api/integrations/providers', route => route.fulfill({ json: options.providers || providerPayload }));
  await page.route(/\/api\/integrations\/connections(?:\?.*)?$/, route => route.fulfill({ json: options.connections || connectionPayload }));
  await page.route(/\/api\/integrations\/sync-runs(?:\?.*)?$/, route => route.fulfill({
    json: options.runs || {
      items: [{ id: 91, public_id: 'run-safe-91', connection_name: '千川测试账户', resource_type: 'orders', status: 'failed', failure_summary: '上游接口暂不可用', window_start: '2026-07-13T00:00:00Z', window_end: '2026-07-13T23:59:59Z' }],
      total: 1, page: 1, per_page: 50, total_pages: 1,
    },
  }));
}

const filterOptions = {
  providers: [
    { key: 'qianchuan', label: '巨量千川' },
    { key: 'doudian', label: '抖店' },
    { key: 'taobao', label: '淘宝店' },
    { key: 'pdd', label: '拼多多店' },
  ],
  connections: [{ id: 1, provider: 'qianchuan', name: '千川测试账户', status: 'active' }],
};

async function mockOperationsApis(page, options = {}) {
  await page.route('**/api/operations/filter-options', route => route.fulfill({ json: options.filterOptions || filterOptions }));
  await page.route(/\/api\/operations\/overview(?:\?.*)?$/, route => route.fulfill({
    status: options.overviewStatus || 200,
    json: options.overview || { actual_sales: '1288.00', order_count: 12, refund_amount: '88.00', average_order_value: '107.33', ad_spend: '320.00', ad_attributed_sales: '760.00', daily: [] },
  }));
  await page.route(/\/api\/operations\/orders(?:\?.*)?$/, route => route.fulfill({
    status: options.ordersStatus || 200,
    json: options.orders || { items: [], total: 0, page: 1, per_page: 50, total_pages: 1 },
  }));
  await page.route(/\/api\/operations\/products(?:\?.*)?$/, route => route.fulfill({
    json: options.products || { items: [], total: 0, page: 1, per_page: 50, total_pages: 1 },
  }));
  await page.route(/\/api\/operations\/refunds(?:\?.*)?$/, route => route.fulfill({ json: { items: [], total: 0, page: 1, per_page: 50, total_pages: 1 } }));
  await page.route(/\/api\/operations\/ad-entities(?:\?.*)?$/, route => route.fulfill({ json: { items: [], total: 0, page: 1, per_page: 50, total_pages: 1 } }));
  await page.route(/\/api\/operations\/ad-metrics(?:\?.*)?$/, route => route.fulfill({ json: { items: [], total: 0, page: 1, per_page: 50, total_pages: 1 } }));
  await page.route(/\/api\/operations\/sync-runs(?:\?.*)?$/, route => route.fulfill({ json: options.runs || { items: [], total: 0, page: 1, per_page: 50, total_pages: 1 } }));
}

test('connection management is a standalone admin page with failed-task retry', async ({ page }) => {
  await mockConnectionApis(page);
  let retried = false;
  await page.route('**/api/integrations/sync-runs/91/retry', async route => {
    retried = route.request().method() === 'POST';
    await route.fulfill({ status: 202, json: { id: 92, status: 'queued' } });
  });

  await page.goto('/app/api-connections');
  await expect(page.getByRole('heading', { name: '电商 API 接入中心' })).toBeVisible();
  await expect(page.getByRole('tab')).toHaveCount(0);
  await expect(page.locator('#panel-overview')).toHaveCount(0);
  await expect(page.locator('.provider-connection-row')).toHaveCount(4);
  await expect(page.getByText('••••9138').first()).toBeVisible();
  await expect(page.getByRole('heading', { name: '最近失败任务' })).toBeVisible();
  await page.getByRole('button', { name: '重试 同步任务 91' }).click();
  expect(retried).toBe(true);
});

test('connection management reports an API rejection without redirecting to login', async ({ page }) => {
  await page.route('**/api/integrations/providers', route => route.fulfill({ status: 401, json: { detail: 'expired' } }));
  await page.route(/\/api\/integrations\/connections(?:\?.*)?$/, route => route.fulfill({ json: { connections: [] } }));
  await page.route(/\/api\/integrations\/sync-runs(?:\?.*)?$/, route => route.fulfill({ json: { items: [] } }));
  await page.goto('/app/api-connections');
  await expect(page).toHaveURL(/\/app\/api-connections$/);
  await expect(page.locator('#connectionPanelStatus')).toContainText('expired');
});

test('operations exposes six keyboard tabs and never renders connection controls', async ({ page }) => {
  await mockOperationsApis(page);
  await page.goto('/app/operations?tab=orders');

  const tabs = page.getByRole('tab');
  await expect(tabs).toHaveCount(6);
  await expect(page.getByRole('tab', { name: '订单' })).toHaveAttribute('aria-selected', 'true');
  await page.getByRole('tab', { name: '订单' }).press('ArrowRight');
  await expect(page.getByRole('tab', { name: '商品' })).toHaveAttribute('aria-selected', 'true');
  await expect(page).toHaveURL(/tab=products/);
  await page.getByRole('tab', { name: '商品' }).press('End');
  await expect(page.getByRole('tab', { name: '同步记录' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#providerConnectionList')).toHaveCount(0);
  await expect(page.locator('#integrationLogout')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /重试/ })).toHaveCount(0);
});

test('invalid and legacy data tabs resolve to the operations page', async ({ page }) => {
  await mockOperationsApis(page);
  await page.goto('/app/operations?tab=not-real');
  await expect(page.getByRole('tab', { name: '概览' })).toHaveAttribute('aria-selected', 'true');

  await page.goto('/app/api-connections?tab=ads');
  await expect(page).toHaveURL(/\/app\/operations\?tab=ads$/);
  await expect(page.getByRole('tab', { name: '广告' })).toHaveAttribute('aria-selected', 'true');
});

test('operations handles safe data, pagination and an API failure state', async ({ page }) => {
  await mockOperationsApis(page, {
    orders: {
      items: [{ external_order_id: 'order-safe-001', provider: 'doudian', status: 'paid', paid_amount: '168.00', business_time: '2026-07-14T03:00:00Z', buyer_phone: 'must-not-render' }],
      total: 120, page: 1, per_page: 50, total_pages: 3,
    },
  });
  await page.goto('/app/operations?tab=orders');
  await expect(page.getByText('order-safe-001')).toBeVisible();
  await expect(page.getByText('must-not-render')).toHaveCount(0);
  await expect(page.locator('#panel-orders [data-page-status]')).toContainText('第 1 / 3 页');

  await page.unroute(/\/api\/operations\/orders(?:\?.*)?$/);
  await page.route(/\/api\/operations\/orders(?:\?.*)?$/, route => route.fulfill({ status: 500, json: { detail: '数据服务暂不可用' } }));
  await page.locator('#panel-orders select[name="status"]').selectOption('paid');
  await expect(page.locator('#panel-orders [data-panel-state]')).toContainText('数据服务暂不可用');
});

test('viewer-style export denial stays on operations and shows a 403 state', async ({ page }) => {
  await mockOperationsApis(page);
  await page.route('**/api/operations/exports', route => route.fulfill({ status: 403, json: { detail: 'Insufficient role' } }));
  await page.goto('/app/operations?tab=orders');
  await page.getByRole('button', { name: '导出当前订单' }).click();
  await expect(page.locator('#panel-orders [data-panel-state]')).toContainText('Insufficient role');
  await expect(page).toHaveURL(/\/app\/operations/);
});

test('operator-style product association uses only the operations write route', async ({ page }) => {
  await mockOperationsApis(page, {
    products: { items: [{ id: 7, external_product_id: 'p-safe-7', title: '测试商品', status: 'on_sale' }], total: 1, page: 1, per_page: 50, total_pages: 1 },
  });
  await page.route('**/api/products/?search=*', route => route.fulfill({ json: [{ id: 9, name: '内部测试产品' }] }));
  let linkedUrl = '';
  await page.route('**/api/operations/products/7/link', async route => {
    linkedUrl = route.request().url();
    await route.fulfill({ json: { commerce_product_id: 7, product_id: 9, linked: true } });
  });

  await page.goto('/app/operations?tab=products');
  await page.getByRole('button', { name: '关联产品 测试商品' }).click();
  await page.locator('[name="product_search"]').fill('内部测试');
  await page.getByRole('button', { name: '搜索', exact: true }).click();
  await page.locator('[name="product_id"]').selectOption('9');
  await page.getByRole('button', { name: '确认关联' }).click();
  expect(linkedUrl).toContain('/api/operations/products/7/link');
});

for (const width of [1920, 1440, 1280, 390]) {
  test(`operations navigation and content stay inside a ${width}px viewport`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockOperationsApis(page);
    await page.goto('/app/operations');
    const layout = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      bodyWidth: document.body.scrollWidth,
      operationsVisible: Boolean(document.querySelector('.nav-links a[href="/app/operations"]')),
      launcherDisplay: getComputedStyle(document.querySelector('.facai-tools-launcher')).display,
      mobileApiEntry: Boolean(document.querySelector('.nav-mobile-utility[href="/app/api-connections"]')),
    }));
    expect(layout.bodyWidth).toBeLessThanOrEqual(layout.viewport + 1);
    expect(layout.operationsVisible).toBe(true);
    if (width === 390) {
      expect(layout.launcherDisplay).toBe('none');
      expect(layout.mobileApiEntry).toBe(true);
    } else {
      expect(layout.launcherDisplay).not.toBe('none');
    }
  });
}
