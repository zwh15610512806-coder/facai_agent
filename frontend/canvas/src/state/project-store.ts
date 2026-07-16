import {
  createEmptyProjectState,
  createEmptyRuntimeState,
  type CanvasNode,
  type CanvasProjectState,
  type CompleteSetOutput,
  type DispatchResult,
  type OutputBoard,
  type OutputType,
  type PendingConfirmation,
  type ProjectAction,
  type ProjectDiff,
  type ProjectIdentity,
  type ProjectRuntimeState,
  type SkuId,
  type TaskSnapshot,
  type TypedEdge,
} from "../domain/types";
import {
  parseProjectState,
  serializeProjectState,
  validateTypedEdge,
} from "../domain/validation";
import { canConnectNodes } from "../domain/node-ports";
import {
  compositionLayoutHash,
  compositionTransform,
  DEFAULT_COMPOSITION_LAYOUT,
} from "../domain/composition";
import {
  patchTextContentWithoutReflow,
  patchTextLineHeight,
} from "../domain/text-layout";
import {
  canonicalManagedGroup,
  managedBoardId,
  managedOutputNodeId,
  synchronizeCompleteSetProjection,
} from "./complete-set-projection";
import {
  createHistoryState,
  recordHistory,
  redoHistory,
  undoHistory,
  type HistoryState,
} from "./history";

export interface ProjectStoreState {
  project: CanvasProjectState;
  runtime: ProjectRuntimeState;
}

export interface ProjectStore {
  getState(): ProjectStoreState;
  dispatch(action: ProjectAction): DispatchResult;
  canUndo(): boolean;
  canRedo(): boolean;
  undo(): boolean;
  redo(): boolean;
  subscribe(listener: () => void): () => void;
  acknowledgeRevision(revision: number): void;
  replaceProject(project: CanvasProjectState, identity?: ProjectIdentity): void;
}

export interface ProjectReduction {
  state: ProjectStoreState;
  result: DispatchResult;
}

const SYSTEM_PIPELINE_NODE_IDS = new Set(["main-product-source", "main-product-cutout"]);
const SINGLETON_INPUT_EDGE_KINDS = new Set<TypedEdge["kind"]>([
  "product_asset",
  "cutout_asset",
  "prompt",
  "background_image",
  "composition",
  "output_image",
]);

function assertNever(value: never): never {
  throw new Error(`unsupported project action: ${String(value)}`);
}

function emptyOutput(outputType: OutputType, skuId: SkuId | null): CompleteSetOutput {
  return {
    outputType,
    skuId,
    quantity: null,
    aspectRatio: null,
    width: null,
    height: null,
    prompt: "",
    modelProfileId: null,
    modelParameters: {},
    referenceAssetId: null,
    compositionGroupId: null,
  };
}

function enableOutput(project: CanvasProjectState, outputType: OutputType): boolean {
  const settings = project.semanticState.completeSet;
  if (settings.selectedOutputTypes.includes(outputType)) {
    return false;
  }
  settings.selectedOutputTypes.push(outputType);
  if (outputType !== "sku") {
    settings.outputs.push(emptyOutput(outputType, null));
  }
  const group = canonicalManagedGroup(outputType);
  project.semanticState.nodes.push(...group.nodes);
  project.semanticState.edges.push(...group.edges);
  return true;
}

function requireQuantity(quantity: number | null): void {
  if (
    quantity !== null &&
    (!Number.isInteger(quantity) || quantity < 1 || quantity > 500)
  ) {
    throw new Error("output quantity must be null or an integer between 1 and 500");
  }
}

function appendMissingBoards(
  project: CanvasProjectState,
  outputType: OutputType,
  skuId: SkuId | null,
  quantity: number,
): void {
  const existingBoards = new Map(
    project.semanticState.outputBoards.map((board) => [board.id, board]),
  );
  for (let ordinal = 1; ordinal <= quantity; ordinal += 1) {
    const id = managedBoardId(outputType, ordinal, skuId);
    const existing = existingBoards.get(id);
    if (existing !== undefined) {
      const outputNode = project.semanticState.nodes.find(
        (node) => node.id === existing.outputNodeId,
      );
      if (
        existing.outputNodeId !== managedOutputNodeId(outputType, id) ||
        existing.outputType !== outputType ||
        existing.skuId !== skuId ||
        outputNode?.managedBy !== "complete-set" ||
        outputNode.outputBoardId !== id
      ) {
        throw new Error(`managed board id collision: ${id}`);
      }
    } else {
      const outputNodeId = managedOutputNodeId(outputType, id);
      project.semanticState.outputBoards.push({
        id,
        outputNodeId,
        outputType,
        skuId,
        sortOrder: project.semanticState.outputBoards.length,
        selectedResultAssetId: null,
      });
      project.semanticState.nodes.push({
        id: outputNodeId,
        kind: `${outputType}_output` as CanvasNode["kind"],
        managedBy: "complete-set",
        skuId,
        assetId: null,
        modelProfileId: null,
        prompt: null,
        compositionGroupId: null,
        textSnapshotId: null,
        outputBoardId: id,
        parameters: {},
      } as CanvasNode);
      project.semanticState.edges.push({
        id: `complete-set:${outputType}:edge:output:${id}`,
        kind: "output_image",
        sourceNodeId: `complete-set:${outputType}:generation`,
        sourcePort: "output",
        targetNodeId: outputNodeId,
        targetPort: "input",
        skuId: null,
      });
      const appended = project.semanticState.outputBoards.at(-1);
      if (appended !== undefined) {
        existingBoards.set(id, appended);
      }
    }
  }
}

function desiredBoardIds(
  outputType: OutputType,
  skuId: SkuId | null,
  quantity: number | null,
): Set<string> {
  const ids = new Set<string>();
  for (let ordinal = 1; ordinal <= (quantity ?? 0); ordinal += 1) {
    ids.add(managedBoardId(outputType, ordinal, skuId));
  }
  return ids;
}

function boardsRemovedByQuantity(
  project: CanvasProjectState,
  outputType: OutputType,
  skuId: SkuId | null,
  quantity: number | null,
): OutputBoard[] {
  const desired = desiredBoardIds(outputType, skuId, quantity);
  const possibleManagedIds = desiredBoardIds(outputType, skuId, 500);
  return project.semanticState.outputBoards.filter(
    (board) =>
      board.outputNodeId === managedOutputNodeId(outputType, board.id) &&
      board.outputType === outputType &&
      board.skuId === skuId &&
      possibleManagedIds.has(board.id) &&
      !desired.has(board.id),
  );
}

function removeManagedBoards(
  project: CanvasProjectState,
  removed: readonly OutputBoard[],
): void {
  const boardIds = new Set(removed.map((board) => board.id));
  const nodeIds = new Set(removed.map((board) => board.outputNodeId));
  project.semanticState.outputBoards = project.semanticState.outputBoards.filter(
    (board) => !boardIds.has(board.id),
  );
  project.semanticState.nodes = project.semanticState.nodes.filter(
    (node) => !nodeIds.has(node.id),
  );
  project.semanticState.edges = project.semanticState.edges.filter(
    (edge) => !nodeIds.has(edge.sourceNodeId) && !nodeIds.has(edge.targetNodeId),
  );
  for (const nodeId of nodeIds) {
    delete project.layoutState.nodePositions[nodeId];
  }
}

function canonicalIdentity(value: unknown, path = "identity"): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new Error(`confirmation identity contains a non-finite number at ${path}`);
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value
      .map((item, index) => canonicalIdentity(item, `${path}[${index}]`))
      .join(",")}]`;
  }
  if (typeof value !== "object" || value === undefined) {
    throw new Error(`confirmation identity contains a non-JSON value at ${path}`);
  }
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object)
    .sort()
    .map(
      (key) =>
        `${JSON.stringify(key)}:${canonicalIdentity(object[key], `${path}.${key}`)}`,
    )
    .join(",")}}`;
}

function injectiveToken(prefix: string, identity: string): string {
  const bytes = new TextEncoder().encode(identity);
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
  return `${prefix}:${hex}`;
}

function createDiff(
  state: ProjectStoreState,
  actionType: ProjectDiff["actionType"],
  removedBoards: OutputBoard[],
  removedNodeIds: string[] = [],
  removedEdgeIds: string[] = [],
  addedNodeIds: string[] = [],
  addedEdgeIds: string[] = [],
  addedBoardIds: string[] = [],
  preservedCustomNodeIds: string[] = [],
): ProjectDiff {
  const boardIds = new Set(removedBoards.map((board) => board.id));
  const taskIds = Object.values(state.runtime.taskSnapshots)
    .filter((task) => task.boardId !== null && boardIds.has(task.boardId))
    .map((task) => task.id)
    .sort();
  const historyResultIds = state.runtime.resultHistory
    .filter((result) => result.boardId !== null && boardIds.has(result.boardId))
    .map((result) => result.id)
    .sort();
  const selectedResultAssetIds = removedBoards
    .flatMap((board) =>
      board.selectedResultAssetId === null ? [] : [board.selectedResultAssetId],
    )
    .sort();
  const diffWithoutId = {
    actionType,
    removedBoardIds: removedBoards.map((board) => board.id),
    removedNodeIds,
    removedEdgeIds,
    addedNodeIds,
    addedEdgeIds,
    addedBoardIds,
    selectedResultAssetIds,
    taskIds,
    historyResultIds,
    preservedCustomNodeIds,
  };
  const identity = canonicalIdentity(diffWithoutId, "diff");
  return {
    id: injectiveToken("canvas-diff", identity),
    ...diffWithoutId,
  };
}

function diffHasBoardImpact(diff: ProjectDiff): boolean {
  return (
    diff.selectedResultAssetIds.length > 0 ||
    diff.taskIds.length > 0 ||
    diff.historyResultIds.length > 0
  );
}

type ConfirmationAction =
  | Extract<ProjectAction, { type: "output/disable" }>
  | Extract<ProjectAction, { type: "output/setQuantity" }>
  | Extract<ProjectAction, { type: "sku/setOutputQuantity" }>
  | Extract<ProjectAction, { type: "completeSet/rebuild" }>;

function confirmationActionIdentity(action: ConfirmationAction): string {
  switch (action.type) {
    case "output/disable":
      return canonicalIdentity(
        { type: action.type, outputType: action.outputType },
        "action",
      );
    case "output/setQuantity":
      return canonicalIdentity(
        {
          type: action.type,
          outputType: action.outputType,
          quantity: action.quantity,
        },
        "action",
      );
    case "sku/setOutputQuantity":
      return canonicalIdentity(
        {
          type: action.type,
          skuId: action.skuId,
          quantity: action.quantity,
        },
        "action",
      );
    case "completeSet/rebuild":
      return canonicalIdentity({ type: action.type }, "action");
  }
  return assertNever(action);
}

function confirmationBaseStateFingerprint(state: ProjectStoreState): string {
  const taskSnapshots = Object.entries(state.runtime.taskSnapshots)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([taskId, task]) => ({ taskId, task }));
  return canonicalIdentity(
    {
      project: serializeProjectState(state.project),
      runtime: {
        projectId: state.runtime.projectId,
        revision: state.runtime.revision,
        selectedNodeId: state.runtime.selectedNodeId,
        selectedBoardId: state.runtime.selectedBoardId,
        taskSnapshots,
        resultHistory: state.runtime.resultHistory,
        unlinkedBoards: state.runtime.unlinkedBoards,
        uploadIds: state.runtime.uploadIds,
        paidGenerationRequestIds: state.runtime.paidGenerationRequestIds,
      },
    },
    "baseState",
  );
}

function buildPendingConfirmation(
  state: ProjectStoreState,
  action: ConfirmationAction,
  diff: ProjectDiff,
): PendingConfirmation {
  const actionIdentity = confirmationActionIdentity(action);
  const baseStateFingerprint = confirmationBaseStateFingerprint(state);
  const diffIdentity = canonicalIdentity(diff, "diffIdentity");
  const challengeIdentity = canonicalIdentity(
    {
      version: 1,
      projectId: state.runtime.projectId,
      revision: state.runtime.revision,
      actionIdentity,
      baseStateFingerprint,
      diffIdentity,
    },
    "challenge",
  );
  return {
    token: injectiveToken("canvas-confirmation", challengeIdentity),
    actionIdentity,
    baseStateFingerprint,
    diffIdentity,
    projectId: state.runtime.projectId,
    revision: state.runtime.revision,
    diff: structuredClone(diff),
  };
}

function confirmationGate(
  state: ProjectStoreState,
  action: ConfirmationAction,
  diff: ProjectDiff,
): ProjectReduction | null {
  const expected = buildPendingConfirmation(state, action, diff);
  if (action.acceptedDiffId === undefined) {
    const nextState =
      state.runtime.pendingConfirmation?.token === expected.token
        ? state
        : {
            ...state,
            runtime: {
              ...state.runtime,
              pendingConfirmation: expected,
            },
          };
    return {
      state: nextState,
      result: {
        applied: false,
        confirmation: { token: expected.token, diff: expected.diff },
      },
    };
  }

  const pending = state.runtime.pendingConfirmation;
  if (
    pending === null ||
    action.acceptedDiffId !== pending.token ||
    pending.token !== expected.token ||
    pending.actionIdentity !== expected.actionIdentity ||
    pending.baseStateFingerprint !== expected.baseStateFingerprint ||
    pending.diffIdentity !== expected.diffIdentity ||
    pending.projectId !== expected.projectId ||
    pending.revision !== expected.revision
  ) {
    return { state, result: { applied: false } };
  }
  return null;
}

function reindexBoards(project: CanvasProjectState): void {
  project.semanticState.outputBoards.forEach((board, index) => {
    board.sortOrder = index;
  });
}

function archiveRemovedBoards(
  runtime: ProjectRuntimeState,
  removedBoards: OutputBoard[],
): void {
  for (const board of removedBoards) {
    const taskIds = Object.values(runtime.taskSnapshots)
      .filter((task) => task.boardId === board.id)
      .map((task) => task.id)
      .sort();
    const resultIds = runtime.resultHistory
      .filter((result) => result.boardId === board.id)
      .map((result) => result.id)
      .sort();
    if (
      board.selectedResultAssetId === null &&
      taskIds.length === 0 &&
      resultIds.length === 0
    ) {
      continue;
    }
    const snapshot = {
      boardId: board.id,
      selectedResultAssetId: board.selectedResultAssetId,
      taskIds,
      resultIds,
    };
    const existingIndex = runtime.unlinkedBoards.findIndex(
      (candidate) => candidate.boardId === board.id,
    );
    if (existingIndex === -1) {
      runtime.unlinkedBoards.push(snapshot);
    } else {
      runtime.unlinkedBoards[existingIndex] = snapshot;
    }
  }
}

function synchronizeUnlinkedBoardsForProjectTransition(
  runtime: ProjectRuntimeState,
  previousProject: CanvasProjectState,
  nextProject: CanvasProjectState,
): void {
  const nextBoardIds = new Set(
    nextProject.semanticState.outputBoards.map((board) => board.id),
  );
  runtime.unlinkedBoards = runtime.unlinkedBoards.filter(
    (snapshot) => !nextBoardIds.has(snapshot.boardId),
  );
  archiveRemovedBoards(
    runtime,
    previousProject.semanticState.outputBoards.filter(
      (board) => !nextBoardIds.has(board.id),
    ),
  );
}

function recordTask(runtime: ProjectRuntimeState, task: TaskSnapshot): boolean {
  const previous = runtime.taskSnapshots[task.id];
  const unchanged = previous !== undefined && JSON.stringify(previous) === JSON.stringify(task);
  const incomingResultIdentities = new Map<string, string>();
  for (const result of task.results) {
    const identity = canonicalIdentity(result, `task.results.${result.id}`);
    const duplicateIdentity = incomingResultIdentities.get(result.id);
    const existing = runtime.resultHistory.find(
      (candidate) => candidate.id === result.id,
    );
    if (
      (duplicateIdentity !== undefined && duplicateIdentity !== identity) ||
      (existing !== undefined &&
        canonicalIdentity(existing, `resultHistory.${result.id}`) !== identity)
    ) {
      throw new Error(`immutable result id conflict ${result.id}`);
    }
    incomingResultIdentities.set(result.id, identity);
  }

  runtime.taskSnapshots[task.id] = structuredClone(task);
  let addedResult = false;
  for (const result of task.results) {
    const index = runtime.resultHistory.findIndex((candidate) => candidate.id === result.id);
    if (index === -1) {
      runtime.resultHistory.push(structuredClone(result));
      addedResult = true;
    }
    if (result.boardId !== null) {
      const permitted = new Set(runtime.allowedResultAssetIds[result.boardId] ?? []);
      permitted.add(result.assetId);
      runtime.allowedResultAssetIds[result.boardId] = [...permitted].sort();
    }
  }
  return !unchanged || addedResult;
}

function canonicalManagedState(project: CanvasProjectState): {
  nodes: CanvasProjectState["semanticState"]["nodes"];
  edges: TypedEdge[];
  boards: OutputBoard[];
} {
  const nodes: CanvasProjectState["semanticState"]["nodes"] = [];
  const edges: TypedEdge[] = [];
  for (const outputType of project.semanticState.completeSet.selectedOutputTypes) {
    const group = canonicalManagedGroup(outputType);
    if (outputType !== "sku") {
      const output = project.semanticState.completeSet.outputs.find(
        (candidate) =>
          candidate.outputType === outputType && candidate.skuId === null,
      );
      const outputNode = group.nodes.find(
        (candidate) => candidate.id === managedOutputNodeId(outputType),
      );
      if (output !== undefined && outputNode !== undefined) {
        outputNode.prompt = output.prompt === "" ? null : output.prompt;
        outputNode.modelProfileId = output.modelProfileId;
        outputNode.parameters = structuredClone(output.modelParameters);
      }
    }
    nodes.push(...group.nodes);
    edges.push(...group.edges);
  }

  const boards: OutputBoard[] = [];
  for (const outputType of project.semanticState.completeSet.selectedOutputTypes) {
    const outputs = project.semanticState.completeSet.outputs.filter(
      (output) => output.outputType === outputType,
    );
    for (const output of outputs) {
      for (let ordinal = 1; ordinal <= (output.quantity ?? 0); ordinal += 1) {
        const boardId = managedBoardId(output.outputType, ordinal, output.skuId);
        const outputNodeId = managedOutputNodeId(output.outputType, boardId);
        boards.push({
          id: boardId,
          outputNodeId,
          outputType: output.outputType,
          skuId: output.skuId,
          sortOrder: boards.length,
          selectedResultAssetId: null,
        });
        nodes.push({
          id: outputNodeId,
          kind: `${output.outputType}_output` as CanvasNode["kind"],
          managedBy: "complete-set",
          skuId: output.skuId,
          assetId: null,
          modelProfileId: null,
          prompt: null,
          compositionGroupId: null,
          textSnapshotId: null,
          outputBoardId: boardId,
          parameters: {},
        } as CanvasNode);
        edges.push({
          id: `complete-set:${output.outputType}:edge:output:${boardId}`,
          kind: "output_image",
          sourceNodeId: `complete-set:${output.outputType}:generation`,
          sourcePort: "output",
          targetNodeId: outputNodeId,
          targetPort: "input",
          skuId: null,
        });
      }
    }
  }
  return { nodes, edges, boards };
}

function typedEdgesEqual(left: TypedEdge, right: TypedEdge): boolean {
  return (
    left.id === right.id &&
    left.kind === right.kind &&
    left.sourceNodeId === right.sourceNodeId &&
    left.sourcePort === right.sourcePort &&
    left.targetNodeId === right.targetNodeId &&
    left.targetPort === right.targetPort &&
    left.skuId === right.skuId
  );
}

function explicitManagedEdges(
  project: CanvasProjectState,
  outputTypes: readonly OutputType[],
): TypedEdge[] {
  const expectedEdges = canonicalManagedState(project).edges.filter((edge) =>
    outputTypes.some((outputType) => edge.id.startsWith(`complete-set:${outputType}:`)),
  );
  const managedNodeIds = new Set(
    project.semanticState.nodes
      .filter((node) => node.managedBy === "complete-set")
      .map((node) => node.id),
  );
  return project.semanticState.edges.filter(
    (edge) =>
      managedNodeIds.has(edge.sourceNodeId) &&
      managedNodeIds.has(edge.targetNodeId) &&
      expectedEdges.some((expected) => typedEdgesEqual(edge, expected)),
  );
}

function assertRebuildManagedIdsAvailable(
  project: CanvasProjectState,
  desired: ReturnType<typeof canonicalManagedState>,
): void {
  for (const desiredNode of desired.nodes) {
    const existing = project.semanticState.nodes.find(
      (node) => node.id === desiredNode.id,
    );
    if (existing !== undefined && existing.managedBy !== "complete-set") {
      throw new Error(`canonical managed node id collision: ${desiredNode.id}`);
    }
  }
  for (const desiredEdge of desired.edges) {
    const existing = project.semanticState.edges.find(
      (edge) => edge.id === desiredEdge.id,
    );
    if (existing === undefined) {
      continue;
    }
    const source = project.semanticState.nodes.find(
      (node) => node.id === existing.sourceNodeId,
    );
    const target = project.semanticState.nodes.find(
      (node) => node.id === existing.targetNodeId,
    );
    if (
      source?.managedBy !== "complete-set" ||
      target?.managedBy !== "complete-set" ||
      existing.kind !== desiredEdge.kind ||
      existing.sourceNodeId !== desiredEdge.sourceNodeId ||
      existing.sourcePort !== desiredEdge.sourcePort ||
      existing.targetNodeId !== desiredEdge.targetNodeId ||
      existing.targetPort !== desiredEdge.targetPort ||
      existing.skuId !== desiredEdge.skuId
    ) {
      throw new Error(`canonical managed edge id collision: ${desiredEdge.id}`);
    }
  }
  for (const desiredBoard of desired.boards) {
    const existing = project.semanticState.outputBoards.find(
      (board) => board.id === desiredBoard.id,
    );
    if (existing === undefined) {
      continue;
    }
    const outputNode = project.semanticState.nodes.find(
      (node) => node.id === existing.outputNodeId,
    );
    if (
      outputNode?.managedBy !== "complete-set" ||
      existing.outputNodeId !== desiredBoard.outputNodeId ||
      existing.outputType !== desiredBoard.outputType ||
      existing.skuId !== desiredBoard.skuId
    ) {
      throw new Error(`canonical managed board id collision: ${desiredBoard.id}`);
    }
  }
}

function rebuildDiff(state: ProjectStoreState): ProjectDiff {
  const removedNodes = state.project.semanticState.nodes.filter(
    (node) => node.managedBy === "complete-set",
  );
  const removedNodeIds = removedNodes.map((node) => node.id);
  const removedNodeSet = new Set(removedNodeIds);
  const removedEdges = explicitManagedEdges(state.project, [
    "main",
    "sku",
    "detail",
  ]);
  const removedBoards = state.project.semanticState.outputBoards.filter(
    (board) => removedNodeSet.has(board.outputNodeId),
  );
  const desired = canonicalManagedState(state.project);
  assertRebuildManagedIdsAvailable(state.project, desired);
  const preservedCustomNodeIds = state.project.semanticState.nodes
    .filter((node) => node.managedBy !== "complete-set")
    .map((node) => node.id);
  return createDiff(
    state,
    "completeSet/rebuild",
    removedBoards,
    removedNodeIds,
    removedEdges.map((edge) => edge.id),
    desired.nodes.map((node) => node.id),
    desired.edges.map((edge) => edge.id),
    desired.boards.map((board) => board.id),
    preservedCustomNodeIds,
  );
}

function applyRebuild(current: ProjectStoreState, diff: ProjectDiff): ProjectStoreState {
  const state = structuredClone(current);
  const removedNodeIds = new Set(diff.removedNodeIds);
  const removedEdgeIds = new Set(diff.removedEdgeIds);
  const removedBoardIds = new Set(diff.removedBoardIds);
  const removedBoards = state.project.semanticState.outputBoards.filter((board) =>
    removedBoardIds.has(board.id),
  );
  state.project.semanticState.nodes = state.project.semanticState.nodes.filter(
    (node) => !removedNodeIds.has(node.id),
  );
  state.project.semanticState.edges = state.project.semanticState.edges.filter(
    (edge) => !removedEdgeIds.has(edge.id),
  );
  state.project.semanticState.outputBoards =
    state.project.semanticState.outputBoards.filter(
      (board) => !removedBoardIds.has(board.id),
    );
  archiveRemovedBoards(state.runtime, removedBoards);
  const desired = canonicalManagedState(state.project);
  state.project.semanticState.nodes.push(...desired.nodes);
  state.project.semanticState.edges.push(...desired.edges);
  state.project.semanticState.outputBoards.push(...desired.boards);
  reindexBoards(state.project);
  synchronizeCompleteSetProjection(state.project);
  return state;
}

function reduceProjectStateUnchecked(
  current: ProjectStoreState,
  action: ProjectAction,
): ProjectReduction {
  switch (action.type) {
    case "output/enable": {
      const state = structuredClone(current);
      const applied = enableOutput(state.project, action.outputType);
      if (applied) {
        synchronizeCompleteSetProjection(state.project);
      }
      return { state: applied ? state : current, result: { applied } };
    }
    case "output/setQuantity": {
      requireQuantity(action.quantity);
      const output = current.project.semanticState.completeSet.outputs.find(
        (candidate) =>
          candidate.outputType === action.outputType && candidate.skuId === null,
      );
      const currentQuantity = output?.quantity ?? null;
      if (currentQuantity === action.quantity) {
        return { state: current, result: { applied: false } };
      }
      const removed = boardsRemovedByQuantity(
        current.project,
        action.outputType,
        null,
        action.quantity,
      );
      if (removed.length > 0) {
        const diff = createDiff(current, action.type, removed);
        if (diffHasBoardImpact(diff)) {
          const confirmation = confirmationGate(current, action, diff);
          if (confirmation !== null) {
            return confirmation;
          }
        }
      }
      const state = structuredClone(current);
      enableOutput(state.project, action.outputType);
      const nextOutput = state.project.semanticState.completeSet.outputs.find(
        (candidate) =>
          candidate.outputType === action.outputType && candidate.skuId === null,
      );
      if (nextOutput === undefined) {
        throw new Error(`missing complete-set output ${action.outputType}`);
      }
      nextOutput.quantity = action.quantity;
      if (removed.length > 0) {
        removeManagedBoards(state.project, removed);
        archiveRemovedBoards(state.runtime, removed);
        reindexBoards(state.project);
      }
      if (action.quantity !== null) {
        appendMissingBoards(state.project, action.outputType, null, action.quantity);
      }
      synchronizeCompleteSetProjection(state.project);
      return { state, result: { applied: true } };
    }
    case "sku/setOutputQuantity": {
      requireQuantity(action.quantity);
      const output = current.project.semanticState.completeSet.outputs.find(
        (candidate) =>
          candidate.outputType === "sku" && candidate.skuId === action.skuId,
      );
      const currentQuantity = output?.quantity ?? null;
      if (output !== undefined && currentQuantity === action.quantity) {
        return { state: current, result: { applied: false } };
      }
      const removed = boardsRemovedByQuantity(
        current.project,
        "sku",
        action.skuId,
        action.quantity,
      );
      if (removed.length > 0) {
        const diff = createDiff(current, action.type, removed);
        if (diffHasBoardImpact(diff)) {
          const confirmation = confirmationGate(current, action, diff);
          if (confirmation !== null) {
            return confirmation;
          }
        }
      }
      const state = structuredClone(current);
      enableOutput(state.project, "sku");
      let nextOutput = state.project.semanticState.completeSet.outputs.find(
        (candidate) =>
          candidate.outputType === "sku" && candidate.skuId === action.skuId,
      );
      if (nextOutput === undefined) {
        nextOutput = emptyOutput("sku", action.skuId);
        state.project.semanticState.completeSet.outputs.push(nextOutput);
      }
      nextOutput.quantity = action.quantity;
      if (removed.length > 0) {
        removeManagedBoards(state.project, removed);
        archiveRemovedBoards(state.runtime, removed);
        reindexBoards(state.project);
      }
      if (action.quantity !== null) {
        appendMissingBoards(state.project, "sku", action.skuId, action.quantity);
      }
      synchronizeCompleteSetProjection(state.project);
      return { state, result: { applied: true } };
    }
    case "output/configure": {
      if ((action.outputType === "sku") !== (action.skuId !== null)) {
        throw new Error("SKU output configuration requires exactly one SKU");
      }
      const output = current.project.semanticState.completeSet.outputs.find(
        (candidate) => candidate.outputType === action.outputType && candidate.skuId === action.skuId,
      );
      if (output === undefined) {
        throw new Error("configure an output only after selecting it");
      }
      if (JSON.stringify(output) === JSON.stringify({ ...output, ...action.patch })) {
        return { state: current, result: { applied: false } };
      }
      const state = structuredClone(current);
      const nextOutput = state.project.semanticState.completeSet.outputs.find(
        (candidate) => candidate.outputType === action.outputType && candidate.skuId === action.skuId,
      );
      if (nextOutput === undefined) {
        throw new Error("complete-set output disappeared while configuring");
      }
      Object.assign(nextOutput, structuredClone(action.patch));
      if (action.outputType !== "sku") {
        const node = state.project.semanticState.nodes.find(
          (candidate) => candidate.id === managedOutputNodeId(action.outputType),
        );
        if (node !== undefined) {
          node.prompt = nextOutput.prompt === "" ? null : nextOutput.prompt;
          node.modelProfileId = nextOutput.modelProfileId;
          node.parameters = structuredClone(nextOutput.modelParameters);
        }
      }
      synchronizeCompleteSetProjection(state.project);
      return { state, result: { applied: true } };
    }
    case "output/disable": {
      if (
        !current.project.semanticState.completeSet.selectedOutputTypes.includes(
          action.outputType,
        )
      ) {
        return { state: current, result: { applied: false } };
      }
      const prefix = `complete-set:${action.outputType}:`;
      const removedNodes = current.project.semanticState.nodes.filter(
        (node) =>
          node.managedBy === "complete-set" && node.id.startsWith(prefix),
      );
      const removedNodeIds = removedNodes.map((node) => node.id);
      const removedNodeSet = new Set(removedNodeIds);
      const managedEdges = explicitManagedEdges(current.project, [
        action.outputType,
      ]);
      const managedEdgeIds = new Set(managedEdges.map((edge) => edge.id));
      const removedEdges = current.project.semanticState.edges.filter(
        (edge) =>
          removedNodeSet.has(edge.sourceNodeId) ||
          removedNodeSet.has(edge.targetNodeId),
      );
      const hasCustomIncidentEdge = removedEdges.some(
        (edge) => !managedEdgeIds.has(edge.id),
      );
      const removedBoards = current.project.semanticState.outputBoards.filter(
        (board) => removedNodeSet.has(board.outputNodeId),
      );
      const diff = createDiff(
        current,
        action.type,
        removedBoards,
        removedNodeIds,
        removedEdges.map((edge) => edge.id),
      );
      if (diffHasBoardImpact(diff) || hasCustomIncidentEdge) {
        const confirmation = confirmationGate(current, action, diff);
        if (confirmation !== null) {
          return confirmation;
        }
      }
      const state = structuredClone(current);
      const removedEdgeIds = new Set(removedEdges.map((edge) => edge.id));
      const removedBoardIds = new Set(removedBoards.map((board) => board.id));
      state.project.semanticState.completeSet.selectedOutputTypes =
        state.project.semanticState.completeSet.selectedOutputTypes.filter(
          (outputType) => outputType !== action.outputType,
        );
      state.project.semanticState.completeSet.outputs =
        state.project.semanticState.completeSet.outputs.filter(
          (output) => output.outputType !== action.outputType,
        );
      state.project.semanticState.nodes = state.project.semanticState.nodes.filter(
        (node) => !removedNodeSet.has(node.id),
      );
      for (const nodeId of removedNodeSet) {
        delete state.project.layoutState.nodePositions[nodeId];
      }
      state.project.semanticState.edges = state.project.semanticState.edges.filter(
        (edge) => !removedEdgeIds.has(edge.id),
      );
      state.project.semanticState.outputBoards =
        state.project.semanticState.outputBoards.filter(
          (board) => !removedBoardIds.has(board.id),
        );
      archiveRemovedBoards(state.runtime, removedBoards);
      reindexBoards(state.project);
      synchronizeCompleteSetProjection(state.project);
      return { state, result: { applied: true } };
    }
    case "board/selectResult": {
      const board = current.project.semanticState.outputBoards.find(
        (candidate) => candidate.id === action.boardId,
      );
      if (board === undefined) {
        throw new Error(`unknown output board ${action.boardId}`);
      }
      const permitted = current.runtime.allowedResultAssetIds[action.boardId];
      if (
        action.assetId !== null &&
        (permitted === undefined || !permitted.includes(action.assetId))
      ) {
        throw new Error("selected asset is not a permitted result version");
      }
      if (board.selectedResultAssetId === action.assetId) {
        return { state: current, result: { applied: false } };
      }
      const state = structuredClone(current);
      const nextBoard = state.project.semanticState.outputBoards.find(
        (candidate) => candidate.id === action.boardId,
      );
      if (nextBoard === undefined) {
        throw new Error(`unknown output board ${action.boardId}`);
      }
      nextBoard.selectedResultAssetId = action.assetId;
      return { state, result: { applied: true } };
    }
    case "task/statusReceived": {
      const state = structuredClone(current);
      const applied = recordTask(state.runtime, action.task);
      return { state: applied ? state : current, result: { applied } };
    }
    case "runtime/setAllowedResultAssets": {
      const assetIds = [...new Set(action.assetIds)].sort();
      const currentAllowed = current.runtime.allowedResultAssetIds[action.boardId];
      if (JSON.stringify(currentAllowed ?? []) === JSON.stringify(assetIds)) {
        return { state: current, result: { applied: false } };
      }
      const state = structuredClone(current);
      state.runtime.allowedResultAssetIds[action.boardId] = assetIds;
      return { state, result: { applied: true } };
    }
    case "asset/useRectangularSource": {
      const layer = current.project.layoutState.productLayers.find(
        (candidate) =>
          candidate.skuId === null &&
          candidate.locked &&
          candidate.sourceAssetId === action.workingAssetId,
      );
      if (layer === undefined) {
        throw new Error("rectangular fallback requires the locked main working asset");
      }
      if (
        layer.renderAssetId === action.workingAssetId &&
        layer.allowOpaqueFallback
      ) {
        return { state: current, result: { applied: false } };
      }
      const state = structuredClone(current);
      const nextLayer = state.project.layoutState.productLayers.find(
        (candidate) => candidate.id === layer.id,
      );
      if (nextLayer === undefined) {
        throw new Error("rectangular fallback projection is unavailable");
      }
      nextLayer.renderAssetId = action.workingAssetId;
      nextLayer.allowOpaqueFallback = true;
      if (nextLayer.compositionGroupId !== null) {
        for (const member of state.project.layoutState.productLayers) {
          if (
            member.compositionGroupId === nextLayer.compositionGroupId &&
            member.sourceAssetId === action.workingAssetId
          ) {
            member.renderAssetId = action.workingAssetId;
            member.allowOpaqueFallback = true;
          }
        }
      }
      return { state, result: { applied: true } };
    }
    case "mode/set": {
      if (current.project.semanticState.mode === action.mode) {
        return { state: current, result: { applied: false } };
      }
      const state = structuredClone(current);
      state.project.semanticState.mode = action.mode;
      return { state, result: { applied: true } };
    }
    case "viewport/set": {
      const viewport = structuredClone(action.viewport);
      if (
        !Number.isFinite(viewport.x) ||
        !Number.isFinite(viewport.y) ||
        !Number.isFinite(viewport.zoom) ||
        viewport.zoom <= 0 ||
        viewport.zoom > 1_000
      ) {
        throw new Error("canvas viewport must contain finite coordinates and a positive zoom");
      }
      const previous = current.project.layoutState.viewport;
      if (
        previous.x === viewport.x &&
        previous.y === viewport.y &&
        previous.zoom === viewport.zoom
      ) {
        return { state: current, result: { applied: false } };
      }
      const state = structuredClone(current);
      state.project.layoutState.viewport = viewport;
      return { state, result: { applied: true } };
    }
    case "node/add": {
      if (action.node.kind === "auto_cutout") {
        throw new Error("auto cutout nodes are projected by the system");
      }
      if (action.node.id === "main-product-source" || action.node.id === "main-product-cutout") {
        throw new Error("system product pipeline nodes are projected by the system");
      }
      if (
        current.project.semanticState.nodes.some(
          (candidate) => candidate.id === action.node.id,
        )
      ) {
        throw new Error(`duplicate canvas node ${action.node.id}`);
      }
      const state = structuredClone(current);
      state.project.semanticState.nodes.push(structuredClone(action.node));
      synchronizeCompleteSetProjection(state.project);
      return { state, result: { applied: true } };
    }
    case "node/update": {
      const node = current.project.semanticState.nodes.find(
        (candidate) => candidate.id === action.nodeId,
      );
      if (node === undefined) {
        throw new Error(`unknown canvas node ${action.nodeId}`);
      }
      if (node.id === "main-product-source" || node.id === "main-product-cutout") {
        throw new Error("system product pipeline nodes are immutable");
      }
      const state = structuredClone(current);
      const nextNode = state.project.semanticState.nodes.find(
        (candidate) => candidate.id === action.nodeId,
      );
      if (nextNode === undefined) {
        throw new Error(`unknown canvas node ${action.nodeId}`);
      }
      if ("prompt" in action.patch) {
        nextNode.prompt = action.patch.prompt ?? null;
      }
      if ("modelProfileId" in action.patch) {
        nextNode.modelProfileId = action.patch.modelProfileId ?? null;
      }
      if ("parameters" in action.patch) {
        nextNode.parameters = {
          ...nextNode.parameters,
          ...structuredClone(action.patch.parameters ?? {}),
        };
      }
      if ("assetId" in action.patch) {
        nextNode.assetId = action.patch.assetId ?? null;
      }
      if ("skuId" in action.patch) {
        nextNode.skuId = action.patch.skuId ?? null;
      }
      if ("compositionGroupId" in action.patch) {
        nextNode.compositionGroupId = action.patch.compositionGroupId ?? null;
      }
      synchronizeCompleteSetProjection(state.project);
      return { state, result: { applied: true } };
    }
    case "node/move": {
      if (
        !current.project.semanticState.nodes.some(
          (candidate) => candidate.id === action.nodeId,
        )
      ) {
        throw new Error(`unknown canvas node ${action.nodeId}`);
      }
      if (SYSTEM_PIPELINE_NODE_IDS.has(action.nodeId)) {
        throw new Error("system product pipeline nodes are immutable");
      }
      const state = structuredClone(current);
      state.project.layoutState.nodePositions[action.nodeId] = structuredClone(
        action.position,
      );
      return { state, result: { applied: true } };
    }
    case "edge/connect": {
      const edge = validateTypedEdge(action.edge);
      if (
        current.project.semanticState.edges.some(
          (candidate) => candidate.id === edge.id,
        )
      ) {
        throw new Error(`duplicate canvas edge ${edge.id}`);
      }
      const nodeIds = new Set(
        current.project.semanticState.nodes.map((candidate) => candidate.id),
      );
      if (
        !nodeIds.has(edge.sourceNodeId) ||
        !nodeIds.has(edge.targetNodeId)
      ) {
        throw new Error("canvas edge endpoints must exist before connect");
      }
      const source = current.project.semanticState.nodes.find(
        (candidate) => candidate.id === edge.sourceNodeId,
      );
      const target = current.project.semanticState.nodes.find(
        (candidate) => candidate.id === edge.targetNodeId,
      );
      if (
        source === undefined ||
        target === undefined ||
        !canConnectNodes(source.kind, target.kind, edge.kind)
      ) {
        throw new Error("incompatible node connection");
      }
      const isSystemCutoutOutput =
        edge.kind === "cutout_asset" &&
        edge.sourceNodeId === "main-product-cutout" &&
        source.id === "main-product-cutout" &&
        source.kind === "auto_cutout" &&
        target.kind === "model_generation";
      if (
        (SYSTEM_PIPELINE_NODE_IDS.has(edge.sourceNodeId) ||
          SYSTEM_PIPELINE_NODE_IDS.has(edge.targetNodeId)) &&
        !isSystemCutoutOutput
      ) {
        throw new Error("system product pipeline edges are projected by the system");
      }
      if (
        SINGLETON_INPUT_EDGE_KINDS.has(edge.kind) &&
        current.project.semanticState.edges.some(
          (candidate) =>
            candidate.kind === edge.kind &&
            candidate.targetNodeId === edge.targetNodeId,
        )
      ) {
        throw new Error("duplicate singleton input is not allowed");
      }
      const state = structuredClone(current);
      state.project.semanticState.edges.push(edge);
      synchronizeCompleteSetProjection(state.project);
      return { state, result: { applied: true } };
    }
    case "text/update": {
      const text = current.project.layoutState.textSnapshots.find(
        (candidate) => candidate.id === action.layerId,
      );
      if (text === undefined) {
        throw new Error(`unknown text layer ${action.layerId}`);
      }
      const state = structuredClone(current);
      const nextText = state.project.layoutState.textSnapshots.find(
        (candidate) => candidate.id === action.layerId,
      );
      if (nextText === undefined) {
        throw new Error(`unknown text layer ${action.layerId}`);
      }
      const patch = structuredClone(action.patch);
      if (patch.lineHeight !== undefined) {
        const metricBasis = {
          ...text,
          fontSize: patch.fontSize ?? text.fontSize,
        };
        const metrics = patchTextLineHeight(metricBasis, patch.lineHeight);
        if (
          patch.lines !== undefined
          && JSON.stringify(patch.lines) !== JSON.stringify(metrics.lines)
        ) {
          throw new Error("行距更新必须使用确定性的显式行坐标");
        }
        patch.lines = metrics.lines;
      }
      if (patch.lines !== undefined) {
        const derivedContent = patch.lines.map((line) => line.text).join("\n");
        if (patch.content !== undefined && patch.content !== derivedContent) {
          throw new Error("文字内容必须与显式行文本一致");
        }
        patch.content = derivedContent;
      } else if (patch.content !== undefined) {
        Object.assign(patch, patchTextContentWithoutReflow(text, patch.content));
      }
      Object.assign(nextText, patch);
      return { state, result: { applied: true } };
    }
    case "composition/update": {
      const group = current.project.semanticState.compositionGroups.find(
        (candidate) => candidate.id === action.groupId,
      );
      if (group === undefined) {
        throw new Error(`unknown composition group ${action.groupId}`);
      }
      if (JSON.stringify(group.layout) === JSON.stringify(action.layout)) {
        return { state: current, result: { applied: false } };
      }
      const state = structuredClone(current);
      const nextGroup = state.project.semanticState.compositionGroups.find(
        (candidate) => candidate.id === action.groupId,
      );
      if (nextGroup === undefined) {
        throw new Error(`unknown composition group ${action.groupId}`);
      }
      nextGroup.layout = structuredClone(action.layout);
      nextGroup.layoutHash = compositionLayoutHash(nextGroup.layout);
      const projection = compositionTransform(nextGroup.layout);
      for (const layerId of nextGroup.productLayerIds) {
        const layer = state.project.layoutState.productLayers.find(
          (candidate) => candidate.id === layerId,
        );
        if (layer === undefined || layer.compositionGroupId !== nextGroup.id) {
          throw new Error(`composition group ${nextGroup.id} has an invalid product member`);
        }
        state.project.layoutState.objectTransforms[layer.transformId] = {
          ...projection,
        };
      }
      return { state, result: { applied: true } };
    }
    case "composition/create": {
      const mainLayer = current.project.layoutState.productLayers.find(
        (layer) => layer.skuId === null && layer.locked,
      );
      if (mainLayer === undefined || mainLayer.compositionGroupId !== null) {
        return { state: current, result: { applied: false } };
      }
      const occupied = new Set(
        current.project.semanticState.compositionGroups.map((group) => group.id),
      );
      let ordinal = 1;
      while (occupied.has(`composition-group-${ordinal}`)) ordinal += 1;
      const groupId = `composition-group-${ordinal}`;
      const layout = structuredClone(DEFAULT_COMPOSITION_LAYOUT);
      const state = structuredClone(current);
      const layer = state.project.layoutState.productLayers.find(
        (candidate) => candidate.id === mainLayer.id,
      );
      if (layer === undefined) {
        throw new Error("main product layer disappeared while creating composition group");
      }
      layer.compositionGroupId = groupId;
      state.project.layoutState.objectTransforms[layer.transformId] = compositionTransform(layout);
      const skuProducts = new Map<
        SkuId,
        (typeof action.skuProducts)[number]
      >();
      for (const product of action.skuProducts) {
        if (product.skuId !== null && !skuProducts.has(product.skuId)) {
          skuProducts.set(product.skuId, product);
        }
      }
      const skuLayerIds: string[] = [];
      for (const [skuId, product] of skuProducts) {
        const existing = state.project.layoutState.productLayers.find(
          (candidate) => (
            candidate.skuId === skuId &&
            candidate.compositionGroupId === null &&
            candidate.locked &&
            candidate.sourceAssetId === product.sourceAssetId &&
            candidate.renderAssetId === product.renderAssetId
          ),
        );
        const skuLayer = existing ?? {
          id: `${groupId}:sku:${skuId}`,
          sourceAssetId: product.sourceAssetId,
          renderAssetId: product.renderAssetId,
          allowOpaqueFallback: product.allowOpaqueFallback,
          skuId,
          compositionGroupId: null,
          transformId: `${groupId}:sku:${skuId}:transform`,
          locked: true,
        };
        if (existing === undefined) {
          if (state.project.layoutState.productLayers.some((candidate) => candidate.id === skuLayer.id)) {
            throw new Error(`composition SKU layer id collision: ${skuLayer.id}`);
          }
          state.project.layoutState.productLayers.push(skuLayer);
        }
        skuLayer.compositionGroupId = groupId;
        state.project.layoutState.objectTransforms[skuLayer.transformId] = compositionTransform(layout);
        skuLayerIds.push(skuLayer.id);
      }
      state.project.semanticState.compositionGroups.push({
        id: groupId,
        skuIds: [...skuProducts.keys()],
        productLayerIds: [layer.id, ...skuLayerIds],
        layout,
        layoutHash: compositionLayoutHash(layout),
      });
      return { state, result: { applied: true } };
    }
    case "runtime/select": {
      const state = structuredClone(current);
      const applied =
        state.runtime.selectedNodeId !== action.nodeId ||
        state.runtime.selectedBoardId !== action.boardId;
      state.runtime.selectedNodeId = action.nodeId;
      state.runtime.selectedBoardId = action.boardId;
      return { state: applied ? state : current, result: { applied } };
    }
    case "upload/record": {
      if (current.runtime.uploadIds.includes(action.uploadId)) {
        return { state: current, result: { applied: false } };
      }
      const state = structuredClone(current);
      state.runtime.uploadIds.push(action.uploadId);
      return { state, result: { applied: true } };
    }
    case "generation/paidRequested": {
      if (current.runtime.paidGenerationRequestIds.includes(action.requestId)) {
        return { state: current, result: { applied: false } };
      }
      const state = structuredClone(current);
      state.runtime.paidGenerationRequestIds.push(action.requestId);
      return { state, result: { applied: true } };
    }
    case "completeSet/rebuild": {
      const diff = rebuildDiff(current);
      const confirmation = confirmationGate(current, action, diff);
      if (confirmation !== null) {
        return confirmation;
      }
      return { state: applyRebuild(current, diff), result: { applied: true } };
    }
  }
  return assertNever(action);
}

export function reduceProjectState(
  current: ProjectStoreState,
  action: ProjectAction,
): ProjectReduction {
  const reduction = reduceProjectStateUnchecked(current, action);
  if (!reduction.result.applied) {
    return reduction;
  }
  return {
    ...reduction,
    state: {
      ...reduction.state,
      project: parseProjectState(reduction.state.project),
      runtime: {
        ...reduction.state.runtime,
        pendingConfirmation: null,
      },
    },
  };
}

function isUndoableAction(action: ProjectAction): boolean {
  switch (action.type) {
    case "output/enable":
    case "output/disable":
    case "output/setQuantity":
    case "sku/setOutputQuantity":
    case "output/configure":
    case "board/selectResult":
    case "asset/useRectangularSource":
    case "mode/set":
    case "node/add":
    case "node/update":
    case "node/move":
    case "edge/connect":
    case "text/update":
    case "composition/update":
    case "composition/create":
    case "completeSet/rebuild":
      return true;
    case "runtime/select":
    case "runtime/setAllowedResultAssets":
    case "upload/record":
    case "generation/paidRequested":
    case "task/statusReceived":
    case "viewport/set":
      return false;
  }
  return assertNever(action);
}

export function createProjectStore(
  project: CanvasProjectState = createEmptyProjectState(),
  identity: ProjectIdentity = { projectId: "local-project", revision: 0 },
): ProjectStore {
  let state: ProjectStoreState = {
    project: parseProjectState(project),
    runtime: createEmptyRuntimeState(identity),
  };
  let history: HistoryState<CanvasProjectState> = createHistoryState();
  const listeners = new Set<() => void>();
  const notify = (): void => {
    for (const listener of [...listeners]) {
      listener();
    }
  };
  return {
    getState: () => structuredClone(state),
    dispatch: (action) => {
      const previousState = state;
      const previousProject = state.project;
      const reduction = reduceProjectState(state, action);
      if (reduction.result.applied && isUndoableAction(action)) {
        history = recordHistory(history, structuredClone(previousProject));
      }
      state = reduction.state;
      if (state !== previousState) {
        notify();
      }
      return structuredClone(reduction.result);
    },
    canUndo: () => history.past.length > 0,
    canRedo: () => history.future.length > 0,
    undo: () => {
      const previousProject = state.project;
      const step = undoHistory(history, structuredClone(previousProject));
      if (step === null) {
        return false;
      }
      history = step.history;
      const runtime = structuredClone(state.runtime);
      runtime.pendingConfirmation = null;
      synchronizeUnlinkedBoardsForProjectTransition(
        runtime,
        previousProject,
        step.snapshot,
      );
      state = {
        ...state,
        project: structuredClone(step.snapshot),
        runtime,
      };
      notify();
      return true;
    },
    redo: () => {
      const previousProject = state.project;
      const step = redoHistory(history, structuredClone(previousProject));
      if (step === null) {
        return false;
      }
      history = step.history;
      const runtime = structuredClone(state.runtime);
      runtime.pendingConfirmation = null;
      synchronizeUnlinkedBoardsForProjectTransition(
        runtime,
        previousProject,
        step.snapshot,
      );
      state = {
        ...state,
        project: structuredClone(step.snapshot),
        runtime,
      };
      notify();
      return true;
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    acknowledgeRevision: (revision) => {
      if (!Number.isInteger(revision) || revision < 0) {
        throw new Error("project revision must be a non-negative integer");
      }
      if (revision <= state.runtime.revision) {
        return;
      }
      state = {
        ...state,
        runtime: {
          ...state.runtime,
          revision,
        },
      };
      notify();
    },
    replaceProject: (replacement, nextIdentity) => {
      const projectState = parseProjectState(replacement);
      const replacementIdentity = nextIdentity ?? {
        projectId: state.runtime.projectId,
        revision: state.runtime.revision,
      };
      state = {
        project: projectState,
        runtime: createEmptyRuntimeState(replacementIdentity),
      };
      history = createHistoryState();
      notify();
    },
  };
}
