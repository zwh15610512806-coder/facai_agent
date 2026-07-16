const crypto = require('node:crypto');
const zlib = require('node:zlib');

const { test, expect } = require('@playwright/test');


const PROVIDER_KEY_ENV_ALIASES = [
  'DEEPSEEK_API_KEY',
  'ARK_API_KEY',
  'DOUBAO_API_KEY',
  'MINIMAX_API_KEY',
  'GLM_API_KEY',
  'ZAI_API_KEY',
  'QWEN_API_KEY',
  'DASHSCOPE_API_KEY',
  'EMBEDDING_API_KEY',
];
const EFFECTIVE_PROVIDER_KEYS = [
  'DEEPSEEK_API_KEY',
  'ARK_API_KEY',
  'DOUBAO_API_KEY',
  'MINIMAX_API_KEY',
  'GLM_API_KEY',
  'QWEN_API_KEY',
  'EMBEDDING_API_KEY',
];
const TERMINAL_OPERATION_STATUSES = new Set([
  'cancelled',
  'failed',
  'interrupted',
  'succeeded',
]);
const createdProjects = new Map();
const IDENTITY_LAYOUT = {
  slot: { x: 0, y: 0, width: 1, height: 1 },
  anchor: { x: 0.5, y: 0.5 },
  baseline: 0.5,
  relativeProductFraction: 1,
  contain: true,
  safeArea: { top: 0, right: 0, bottom: 0, left: 0 },
  rotation: 0,
};
const IDENTITY_LAYOUT_HASH = 'sha256:2c14ea8e8c9481a4e2b21582739fb0e8800fbf6d836d01e0c2098dcacdaf2169';


function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
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


function makePng({ width = 8, height = 8, alpha = false, pixel }) {
  const channels = alpha ? 4 : 3;
  const rows = [];
  for (let y = 0; y < height; y += 1) {
    const row = Buffer.alloc(1 + width * channels);
    row[0] = 0;
    for (let x = 0; x < width; x += 1) {
      const color = pixel(x, y);
      if (!Array.isArray(color) || color.length !== channels) {
        throw new Error('PNG pixel has an invalid channel count');
      }
      for (let channel = 0; channel < channels; channel += 1) {
        row[1 + x * channels + channel] = color[channel];
      }
    }
    rows.push(row);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = alpha ? 6 : 2;
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk('IHDR', ihdr),
    pngChunk('IDAT', zlib.deflateSync(Buffer.concat(rows), { level: 9 })),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}


function paethPredictor(left, above, upperLeft) {
  const prediction = left + above - upperLeft;
  const leftDistance = Math.abs(prediction - left);
  const aboveDistance = Math.abs(prediction - above);
  const diagonalDistance = Math.abs(prediction - upperLeft);
  if (leftDistance <= aboveDistance && leftDistance <= diagonalDistance) return left;
  return aboveDistance <= diagonalDistance ? above : upperLeft;
}


function decodePng(buffer) {
  expect(buffer.subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  let offset = 8;
  let width = 0;
  let height = 0;
  let colorType = null;
  const compressed = [];
  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString('ascii', offset + 4, offset + 8);
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    offset += 12 + length;
    if (type === 'IHDR') {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      expect(data[8]).toBe(8);
      colorType = data[9];
      expect(data[12]).toBe(0);
    } else if (type === 'IDAT') {
      compressed.push(data);
    } else if (type === 'IEND') {
      break;
    }
  }
  const channels = colorType === 6 ? 4 : colorType === 2 ? 3 : 0;
  expect(channels, `unsupported PNG color type ${colorType}`).toBeGreaterThan(0);
  const inflated = zlib.inflateSync(Buffer.concat(compressed));
  const stride = width * channels;
  expect(inflated.length).toBe((stride + 1) * height);
  const pixels = Buffer.alloc(stride * height);
  let sourceOffset = 0;
  for (let y = 0; y < height; y += 1) {
    const filter = inflated[sourceOffset];
    sourceOffset += 1;
    for (let index = 0; index < stride; index += 1) {
      const encoded = inflated[sourceOffset + index];
      const left = index >= channels ? pixels[y * stride + index - channels] : 0;
      const above = y > 0 ? pixels[(y - 1) * stride + index] : 0;
      const upperLeft = y > 0 && index >= channels
        ? pixels[(y - 1) * stride + index - channels]
        : 0;
      let value;
      switch (filter) {
        case 0: value = encoded; break;
        case 1: value = encoded + left; break;
        case 2: value = encoded + above; break;
        case 3: value = encoded + Math.floor((left + above) / 2); break;
        case 4: value = encoded + paethPredictor(left, above, upperLeft); break;
        default: throw new Error(`unsupported PNG filter ${filter}`);
      }
      pixels[y * stride + index] = value & 0xff;
    }
    sourceOffset += stride;
  }
  return {
    width,
    height,
    channels,
    pixelAt: (x, y) => {
      const start = y * stride + x * channels;
      const values = [...pixels.subarray(start, start + channels)];
      return channels === 4 ? values : [...values, 255];
    },
  };
}


function transparentProductPng() {
  return makePng({
    alpha: true,
    pixel: (x, y) => (
      x >= 2 && x <= 5 && y >= 2 && y <= 5
        ? [24 + x, 80 + y, 160, 255]
        : [0, 0, 0, 0]
    ),
  });
}


function whiteProductPng() {
  return makePng({
    pixel: (x, y) => (
      x >= 2 && x <= 5 && y >= 2 && y <= 5
        ? [24 + x, 80 + y, 160]
        : [255, 255, 255]
    ),
  });
}


function complexProductPng() {
  return makePng({
    pixel: (x, y) => (
      x >= 2 && x <= 5 && y >= 2 && y <= 5
        ? [180, 40 + x, 20 + y]
        : [32 + x * 3, 48 + y * 5, 64 + ((x + y) % 3) * 7]
    ),
  });
}


function failOnceProductPng() {
  return makePng({
    pixel: (x, y) => (
      x >= 2 && x <= 5 && y >= 2 && y <= 5
        ? [28 + x, 104 + y, 196]
        : [255, 0, 255]
    ),
  });
}


function projectUrl(projectId) {
  return `/api/canvas/projects/${encodeURIComponent(projectId)}`;
}


function operationUrl(operationId) {
  return `/api/canvas/operations/${encodeURIComponent(operationId)}`;
}


function trackProject(projectId) {
  createdProjects.set(projectId, new Set());
}


function trackOperation(projectId, operationId) {
  const operations = createdProjects.get(projectId);
  if (operations === undefined) throw new Error(`untracked project ${projectId}`);
  operations.add(operationId);
}


async function createProject(request, name) {
  const response = await request.post('/api/canvas/projects', { data: { name } });
  expect(response.status()).toBe(201);
  const snapshot = await response.json();
  trackProject(snapshot.project.id);
  return snapshot;
}


async function seedBackground(request, projectId, color) {
  const response = await request.post(`/_e2e/projects/${encodeURIComponent(projectId)}/seed-background`, {
    data: { width: 8, height: 8, color },
  });
  expect(response.status()).toBe(201);
  return response.json();
}


async function createSku(request, projectId, revision, name) {
  const response = await request.post(`${projectUrl(projectId)}/skus`, {
    data: { revision, name, referenceAssetId: null, prompt: '', config: {} },
  });
  expect(response.status()).toBe(201);
  return response.json();
}


function canvasNode(id, kind, patch = {}) {
  return {
    id,
    kind,
    managedBy: null,
    skuId: null,
    assetId: null,
    modelProfileId: null,
    prompt: null,
    compositionGroupId: null,
    textSnapshotId: null,
    outputBoardId: null,
    parameters: {},
    ...patch,
  };
}


async function saveProjectState(request, snapshot, semanticState, layoutState) {
  const response = await request.put(`${projectUrl(snapshot.project.id)}/state`, {
    data: {
      revision: snapshot.revision,
      semanticState,
      layoutState,
    },
  });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}


function sharedSkuState({ snapshot, workingAssetId, skuId, backgroundIds }) {
  const groupId = 'shared-product-composition';
  const mainLayerId = 'main-product';
  const skuLayerId = `sku-product-${skuId}`;
  return {
    semanticState: {
      nodes: [
        canvasNode('main-product-source', 'product_source', {
          assetId: workingAssetId,
        }),
        canvasNode('main-product-cutout', 'auto_cutout', {
          assetId: workingAssetId,
        }),
        canvasNode('output-main', 'main_output', {
          prompt: 'main prompt remains independent',
          modelProfileId: 'model-main',
          compositionGroupId: groupId,
          outputBoardId: 'board-main',
        }),
        canvasNode('output-sku', 'sku_output', {
          skuId,
          prompt: 'sku prompt remains independent',
          modelProfileId: 'model-sku',
          compositionGroupId: groupId,
          outputBoardId: 'board-sku',
        }),
      ],
      edges: [{
        id: 'main-product-source-cutout',
        kind: 'product_asset',
        sourceNodeId: 'main-product-source',
        sourcePort: 'product',
        targetNodeId: 'main-product-cutout',
        targetPort: 'reference',
        skuId: null,
      }],
      outputBoards: [
        {
          id: 'board-main',
          outputNodeId: 'output-main',
          outputType: 'main',
          skuId: null,
          sortOrder: 0,
          selectedResultAssetId: null,
        },
        {
          id: 'board-sku',
          outputNodeId: 'output-sku',
          outputType: 'sku',
          skuId,
          sortOrder: 1,
          selectedResultAssetId: null,
        },
      ],
      mode: 'complete-set',
      advancedCustomized: false,
      completeSet: {
        selectedOutputTypes: ['main', 'sku'],
        outputs: [
          {
            outputType: 'main',
            skuId: null,
            quantity: 1,
            aspectRatio: '1:1',
            width: 8,
            height: 8,
            prompt: 'main prompt remains independent',
            modelProfileId: 'model-main',
            modelParameters: { lighting: 'main-light' },
            referenceAssetId: workingAssetId,
            compositionGroupId: groupId,
          },
          {
            outputType: 'sku',
            skuId,
            quantity: 1,
            aspectRatio: '1:1',
            width: 8,
            height: 8,
            prompt: 'sku prompt remains independent',
            modelProfileId: 'model-sku',
            modelParameters: { lighting: 'sku-light' },
            referenceAssetId: workingAssetId,
            compositionGroupId: groupId,
          },
        ],
      },
      compositionGroups: [{
        id: groupId,
        skuIds: [skuId],
        productLayerIds: [mainLayerId, skuLayerId],
        layoutHash: IDENTITY_LAYOUT_HASH,
        layout: structuredClone(IDENTITY_LAYOUT),
      }],
    },
    layoutState: {
      nodePositions: {
        'main-product-source': { x: 100, y: 120 },
        'main-product-cutout': { x: 300, y: 120 },
        'output-main': { x: 520, y: 100 },
        'output-sku': { x: 520, y: 260 },
      },
      objectTransforms: {
        'transform-main': { x: 0.5, y: 0.5, scale: 1, rotation: 0 },
        'transform-sku': { x: 0.5, y: 0.5, scale: 1, rotation: 0 },
      },
      viewport: structuredClone(snapshot.project.layoutState.viewport),
      productLayers: [
        {
          id: mainLayerId,
          sourceAssetId: workingAssetId,
          renderAssetId: workingAssetId,
          allowOpaqueFallback: false,
          skuId: null,
          compositionGroupId: groupId,
          transformId: 'transform-main',
          locked: true,
        },
        {
          id: skuLayerId,
          sourceAssetId: workingAssetId,
          renderAssetId: workingAssetId,
          allowOpaqueFallback: false,
          skuId,
          compositionGroupId: groupId,
          transformId: 'transform-sku',
          locked: true,
        },
      ],
      textSnapshots: [],
    },
  };
}


function authoritativeComposeState({ snapshot, workingAssetId, backgroundAssetId, textBand = null }) {
  const groupId = 'identity-main-composition';
  const textNode = textBand === null
    ? []
    : [canvasNode('text-main', 'text_layer', {
      textSnapshotId: 'text-main-snapshot',
      outputBoardId: 'board-main',
    })];
  const textSnapshots = textBand === null
    ? []
    : [{
      id: 'text-main-snapshot',
      nodeId: 'text-main',
      content: 'X',
      fontAssetId: null,
      fontFamily: 'Noto Sans CJK SC',
      fontVersion: 'sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b',
      boxWidth: 8,
      lines: [{ text: 'X', x: 1, y: 0, width: 7 }],
      fontSize: 8,
      color: '#ff0000',
      letterSpacing: 0,
      lineHeight: 1,
      align: 'left',
      baseline: 'top',
      zBand: textBand,
      sortOrder: 0,
    }];
  return {
    semanticState: {
      nodes: [
        canvasNode('main-product-source', 'product_source', {
          assetId: workingAssetId,
        }),
        canvasNode('main-product-cutout', 'auto_cutout', {
          assetId: workingAssetId,
        }),
        canvasNode('output-main', 'main_output', {
          compositionGroupId: groupId,
          outputBoardId: 'board-main',
        }),
        ...textNode,
      ],
      edges: [{
        id: 'main-product-source-cutout',
        kind: 'product_asset',
        sourceNodeId: 'main-product-source',
        sourcePort: 'product',
        targetNodeId: 'main-product-cutout',
        targetPort: 'reference',
        skuId: null,
      }],
      outputBoards: [{
        id: 'board-main',
        outputNodeId: 'output-main',
        outputType: 'main',
        skuId: null,
        sortOrder: 0,
        selectedResultAssetId: null,
      }],
      mode: 'complete-set',
      advancedCustomized: false,
      completeSet: {
        selectedOutputTypes: ['main'],
        outputs: [{
          outputType: 'main',
          skuId: null,
          quantity: 1,
          aspectRatio: '1:1',
          width: 8,
          height: 8,
          prompt: 'authoritative compose only',
          modelProfileId: 'model-compose-main',
          modelParameters: { lighting: 'neutral' },
          referenceAssetId: workingAssetId,
          compositionGroupId: groupId,
        }],
      },
      compositionGroups: [{
        id: groupId,
        skuIds: [],
        productLayerIds: ['main-product'],
        layoutHash: IDENTITY_LAYOUT_HASH,
        layout: structuredClone(IDENTITY_LAYOUT),
      }],
    },
    layoutState: {
      nodePositions: {
        'main-product-source': { x: 100, y: 120 },
        'main-product-cutout': { x: 300, y: 120 },
        'output-main': { x: 520, y: 120 },
        ...(textBand === null ? {} : { 'text-main': { x: 300, y: 300 } }),
      },
      objectTransforms: {
        'transform-main': { x: 0.5, y: 0.5, scale: 1, rotation: 0 },
      },
      viewport: structuredClone(snapshot.project.layoutState.viewport),
      productLayers: [{
        id: 'main-product',
        sourceAssetId: workingAssetId,
        renderAssetId: workingAssetId,
        allowOpaqueFallback: false,
        skuId: null,
        compositionGroupId: groupId,
        transformId: 'transform-main',
        locked: true,
      }],
      textSnapshots,
    },
  };
}


async function enqueueCompose(request, projectId, revision, backgroundAssetId, idempotencyKey) {
  const response = await request.post(`${projectUrl(projectId)}/compose`, {
    data: {
      revision,
      boardId: 'board-main',
      backgroundAssetId,
      idempotencyKey,
    },
  });
  expect(response.status(), await response.text()).toBe(202);
  const operation = await response.json();
  trackOperation(projectId, operation.id);
  return waitForOperation(request, operation.id, 'succeeded');
}


async function assetBytes(request, assetId) {
  const response = await request.get(`/api/canvas/assets/${encodeURIComponent(assetId)}/content`);
  expect(response.ok(), `download asset ${assetId}`).toBeTruthy();
  return response.body();
}


function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}


function expectedFakeMaskAlpha(x, y, width, height) {
  const left = Math.floor(width / 4);
  const right = width - left;
  const top = Math.floor(height / 4);
  const bottom = height - top;
  return x >= left && x < right && y >= top && y < bottom ? 255 : 0;
}


async function expectOpaqueCutoutFidelity({
  page,
  request,
  projectId,
  originalBytes,
  upload,
  terminal,
}) {
  await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'saved');
  const assetsResponse = await request.get(`${projectUrl(projectId)}/assets`);
  expect(assetsResponse.ok()).toBeTruthy();
  const assets = (await assetsResponse.json()).assets;
  const source = assets.find((asset) => asset.id === upload.source.id);
  const working = assets.find((asset) => asset.id === upload.working.id);
  const cutout = assets.find((asset) => asset.id === terminal.outputAssetId);
  expect(source).toMatchObject({
    id: upload.source.id,
    assetType: 'source',
    sourceAssetId: null,
    sha256: sha256(originalBytes),
  });
  expect(working).toMatchObject({
    id: upload.working.id,
    assetType: 'working',
    sourceAssetId: upload.source.id,
    sha256: upload.working.sha256,
  });
  expect(cutout).toMatchObject({
    id: terminal.outputAssetId,
    assetType: 'cutout',
    sourceAssetId: upload.working.id,
  });

  const sourceBytes = await assetBytes(request, source.id);
  const workingBytes = await assetBytes(request, working.id);
  const cutoutBytes = await assetBytes(request, cutout.id);
  expect(sourceBytes).toEqual(originalBytes);
  expect(sha256(sourceBytes)).toBe(source.sha256);
  expect(sha256(workingBytes)).toBe(working.sha256);
  expect(sha256(cutoutBytes)).toBe(cutout.sha256);

  const workingPng = decodePng(workingBytes);
  const cutoutPng = decodePng(cutoutBytes);
  expect(cutoutPng).toMatchObject({
    width: workingPng.width,
    height: workingPng.height,
    channels: 4,
  });
  for (let y = 0; y < workingPng.height; y += 1) {
    for (let x = 0; x < workingPng.width; x += 1) {
      const workingPixel = workingPng.pixelAt(x, y);
      const cutoutPixel = cutoutPng.pixelAt(x, y);
      expect(cutoutPixel.slice(0, 3), `cutout RGB at ${x},${y}`).toEqual(
        workingPixel.slice(0, 3),
      );
      expect(cutoutPixel[3], `cutout Alpha at ${x},${y}`).toBe(
        expectedFakeMaskAlpha(x, y, workingPng.width, workingPng.height),
      );
    }
  }

  const snapshotResponse = await request.get(projectUrl(projectId));
  expect(snapshotResponse.ok()).toBeTruthy();
  const snapshot = await snapshotResponse.json();
  expect(snapshot.project.layoutState.productLayers.find(
    (layer) => layer.skuId === null && layer.locked,
  )).toMatchObject({
    sourceAssetId: working.id,
    renderAssetId: cutout.id,
    allowOpaqueFallback: false,
  });
}


async function uploadThroughUi(page, projectId, name, buffer) {
  const responsePromise = page.waitForResponse((response) => (
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/assets`
  ));
  await page.getByRole('button', { name: '上传主商品图片' }).setInputFiles({
    name,
    mimeType: 'image/png',
    buffer,
  });
  const response = await responsePromise;
  expect(response.status(), `upload ${name}`).toBe(201);
  const bundle = await response.json();
  if (bundle.operation !== null) trackOperation(projectId, bundle.operation.id);
  return bundle;
}


async function getOperation(request, operationId) {
  const response = await request.get(operationUrl(operationId));
  expect(response.ok(), `load operation ${operationId}`).toBeTruthy();
  return response.json();
}


async function waitForOperation(request, operationId, expectedStatus) {
  await expect.poll(
    async () => (await getOperation(request, operationId)).status,
    { timeout: 30_000, message: `operation ${operationId} -> ${expectedStatus}` },
  ).toBe(expectedStatus);
  return getOperation(request, operationId);
}


async function runtimeAudit(request) {
  const response = await request.get('/_e2e/runtime-audit');
  expect(response.ok()).toBeTruthy();
  return response.json();
}


async function installNativeEventSourceAudit(page) {
  await page.addInitScript(() => {
    const NativeEventSource = window.EventSource;
    const eventTypes = [
      'project.created',
      'project.updated',
      'project.state_saved',
      'asset.uploaded',
      'operation.queued',
      'operation.retried',
      'operation.running',
      'operation.succeeded',
      'operation.failed',
      'snapshot',
    ];
    const records = [];
    function AuditedNativeEventSource(url, options) {
      const source = new NativeEventSource(url, options);
      const record = { url: String(url), events: [], errors: 0 };
      for (const type of eventTypes) {
        source.addEventListener(type, (event) => {
          record.events.push({
            type,
            lastEventId: event.lastEventId,
            data: event.data,
          });
        });
      }
      source.addEventListener('error', () => {
        record.errors += 1;
      });
      records.push(record);
      return source;
    }
    AuditedNativeEventSource.prototype = NativeEventSource.prototype;
    for (const constant of ['CONNECTING', 'OPEN', 'CLOSED']) {
      Object.defineProperty(AuditedNativeEventSource, constant, {
        value: NativeEventSource[constant],
      });
    }
    Object.defineProperty(window, 'EventSource', {
      configurable: true,
      writable: true,
      value: AuditedNativeEventSource,
    });
    window.__canvasNativeEventSourceAudit = {
      snapshot: () => records.map((record) => ({
        url: record.url,
        errors: record.errors,
        events: record.events.map((event) => ({ ...event })),
      })),
    };
  });
}


async function nativeEventSourceAudit(page) {
  return page.evaluate(() => window.__canvasNativeEventSourceAudit.snapshot());
}


async function resetRuntimeAudit(request) {
  const response = await request.post('/_e2e/runtime-audit/reset');
  expect(response.ok()).toBeTruthy();
}


async function expectIsolatedRuntimeAudit(request) {
  const audit = await runtimeAudit(request);
  expect(audit.providerKeyAliases).toEqual(Object.fromEntries(
    PROVIDER_KEY_ENV_ALIASES.map((name) => [name, '']),
  ));
  expect(audit.effectiveProviderKeys).toEqual(Object.fromEntries(
    EFFECTIVE_PROVIDER_KEYS.map((name) => [name, '']),
  ));
  expect(audit.rembg).toMatchObject({
    rembgImported: false,
    onnxruntimeImported: false,
    modelFileCount: 0,
    modelFiles: [],
  });
  expect(audit.network).toEqual({
    lifetimeExternalAttemptCount: 0,
    lifetimeExternalAttemptTargets: [],
    scenarioExternalAttemptCount: 0,
    scenarioExternalAttemptTargets: [],
  });
}


async function waitForAllTrackedOperations(request) {
  for (const operationIds of createdProjects.values()) {
    for (const operationId of operationIds) {
      await expect.poll(
        async () => (await getOperation(request, operationId)).status,
        { timeout: 30_000, message: `cleanup waits for ${operationId}` },
      ).toMatch(/^(cancelled|failed|interrupted|succeeded)$/);
    }
  }
}


async function deleteProject(request, projectId) {
  const url = projectUrl(projectId);
  let deletion = null;
  let failure = null;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const current = await request.get(url);
    if (current.status() === 404) return;
    expect(current.ok(), `load cleanup project ${projectId}`).toBeTruthy();
    const snapshot = await current.json();
    deletion = await request.fetch(url, {
      method: 'DELETE',
      data: { revision: snapshot.revision },
    });
    if (deletion.ok()) break;
    let body = null;
    try {
      body = await deletion.json();
    } catch {
      body = await deletion.text();
    }
    failure = { status: deletion.status(), body };
    if (deletion.status() !== 409 || body?.code !== 'canvas_revision_conflict') break;
  }
  expect(
    deletion?.ok(),
    `delete cleanup project ${projectId}: ${JSON.stringify(failure)}`,
  ).toBeTruthy();
  await expect.poll(async () => (await request.get(url)).status(), { timeout: 30_000 }).toBe(404);
}


test.afterEach(async ({ page, request }) => {
  await waitForAllTrackedOperations(request);
  await expectIsolatedRuntimeAudit(request);
  if (!page.isClosed()) await page.close();
  for (const projectId of createdProjects.keys()) {
    await deleteProject(request, projectId);
  }
  createdProjects.clear();
});


test('transparent skips cutout while white and complex opaque products run it exactly once', async ({ page, request }) => {
  await resetRuntimeAudit(request);
  const created = await createProject(request, 'P10 自动抠图边界');
  const transparentProjectId = created.project.id;
  await page.goto(`/app/canvas/${transparentProjectId}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');

  const transparent = await uploadThroughUi(
    page,
    transparentProjectId,
    'transparent-product.png',
    transparentProductPng(),
  );
  expect(transparent.working.transparencyStatus).toBe('transparent');
  expect(transparent.operation).toBeNull();
  await expect(page.getByTestId('canvas-cutout-status')).toHaveText('素材已就绪');
  await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'saved');
  await expect(page.getByTestId('canvas-asset-inspector').locator('input[type="checkbox"]')).toHaveCount(0);
  expect((await runtimeAudit(request)).masker).toEqual({
    totalCalls: 0,
    callsByDigest: {},
  });

  const whiteProject = await createProject(request, 'P10 白底自动抠图');
  const whiteProjectId = whiteProject.project.id;
  await page.goto(`/app/canvas/${whiteProjectId}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');
  const whiteBytes = whiteProductPng();
  const white = await uploadThroughUi(page, whiteProjectId, 'white-product.png', whiteBytes);
  expect(white.working.transparencyStatus).toBe('opaque');
  expect(white.operation).not.toBeNull();
  const whiteTerminal = await waitForOperation(request, white.operation.id, 'succeeded');
  expect(whiteTerminal.attemptCount).toBe(1);
  await expect(page.getByTestId('canvas-cutout-status')).toHaveText('素材已就绪');
  await expectOpaqueCutoutFidelity({
    page,
    request,
    projectId: whiteProjectId,
    originalBytes: whiteBytes,
    upload: white,
    terminal: whiteTerminal,
  });
  expect((await runtimeAudit(request)).masker.totalCalls).toBe(1);

  const complexProject = await createProject(request, 'P10 复杂背景自动抠图');
  const complexProjectId = complexProject.project.id;
  await page.goto(`/app/canvas/${complexProjectId}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');
  const complexBytes = complexProductPng();
  const complex = await uploadThroughUi(
    page,
    complexProjectId,
    'complex-product.png',
    complexBytes,
  );
  expect(complex.working.transparencyStatus).toBe('opaque');
  expect(complex.operation).not.toBeNull();
  const complexTerminal = await waitForOperation(request, complex.operation.id, 'succeeded');
  expect(complexTerminal.attemptCount).toBe(1);
  await expect(page.getByTestId('canvas-cutout-status')).toHaveText('素材已就绪');
  await expectOpaqueCutoutFidelity({
    page,
    request,
    projectId: complexProjectId,
    originalBytes: complexBytes,
    upload: complex,
    terminal: complexTerminal,
  });

  const audit = await runtimeAudit(request);
  expect(audit.masker.totalCalls).toBe(2);
  expect(Object.values(audit.masker.callsByDigest).sort()).toEqual([1, 1]);
  const operations = [];
  for (const opaqueProjectId of [whiteProjectId, complexProjectId]) {
    const operationsResponse = await request.get(`${projectUrl(opaqueProjectId)}/operations`);
    expect(operationsResponse.ok()).toBeTruthy();
    operations.push(...(await operationsResponse.json()).operations.filter(
      (operation) => operation.operationType === 'cutout',
    ));
  }
  expect(operations).toHaveLength(2);
  expect(operations.map((operation) => operation.inputAssetId).sort()).toEqual(
    [white.working.id, complex.working.id].sort(),
  );
});


test('failed cutout retries the same operation without mutating source or saved rectangular fallback', async ({ page, request }) => {
  await resetRuntimeAudit(request);
  const created = await createProject(request, 'P10 失败重试与回退');
  const projectId = created.project.id;
  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');

  const sourceBytes = failOnceProductPng();
  const upload = await uploadThroughUi(page, projectId, 'fail-once-product.png', sourceBytes);
  expect(upload.operation).not.toBeNull();
  const operationId = upload.operation.id;
  const sourceId = upload.source.id;
  const workingId = upload.working.id;
  const sourceSha = crypto.createHash('sha256').update(sourceBytes).digest('hex');
  expect(upload.source.sha256).toBe(sourceSha);
  expect(upload.working.sourceAssetId).toBe(sourceId);

  const failed = await waitForOperation(request, operationId, 'failed');
  expect(failed).toMatchObject({
    id: operationId,
    attemptCount: 1,
    inputAssetId: workingId,
    outputAssetId: null,
  });
  await expect(page.getByTestId('canvas-cutout-status')).toContainText('自动抠图失败');
  await expect(page.getByRole('button', { name: '重新抠图' })).toBeVisible();
  await expect(page.getByRole('button', { name: '使用原图矩形继续' })).toBeVisible();
  await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'saved');

  const fallbackSave = page.waitForResponse((response) => (
    response.request().method() === 'PUT'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/state`
      && response.status() === 200
  ));
  await page.getByRole('button', { name: '使用原图矩形继续' }).click();
  const fallbackSnapshot = await (await fallbackSave).json();
  const fallbackLayer = fallbackSnapshot.project.layoutState.productLayers.find(
    (layer) => layer.skuId === null && layer.locked,
  );
  expect(fallbackLayer).toMatchObject({
    sourceAssetId: workingId,
    renderAssetId: workingId,
    allowOpaqueFallback: true,
  });

  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-workspace')).toHaveAttribute('data-editable', 'true');
  await expect(page.getByTestId('canvas-cutout-status')).toContainText('自动抠图失败');
  await expect(page.getByRole('button', { name: '使用原图矩形继续' })).toHaveCount(0);
  const persistedFallback = await (await request.get(projectUrl(projectId))).json();
  expect(persistedFallback.project.layoutState.productLayers.find(
    (layer) => layer.skuId === null && layer.locked,
  )).toMatchObject({
    sourceAssetId: workingId,
    renderAssetId: workingId,
    allowOpaqueFallback: true,
  });

  const retryResponsePromise = page.waitForResponse((response) => (
    response.request().method() === 'POST'
      && new URL(response.url()).pathname
        === `/api/canvas/assets/${encodeURIComponent(workingId)}/cutout/retry`
  ));
  await page.getByRole('button', { name: '重新抠图' }).click();
  const retryResponse = await retryResponsePromise;
  expect(retryResponse.ok()).toBeTruthy();
  expect((await retryResponse.json()).id).toBe(operationId);

  const succeeded = await waitForOperation(request, operationId, 'succeeded');
  expect(succeeded).toMatchObject({
    id: operationId,
    attemptCount: 2,
    inputAssetId: workingId,
  });
  expect(succeeded.outputAssetId).toEqual(expect.any(String));
  await expect(page.getByTestId('canvas-cutout-status')).toHaveText('素材已就绪');
  await expect(page.getByAltText('抠图预览')).toBeVisible();

  const finalSnapshot = await (await request.get(projectUrl(projectId))).json();
  expect(finalSnapshot.project.layoutState.productLayers.find(
    (layer) => layer.skuId === null && layer.locked,
  )).toMatchObject({
    sourceAssetId: workingId,
    renderAssetId: workingId,
    allowOpaqueFallback: true,
  });
  const assetsResponse = await request.get(`${projectUrl(projectId)}/assets`);
  expect(assetsResponse.ok()).toBeTruthy();
  const assets = (await assetsResponse.json()).assets;
  expect(assets.find((asset) => asset.id === sourceId)).toMatchObject({
    sha256: sourceSha,
    sourceAssetId: null,
  });
  expect(assets.find((asset) => asset.id === workingId)).toMatchObject({
    id: workingId,
    sourceAssetId: sourceId,
    sha256: upload.working.sha256,
  });
  expect(assets.find((asset) => asset.id === succeeded.outputAssetId)).toMatchObject({
    assetType: 'cutout',
    sourceAssetId: workingId,
  });
  const sourceDownload = await request.get(`/api/canvas/assets/${encodeURIComponent(sourceId)}/content`);
  expect(sourceDownload.ok()).toBeTruthy();
  expect(crypto.createHash('sha256').update(await sourceDownload.body()).digest('hex')).toBe(sourceSha);

  const audit = await runtimeAudit(request);
  expect(audit.masker.totalCalls).toBe(2);
  expect(Object.values(audit.masker.callsByDigest)).toEqual([2]);
});


test('one shared composition edit synchronizes main and SKU transforms while creative choices stay independent', async ({ page, request }) => {
  const created = await createProject(request, 'P10 SKU 共享构图');
  const projectId = created.project.id;
  const skuSnapshot = await createSku(request, projectId, created.revision, 'SKU 独立版本');
  const skuId = skuSnapshot.skus[0].id;
  const backgroundA = await seedBackground(request, projectId, [238, 242, 255]);
  const backgroundB = await seedBackground(request, projectId, [255, 244, 232]);

  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  const upload = await uploadThroughUi(
    page,
    projectId,
    'shared-transparent-product.png',
    transparentProductPng(),
  );
  expect(upload.operation).toBeNull();
  await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'saved');
  const latest = await (await request.get(projectUrl(projectId))).json();
  const state = sharedSkuState({
    snapshot: latest,
    workingAssetId: upload.working.id,
    skuId,
    backgroundIds: [backgroundA.asset.id, backgroundB.asset.id],
  });
  const saved = await saveProjectState(
    request,
    latest,
    state.semanticState,
    state.layoutState,
  );

  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-composition-group-select')).toHaveValue(
    'shared-product-composition',
  );
  const baseline = page.getByTestId('canvas-composition-inspector').locator(
    'input[data-field="baseline"]',
  );
  await expect(baseline).toHaveValue('0.5');
  const saveResponse = page.waitForResponse((response) => (
    response.request().method() === 'PUT'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/state`
      && response.status() === 200
  ));
  await baseline.fill('0.6');
  await baseline.press('Tab');
  const updated = await (await saveResponse).json();

  const group = updated.project.semanticState.compositionGroups[0];
  expect(group).toMatchObject({
    id: 'shared-product-composition',
    layout: { baseline: 0.6 },
  });
  expect(group.layoutHash).toMatch(/^sha256:[0-9a-f]{64}$/);
  expect(group.layoutHash).not.toBe(IDENTITY_LAYOUT_HASH);
  expect(updated.project.layoutState.objectTransforms['transform-main']).toEqual({
    x: 0.5,
    y: 0.6,
    scale: 1,
    rotation: 0,
  });
  expect(updated.project.layoutState.objectTransforms['transform-sku']).toEqual(
    updated.project.layoutState.objectTransforms['transform-main'],
  );
  expect(updated.project.layoutState.productLayers.map((layer) => layer.compositionGroupId)).toEqual([
    'shared-product-composition',
    'shared-product-composition',
  ]);
  expect(updated.project.semanticState.completeSet.outputs.map((output) => ({
    skuId: output.skuId,
    prompt: output.prompt,
    modelProfileId: output.modelProfileId,
    lighting: output.modelParameters.lighting,
  }))).toEqual([
    {
      skuId: null,
      prompt: 'main prompt remains independent',
      modelProfileId: 'model-main',
      lighting: 'main-light',
    },
    {
      skuId,
      prompt: 'sku prompt remains independent',
      modelProfileId: 'model-sku',
      lighting: 'sku-light',
    },
  ]);
  expect(updated.project.semanticState.outputBoards.map((board) => board.selectedResultAssetId)).toEqual([
    null,
    null,
  ]);
  expect(saved.revision + 1).toBe(updated.revision);
});


test('authoritative compose preserves product RGB, text z-bands, deterministic SHA, and downloaded bytes', async ({ page, request }) => {
  await resetRuntimeAudit(request);
  const created = await createProject(request, 'P10 权威合成像素保真');
  const projectId = created.project.id;
  const background = await seedBackground(request, projectId, [224, 232, 240]);
  const backgroundAssetId = background.asset.id;

  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  const productBytes = transparentProductPng();
  const upload = await uploadThroughUi(page, projectId, 'compose-product.png', productBytes);
  expect(upload.operation).toBeNull();
  await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'saved');
  const current = await (await request.get(projectUrl(projectId))).json();
  const baselineState = authoritativeComposeState({
    snapshot: current,
    workingAssetId: upload.working.id,
    backgroundAssetId,
  });
  const baselineSnapshot = await saveProjectState(
    request,
    current,
    baselineState.semanticState,
    baselineState.layoutState,
  );

  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('canvas-compose-board')).toHaveValue('board-main');
  await page.getByTestId('canvas-compose-background').selectOption(backgroundAssetId);
  const composeResponsePromise = page.waitForResponse((response) => (
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${projectUrl(projectId)}/compose`
  ));
  await page.getByTestId('canvas-compose-submit').click();
  const composeResponse = await composeResponsePromise;
  expect(composeResponse.status()).toBe(202);
  expect(Object.keys(composeResponse.request().postDataJSON()).sort()).toEqual([
    'backgroundAssetId',
    'boardId',
    'idempotencyKey',
    'revision',
  ]);
  const baselineOperation = await composeResponse.json();
  trackOperation(projectId, baselineOperation.id);
  const baselineTerminal = await waitForOperation(request, baselineOperation.id, 'succeeded');
  await expect(page.getByTestId('canvas-compose-feedback')).toHaveText('合成完成');
  await expect(page.getByTestId('canvas-compose-preview')).toBeVisible();

  const duplicateTerminal = await enqueueCompose(
    request,
    projectId,
    baselineSnapshot.revision,
    backgroundAssetId,
    'compose-same-input-second-client-request',
  );
  const belowState = authoritativeComposeState({
    snapshot: baselineSnapshot,
    workingAssetId: upload.working.id,
    backgroundAssetId,
    textBand: 'below-product',
  });
  const belowSnapshot = await saveProjectState(
    request,
    baselineSnapshot,
    belowState.semanticState,
    belowState.layoutState,
  );
  const belowTerminal = await enqueueCompose(
    request,
    projectId,
    belowSnapshot.revision,
    backgroundAssetId,
    'compose-below-product-text',
  );
  const aboveState = authoritativeComposeState({
    snapshot: belowSnapshot,
    workingAssetId: upload.working.id,
    backgroundAssetId,
    textBand: 'above-product',
  });
  const aboveSnapshot = await saveProjectState(
    request,
    belowSnapshot,
    aboveState.semanticState,
    aboveState.layoutState,
  );
  const aboveTerminal = await enqueueCompose(
    request,
    projectId,
    aboveSnapshot.revision,
    backgroundAssetId,
    'compose-above-product-text',
  );

  const assetsResponse = await request.get(`${projectUrl(projectId)}/assets`);
  expect(assetsResponse.ok()).toBeTruthy();
  const assets = (await assetsResponse.json()).assets;
  const baselineAsset = assets.find((asset) => asset.id === baselineTerminal.outputAssetId);
  const duplicateAsset = assets.find((asset) => asset.id === duplicateTerminal.outputAssetId);
  const belowAsset = assets.find((asset) => asset.id === belowTerminal.outputAssetId);
  const aboveAsset = assets.find((asset) => asset.id === aboveTerminal.outputAssetId);
  for (const asset of [baselineAsset, duplicateAsset, belowAsset, aboveAsset]) {
    expect(asset).toMatchObject({
      assetType: 'composed',
      mimeType: 'image/png',
      width: 8,
      height: 8,
    });
  }
  expect(duplicateAsset.sha256).toBe(baselineAsset.sha256);

  const baselineBytes = await assetBytes(request, baselineAsset.id);
  const duplicateBytes = await assetBytes(request, duplicateAsset.id);
  const belowBytes = await assetBytes(request, belowAsset.id);
  const aboveBytes = await assetBytes(request, aboveAsset.id);
  expect(crypto.createHash('sha256').update(baselineBytes).digest('hex')).toBe(baselineAsset.sha256);
  expect(crypto.createHash('sha256').update(duplicateBytes).digest('hex')).toBe(duplicateAsset.sha256);
  expect(duplicateBytes.equals(baselineBytes)).toBe(true);

  const source = decodePng(productBytes);
  const baseline = decodePng(baselineBytes);
  const below = decodePng(belowBytes);
  const above = decodePng(aboveBytes);
  let visibleProductPixels = 0;
  let aboveProductChanges = 0;
  for (let y = 0; y < source.height; y += 1) {
    for (let x = 0; x < source.width; x += 1) {
      const sourcePixel = source.pixelAt(x, y);
      if (sourcePixel[3] === 0) continue;
      visibleProductPixels += 1;
      expect(baseline.pixelAt(x, y).slice(0, 3)).toEqual(sourcePixel.slice(0, 3));
      expect(below.pixelAt(x, y)).toEqual(baseline.pixelAt(x, y));
      if (!Buffer.from(above.pixelAt(x, y)).equals(Buffer.from(baseline.pixelAt(x, y)))) {
        aboveProductChanges += 1;
      }
    }
  }
  expect(visibleProductPixels).toBeGreaterThan(0);
  expect(aboveProductChanges).toBeGreaterThan(0);

  const audit = await runtimeAudit(request);
  expect(audit.compose.totalCalls).toBe(4);
  expect(audit.compose.calls.map((call) => call.operationId).sort()).toEqual([
    baselineTerminal.id,
    duplicateTerminal.id,
    belowTerminal.id,
    aboveTerminal.id,
  ].sort());
});


test('native EventSource reconnects with Last-Event-ID and accepts a retention-gap terminal snapshot', async ({ page, request }) => {
  await resetRuntimeAudit(request);
  await installNativeEventSourceAudit(page);
  const created = await createProject(request, 'P10 SSE retention gap');
  const projectId = created.project.id;
  await page.goto(`/app/canvas/${projectId}`, { waitUntil: 'domcontentloaded' });
  const upload = await uploadThroughUi(page, projectId, 'sse-fail-once.png', failOnceProductPng());
  const operationId = upload.operation.id;
  const failed = await waitForOperation(request, operationId, 'failed');
  expect(failed.attemptCount).toBe(1);
  await expect(page.getByTestId('canvas-save-status')).toHaveAttribute('data-state', 'saved');
  await expect(page.getByTestId('canvas-cutout-status')).toContainText('自动抠图失败');
  await expect.poll(async () => {
    const records = await nativeEventSourceAudit(page);
    return records.flatMap((record) => record.events).some((event) => (
      event.type === 'operation.failed'
        && JSON.parse(event.data).operationId === operationId
    ));
  }, { timeout: 15_000 }).toBe(true);
  const savedSnapshotResponse = await request.get(projectUrl(projectId));
  expect(savedSnapshotResponse.ok()).toBeTruthy();
  const savedSnapshot = await savedSnapshotResponse.json();
  await expect.poll(async () => {
    const records = await nativeEventSourceAudit(page);
    return records.flatMap((record) => record.events).some((event) => {
      if (event.type !== 'project.state_saved') return false;
      const stateSaved = JSON.parse(event.data);
      return stateSaved.projectId === projectId && stateSaved.revision === savedSnapshot.revision;
    });
  }, { timeout: 15_000 }).toBe(true);

  const beforeOffline = await nativeEventSourceAudit(page);
  const terminalPreOfflineEvent = beforeOffline
    .flatMap((record) => record.events)
    .findLast((event) => {
      if (event.type !== 'project.state_saved') return false;
      const stateSaved = JSON.parse(event.data);
      return stateSaved.projectId === projectId && stateSaved.revision === savedSnapshot.revision;
    });
  expect(terminalPreOfflineEvent).toBeDefined();
  const deliveredIds = beforeOffline
    .flatMap((record) => record.events)
    .map((event) => Number(event.lastEventId))
    .filter((eventId) => Number.isSafeInteger(eventId) && eventId > 0);
  const eventA = Math.max(...deliveredIds);
  expect(eventA).toBeGreaterThan(0);
  expect(eventA).toBe(Number(terminalPreOfflineEvent.lastEventId));

  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.emulateNetworkConditions', {
    offline: true,
    latency: 0,
    downloadThroughput: 0,
    uploadThroughput: 0,
    connectionType: 'none',
  });
  expect(await page.evaluate(() => navigator.onLine)).toBe(false);
  const disconnect = await request.post(
    `/_e2e/projects/${encodeURIComponent(projectId)}/events/disconnect`,
  );
  expect(disconnect.ok()).toBeTruthy();
  expect(await disconnect.json()).toMatchObject({
    projectId,
    disconnectGeneration: 1,
  });
  const retry = await request.post(operationUrl(operationId) + '/retry');
  expect(retry.ok()).toBeTruthy();
  expect((await retry.json()).id).toBe(operationId);
  const terminalB = await waitForOperation(request, operationId, 'succeeded');
  expect(terminalB).toMatchObject({ attemptCount: 2, outputAssetId: expect.any(String) });
  const prune = await request.post(
    `/_e2e/projects/${encodeURIComponent(projectId)}/events/prune-through`,
    { data: { eventId: eventA } },
  );
  expect(prune.ok()).toBeTruthy();
  const pruneResult = await prune.json();
  expect(pruneResult.prunedThrough).toBe(eventA);
  expect(pruneResult.deletedEventIds).toContain(eventA);
  expect(pruneResult.earliestEventId).toBeGreaterThan(eventA);
  expect(pruneResult.latestEventId).toBeGreaterThanOrEqual(pruneResult.earliestEventId);

  await cdp.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: 0,
    downloadThroughput: -1,
    uploadThroughput: -1,
    connectionType: 'wifi',
  });
  await expect.poll(async () => {
    const audit = await runtimeAudit(request);
    return audit.eventRequests.some((eventRequest) => (
      eventRequest.path === `${projectUrl(projectId)}/events`
        && eventRequest.lastEventId === String(eventA)
    ));
  }, { timeout: 20_000 }).toBe(true);
  await expect.poll(async () => {
    const records = await nativeEventSourceAudit(page);
    return records.flatMap((record) => record.events).some((event) => {
      if (event.type !== 'snapshot') return false;
      const snapshot = JSON.parse(event.data);
      return snapshot.operations.some((operation) => (
        operation.id === operationId
          && operation.status === 'succeeded'
          && operation.attemptCount === 2
          && operation.outputAssetId === terminalB.outputAssetId
      ));
    });
  }, { timeout: 20_000 }).toBe(true);
  await expect(page.getByTestId('canvas-cutout-status')).toHaveText('素材已就绪', {
    timeout: 20_000,
  });
  await expect(page.getByAltText('抠图预览')).toBeVisible();

  const reconnectAudit = await runtimeAudit(request);
  expect(reconnectAudit.masker).toMatchObject({ totalCalls: 2 });
  expect(Object.values(reconnectAudit.masker.callsByDigest)).toEqual([2]);
});
