const { execFileSync } = require('node:child_process');
const zlib = require('node:zlib');
const { test, expect } = require('@playwright/test');

test.setTimeout(60_000);

const createdProjectIds = new Set();

function projectApiUrl(projectId) {
  return `/api/canvas/projects/${encodeURIComponent(projectId)}`;
}

function projectEventsUrl(projectId) {
  return `${projectApiUrl(projectId)}/events`;
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
  const rows = [];
  for (let y = 0; y < height; y += 1) {
    const row = Buffer.alloc(1 + width * 4);
    for (let x = 0; x < width; x += 1) {
      const offset = 1 + x * 4;
      const product = x >= 2 && x <= 5 && y >= 2 && y <= 5;
      row[offset] = product ? 26 : 0;
      row[offset + 1] = product ? 92 : 0;
      row[offset + 2] = product ? 180 : 0;
      row[offset + 3] = product ? 255 : 0;
    }
    rows.push(row);
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

function requestPathMatches(request, pathname) {
  return new URL(request.url()).pathname === pathname;
}

async function installEventSourceAudit(page) {
  await page.addInitScript(() => {
    const NativeEventSource = window.EventSource;
    const records = [];
    let nextId = 1;

    function AuditedEventSource(url, options) {
      const source = new NativeEventSource(url, options);
      const record = {
        id: nextId,
        url: String(url),
        closeCalls: 0,
        source,
      };
      nextId += 1;
      const nativeClose = source.close.bind(source);
      Object.defineProperty(source, 'close', {
        configurable: true,
        value: () => {
          record.closeCalls += 1;
          nativeClose();
        },
      });
      records.push(record);
      return source;
    }

    AuditedEventSource.prototype = NativeEventSource.prototype;
    for (const state of ['CONNECTING', 'OPEN', 'CLOSED']) {
      Object.defineProperty(AuditedEventSource, state, {
        value: NativeEventSource[state],
      });
    }
    Object.defineProperty(window, 'EventSource', {
      configurable: true,
      writable: true,
      value: AuditedEventSource,
    });
    window.__canvasEventSourceAudit = {
      snapshot: () => records.map(record => ({
        id: record.id,
        url: record.url,
        closeCalls: record.closeCalls,
        readyState: record.source.readyState,
      })),
    };
  });
}

async function eventSourceSnapshot(page) {
  return page.evaluate(() => window.__canvasEventSourceAudit.snapshot());
}

function responseMatches(response, method, pathname, status) {
  return response.request().method() === method
    && new URL(response.url()).pathname === pathname
    && (status === undefined || response.status() === status);
}

function projectRow(page, projectId) {
  return page.locator(
    `[data-testid="canvas-project-row"][data-project-id="${projectId}"]`,
  );
}

async function createProjectThroughApi(request, name) {
  const response = await request.post('/api/canvas/projects', { data: { name } });
  expect(response.status()).toBe(201);
  const snapshot = await response.json();
  createdProjectIds.add(snapshot.project.id);
  return snapshot;
}

async function createProjectThroughUi(page, name) {
  const responsePromise = page.waitForResponse(response =>
    responseMatches(response, 'POST', '/api/canvas/projects', 201),
  );
  await page.getByTestId('canvas-project-create-name').fill(name);
  await page.getByTestId('canvas-project-create').click();
  const snapshot = await (await responsePromise).json();
  createdProjectIds.add(snapshot.project.id);
  await expect(page).toHaveURL(new RegExp(`/app/canvas/${snapshot.project.id}$`));
  return snapshot;
}

async function uploadMainProduct(page, projectId) {
  const input = page.getByTestId('canvas-asset-uploader').locator('input[type="file"]');
  await expect(input).toBeEnabled();
  const responsePromise = page.waitForResponse(response => (
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${projectApiUrl(projectId)}/assets`
  ));
  await input.setInputFiles({
    name: 'foundation-product.png', mimeType: 'image/png', buffer: transparentProductPng(),
  });
  const response = await responsePromise;
  expect(response.status()).toBe(201);
  await expect(page.getByRole('tab', { name: '生成' })).toBeVisible();
  await expect(page.getByTestId('canvas-stage-empty')).toBeHidden();
  await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'saved');
  return response.json();
}

async function expectNoHorizontalOverflow(page) {
  const widths = await page.evaluate(() => ({
    document: {
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    },
    body: {
      client: document.body.clientWidth,
      scroll: document.body.scrollWidth,
    },
  }));
  expect(widths.document.scroll).toBeLessThanOrEqual(widths.document.client);
  expect(widths.body.scroll).toBeLessThanOrEqual(widths.body.client);
}

async function removeProject(request, projectId) {
  const projectUrl = projectApiUrl(projectId);
  const current = await request.get(projectUrl);
  if (current.status() === 404) return;
  expect(current.ok(), `load cleanup snapshot for ${projectId}`).toBeTruthy();
  const snapshot = await current.json();
  const deletion = await request.fetch(projectUrl, {
    method: 'DELETE',
    data: { revision: snapshot.revision },
  });
  expect(deletion.ok(), `delete cleanup project ${projectId}`).toBeTruthy();
  await expect.poll(async () => (await request.get(projectUrl)).status()).toBe(404);
}

test.afterEach(async ({ page, request }) => {
  if (!page.isClosed()) await page.close();
  for (const projectId of createdProjectIds) {
    await removeProject(request, projectId);
  }
  createdProjectIds.clear();
});

test('E2E server isolates Canvas files before application import', () => {
  const probe = [
    'import json, os',
    'from pathlib import Path',
    'import scripts.e2e_server as server',
    'import config',
    'print(json.dumps({',
    '  "root": str(server.ROOT.resolve()),',
    '  "expected": str((server.ROOT / "canvas-data").resolve()),',
    '  "environment": str(Path(os.environ["CANVAS_DATA_DIR"]).resolve()),',
    '  "configured": str(Path(config.CANVAS_DATA_DIR).resolve()),',
    '}))',
  ].join('\n');

  const result = JSON.parse(
    execFileSync('python', ['-c', probe], { encoding: 'utf8' }).trim(),
  );
  expect(result.environment).toBe(result.expected);
  expect(result.configured).toBe(result.expected);
});

test('AI work opens an empty Canvas and creation selects a real project URL', async ({ page }) => {
  const appResponse = await page.goto('/app', { waitUntil: 'domcontentloaded' });
  expect(appResponse?.ok()).toBeTruthy();

  const canvasEntry = page.getByRole('link', { name: '产品视觉画布' });
  await expect(canvasEntry).toBeVisible();
  await canvasEntry.click();
  await expect(page).toHaveURL(/\/app\/canvas$/);
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'false');
  await expect(page.getByTestId('canvas-project-row')).toHaveCount(0);

  for (const outputType of ['main', 'sku', 'detail']) {
    await expect(page.getByTestId(`canvas-output-${outputType}`)).toHaveAttribute('aria-pressed', 'false');
  }

  const snapshot = await createProjectThroughUi(page, '入口项目');
  const projectId = snapshot.project.id;

  await expect(page).toHaveURL(new RegExp(`/app/canvas/${projectId}$`));
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');
  expect(snapshot.project.semanticState.completeSet.selectedOutputTypes).toEqual([]);
  expect(snapshot.project.semanticState.outputBoards).toEqual([]);
  for (const outputType of ['main', 'sku', 'detail']) {
    await expect(page.getByTestId(`canvas-output-${outputType}`)).toHaveAttribute('aria-pressed', 'false');
  }
});

test('project lifecycle supports rename, search, switch, archive, restore and delete', async ({ page, request }) => {
  await page.goto('/app/canvas', { waitUntil: 'domcontentloaded' });
  const alpha = await createProjectThroughUi(page, 'Alpha 项目');
  const beta = await createProjectThroughUi(page, 'Beta 项目');
  const alphaId = alpha.project.id;
  const betaId = beta.project.id;

  const renameResponse = page.waitForResponse(response =>
    responseMatches(response, 'PATCH', projectApiUrl(betaId), 200),
  );
  await projectRow(page, betaId).locator('summary').click();
  await projectRow(page, betaId).getByTestId('canvas-project-rename-start').click();
  await projectRow(page, betaId).getByTestId('canvas-project-rename').fill('Beta 已重命名');
  await projectRow(page, betaId).getByTestId('canvas-project-rename-save').click();
  const renamed = await (await renameResponse).json();
  expect(renamed.project.name).toBe('Beta 已重命名');
  await expect(projectRow(page, betaId).getByRole('button', { name: 'Beta 已重命名' })).toBeVisible();

  const searchInput = page.getByTestId('canvas-project-search');
  const alphaSearch = page.waitForResponse(response => {
    const url = new URL(response.url());
    return response.request().method() === 'GET'
      && url.pathname === '/api/canvas/projects'
      && url.searchParams.get('q') === 'Alpha 项目';
  });
  await searchInput.fill('Alpha 项目');
  await alphaSearch;
  await expect(projectRow(page, alphaId)).toBeVisible();
  await expect(projectRow(page, betaId)).toHaveCount(0);

  const clearSearch = page.waitForResponse(response => {
    const url = new URL(response.url());
    return response.request().method() === 'GET'
      && url.pathname === '/api/canvas/projects'
      && !url.searchParams.has('q');
  });
  await searchInput.fill('');
  await clearSearch;
  await expect(projectRow(page, betaId)).toBeVisible();

  const switchResponse = page.waitForResponse(response =>
    responseMatches(response, 'GET', projectApiUrl(alphaId), 200),
  );
  await projectRow(page, alphaId).getByTestId('canvas-project-switch').click();
  await switchResponse;
  await expect(page).toHaveURL(new RegExp(`/app/canvas/${alphaId}$`));
  await expect(projectRow(page, alphaId)).toHaveClass(/is-active/);

  const archiveResponse = page.waitForResponse(response =>
    responseMatches(response, 'POST', `${projectApiUrl(alphaId)}/archive`, 200),
  );
  await projectRow(page, alphaId).locator('summary').click();
  await projectRow(page, alphaId).getByTestId('canvas-project-archive').click();
  const archived = await (await archiveResponse).json();
  expect(archived.project.status).toBe('archived');
  await expect(page).toHaveURL(/\/app\/canvas$/);
  await expect(projectRow(page, alphaId)).toHaveCount(0);

  const archivedListResponse = page.waitForResponse(response => {
    const url = new URL(response.url());
    return response.request().method() === 'GET'
      && url.pathname === '/api/canvas/projects'
      && url.searchParams.get('includeArchived') === 'true';
  });
  await page.getByRole('checkbox', { name: '显示已归档' }).check();
  await archivedListResponse;
  await projectRow(page, alphaId).locator('summary').click();
  await expect(projectRow(page, alphaId).getByTestId('canvas-project-restore')).toBeVisible();

  const restoreResponse = page.waitForResponse(response =>
    responseMatches(response, 'POST', `${projectApiUrl(alphaId)}/restore`, 200),
  );
  await projectRow(page, alphaId).getByTestId('canvas-project-restore').click();
  const restored = await (await restoreResponse).json();
  expect(restored.project.status).toBe('active');
  await projectRow(page, alphaId).locator('summary').click();
  await expect(projectRow(page, alphaId).getByTestId('canvas-project-archive')).toBeVisible();

  await projectRow(page, betaId).locator('summary').click();
  await projectRow(page, betaId).getByTestId('canvas-project-delete').click();
  await expect(page.getByRole('dialog', { name: '确认删除项目' })).toBeVisible();
  const deleteResponse = page.waitForResponse(response =>
    responseMatches(response, 'DELETE', projectApiUrl(betaId), 200),
  );
  await page.getByTestId('canvas-delete-confirm-submit').click();
  const deleting = await (await deleteResponse).json();
  expect(deleting.project.status).toBe('deleting');
  await expect.poll(async () => (await request.get(projectApiUrl(betaId))).status()).toBe(404);
  createdProjectIds.delete(betaId);
  await expect(projectRow(page, betaId)).toHaveCount(0);
});

test('switching projects closes the old EventSource exactly once and leaves one active', async ({ page, request }) => {
  const alpha = await createProjectThroughApi(request, 'SSE 切换 A');
  const beta = await createProjectThroughApi(request, 'SSE 切换 B');
  const alphaId = alpha.project.id;
  const betaId = beta.project.id;
  await installEventSourceAudit(page);

  await page.goto(`/app/canvas/${alphaId}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');
  await expect.poll(async () => (await eventSourceSnapshot(page)).length).toBe(1);

  const switchResponse = page.waitForResponse(response =>
    responseMatches(response, 'GET', projectApiUrl(betaId), 200),
  );
  await projectRow(page, betaId).getByTestId('canvas-project-switch').click();
  await switchResponse;
  await expect(page).toHaveURL(new RegExp(`/app/canvas/${betaId}$`));
  await expect.poll(async () => (await eventSourceSnapshot(page)).length).toBe(2);

  const audit = await eventSourceSnapshot(page);
  const alphaSource = audit.find(record =>
    new URL(record.url, 'http://canvas.test').pathname === projectEventsUrl(alphaId),
  );
  const betaSource = audit.find(record =>
    new URL(record.url, 'http://canvas.test').pathname === projectEventsUrl(betaId),
  );
  expect(alphaSource).toMatchObject({ closeCalls: 1, readyState: 2 });
  expect(betaSource).toMatchObject({ closeCalls: 0 });
  expect(audit.filter(record => record.closeCalls === 0)).toHaveLength(1);
});

test('EventSource reconnects after a network failure and refreshes an externally renamed project', async ({ page, request }) => {
  const created = await createProjectThroughApi(request, 'SSE 重连项目');
  const projectId = created.project.id;
  const eventsPath = projectEventsUrl(projectId);
  let routedAttempts = 0;
  let observedRequests = 0;
  await installEventSourceAudit(page);
  await page.route(
    url => url.pathname === eventsPath,
    async route => {
      routedAttempts += 1;
      if (routedAttempts === 1) {
        await route.abort('connectionrefused');
        return;
      }
      await route.continue();
    },
  );

  const reconnectRequest = page.waitForRequest(browserRequest => {
    if (!requestPathMatches(browserRequest, eventsPath)) return false;
    observedRequests += 1;
    return observedRequests === 2;
  });
  const reconnectResponse = page.waitForResponse(response =>
    requestPathMatches(response.request(), eventsPath) && response.status() === 200,
  );
  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');
  await reconnectRequest;
  await reconnectResponse;
  expect(routedAttempts).toBeGreaterThanOrEqual(2);
  await expect.poll(async () => {
    const audit = await eventSourceSnapshot(page);
    return audit.length === 1 ? audit[0].readyState : -1;
  }).toBe(1);
  expect(await eventSourceSnapshot(page)).toEqual([
    expect.objectContaining({ closeCalls: 0, readyState: 1 }),
  ]);

  const remoteName = 'SSE 外部更新名称';
  const refreshResponse = page.waitForResponse(response =>
    responseMatches(response, 'GET', projectApiUrl(projectId), 200),
  );
  const external = await request.patch(projectApiUrl(projectId), {
    data: { revision: created.revision, name: remoteName },
  });
  expect(external.status()).toBe(200);
  await refreshResponse;
  await expect(projectRow(page, projectId).getByTestId('canvas-project-switch')).toHaveText(remoteName);

  await expect.poll(async () => (await eventSourceSnapshot(page)).length).toBe(2);
  const audit = await eventSourceSnapshot(page);
  expect(audit[0]).toMatchObject({ closeCalls: 1, readyState: 2 });
  expect(audit[1]).toMatchObject({ closeCalls: 0 });
  expect(audit.filter(record => record.closeCalls === 0)).toHaveLength(1);
});

test('complete-set and advanced round-trip preserves prompt, nodes and layout after autosave reload', async ({ page, request }) => {
  const created = await createProjectThroughApi(request, '往返持久化项目');
  const projectId = created.project.id;
  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');
  await uploadMainProduct(page, projectId);
  await page.getByRole('tab', { name: '生成' }).click();

  const savedResponse = page.waitForResponse(response =>
    responseMatches(response, 'PUT', `${projectApiUrl(projectId)}/state`, 200),
  );
  await page.getByTestId('canvas-output-main').click();
  await page.getByRole('spinbutton', { name: '主图数量' }).fill('2');
  const mainPrompt = page.getByRole('textbox', { name: '主图提示词' });
  await expect(mainPrompt).toBeEditable();
  await mainPrompt.fill('保留这段主图提示词');
  await expect(mainPrompt).toHaveValue('保留这段主图提示词');
  await page.getByTestId('canvas-mode').selectOption('advanced');
  await page.getByRole('button', { name: '添加 prompt' }).click();
  await page.getByTestId('canvas-mode').selectOption('complete-set');
  await expect(page.getByRole('textbox', { name: '主图提示词' })).toHaveValue('保留这段主图提示词');
  await page.getByTestId('canvas-mode').selectOption('advanced');

  const saved = await (await savedResponse).json();
  await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'saved');
  expect(saved.project.semanticState.mode).toBe('advanced');
  expect(saved.project.semanticState.completeSet.selectedOutputTypes).toEqual(['main']);
  expect(saved.project.semanticState.completeSet.outputs).toEqual([
    expect.objectContaining({
      outputType: 'main',
      quantity: 2,
      prompt: '保留这段主图提示词',
    }),
  ]);
  expect(saved.project.semanticState.nodes).toEqual(expect.arrayContaining([
    expect.objectContaining({
      id: 'complete-set:main:output',
      prompt: '保留这段主图提示词',
    }),
    expect.objectContaining({
      id: 'advanced:prompt:1',
      kind: 'prompt',
      prompt: '',
    }),
  ]));
  expect(saved.project.layoutState.nodePositions['advanced:prompt:1']).toEqual({ x: 144, y: 120 });

  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-mode')).toHaveValue('advanced');
  const reloadSave = page.waitForResponse(response =>
    responseMatches(response, 'PUT', `${projectApiUrl(projectId)}/state`, 200),
  );
  await page.getByTestId('canvas-mode').selectOption('complete-set');
  await expect(page.getByTestId('canvas-output-main')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('spinbutton', { name: '主图数量' })).toHaveValue('2');
  await expect(page.getByRole('textbox', { name: '主图提示词' })).toHaveValue('保留这段主图提示词');
  await page.getByTestId('canvas-mode').selectOption('advanced');
  const reloaded = await (await reloadSave).json();
  expect(reloaded.project.semanticState.nodes).toEqual(expect.arrayContaining([
    expect.objectContaining({ id: 'advanced:prompt:1', prompt: '' }),
  ]));
  expect(reloaded.project.layoutState.nodePositions['advanced:prompt:1']).toEqual({ x: 144, y: 120 });
  await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'saved');
});

test('a real stale revision returns 409 and leaves the local edit in conflict', async ({ page, request }) => {
  const created = await createProjectThroughApi(request, '冲突项目');
  const projectId = created.project.id;
  await page.route(/\/api\/canvas\/projects\/[^/]+\/events(?:\?|$)/, route => route.abort());
  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');
  await uploadMainProduct(page, projectId);
  await page.getByRole('tab', { name: '生成' }).click();

  const beforeExternal = await (await request.get(projectApiUrl(projectId))).json();
  const external = await request.patch(projectApiUrl(projectId), {
    data: { revision: beforeExternal.revision, name: '外部已更新项目' },
  });
  expect(external.status()).toBe(200);
  const externalSnapshot = await external.json();
  expect(externalSnapshot.revision).toBe(beforeExternal.revision + 1);

  const staleSave = page.waitForResponse(response =>
    responseMatches(response, 'PUT', `${projectApiUrl(projectId)}/state`, 409),
  );
  await page.getByTestId('canvas-output-detail').click();
  const conflictResponse = await staleSave;
  const conflict = await conflictResponse.json();
  expect(conflict).toMatchObject({
    code: 'canvas_revision_conflict',
    currentRevision: externalSnapshot.revision,
  });
  await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'conflict');
  await expect(page.getByTestId('canvas-save-status')).toContainText('检测到版本冲突');
  await expect(page.getByTestId('canvas-output-detail')).toHaveAttribute('aria-pressed', 'true');

  const authoritative = await request.get(projectApiUrl(projectId));
  expect(authoritative.ok()).toBeTruthy();
  const persisted = await authoritative.json();
  expect(persisted.project.name).toBe('外部已更新项目');
  expect(persisted.project.semanticState.completeSet.selectedOutputTypes).toEqual([]);
});

for (const viewportCase of [
  { name: 'desktop', width: 1440, height: 900 },
]) {
  test(`${viewportCase.name} pan and zoom persist without document overflow`, async ({ page, request }) => {
    await page.setViewportSize({ width: viewportCase.width, height: viewportCase.height });
    const created = await createProjectThroughApi(request, `${viewportCase.name} 视口项目`);
    const projectId = created.project.id;
    await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');
    await expectNoHorizontalOverflow(page);
    await uploadMainProduct(page, projectId);

    const stageBox = await page.getByTestId('canvas-stage').boundingBox();
    expect(stageBox).not.toBeNull();
    const startX = stageBox.x + Math.min(120, stageBox.width / 3);
    const startY = stageBox.y + Math.min(100, stageBox.height / 3);
    const endX = Math.min(stageBox.x + stageBox.width - 12, startX + 58);
    const endY = Math.min(stageBox.y + stageBox.height - 12, startY + 34);

    const savedResponse = page.waitForResponse(response =>
      responseMatches(response, 'PUT', `${projectApiUrl(projectId)}/state`, 200),
    );
    await page.keyboard.down('Alt');
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(endX, endY, { steps: 4 });
    await page.mouse.up();
    await page.keyboard.up('Alt');
    await page.mouse.wheel(0, -300);

    const saved = await (await savedResponse).json();
    const viewport = saved.project.layoutState.viewport;
    expect(Math.abs(viewport.x) + Math.abs(viewport.y)).toBeGreaterThan(0);
    expect(viewport.zoom).toBeGreaterThan(1);
    await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'saved');

    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');
    await expect(page.getByTestId('canvas-zoom-readout')).toHaveText(
      `${Math.round(viewport.zoom * 100)}%`,
    );
    const reloaded = await request.get(projectApiUrl(projectId));
    expect(reloaded.ok()).toBeTruthy();
    expect((await reloaded.json()).project.layoutState.viewport).toEqual(viewport);
    await expectNoHorizontalOverflow(page);
  });
}

test('1100px uses accessible project and inspector drawers without horizontal overflow', async ({ page, request }) => {
  await page.setViewportSize({ width: 1100, height: 820 });
  const created = await createProjectThroughApi(request, '抽屉布局项目');
  const projectId = created.project.id;
  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  await expectNoHorizontalOverflow(page);

  const projectsToggle = page.getByTestId('canvas-toggle-projects');
  await expect(projectsToggle).toBeVisible();
  await projectsToggle.click();
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-projects-open', 'true');
  await expect(page.getByTestId('canvas-project-sidebar')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-projects-open', 'false');
  await expect(projectsToggle).toBeFocused();

  await uploadMainProduct(page, projectId);
  const inspectorToggle = page.getByTestId('canvas-toggle-inspector');
  await inspectorToggle.click();
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-inspector-open', 'true');
  await expect(page.getByTestId('canvas-properties')).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

for (const viewportCase of [
  { name: 'tablet gate', width: 800, height: 900 },
  { name: 'mobile gate', width: 390, height: 844 },
]) {
  test(`${viewportCase.name} shows only the desktop guidance and restores the project after resize`, async ({ page, request }) => {
    await page.setViewportSize({ width: viewportCase.width, height: viewportCase.height });
    const created = await createProjectThroughApi(request, `${viewportCase.name} 项目`);
    await page.goto(`/app/canvas/${created.project.id}`, { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', { name: '请使用桌面端打开产品视觉画布' })).toBeVisible();
    await expect(page.getByRole('link', { name: '返回 AI 工作台' })).toBeVisible();
    await expect(page.getByTestId('canvas-workspace')).toBeHidden();
    await expectNoHorizontalOverflow(page);

    await page.setViewportSize({ width: 1100, height: 820 });
    await expect(page.getByTestId('canvas-workspace')).toBeVisible();
    await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-active-project-id', created.project.id);
  });
}
