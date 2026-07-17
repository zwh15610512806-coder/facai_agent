const zlib = require('node:zlib');
const { test, expect } = require('@playwright/test');

test.setTimeout(90_000);

const createdProjectIds = new Set();

function projectUrl(projectId) {
  return `/api/canvas/projects/${encodeURIComponent(projectId)}`;
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const name = Buffer.from(type, 'ascii');
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([name, data])));
  return Buffer.concat([length, name, data, checksum]);
}

function transparentProductPng() {
  const width = 8;
  const height = 8;
  const row = Buffer.alloc(1 + width * 4);
  const rows = [];
  for (let y = 0; y < height; y += 1) {
    const next = Buffer.from(row);
    for (let x = 0; x < width; x += 1) {
      const offset = 1 + x * 4;
      const product = x >= 2 && x <= 5 && y >= 2 && y <= 5;
      next[offset] = product ? 26 : 0;
      next[offset + 1] = product ? 92 : 0;
      next[offset + 2] = product ? 180 : 0;
      next[offset + 3] = product ? 255 : 0;
    }
    rows.push(next);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk('IHDR', ihdr),
    pngChunk('IDAT', zlib.deflateSync(Buffer.concat(rows), { level: 9 })),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}

async function createProject(request, name) {
  const response = await request.post('/api/canvas/projects', { data: { name } });
  expect(response.status()).toBe(201);
  const snapshot = await response.json();
  createdProjectIds.add(snapshot.project.id);
  return snapshot;
}

async function createSku(request, projectId, revision, name) {
  const response = await request.post(`${projectUrl(projectId)}/skus`, {
    data: { revision, name, referenceAssetId: null, prompt: '', config: {} },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

async function removeProject(request, projectId) {
  const current = await request.get(projectUrl(projectId));
  if (current.status() === 404) return;
  expect(current.ok()).toBeTruthy();
  const snapshot = await current.json();
  const deleted = await request.delete(projectUrl(projectId), { data: { revision: snapshot.revision } });
  expect(deleted.ok()).toBeTruthy();
  await expect.poll(async () => (await request.get(projectUrl(projectId))).status()).toBe(404);
}

async function uploadMainProduct(page, projectId) {
  const input = page.getByTestId('canvas-asset-uploader').locator('input[type="file"]');
  // The shell mounts before the selected project finishes hydrating. Waiting for
  // the uploader to become enabled prevents a file-change event from being
  // discarded while its projectId is still null on a busy full-suite run.
  await expect(input).toBeEnabled();
  const responsePromise = page.waitForResponse((response) => (
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/assets`
  ));
  await input.setInputFiles({
    name: 'e2e-product.png', mimeType: 'image/png', buffer: transparentProductPng(),
  });
  const response = await responsePromise;
  expect(response.status()).toBe(201);
  return response.json();
}

async function waitForSaved(page) {
  await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'saved');
}

async function saveChange(page, projectId, change) {
  const saved = page.waitForResponse((response) => (
    response.request().method() === 'PUT'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/state`
      && response.status() === 200
  ));
  await change();
  return (await saved).json();
}

async function configureOutput(page, fieldset, projectId, { outputType, skuId, modelId, prompt, quantity, compositionGroupId, referenceAssetId = null }) {
  const outputFrom = (snapshot) => snapshot.project.semanticState.completeSet.outputs.find((output) => (
    output.outputType === outputType && output.skuId === skuId
  ));
  const quantityInput = fieldset.locator('input[type="number"]').first();
  await saveChange(page, projectId, async () => {
    await quantityInput.fill(String(quantity));
    await quantityInput.press('Tab');
  });
  await saveChange(page, projectId, () => fieldset.locator('select').first().selectOption(modelId));
  const promptInput = fieldset.locator('textarea').first();
  await saveChange(page, projectId, async () => {
    await promptInput.fill(prompt);
    await promptInput.press('Tab');
  });
  const dimensions = fieldset.locator('input[type="number"]');
  const widthSaved = await saveChange(page, projectId, async () => {
    await dimensions.nth(1).fill('96');
    await dimensions.nth(1).press('Tab');
  });
  expect(outputFrom(widthSaved)).toMatchObject({ width: 96, height: null, aspectRatio: null });
  const heightSaved = await saveChange(page, projectId, async () => {
    await dimensions.nth(2).fill('64');
    await dimensions.nth(2).press('Tab');
  });
  expect(outputFrom(heightSaved)).toMatchObject({ width: 96, height: 64, aspectRatio: '3:2' });
  const compositionSaved = await saveChange(page, projectId, () => (
    fieldset.locator('select').nth(2).selectOption(compositionGroupId)
  ));
  expect(outputFrom(compositionSaved)).toMatchObject({ compositionGroupId });
  if (referenceAssetId !== null) {
    const referenceSaved = await saveChange(page, projectId, () => (
      fieldset.locator('select').nth(1).selectOption(referenceAssetId)
    ));
    expect(outputFrom(referenceSaved)).toMatchObject({ referenceAssetId });
  }
}

async function getGeneration(request, generationId) {
  const response = await request.get(`/api/canvas/generations/${generationId}`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function waitForGeneration(request, generationId, predicate, timeout = 30_000) {
  let latest = null;
  try {
    await expect.poll(async () => {
      latest = await getGeneration(request, generationId);
      return predicate(latest);
    }, { timeout }).toBe(true);
  } catch (error) {
    const diagnostic = latest ? JSON.stringify(latest) : 'unavailable';
    let audit = 'unavailable';
    try {
      audit = JSON.stringify(await (await request.get('/_e2e/runtime-audit')).json());
    } catch {
      // Preserve the original assertion failure if the diagnostic endpoint is unavailable.
    }
    throw new Error(`${error.message}\nLatest generation: ${diagnostic}\nRuntime audit: ${audit}`);
  }
  return latest;
}

async function submitFromPage(page, projectId) {
  const generationCreated = page.waitForResponse((response) => (
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/generations`
  ));
  await page.getByTestId('canvas-generate').click();
  const response = await generationCreated;
  const body = await response.text();
  expect(response.status(), body).toBeGreaterThanOrEqual(200);
  expect(response.status(), body).toBeLessThan(300);
  return JSON.parse(body);
}

async function configureMainOutput(page, request, { name, modelId, prompt, quantity = 1 }) {
  const created = await createProject(request, name);
  const projectId = created.project.id;
  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  await uploadMainProduct(page, projectId);
  await waitForSaved(page);
  const compositionSnapshot = await saveChange(page, projectId, () => (
    page.getByTestId('canvas-composition-group-create').click()
  ));
  const composition = compositionSnapshot.project.semanticState.compositionGroups[0];
  await page.getByTestId('canvas-output-main').click();
  const output = page.locator('.canvas-output-control').first();
  await configureOutput(page, output, projectId, {
    outputType: 'main', skuId: null, modelId, prompt, quantity,
    compositionGroupId: composition.id,
  });
  await waitForSaved(page);
  return { projectId, composition };
}

test.afterEach(async ({ page, request }) => {
  if (!page.isClosed()) await page.close();
  for (const projectId of createdProjectIds) await removeProject(request, projectId);
  createdProjectIds.clear();
  // Let Windows release the final preview/worker handles before the next
  // isolated scenario starts using a fresh project tree.
  await new Promise((resolve) => setTimeout(resolve, 200));
});

test.beforeEach(async ({ request }) => {
  const reset = await request.post('/_e2e/runtime-audit/reset');
  expect(reset.status()).toBe(200);
});

test('isolated fake models support an explicit complete-set generation without outbound calls', async ({ page, request }) => {
  const assetContentRequests = [];
  page.on('request', (candidate) => {
    const url = new URL(candidate.url());
    if (/\/api\/canvas\/assets\/[^/]+\/content$/.test(url.pathname)) {
      assetContentRequests.push(url);
    }
  });
  const catalog = await request.get('/api/canvas/model-providers');
  expect(catalog.ok()).toBeTruthy();
  const providers = await catalog.json();
  const fakeProvider = providers.find((provider) => provider.id === 'e2e-fake-provider');
  expect(fakeProvider).toMatchObject({ enabled: true, availability: 'available' });
  const models = await request.get('/api/canvas/model-providers/e2e-fake-provider/models');
  expect(models.ok()).toBeTruthy();
  expect(await models.json()).toEqual(expect.arrayContaining([
    expect.objectContaining({ id: 'e2e-fake-sync', displayName: 'Fake Sync', availability: 'available', capabilities: expect.objectContaining({ protocol: 'sync' }) }),
    expect.objectContaining({ id: 'e2e-fake-async', displayName: 'Fake Async', availability: 'available', capabilities: expect.objectContaining({ protocol: 'async', supports_cancel: true }) }),
  ]));

  const created = await createProject(request, 'G10 generated complete set');
  const projectId = created.project.id;
  const skuSnapshot = await createSku(request, projectId, created.revision, 'Blue SKU');
  const skuId = skuSnapshot.skus[0].id;
  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-generate')).toBeDisabled();
  const uploaded = await uploadMainProduct(page, projectId);
  await waitForSaved(page);
  const compositionSnapshot = await saveChange(page, projectId, () => (
    page.getByTestId('canvas-composition-group-create').click()
  ));
  const composition = compositionSnapshot.project.semanticState.compositionGroups[0];
  expect(composition).toMatchObject({
    id: 'composition-group-1',
    productLayerIds: [expect.any(String), expect.any(String)],
    skuIds: [skuId],
  });

  for (const type of ['main', 'sku', 'detail']) await page.getByTestId(`canvas-output-${type}`).click();
  const outputs = page.locator('.canvas-output-control');
  await expect(outputs).toHaveCount(3);
  await configureOutput(page, outputs.nth(0), projectId, {
    outputType: 'main', skuId: null, modelId: 'e2e-fake-sync', prompt: 'main product setting', quantity: 1,
    compositionGroupId: composition.id,
  });
  await configureOutput(page, outputs.nth(1), projectId, {
    outputType: 'detail', skuId: null, modelId: 'e2e-fake-sync', prompt: 'detail product setting', quantity: 1,
    compositionGroupId: composition.id,
  });
  await configureOutput(page, outputs.nth(2), projectId, {
    outputType: 'sku', skuId, modelId: 'e2e-fake-async', prompt: 'sku composition [e2e:async]', quantity: 3,
    compositionGroupId: composition.id,
    referenceAssetId: uploaded.working.id,
  });
  await waitForSaved(page);
  await expect(page.getByTestId('canvas-generation-item-count')).toContainText('5');
  const validationMessage = await page.getByTestId('canvas-generation-validation').textContent();
  if (await page.getByTestId('canvas-generate').isDisabled()) {
    const saved = await (await request.get(projectUrl(projectId))).json();
    throw new Error(`generation configuration remained disabled: ${validationMessage}; outputs=${JSON.stringify(saved.project.semanticState.completeSet.outputs)}`);
  }
  await expect(page.getByTestId('canvas-generate')).toBeEnabled();

  const generationCreated = page.waitForResponse((response) => (
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/generations`
  ));
  await page.getByTestId('canvas-generate').click();
  const generationResponse = await generationCreated;
  const generationResponseBody = await generationResponse.text();
  expect(generationResponse.status(), generationResponseBody).toBe(201);
  const generation = JSON.parse(generationResponseBody);
  expect(generationResponse.request().postDataJSON()).toMatchObject({ revision: generation.projectRevision });
  expect(generation).toMatchObject({ totalItems: 5, status: expect.stringMatching(/queued|running/) });
  let terminalGeneration;
  await expect.poll(async () => {
    const response = await request.get(`/api/canvas/generations/${generation.id}`);
    terminalGeneration = await response.json();
    return terminalGeneration.status;
  }, { timeout: 30_000 }).toMatch(/succeeded|partially_failed|failed|cancelled/);
  expect(terminalGeneration.status, JSON.stringify(terminalGeneration)).toBe('succeeded');

  const completed = terminalGeneration;
  expect(completed.items).toHaveLength(5);
  expect(completed.items.filter((item) => item.outputType === 'sku')).toHaveLength(3);
  expect(new Set(completed.items.filter((item) => item.outputType === 'sku').map((item) => item.boardId)).size).toBe(3);
  expect(new Set(completed.items.filter((item) => item.outputType === 'sku').map((item) => item.latestBackgroundAssetId)).size).toBe(3);

  const persisted = await (await request.get(projectUrl(projectId))).json();
  const skuBoards = persisted.project.semanticState.outputBoards.filter((board) => board.skuId === skuId);
  expect(skuBoards).toHaveLength(3);
  expect(new Set(persisted.project.semanticState.completeSet.outputs
    .filter((output) => output.skuId === skuId)
    .map((output) => output.compositionGroupId)).size).toBe(1);

  await page.reload({ waitUntil: 'domcontentloaded' });
  const reviewBoards = [
    persisted.project.semanticState.outputBoards.find((board) => board.outputType === 'main'),
    persisted.project.semanticState.outputBoards.find((board) => board.outputType === 'sku'),
    persisted.project.semanticState.outputBoards.find((board) => board.outputType === 'detail'),
  ];
  expect(reviewBoards.every(Boolean)).toBe(true);
  const boardPicker = page.getByTestId('canvas-result-board-picker');
  await expect(boardPicker.locator('option')).toHaveCount(5);
  for (const board of reviewBoards) {
    await boardPicker.selectOption(board.id);
    const resultCard = page.getByRole('listbox', { name: '选择结果版本' }).getByRole('option').first();
    await expect(resultCard).toBeVisible();
    await resultCard.click();
    await waitForSaved(page);
  }

  await page.getByTestId('canvas-toolbar-export').click();
  const exportPanel = page.getByTestId('canvas-export-panel');
  const exportBoards = exportPanel.locator('input[type="checkbox"]');
  await expect(exportBoards).toHaveCount(3);
  for (let index = 0; index < 3; index += 1) await exportBoards.nth(index).check();
  await exportPanel.locator('[data-export-mode="category_zip"]').click();
  await exportPanel.locator('[data-export-format="png"]').click();
  const exported = page.waitForResponse((response) => (
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/exports`
  ));
  await page.getByTestId('canvas-export-submit').click();
  expect((await exported).status()).toBe(202);
  await expect(page.getByTestId('canvas-export-download')).toBeVisible({ timeout: 30_000 });

  const resultVersions = await request.get(`${projectUrl(projectId)}/result-versions?limit=100`);
  expect(resultVersions.ok()).toBeTruthy();
  expect((await resultVersions.json()).items).toHaveLength(5);
  const audit = await (await request.get('/_e2e/runtime-audit')).json();
  expect(audit.provider).toMatchObject({ submitCount: 5 });
  expect(audit.network).toMatchObject({ scenarioExternalAttemptCount: 0, lifetimeExternalAttemptCount: 0 });
  expect(assetContentRequests.every((url) => url.searchParams.get('variant') === 'preview')).toBe(true);
});

test('persists async progress through refresh and cancels the saved provider task exactly once', async ({ page, request }) => {
  const { projectId } = await configureMainOutput(page, request, {
    name: 'G10 cancellation recovery',
    modelId: 'e2e-fake-async',
    prompt: 'cancel this delayed task [e2e:cancel-delay]',
  });
  const generation = await submitFromPage(page, projectId);
  await waitForGeneration(request, generation.id, (detail) => (
    detail.items[0]?.attempts[0]?.status === 'polling'
  ));

  const cancelled = await request.post(`/api/canvas/generations/${generation.id}/cancel`);
  expect(cancelled.status()).toBe(200);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-generation-status')).toContainText('已取消');
  const terminal = await waitForGeneration(request, generation.id, (detail) => detail.status === 'cancelled');
  expect(terminal.items[0]).toMatchObject({ status: 'cancelled' });
  await expect(page.getByTestId('canvas-generation-status')).toContainText('已取消');
  const audit = await (await request.get('/_e2e/runtime-audit')).json();
  expect(audit.provider).toMatchObject({ submitCount: 1, cancelCount: 1 });
  expect(audit.network).toMatchObject({ scenarioExternalAttemptCount: 0 });
});

test('partially failed item retries once and browser reload pages immutable result versions', async ({ page, request }) => {
  const created = await createProject(request, 'G10 retry versions');
  const projectId = created.project.id;
  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  await uploadMainProduct(page, projectId);
  await waitForSaved(page);
  const compositionSnapshot = await saveChange(page, projectId, () => (
    page.getByTestId('canvas-composition-group-create').click()
  ));
  const composition = compositionSnapshot.project.semanticState.compositionGroups[0];
  await page.getByTestId('canvas-output-main').click();
  await page.getByTestId('canvas-output-detail').click();
  const outputs = page.locator('.canvas-output-control');
  await configureOutput(page, outputs.nth(0), projectId, {
    outputType: 'main', skuId: null, modelId: 'e2e-fake-sync', prompt: 'persistent main', quantity: 1,
    compositionGroupId: composition.id,
  });
  await configureOutput(page, outputs.nth(1), projectId, {
    outputType: 'detail', skuId: null, modelId: 'e2e-fake-sync', prompt: 'retry detail [e2e:fail-once]', quantity: 1,
    compositionGroupId: composition.id,
  });
  await waitForSaved(page);
  const generation = await submitFromPage(page, projectId);
  const partial = await waitForGeneration(request, generation.id, (detail) => detail.status === 'partially_failed');
  const failedItem = partial.items.find((item) => item.status === 'failed');
  expect(failedItem).toBeTruthy();
  expect(partial.items.find((item) => item.status === 'succeeded')).toBeTruthy();

  const retried = await request.post(`/api/canvas/generation-items/${failedItem.id}/retry`);
  expect(retried.status()).toBe(200);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-generation-status')).toContainText('已完成');
  const completed = await waitForGeneration(request, generation.id, (detail) => detail.status === 'succeeded');
  const retriedItem = completed.items.find((item) => item.id === failedItem.id);
  expect(retriedItem).toMatchObject({ status: 'succeeded', attemptCount: 2 });
  expect(retriedItem.attempts.map((attempt) => attempt.status)).toEqual(['failed', 'succeeded']);

  const firstPageResponse = await request.get(`${projectUrl(projectId)}/result-versions?limit=1`);
  expect(firstPageResponse.ok()).toBeTruthy();
  const firstPage = await firstPageResponse.json();
  expect(firstPage.nextCursor).toBeTruthy();
  const secondPageResponse = await request.get(`${projectUrl(projectId)}/result-versions?limit=1&cursor=${encodeURIComponent(firstPage.nextCursor)}`);
  expect(secondPageResponse.ok()).toBeTruthy();
  const secondPage = await secondPageResponse.json();
  const versions = [...firstPage.items, ...secondPage.items];
  expect(versions).toHaveLength(2);
  expect(new Set(versions.map((version) => version.versionId)).size).toBe(2);
  const retryVersion = versions.find((version) => version.itemId === failedItem.id);
  expect(retryVersion).toBeTruthy();
  expect(retryVersion.attemptId).toBe(retriedItem.attempts[1].id);

  let resultVersionRequests = 0;
  await page.route('**/result-versions*', async (route) => {
    resultVersionRequests += 1;
    const url = new URL(route.request().url());
    url.searchParams.set('limit', '1');
    await route.continue({ url: url.toString() });
  });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect.poll(() => resultVersionRequests).toBeGreaterThanOrEqual(2);
  const resultList = page.getByRole('listbox', { name: '选择结果版本' });
  await expect(resultList).toBeVisible();
  const versionCards = resultList.getByRole('option');
  await expect(versionCards).toHaveCount(1);
  const selectableVersionIds = await versionCards.evaluateAll((cards) => (
    cards.map((card) => card.dataset.assetId).filter(Boolean)
  ));
  expect(selectableVersionIds).toHaveLength(1);
  expect(versions.some((version) => version.composedAssetId === selectableVersionIds[0])).toBe(true);
  await versionCards.first().click();
  await waitForSaved(page);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator(`[data-asset-id="${selectableVersionIds[0]}"]`)).toHaveAttribute('aria-selected', 'true');
});

test('unknown submission stays actionable until explicit retry and succeeds without external network', async ({ page, request }) => {
  const { projectId } = await configureMainOutput(page, request, {
    name: 'G10 unknown recovery',
    modelId: 'e2e-fake-sync',
    prompt: 'unknown once [e2e:uncertain-once]',
  });
  const generation = await submitFromPage(page, projectId);
  const unknown = await waitForGeneration(request, generation.id, (detail) => detail.status === 'unknown');
  expect(unknown.items[0]).toMatchObject({ status: 'unknown', attemptCount: 1 });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-generation-status')).toContainText('状态待确认');

  const retried = await request.post(`/api/canvas/generation-items/${unknown.items[0].id}/resolve-unknown`, {
    data: { action: 'retry' },
  });
  expect(retried.status()).toBe(200);
  const completed = await waitForGeneration(request, generation.id, (detail) => detail.status === 'succeeded');
  expect(completed.items[0].attempts.map((attempt) => attempt.status)).toEqual(['unknown', 'succeeded']);
  const audit = await (await request.get('/_e2e/runtime-audit')).json();
  expect(audit.provider).toMatchObject({ submitCount: 2 });
  expect(audit.network).toMatchObject({ scenarioExternalAttemptCount: 0 });
});

test('capacity rejection is safe before generation and the retained intent succeeds after capacity recovers', async ({ page, request }) => {
  const { projectId } = await configureMainOutput(page, request, {
    name: 'G10 capacity rejection',
    modelId: 'e2e-fake-sync',
    prompt: 'capacity protected product',
  });
  await (await request.post('/_e2e/runtime-audit/reset')).json();
  const capacity = await request.post('/_e2e/runtime/capacity', { data: { blocked: true } });
  expect(capacity.status()).toBe(200);
  const rejectedResponse = page.waitForResponse((response) => (
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/generations`
  ));
  await page.getByTestId('canvas-generate').click();
  const rejected = await rejectedResponse;
  expect(rejected.status()).toBe(507);
  await expect(page.getByTestId('canvas-generation-status')).toContainText('存储空间不足');
  const blockedAudit = await (await request.get('/_e2e/runtime-audit')).json();
  expect(blockedAudit.capacity).toMatchObject({ forcedFailure: true });
  expect(blockedAudit.provider).toMatchObject({ submitCount: 0 });

  const restored = await request.post('/_e2e/runtime/capacity', { data: { blocked: false } });
  expect(restored.status()).toBe(200);
  const generation = await submitFromPage(page, projectId);
  const complete = await waitForGeneration(request, generation.id, (detail) => detail.status === 'succeeded');
  expect(complete.items).toHaveLength(1);
  const audit = await (await request.get('/_e2e/runtime-audit')).json();
  expect(audit.capacity).toMatchObject({ forcedFailure: false });
  expect(audit.provider).toMatchObject({ submitCount: 1 });
  expect(audit.network).toMatchObject({ scenarioExternalAttemptCount: 0 });
});

test('double click plus a committed response drop reuses the pending idempotency key after refresh', async ({ page, request }) => {
  const { projectId } = await configureMainOutput(page, request, {
    name: 'G10 dropped client response',
    modelId: 'e2e-fake-async',
    prompt: 'idempotent delayed task [e2e:delay]',
  });
  // Establish the browser-only access proof before exercising a double click.
  const first = await submitFromPage(page, projectId);
  await waitForGeneration(request, first.id, (detail) => detail.status === 'succeeded');
  await (await request.post('/_e2e/runtime-audit/reset')).json();
  await page.getByRole('tab', { name: '生成' }).click();
  const output = page.locator('.canvas-output-control').first();
  await saveChange(page, projectId, async () => {
    const prompt = output.locator('textarea').first();
    await prompt.fill('dropped response [e2e:delay]');
    await prompt.press('Tab');
  });

  let interceptedPosts = 0;
  let committed = null;
  await page.route('**/generations', async (route) => {
    if (route.request().method() !== 'POST' || !route.request().url().includes(`/projects/${projectId}/generations`)) {
      await route.continue();
      return;
    }
    interceptedPosts += 1;
    const upstream = await route.fetch();
    expect(upstream.status()).toBe(201);
    committed = await upstream.json();
    await route.abort('connectionfailed');
  });
  const generateButton = page.getByTestId('canvas-generate');
  await expect(generateButton).toBeVisible();
  // Dispatch both activations in the same browser task. The contextual action
  // correctly disappears as soon as generation starts, so two independent
  // Playwright clicks would make the second one wait on a deliberately hidden
  // control instead of exercising the duplicate-submission guard.
  await generateButton.evaluate((button) => {
    button.click();
    button.click();
  });
  await expect.poll(() => interceptedPosts).toBe(1);
  await expect(page.getByTestId('canvas-generation-status')).toContainText('网络不可用');
  await page.unroute('**/generations');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-generation-status')).toContainText('已完成');

  const replay = page.waitForResponse((response) => (
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/generations`
  ));
  await page.getByRole('tab', { name: '生成' }).click();
  await page.getByTestId('canvas-generate').click();
  const replayResponse = await replay;
  expect(replayResponse.status()).toBe(200);
  expect((await replayResponse.json()).id).toBe(committed.id);
  const complete = await waitForGeneration(request, committed.id, (detail) => detail.status === 'succeeded');
  expect(complete.items).toHaveLength(1);
  const audit = await (await request.get('/_e2e/runtime-audit')).json();
  expect(audit.provider).toMatchObject({ submitCount: 1 });
  expect(audit.network).toMatchObject({ scenarioExternalAttemptCount: 0 });
});

test('saved generated result exports only after explicit board mode and format choices', async ({ page, request }) => {
  const { projectId } = await configureMainOutput(page, request, {
    name: 'X9 explicit browser export',
    modelId: 'e2e-fake-sync',
    prompt: 'exportable product background',
  });
  const generation = await submitFromPage(page, projectId);
  await waitForGeneration(request, generation.id, (detail) => detail.status === 'succeeded');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await waitForSaved(page);
  const resultList = page.getByRole('listbox', { name: '选择结果版本' });
  const resultCard = resultList.getByRole('option').first();
  await expect(resultCard).toBeVisible();
  const composedAssetId = await resultCard.getAttribute('data-asset-id');
  expect(composedAssetId).toBeTruthy();
  await resultCard.click();
  await waitForSaved(page);

  await page.getByTestId('canvas-toolbar-export').click();

  const panel = page.getByTestId('canvas-export-panel');
  const submit = page.getByTestId('canvas-export-submit');
  await expect(panel.locator('input[type="checkbox"]')).toHaveCount(1, { timeout: 30_000 });
  await expect(panel.locator('[data-export-mode][aria-pressed="true"]')).toHaveCount(0);
  await expect(panel.locator('[data-export-format][aria-pressed="true"]')).toHaveCount(0);
  await expect(submit).toBeDisabled();

  await panel.locator('input[type="checkbox"]').check();
  await panel.locator('[data-export-mode="single"]').click();
  await panel.locator('[data-export-format="png"]').click();
  await expect(submit).toBeEnabled();

  const created = page.waitForResponse((response) => (
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/exports`
  ));
  await submit.click();
  const exportResponse = await created;
  const exportBody = await exportResponse.text();
  expect(exportResponse.status(), exportBody).toBe(202);
  expect(JSON.parse(exportBody)).toMatchObject({ operationType: 'export' });

  const download = page.getByTestId('canvas-export-download');
  await expect(download).toBeVisible({ timeout: 30_000 });
  await expect(panel.locator('.canvas-export-feedback')).toHaveText('导出完成');
  const href = await download.getAttribute('href');
  expect(href).toMatch(/\/api\/canvas\/assets\/[^/]+\/download$/);
  const downloaded = await request.get(href);
  expect(downloaded.status()).toBe(200);
  expect(downloaded.headers()['content-type']).toBe('image/png');
  expect(downloaded.headers()['content-disposition']).toContain('attachment');
  expect((await downloaded.body()).subarray(0, 8)).toEqual(
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  );
});
