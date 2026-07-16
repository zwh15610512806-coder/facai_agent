import type {
  CanvasLayoutState,
  CanvasNode,
  CanvasProjectState,
  CanvasSemanticState,
  CompleteSetOutput,
  CompleteSetSettings,
  CompositionGroup,
  CompositionLayout,
  JsonValue,
  NormalizedPoint,
  NormalizedTransform,
  OutputBoard,
  OutputType,
  ProductLayer,
  TextLineSnapshot,
  TextSnapshot,
  TypedEdge,
} from "./types";
import {
  compositionLayoutHash,
  compositionTransform,
  DEFAULT_COMPOSITION_LAYOUT,
} from "./composition";
import { isCodePointLetterSpacingSafe } from "./text-layout";
import { canConnectNodes } from "./node-ports";

const MAX_CANVAS_NODES = 500;
const MAX_CANVAS_EDGES = 1_000;
const MAX_PROMPT_CHARACTERS = 4_000;
const MAX_TEXT_CHARACTERS = 100_000;

const NODE_KINDS = [
  "product_source",
  "sku_reference",
  "auto_cutout",
  "prompt",
  "model_generation",
  "main_output",
  "sku_output",
  "detail_output",
  "text_layer",
  "composition_group",
  "export",
] as const;

const OUTPUT_TYPES = ["main", "sku", "detail"] as const;
const EDGE_PORTS = {
  product_asset: { sourcePort: "product", targetPort: "reference" },
  cutout_asset: { sourcePort: "cutout", targetPort: "reference" },
  prompt: { sourcePort: "prompt", targetPort: "prompt" },
  background_image: { sourcePort: "image", targetPort: "background" },
  composition: { sourcePort: "composition", targetPort: "composition" },
  text_layer: { sourcePort: "text", targetPort: "text" },
  output_image: { sourcePort: "output", targetPort: "input" },
} as const;

const FABRIC_MARKER_KEYS = new Set([
  "generationhistory",
  "history",
  "objects",
  "resultassetids",
  "resultversions",
  "version",
  "versionhistory",
  "versions",
]);
const REMOTE_URL = /\b[A-Za-z][A-Za-z0-9+.-]*:\/\//;
const WINDOWS_ABSOLUTE_PATH = /^[A-Za-z]:[\\/]/;

export class ProjectValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProjectValidationError";
  }
}

function fail(path: string, message: string): never {
  throw new ProjectValidationError(`${message} at ${path}`);
}

function assertSafeWire(value: unknown, path: string): void {
  if (value === null || typeof value === "boolean") {
    return;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      fail(path, "JSON numbers must be finite");
    }
    return;
  }
  if (typeof value === "string") {
    const stripped = value.trim();
    const lowered = stripped.toLowerCase();
    if (lowered.startsWith("data:")) {
      fail(path, "data URLs are forbidden");
    }
    if (
      REMOTE_URL.test(stripped) ||
      lowered.startsWith("//") ||
      lowered.startsWith("blob:") ||
      lowered.startsWith("file:")
    ) {
      fail(path, "remote URLs are forbidden");
    }
    if (
      stripped.startsWith("/") ||
      stripped.startsWith("\\") ||
      WINDOWS_ABSOLUTE_PATH.test(stripped)
    ) {
      fail(path, "absolute paths are forbidden");
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertSafeWire(item, `${path}[${index}]`));
    return;
  }
  if (typeof value !== "object" || value === undefined) {
    fail(path, "non-JSON value is forbidden");
  }
  for (const [key, item] of Object.entries(value)) {
    if (FABRIC_MARKER_KEYS.has(key.toLowerCase())) {
      fail(path, `Fabric marker ${JSON.stringify(key)} is forbidden`);
    }
    assertSafeWire(item, `${path}.${key}`);
  }
}

function objectValue(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(path, "expected an object");
  }
  return value as Record<string, unknown>;
}

function exactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
  path: string,
): void {
  const expectedKeys = new Set(expected);
  for (const key of Object.keys(value)) {
    if (!expectedKeys.has(key)) {
      fail(path, `unknown key ${JSON.stringify(key)}`);
    }
  }
  for (const key of expected) {
    if (!Object.hasOwn(value, key)) {
      fail(path, `missing key ${JSON.stringify(key)}`);
    }
  }
}

function stringValue(
  value: unknown,
  path: string,
  options: { maxLength: number; allowEmpty?: boolean; trim?: boolean },
): string {
  if (typeof value !== "string") {
    fail(path, "expected a string");
  }
  const normalized = options.trim === true ? value.trim() : value;
  if (options.allowEmpty !== true && normalized.length === 0) {
    fail(path, "string must not be empty");
  }
  if (normalized.length > options.maxLength) {
    fail(path, `string exceeds ${options.maxLength} characters`);
  }
  return normalized;
}

function identifier(value: unknown, path: string): string {
  return stringValue(value, path, { maxLength: 200, trim: true });
}

function nullableIdentifier(value: unknown, path: string): string | null {
  return value === null ? null : identifier(value, path);
}

function booleanValue(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") {
    fail(path, "expected a boolean");
  }
  return value;
}

function numberValue(
  value: unknown,
  path: string,
  options: { min?: number; exclusiveMin?: number; max?: number } = {},
): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    fail(path, "expected a finite number");
  }
  if (options.min !== undefined && value < options.min) {
    fail(path, `number must be at least ${options.min}`);
  }
  if (options.exclusiveMin !== undefined && value <= options.exclusiveMin) {
    fail(path, `number must be greater than ${options.exclusiveMin}`);
  }
  if (options.max !== undefined && value > options.max) {
    fail(path, `number must be at most ${options.max}`);
  }
  return value;
}

function integerValue(
  value: unknown,
  path: string,
  options: { min?: number; max?: number } = {},
): number {
  const parsed = numberValue(value, path, options);
  if (!Number.isInteger(parsed)) {
    fail(path, "expected an integer");
  }
  return parsed;
}

function nullableInteger(
  value: unknown,
  path: string,
  options: { min?: number; max?: number } = {},
): number | null {
  return value === null ? null : integerValue(value, path, options);
}

function enumValue<const Values extends readonly string[]>(
  value: unknown,
  values: Values,
  path: string,
): Values[number] {
  if (typeof value !== "string" || !values.includes(value)) {
    fail(path, `expected one of ${values.join(", ")}`);
  }
  return value as Values[number];
}

function arrayValue<Item>(
  value: unknown,
  path: string,
  parser: (item: unknown, itemPath: string) => Item,
  maxLength: number,
): Item[] {
  if (!Array.isArray(value)) {
    fail(path, "expected an array");
  }
  if (value.length > maxLength) {
    fail(path, `array exceeds ${maxLength} items`);
  }
  return value.map((item, index) => parser(item, `${path}[${index}]`));
}

function requireUniqueIds(
  values: ReadonlyArray<{ id: string }>,
  label: string,
  path: string,
): void {
  const seen = new Set<string>();
  for (const value of values) {
    if (seen.has(value.id)) {
      fail(path, `duplicate ${label} id ${JSON.stringify(value.id)}`);
    }
    seen.add(value.id);
  }
}

function jsonValue(value: unknown, path: string): JsonValue {
  if (
    value === null ||
    typeof value === "boolean" ||
    typeof value === "string"
  ) {
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      fail(path, "JSON numbers must be finite");
    }
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => jsonValue(item, `${path}[${index}]`));
  }
  const object = objectValue(value, path);
  const parsed: { [key: string]: JsonValue } = {};
  for (const [key, item] of Object.entries(object)) {
    parsed[key] = jsonValue(item, `${path}.${key}`);
  }
  return parsed;
}

function jsonObject(
  value: unknown,
  path: string,
): { [key: string]: JsonValue } {
  const parsed = jsonValue(value, path);
  if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
    fail(path, "expected a JSON object");
  }
  return parsed;
}

function parseNode(value: unknown, path: string): CanvasNode {
  const object = objectValue(value, path);
  exactKeys(
    object,
    [
      "id",
      "kind",
      "managedBy",
      "skuId",
      "assetId",
      "modelProfileId",
      "prompt",
      "compositionGroupId",
      "textSnapshotId",
      "outputBoardId",
      "parameters",
    ],
    path,
  );
  const kind = enumValue(object.kind, NODE_KINDS, `${path}.kind`);
  const managedBy =
    object.managedBy === null
      ? null
      : enumValue(object.managedBy, ["complete-set"] as const, `${path}.managedBy`);
  const prompt =
    object.prompt === null
      ? null
      : stringValue(object.prompt, `${path}.prompt`, {
          maxLength: MAX_PROMPT_CHARACTERS,
          allowEmpty: true,
        });
  return {
    id: identifier(object.id, `${path}.id`),
    kind,
    managedBy,
    skuId: nullableIdentifier(object.skuId, `${path}.skuId`),
    assetId: nullableIdentifier(object.assetId, `${path}.assetId`),
    modelProfileId: nullableIdentifier(
      object.modelProfileId,
      `${path}.modelProfileId`,
    ),
    prompt,
    compositionGroupId: nullableIdentifier(
      object.compositionGroupId,
      `${path}.compositionGroupId`,
    ),
    textSnapshotId: nullableIdentifier(
      object.textSnapshotId,
      `${path}.textSnapshotId`,
    ),
    outputBoardId: nullableIdentifier(
      object.outputBoardId,
      `${path}.outputBoardId`,
    ),
    parameters: jsonObject(object.parameters, `${path}.parameters`),
  } as CanvasNode;
}

export function validateTypedEdge(value: unknown, path = "edge"): TypedEdge {
  const object = objectValue(value, path);
  exactKeys(
    object,
    [
      "id",
      "kind",
      "sourceNodeId",
      "sourcePort",
      "targetNodeId",
      "targetPort",
      "skuId",
    ],
    path,
  );
  const kind = enumValue(
    object.kind,
    Object.keys(EDGE_PORTS) as Array<keyof typeof EDGE_PORTS>,
    `${path}.kind`,
  );
  const expected = EDGE_PORTS[kind];
  if (
    object.sourcePort !== expected.sourcePort ||
    object.targetPort !== expected.targetPort
  ) {
    fail(
      path,
      `invalid ports for ${kind}: ${String(object.sourcePort)} -> ${String(object.targetPort)}`,
    );
  }
  return {
    id: identifier(object.id, `${path}.id`),
    kind,
    sourceNodeId: identifier(object.sourceNodeId, `${path}.sourceNodeId`),
    sourcePort: expected.sourcePort,
    targetNodeId: identifier(object.targetNodeId, `${path}.targetNodeId`),
    targetPort: expected.targetPort,
    skuId: nullableIdentifier(object.skuId, `${path}.skuId`),
  } as TypedEdge;
}

function parseOutputType(value: unknown, path: string): OutputType {
  return enumValue(value, OUTPUT_TYPES, path);
}

function parseOutputBoard(value: unknown, path: string): OutputBoard {
  const object = objectValue(value, path);
  exactKeys(
    object,
    [
      "id",
      "outputNodeId",
      "outputType",
      "skuId",
      "sortOrder",
      "selectedResultAssetId",
    ],
    path,
  );
  return {
    id: identifier(object.id, `${path}.id`),
    outputNodeId: identifier(object.outputNodeId, `${path}.outputNodeId`),
    outputType: parseOutputType(object.outputType, `${path}.outputType`),
    skuId: nullableIdentifier(object.skuId, `${path}.skuId`),
    sortOrder: integerValue(object.sortOrder, `${path}.sortOrder`, { min: 0 }),
    selectedResultAssetId: nullableIdentifier(
      object.selectedResultAssetId,
      `${path}.selectedResultAssetId`,
    ),
  };
}

function parseCompleteSetOutput(value: unknown, path: string): CompleteSetOutput {
  const object = objectValue(value, path);
  exactKeys(
    object,
    [
      "outputType",
      "skuId",
      "quantity",
      "aspectRatio",
      "width",
      "height",
      "prompt",
      "modelProfileId",
      "modelParameters",
      "referenceAssetId",
      "compositionGroupId",
    ],
    path,
  );
  return {
    outputType: parseOutputType(object.outputType, `${path}.outputType`),
    skuId: nullableIdentifier(object.skuId, `${path}.skuId`),
    quantity: nullableInteger(object.quantity, `${path}.quantity`, {
      min: 1,
      max: 500,
    }),
    aspectRatio:
      object.aspectRatio === null
        ? null
        : stringValue(object.aspectRatio, `${path}.aspectRatio`, {
            maxLength: 40,
            trim: true,
          }),
    width: nullableInteger(object.width, `${path}.width`, {
      min: 1,
      max: 32_768,
    }),
    height: nullableInteger(object.height, `${path}.height`, {
      min: 1,
      max: 32_768,
    }),
    prompt: stringValue(object.prompt, `${path}.prompt`, {
      maxLength: MAX_PROMPT_CHARACTERS,
      allowEmpty: true,
    }),
    modelProfileId: nullableIdentifier(
      object.modelProfileId,
      `${path}.modelProfileId`,
    ),
    modelParameters: jsonObject(
      object.modelParameters,
      `${path}.modelParameters`,
    ),
    referenceAssetId: nullableIdentifier(
      object.referenceAssetId,
      `${path}.referenceAssetId`,
    ),
    compositionGroupId: nullableIdentifier(
      object.compositionGroupId,
      `${path}.compositionGroupId`,
    ),
  };
}

function parseCompleteSetSettings(
  value: unknown,
  path: string,
): CompleteSetSettings {
  const object = objectValue(value, path);
  exactKeys(object, ["selectedOutputTypes", "outputs"], path);
  const selectedOutputTypes = arrayValue(
    object.selectedOutputTypes,
    `${path}.selectedOutputTypes`,
    parseOutputType,
    3,
  );
  if (new Set(selectedOutputTypes).size !== selectedOutputTypes.length) {
    fail(`${path}.selectedOutputTypes`, "selected output types must be unique");
  }
  return {
    selectedOutputTypes,
    outputs: arrayValue(
      object.outputs,
      `${path}.outputs`,
      parseCompleteSetOutput,
      500,
    ),
  };
}

function parseCompositionLayout(value: unknown, path: string): CompositionLayout {
  const object = objectValue(value, path);
  exactKeys(
    object,
    ["slot", "anchor", "baseline", "relativeProductFraction", "contain", "safeArea", "rotation"],
    path,
  );
  const slot = objectValue(object.slot, `${path}.slot`);
  exactKeys(slot, ["x", "y", "width", "height"], `${path}.slot`);
  const parsedSlot = {
    x: numberValue(slot.x, `${path}.slot.x`, { min: 0, max: 1 }),
    y: numberValue(slot.y, `${path}.slot.y`, { min: 0, max: 1 }),
    width: numberValue(slot.width, `${path}.slot.width`, { exclusiveMin: 0, max: 1 }),
    height: numberValue(slot.height, `${path}.slot.height`, { exclusiveMin: 0, max: 1 }),
  };
  if (parsedSlot.x + parsedSlot.width > 1 || parsedSlot.y + parsedSlot.height > 1) {
    fail(`${path}.slot`, "normalized slot must remain inside the board");
  }
  const anchor = objectValue(object.anchor, `${path}.anchor`);
  exactKeys(anchor, ["x", "y"], `${path}.anchor`);
  const safeArea = objectValue(object.safeArea, `${path}.safeArea`);
  exactKeys(safeArea, ["top", "right", "bottom", "left"], `${path}.safeArea`);
  const parsedSafeArea = {
    top: numberValue(safeArea.top, `${path}.safeArea.top`, { min: 0, max: 1 }),
    right: numberValue(safeArea.right, `${path}.safeArea.right`, { min: 0, max: 1 }),
    bottom: numberValue(safeArea.bottom, `${path}.safeArea.bottom`, { min: 0, max: 1 }),
    left: numberValue(safeArea.left, `${path}.safeArea.left`, { min: 0, max: 1 }),
  };
  if (
    parsedSafeArea.left + parsedSafeArea.right >= 1 ||
    parsedSafeArea.top + parsedSafeArea.bottom >= 1
  ) {
    fail(`${path}.safeArea`, "safe area insets must leave a visible board region");
  }
  if (object.contain !== true) fail(`${path}.contain`, "contain must be true");
  return {
    slot: parsedSlot,
    anchor: {
      x: numberValue(anchor.x, `${path}.anchor.x`, { min: 0, max: 1 }),
      y: numberValue(anchor.y, `${path}.anchor.y`, { min: 0, max: 1 }),
    },
    baseline: numberValue(object.baseline, `${path}.baseline`, { min: 0, max: 1 }),
    relativeProductFraction: numberValue(
      object.relativeProductFraction,
      `${path}.relativeProductFraction`,
      { exclusiveMin: 0, max: 1 },
    ),
    contain: true,
    safeArea: parsedSafeArea,
    rotation: numberValue(object.rotation, `${path}.rotation`, { min: -180, max: 180 }),
  };
}

function parseCompositionGroup(value: unknown, path: string): CompositionGroup {
  const wire = objectValue(value, path);
  const legacy = wire.layout === undefined;
  const object: Record<string, unknown> = {
    ...wire,
    layout: wire.layout ?? structuredClone(DEFAULT_COMPOSITION_LAYOUT),
  };
  exactKeys(object, ["id", "skuIds", "productLayerIds", "layoutHash", "layout"], path);
  const layout = parseCompositionLayout(object.layout, `${path}.layout`);
  const layoutHash = legacy
    ? compositionLayoutHash(layout)
    : stringValue(object.layoutHash, `${path}.layoutHash`, { maxLength: 200 });
  return {
    id: identifier(object.id, `${path}.id`),
    skuIds: arrayValue(object.skuIds, `${path}.skuIds`, identifier, 500),
    productLayerIds: arrayValue(
      object.productLayerIds,
      `${path}.productLayerIds`,
      identifier,
      500,
    ),
    layoutHash,
    layout,
  };
}

function parseSemanticState(value: unknown, path: string): CanvasSemanticState {
  const object = objectValue(value, path);
  exactKeys(
    object,
    [
      "nodes",
      "edges",
      "outputBoards",
      "mode",
      "advancedCustomized",
      "completeSet",
      "compositionGroups",
    ],
    path,
  );
  const nodes = arrayValue(
    object.nodes,
    `${path}.nodes`,
    parseNode,
    MAX_CANVAS_NODES,
  );
  const edges = arrayValue(
    object.edges,
    `${path}.edges`,
    validateTypedEdge,
    MAX_CANVAS_EDGES,
  );
  const outputBoards = arrayValue(
    object.outputBoards,
    `${path}.outputBoards`,
    parseOutputBoard,
    500,
  );
  const compositionGroups = arrayValue(
    object.compositionGroups,
    `${path}.compositionGroups`,
    parseCompositionGroup,
    500,
  );
  requireUniqueIds(nodes, "node", `${path}.nodes`);
  requireUniqueIds(edges, "edge", `${path}.edges`);
  requireUniqueIds(outputBoards, "output board", `${path}.outputBoards`);
  requireUniqueIds(
    compositionGroups,
    "composition group",
    `${path}.compositionGroups`,
  );
  return {
    nodes,
    edges,
    outputBoards,
    mode: enumValue(
      object.mode,
      ["complete-set", "advanced"] as const,
      `${path}.mode`,
    ),
    advancedCustomized: booleanValue(
      object.advancedCustomized,
      `${path}.advancedCustomized`,
    ),
    completeSet: parseCompleteSetSettings(object.completeSet, `${path}.completeSet`),
    compositionGroups,
  };
}

function parsePoint(value: unknown, path: string): NormalizedPoint {
  const object = objectValue(value, path);
  exactKeys(object, ["x", "y"], path);
  return {
    x: numberValue(object.x, `${path}.x`),
    y: numberValue(object.y, `${path}.y`),
  };
}

function parseTransform(value: unknown, path: string): NormalizedTransform {
  const object = objectValue(value, path);
  exactKeys(object, ["x", "y", "scale", "rotation"], path);
  return {
    x: numberValue(object.x, `${path}.x`),
    y: numberValue(object.y, `${path}.y`),
    scale: numberValue(object.scale, `${path}.scale`, {
      exclusiveMin: 0,
      max: 1_000,
    }),
    rotation: numberValue(object.rotation, `${path}.rotation`, {
      min: -360_000,
      max: 360_000,
    }),
  };
}

function parseProductLayer(value: unknown, path: string): ProductLayer {
  const object: Record<string, unknown> = {
    ...objectValue(value, path),
    allowOpaqueFallback: objectValue(value, path).allowOpaqueFallback ?? false,
  };
  exactKeys(
    object,
    [
      "id",
      "sourceAssetId",
      "renderAssetId",
      "allowOpaqueFallback",
      "skuId",
      "compositionGroupId",
      "transformId",
      "locked",
    ],
    path,
  );
  return {
    id: identifier(object.id, `${path}.id`),
    sourceAssetId: identifier(object.sourceAssetId, `${path}.sourceAssetId`),
    renderAssetId: identifier(object.renderAssetId, `${path}.renderAssetId`),
    allowOpaqueFallback: booleanValue(
      object.allowOpaqueFallback,
      `${path}.allowOpaqueFallback`,
    ),
    skuId: nullableIdentifier(object.skuId, `${path}.skuId`),
    compositionGroupId: nullableIdentifier(
      object.compositionGroupId,
      `${path}.compositionGroupId`,
    ),
    transformId: identifier(object.transformId, `${path}.transformId`),
    locked: booleanValue(object.locked, `${path}.locked`),
  };
}

function parseTextLine(value: unknown, path: string): TextLineSnapshot {
  const object = objectValue(value, path);
  exactKeys(object, ["text", "x", "y", "width"], path);
  const text = stringValue(object.text, `${path}.text`, {
      maxLength: MAX_TEXT_CHARACTERS,
      allowEmpty: true,
    });
  if (text.includes("\r") || text.includes("\n")) {
    fail(`${path}.text`, "must not contain CR or LF");
  }
  return {
    text,
    x: numberValue(object.x, `${path}.x`),
    y: numberValue(object.y, `${path}.y`),
    width: numberValue(object.width, `${path}.width`, { min: 0 }),
  };
}

function parseTextSnapshot(value: unknown, path: string): TextSnapshot {
  const object = objectValue(value, path);
  exactKeys(
    object,
    [
      "id",
      "nodeId",
      "content",
      "fontAssetId",
      "fontFamily",
      "fontVersion",
      "boxWidth",
      "lines",
      "fontSize",
      "color",
      "letterSpacing",
      "lineHeight",
      "align",
      "baseline",
      "zBand",
      "sortOrder",
    ],
    path,
  );
  const lines = arrayValue(object.lines, `${path}.lines`, parseTextLine, 10_000);
  if (lines.reduce((length, line) => length + line.text.length, 0) > MAX_TEXT_CHARACTERS) {
    fail(`${path}.lines`, `text lines exceed ${MAX_TEXT_CHARACTERS} characters`);
  }
  const content = stringValue(object.content, `${path}.content`, {
    maxLength: MAX_TEXT_CHARACTERS,
    allowEmpty: true,
  });
  const fontSize = integerValue(object.fontSize, `${path}.fontSize`, {
    min: 1,
    max: 10_000,
  });
  const letterSpacing = numberValue(object.letterSpacing, `${path}.letterSpacing`, {
    min: -10_000,
    max: 10_000,
  });
  const expectedContent = lines.map((line) => line.text).join("\n");
  if (content !== expectedContent || (content.length === 0 && lines.length > 0)) {
    fail(`${path}.content`, "must match canonical explicit lines");
  }
  if (
    letterSpacing !== 0
    && lines.some((line) => !isCodePointLetterSpacingSafe(line.text))
  ) {
    fail(`${path}.letterSpacing`, "supports only independent BMP code points");
  }
  return {
    id: identifier(object.id, `${path}.id`),
    nodeId: identifier(object.nodeId, `${path}.nodeId`),
    content,
    fontAssetId: object.fontAssetId === null
      ? null
      : fail(`${path}.fontAssetId`, "must be null for the pinned font"),
    fontFamily: object.fontFamily === "Noto Sans CJK SC"
      ? object.fontFamily
      : fail(`${path}.fontFamily`, "must use the pinned Canvas font"),
    fontVersion:
      object.fontVersion ===
      "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
        ? object.fontVersion
        : fail(`${path}.fontVersion`, "must match the pinned Canvas font"),
    boxWidth: numberValue(object.boxWidth, `${path}.boxWidth`, { min: 0 }),
    lines,
    fontSize,
    color: (() => {
      const color = stringValue(object.color, `${path}.color`, {
        maxLength: 7,
        allowEmpty: false,
      });
      return /^#[0-9a-fA-F]{6}$/.test(color)
        ? color
        : fail(`${path}.color`, "must be a six-digit hex color");
    })(),
    letterSpacing,
    lineHeight: numberValue(object.lineHeight, `${path}.lineHeight`, {
      exclusiveMin: 0,
      max: 1_000,
    }),
    align: enumValue(
      object.align,
      ["left", "center", "right"] as const,
      `${path}.align`,
    ),
    baseline: enumValue(
      object.baseline,
      ["alphabetic", "top", "middle", "bottom"] as const,
      `${path}.baseline`,
    ),
    zBand: enumValue(
      object.zBand,
      ["below-product", "above-product"] as const,
      `${path}.zBand`,
    ),
    sortOrder: integerValue(object.sortOrder, `${path}.sortOrder`, { min: 0, max: 10_000 }),
  };
}

function parseLayoutState(value: unknown, path: string): CanvasLayoutState {
  const object = objectValue(value, path);
  exactKeys(
    object,
    [
      "nodePositions",
      "objectTransforms",
      "viewport",
      "productLayers",
      "textSnapshots",
    ],
    path,
  );
  const nodePositionWire = objectValue(object.nodePositions, `${path}.nodePositions`);
  const nodePositions: Record<string, NormalizedPoint> = {};
  for (const [key, point] of Object.entries(nodePositionWire)) {
    nodePositions[identifier(key, `${path}.nodePositions key`)] = parsePoint(
      point,
      `${path}.nodePositions.${key}`,
    );
  }
  const transformWire = objectValue(
    object.objectTransforms,
    `${path}.objectTransforms`,
  );
  const objectTransforms: Record<string, NormalizedTransform> = {};
  for (const [key, transform] of Object.entries(transformWire)) {
    objectTransforms[identifier(key, `${path}.objectTransforms key`)] =
      parseTransform(transform, `${path}.objectTransforms.${key}`);
  }
  const viewport = objectValue(object.viewport, `${path}.viewport`);
  exactKeys(viewport, ["x", "y", "zoom"], `${path}.viewport`);
  const productLayers = arrayValue(
    object.productLayers,
    `${path}.productLayers`,
    parseProductLayer,
    500,
  );
  const textSnapshots = arrayValue(
    object.textSnapshots,
    `${path}.textSnapshots`,
    parseTextSnapshot,
    500,
  );
  requireUniqueIds(productLayers, "product layer", `${path}.productLayers`);
  requireUniqueIds(textSnapshots, "text snapshot", `${path}.textSnapshots`);
  return {
    nodePositions,
    objectTransforms,
    viewport: {
      x: numberValue(viewport.x, `${path}.viewport.x`),
      y: numberValue(viewport.y, `${path}.viewport.y`),
      zoom: numberValue(viewport.zoom, `${path}.viewport.zoom`, {
        exclusiveMin: 0,
        max: 1_000,
      }),
    },
    productLayers,
    textSnapshots,
  };
}

function requireReference(
  id: string | null,
  knownIds: ReadonlySet<string>,
  path: string,
  label: string,
): void {
  if (id !== null && !knownIds.has(id)) {
    fail(path, `references unknown ${label} ${JSON.stringify(id)}`);
  }
}

function validateProjectReferences(project: CanvasProjectState): void {
  const nodeIds = new Set(project.semanticState.nodes.map((node) => node.id));
  const boardIds = new Set(
    project.semanticState.outputBoards.map((board) => board.id),
  );
  const compositionGroupIds = new Set(
    project.semanticState.compositionGroups.map((group) => group.id),
  );
  const productLayerIds = new Set(
    project.layoutState.productLayers.map((layer) => layer.id),
  );
  const textSnapshotIds = new Set(
    project.layoutState.textSnapshots.map((snapshot) => snapshot.id),
  );
  const transformIds = new Set(
    Object.keys(project.layoutState.objectTransforms),
  );

  project.semanticState.nodes.forEach((node, index) => {
    const path = `project.semanticState.nodes[${index}]`;
    requireReference(
      node.compositionGroupId,
      compositionGroupIds,
      `${path}.compositionGroupId`,
      "composition group",
    );
    requireReference(
      node.textSnapshotId,
      textSnapshotIds,
      `${path}.textSnapshotId`,
      "text snapshot",
    );
    requireReference(
      node.outputBoardId,
      boardIds,
      `${path}.outputBoardId`,
      "output board",
    );
  });

  project.semanticState.edges.forEach((edge, index) => {
    const path = `project.semanticState.edges[${index}]`;
    requireReference(edge.sourceNodeId, nodeIds, `${path}.sourceNodeId`, "node");
    requireReference(edge.targetNodeId, nodeIds, `${path}.targetNodeId`, "node");
    const source = project.semanticState.nodes.find((node) => node.id === edge.sourceNodeId);
    const target = project.semanticState.nodes.find((node) => node.id === edge.targetNodeId);
    if (
      source === undefined ||
      target === undefined ||
      !canConnectNodes(source.kind, target.kind, edge.kind)
    ) {
      fail(path, "incompatible node connection");
    }
  });

  project.semanticState.nodes.forEach((node, index) => {
    if (node.kind !== "auto_cutout") return;
    const productRoutes = project.semanticState.edges.filter(
      (edge) =>
        edge.kind === "product_asset" &&
        edge.targetNodeId === node.id,
    );
    if (productRoutes.length !== 1) {
      fail(
        `project.semanticState.nodes[${index}]`,
        "auto cutout must retain its product route",
      );
    }
    const route = productRoutes[0];
    const source = project.semanticState.nodes.find(
      (candidate) => candidate.id === route.sourceNodeId,
    );
    if (
      node.id !== "main-product-cutout" ||
      node.skuId !== null ||
      node.assetId === null ||
      source?.id !== "main-product-source" ||
      source.kind !== "product_source" ||
      source.skuId !== null ||
      source.assetId === null
    ) {
      fail(
        `project.semanticState.nodes[${index}]`,
        "auto cutout must use the canonical system product pipeline",
      );
    }
    const mainLayers = project.layoutState.productLayers.filter(
      (layer) => layer.skuId === null && layer.locked,
    );
    if (
      mainLayers.length !== 1 ||
      source.assetId !== mainLayers[0]?.sourceAssetId ||
      node.assetId !== mainLayers[0]?.renderAssetId
    ) {
      fail(
        `project.semanticState.nodes[${index}]`,
        "auto cutout asset binding must match the locked product layer",
      );
    }
  });

  project.semanticState.outputBoards.forEach((board, index) => {
    requireReference(
      board.outputNodeId,
      nodeIds,
      `project.semanticState.outputBoards[${index}].outputNodeId`,
      "node",
    );
  });

  project.semanticState.completeSet.outputs.forEach((output, index) => {
    requireReference(
      output.compositionGroupId,
      compositionGroupIds,
      `project.semanticState.completeSet.outputs[${index}].compositionGroupId`,
      "composition group",
    );
  });

  project.semanticState.compositionGroups.forEach((group, groupIndex) => {
    if (!/^sha256:[0-9a-f]{64}$/.test(group.layoutHash)) {
      fail(
        `project.semanticState.compositionGroups[${groupIndex}].layoutHash`,
        "expected sha256:<lowercase hex>",
      );
    }
    if (group.layoutHash !== compositionLayoutHash(group.layout)) {
      fail(
        `project.semanticState.compositionGroups[${groupIndex}].layoutHash`,
        "layout hash does not match shared composition layout",
      );
    }
    if (new Set(group.skuIds).size !== group.skuIds.length) {
      fail(`project.semanticState.compositionGroups[${groupIndex}].skuIds`, "duplicate SKU id");
    }
    if (new Set(group.productLayerIds).size !== group.productLayerIds.length) {
      fail(
        `project.semanticState.compositionGroups[${groupIndex}].productLayerIds`,
        "duplicate product layer id",
      );
    }
    group.productLayerIds.forEach((layerId, layerIndex) => {
      requireReference(
        layerId,
        productLayerIds,
        `project.semanticState.compositionGroups[${groupIndex}].productLayerIds[${layerIndex}]`,
        "product layer",
      );
    });
    const actualLayers = project.layoutState.productLayers.filter(
      (layer) => layer.compositionGroupId === group.id,
    );
    if (
      actualLayers.length !== group.productLayerIds.length ||
      actualLayers.some((layer) => !group.productLayerIds.includes(layer.id))
    ) {
      fail(
        `project.semanticState.compositionGroups[${groupIndex}]`,
        "composition group product membership is inconsistent or references unknown group",
      );
    }
    const actualSkuIds = actualLayers
      .flatMap((layer) => (layer.skuId === null ? [] : [layer.skuId]))
      .sort();
    if (JSON.stringify(actualSkuIds) !== JSON.stringify([...group.skuIds].sort())) {
      fail(
        `project.semanticState.compositionGroups[${groupIndex}].skuIds`,
        "composition group SKU membership is inconsistent",
      );
    }
    const expectedTransform = compositionTransform(group.layout);
    for (const layer of actualLayers) {
      if (!layer.locked) {
        fail(`project.layoutState.productLayers.${layer.id}.locked`, "composition product must remain locked");
      }
      if (layer.allowOpaqueFallback && layer.renderAssetId !== layer.sourceAssetId) {
        fail(
          `project.layoutState.productLayers.${layer.id}.allowOpaqueFallback`,
          "opaque fallback must render its working source",
        );
      }
      const transform = project.layoutState.objectTransforms[layer.transformId];
      if (
        transform === undefined ||
        Math.abs(transform.x - expectedTransform.x) > 1e-6 ||
        Math.abs(transform.y - expectedTransform.y) > 1e-6 ||
        Math.abs(transform.scale - expectedTransform.scale) > 1e-6 ||
        Math.abs(transform.rotation - expectedTransform.rotation) > 1e-6
      ) {
        fail(
          `project.layoutState.productLayers.${layer.id}.transformId`,
          "composition projection does not match its shared layout or references unknown transform",
        );
      }
    }
  });

  project.layoutState.productLayers.forEach((layer, index) => {
    const path = `project.layoutState.productLayers[${index}]`;
    requireReference(
      layer.compositionGroupId,
      compositionGroupIds,
      `${path}.compositionGroupId`,
      "composition group",
    );
    requireReference(layer.transformId, transformIds, `${path}.transformId`, "transform");
  });

  project.layoutState.textSnapshots.forEach((snapshot, index) => {
    requireReference(
      snapshot.nodeId,
      nodeIds,
      `project.layoutState.textSnapshots[${index}].nodeId`,
      "node",
    );
  });

  for (const nodeId of Object.keys(project.layoutState.nodePositions)) {
    requireReference(
      nodeId,
      nodeIds,
      `project.layoutState.nodePositions.${nodeId}`,
      "node",
    );
  }
}

function migrateLegacyCompositionGroups(
  project: CanvasProjectState,
  legacyGroupIds: ReadonlySet<string>,
): void {
  for (const group of project.semanticState.compositionGroups) {
    if (!legacyGroupIds.has(group.id)) continue;
    const firstLayer = project.layoutState.productLayers.find(
      (layer) => group.productLayerIds.includes(layer.id),
    );
    const transform = firstLayer === undefined
      ? undefined
      : project.layoutState.objectTransforms[firstLayer.transformId];
    const layout = structuredClone(DEFAULT_COMPOSITION_LAYOUT);
    if (transform !== undefined) {
      if (transform.x > 0 && transform.x < 1) {
        const width = Math.min(0.8, 2 * transform.x, 2 * (1 - transform.x));
        layout.slot.width = width;
        layout.slot.x = transform.x - width * 0.5;
      }
      layout.baseline = transform.y;
      layout.relativeProductFraction = transform.scale;
      layout.rotation = transform.rotation;
    }
    group.layout = layout;
    group.layoutHash = compositionLayoutHash(layout);
  }
}

export function parseProjectState(value: unknown): CanvasProjectState {
  assertSafeWire(value, "project");
  const object = objectValue(value, "project");
  exactKeys(object, ["schemaVersion", "semanticState", "layoutState"], "project");
  const schemaVersion = integerValue(object.schemaVersion, "project.schemaVersion");
  if (schemaVersion !== 1) {
    fail("project.schemaVersion", `unsupported schema version ${schemaVersion}`);
  }
  const semanticWire = objectValue(object.semanticState, "project.semanticState");
  const rawGroups = Array.isArray(semanticWire.compositionGroups)
    ? semanticWire.compositionGroups
    : [];
  const legacyGroupIds = new Set(
    rawGroups.flatMap((candidate) => {
      if (typeof candidate !== "object" || candidate === null || Array.isArray(candidate)) {
        return [];
      }
      const group = candidate as Record<string, unknown>;
      return group.layout === undefined && typeof group.id === "string" ? [group.id] : [];
    }),
  );
  const project: CanvasProjectState = {
    schemaVersion: 1,
    semanticState: parseSemanticState(object.semanticState, "project.semanticState"),
    layoutState: parseLayoutState(object.layoutState, "project.layoutState"),
  };
  migrateLegacyCompositionGroups(project, legacyGroupIds);
  const fallbackAssetIds = new Set<string>();
  for (const node of project.semanticState.nodes) {
    if (
      node.kind === "product_source" &&
      node.assetId !== null &&
      node.parameters.allowOpaqueFallback === true
    ) {
      fallbackAssetIds.add(node.assetId);
      delete node.parameters.allowOpaqueFallback;
    }
  }
  for (const layer of project.layoutState.productLayers) {
    if (layer.skuId === null && fallbackAssetIds.has(layer.sourceAssetId)) {
      layer.allowOpaqueFallback = true;
    }
  }
  validateProjectReferences(project);
  return project;
}

function stableJson(value: unknown, path: string): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      fail(path, "JSON numbers must be finite");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value
      .map((item, index) => stableJson(item, `${path}[${index}]`))
      .join(",")}]`;
  }
  const object = objectValue(value, path);
  return `{${Object.keys(object)
    .sort()
    .map(
      (key) =>
        `${JSON.stringify(key)}:${stableJson(object[key], `${path}.${key}`)}`,
    )
    .join(",")}}`;
}

export function serializeProjectState(state: CanvasProjectState): string {
  return stableJson(parseProjectState(state), "project");
}
