const { test, expect } = require('@playwright/test');

function mutation(page, method, expectedPath) {
  return page.waitForResponse(response => {
    const path = new URL(response.url()).pathname;
    return response.request().method() === method && path === expectedPath;
  });
}

test('creator BD workbench completes profile, deal, sample and export flow', async ({ page, request }) => {
  test.setTimeout(60_000);
  const browserErrors = [];
  page.on('console', message => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });
  page.on('pageerror', error => browserErrors.push(error.message));
  page.on('dialog', dialog => dialog.accept());

  const suffix = Date.now();
  const memberResponse = await request.post('/api/creators/bd-members', {
    data: { name: `E2E负责人-${suffix}` },
  });
  expect(memberResponse.status()).toBe(201);
  const member = await memberResponse.json();

  const productResponse = await request.post('/api/products/', {
    data: {
      name: `E2E草莓果酱-${suffix}`,
      category: '测试产品',
      price: 59,
      description: '隔离端到端测试产品',
    },
  });
  expect(productResponse.ok()).toBeTruthy();
  const product = await productResponse.json();

  await page.goto('/app/creators', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#creatorWorkbench')).toBeVisible();

  await page.locator('.creator-sidebar [data-action="new-creator"]').click();
  const creatorForm = page.locator('#creatorForm');
  await creatorForm.locator('[name="nickname"]').fill(`E2E烘焙达人-${suffix}`);
  await creatorForm.locator('[name="douyin_handle"]').fill(`e2e-baker-${suffix}`);
  await creatorForm.locator('[name="owner_id"]').selectOption(String(member.id));
  await creatorForm.locator('[name="contact_name"]').fill('张达人');
  await creatorForm.locator('[name="contact_phone"]').fill('13812345678');
  const creatorDone = mutation(page, 'POST', '/api/creators');
  await creatorForm.locator('[type="submit"]').click();
  const creatorResponse = await creatorDone;
  expect(creatorResponse.status()).toBe(201);
  const creator = await creatorResponse.json();
  const creatorCard = page.locator(`[data-creator-id="${creator.id}"]`);
  await expect(creatorCard).toContainText(`E2E烘焙达人-${suffix}`);

  await page.locator('.creator-quick-actions [data-action="new-followup"]').click();
  const followupForm = page.locator('#followupForm');
  await followupForm.locator('[name="method"]').selectOption('wechat');
  await followupForm.locator('[name="content"]').fill('确认寄样并讨论直播排期');
  await followupForm.locator('[name="result"]').fill('同意寄样');
  await followupForm.locator('[name="stage_after"]').selectOption('negotiating');
  const followupDone = mutation(page, 'POST', `/api/creators/${creator.id}/followups`);
  await followupForm.locator('[type="submit"]').click();
  expect((await followupDone).status()).toBe(201);
  await expect(page.locator('[data-record-type="followup"]')).toContainText('确认寄样并讨论直播排期');
  await expect(page.locator('#creatorDetailBody')).toContainText('洽谈中');

  await page.locator('.creator-quick-actions [data-action="new-collaboration"]').click();
  const collaborationForm = page.locator('#collaborationForm');
  await collaborationForm.locator('[name="internal_code"]').fill(`E2E-COOP-${suffix}`);
  await collaborationForm.locator('[name="collaboration_type"]').selectOption('live');
  await collaborationForm.locator('[name="collaboration_date"]').fill('2026-07-13');
  await collaborationForm.locator('[name="status"]').selectOption('planned');
  await collaborationForm.locator(`[name="product_ids"][value="${product.id}"]`).check();
  const collaborationDone = mutation(page, 'POST', `/api/creators/${creator.id}/collaborations`);
  await collaborationForm.locator('[type="submit"]').click();
  const collaborationResponse = await collaborationDone;
  expect(collaborationResponse.status()).toBe(201);
  const collaboration = await collaborationResponse.json();
  const collaborationCard = page.locator(`[data-record-type="collaboration"][data-record-id="${collaboration.id}"]`);
  await expect(collaborationCard).toContainText(`E2E-COOP-${suffix}`);
  await expect(collaborationCard).toContainText('待执行');

  await collaborationCard.locator('[data-action="edit-collaboration"]').click();
  await collaborationForm.locator('[name="status"]').selectOption('in_progress');
  let collaborationUpdated = mutation(page, 'PUT', `/api/creators/${creator.id}/collaborations/${collaboration.id}`);
  await collaborationForm.locator('[type="submit"]').click();
  expect((await collaborationUpdated).status()).toBe(200);
  await expect(collaborationCard).toContainText('执行中');

  await collaborationCard.locator('[data-action="edit-collaboration"]').click();
  await collaborationForm.locator('[name="status"]').selectOption('completed');
  await collaborationForm.locator('[name="amount_status"]').selectOption('confirmed');
  await collaborationForm.locator('[name="actual_paid_yuan"]').fill('1286.00');
  collaborationUpdated = mutation(page, 'PUT', `/api/creators/${creator.id}/collaborations/${collaboration.id}`);
  await collaborationForm.locator('[type="submit"]').click();
  expect((await collaborationUpdated).status()).toBe(200);
  await expect(collaborationCard).toContainText('已完成');
  await expect(page.locator('[data-metric="confirmed-paid"]')).toContainText(/1,?286\.00/);

  await collaborationCard.locator('[data-action="edit-collaboration"]').click();
  await collaborationForm.locator('[name="actual_paid_yuan"]').fill('1200.00');
  collaborationUpdated = mutation(page, 'PUT', `/api/creators/${creator.id}/collaborations/${collaboration.id}`);
  await collaborationForm.locator('[type="submit"]').click();
  expect((await collaborationUpdated).status()).toBe(200);
  await expect(page.locator('[data-metric="confirmed-paid"]')).toContainText(/1,?200\.00/);

  await page.locator('#creatorDetailBody [data-action="new-address"]').click();
  const addressForm = page.locator('#addressForm');
  await addressForm.locator('[name="recipient_name"]').fill('张达人');
  await addressForm.locator('[name="phone"]').fill('13812345678');
  await addressForm.locator('[name="province"]').fill('广东省');
  await addressForm.locator('[name="city"]').fill('深圳市');
  await addressForm.locator('[name="district"]').fill('南山区');
  await addressForm.locator('[name="detail"]').fill('科技园 8 号 1201');
  await addressForm.locator('[name="is_default"]').check();
  const addressDone = mutation(page, 'POST', `/api/creators/${creator.id}/addresses`);
  await addressForm.locator('[type="submit"]').click();
  const addressResponse = await addressDone;
  expect(addressResponse.status()).toBe(201);
  const address = await addressResponse.json();

  await page.locator('.creator-quick-actions [data-action="new-sample"]').click();
  const sampleForm = page.locator('#sampleOrderForm');
  await sampleForm.locator('[name="address_id"]').selectOption(String(address.id));
  await sampleForm.locator('[data-sample-item] [name="product_id"]').first().selectOption(String(product.id));
  await sampleForm.locator('[data-sample-item] [name="specification"]').first().fill('500g');
  await sampleForm.locator('[data-sample-item] [name="quantity"]').first().fill('2');
  const sampleDone = mutation(page, 'POST', `/api/creators/${creator.id}/sample-orders`);
  await sampleForm.locator('[type="submit"]').click();
  const sampleResponse = await sampleDone;
  expect(sampleResponse.status()).toBe(201);
  const order = await sampleResponse.json();
  const orderRow = page.locator(`[data-record-type="sample"][data-order-id="${order.id}"]`);
  await expect(orderRow).toContainText('待发货');

  await orderRow.locator('[data-action="ship-sample-order"]').click();
  const shippingForm = page.locator('#shippingForm');
  await shippingForm.locator('[name="shipping_company"]').fill('顺丰');
  await shippingForm.locator('[name="tracking_number"]').fill(`SF${suffix}`);
  const shippedDone = mutation(page, 'PUT', `/api/creators/${creator.id}/sample-orders/${order.id}`);
  await shippingForm.locator('[type="submit"]').click();
  expect((await shippedDone).status()).toBe(200);
  await expect(orderRow).toContainText('已发货');

  const receivedDone = mutation(page, 'PUT', `/api/creators/${creator.id}/sample-orders/${order.id}`);
  await orderRow.locator('[data-action="receive-sample-order"]').click();
  expect((await receivedDone).status()).toBe(200);
  await expect(orderRow).toContainText('已签收');

  const downloadPromise = page.waitForEvent('download');
  await page.locator('[data-export-entity="sample_orders"]').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('creator-sample_orders-export.xlsx');
  const stream = await download.createReadStream();
  let bytes = 0;
  for await (const chunk of stream) bytes += chunk.length;
  expect(bytes).toBeGreaterThan(1000);

  expect(browserErrors).toEqual([]);
});

test('creator workbench switches list, detail and activity views on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app/creators', { waitUntil: 'domcontentloaded' });
  const workbench = page.locator('#creatorWorkbench');
  await expect(workbench).toHaveAttribute('data-mobile-view', 'list');
  await expect(page.locator('.creator-sidebar')).toBeVisible();
  await page.locator('[data-mobile-target="detail"]').click();
  await expect(workbench).toHaveAttribute('data-mobile-view', 'detail');
  await expect(page.locator('.creator-detail-panel')).toBeVisible();
  await page.locator('[data-mobile-target="activity"]').click();
  await expect(workbench).toHaveAttribute('data-mobile-view', 'activity');
  await expect(page.locator('.creator-activity-panel')).toBeVisible();
});

test('a slow creator response cannot overwrite a newer creator selection', async ({ page, request }) => {
  const suffix = Date.now();
  const slow = await (await request.post('/api/creators', {
    data: { nickname: `慢响应达人-${suffix}`, douyin_handle: `slow-${suffix}` },
  })).json();
  const fast = await (await request.post('/api/creators', {
    data: { nickname: `最新选择达人-${suffix}`, douyin_handle: `fast-${suffix}` },
  })).json();

  await page.route(`**/api/creators/${slow.id}`, async route => {
    await new Promise(resolve => setTimeout(resolve, 450));
    await route.continue();
  });
  await page.goto('/app/creators', { waitUntil: 'domcontentloaded' });
  await expect(page.locator(`[data-creator-id="${fast.id}"]`)).toBeVisible();
  await page.locator(`[data-creator-id="${slow.id}"]`).click();
  await page.locator(`[data-creator-id="${fast.id}"]`).click();
  await expect(page.locator('#creatorDetailBody')).toContainText(`最新选择达人-${suffix}`);
  await page.waitForTimeout(650);
  await expect(page.locator('#creatorDetailBody')).toContainText(`最新选择达人-${suffix}`);
  await expect(page.locator('#creatorDetailBody')).not.toContainText(`慢响应达人-${suffix}`);
});
