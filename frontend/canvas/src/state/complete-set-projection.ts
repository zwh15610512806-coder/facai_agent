import type {
  CanvasNode,
  CanvasProjectState,
  CompleteSetOutput,
  OutputBoard,
  OutputType,
  TypedEdge,
} from "../domain/types";
import type { ProjectStore, ProjectStoreState } from "./project-store";

export interface CompleteSetFormProjection {
  readOnly: boolean;
  advancedCustomized: boolean;
  selectedOutputTypes: OutputType[];
  outputs: CompleteSetOutput[];
  outputBoards: OutputBoard[];
}

const OUTPUT_KIND: Record<OutputType, CanvasNode["kind"]> = {
  main: "main_output",
  sku: "sku_output",
  detail: "detail_output",
};

function emptyManagedNode(id: string, kind: CanvasNode["kind"]): CanvasNode {
  return {
    id,
    kind,
    managedBy: "complete-set",
    skuId: null,
    assetId: null,
    modelProfileId: null,
    prompt: null,
    compositionGroupId: null,
    textSnapshotId: null,
    outputBoardId: null,
    parameters: {},
  } as CanvasNode;
}

export function managedOutputNodeId(outputType: OutputType, boardId?: string): string {
  return boardId === undefined
    ? `complete-set:${outputType}:output`
    : `complete-set:${outputType}:output:${boardId}`;
}

export function managedBoardId(
  outputType: OutputType,
  ordinal: number,
  skuId: string | null,
): string {
  return skuId === null
    ? `complete-set:board:${outputType}:${ordinal}`
    : `complete-set:board:${outputType}:${skuId}:${ordinal}`;
}

export function canonicalManagedGroup(outputType: OutputType): {
  nodes: CanvasNode[];
  edges: TypedEdge[];
} {
  const prefix = `complete-set:${outputType}`;
  const promptId = `${prefix}:prompt`;
  const generationId = `${prefix}:generation`;
  const outputId = managedOutputNodeId(outputType);
  return {
    nodes: [
      emptyManagedNode(promptId, "prompt"),
      emptyManagedNode(generationId, "model_generation"),
      emptyManagedNode(outputId, OUTPUT_KIND[outputType]),
    ],
    edges: [
      {
        id: `${prefix}:edge:prompt`,
        kind: "prompt",
        sourceNodeId: promptId,
        sourcePort: "prompt",
        targetNodeId: generationId,
        targetPort: "prompt",
        skuId: null,
      },
      {
        id: `${prefix}:edge:output`,
        kind: "output_image",
        sourceNodeId: generationId,
        sourcePort: "output",
        targetNodeId: outputId,
        targetPort: "input",
        skuId: null,
      },
    ],
  };
}

function recordsEqual(
  left: { [key: string]: unknown },
  right: { [key: string]: unknown },
): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function managedNodeFieldsAreRepresentable(
  node: CanvasNode,
  outputType: OutputType | undefined,
  expected: CanvasNode,
): boolean {
  const commonFieldsAreEmpty =
    node.skuId === expected.skuId &&
    node.assetId === null &&
    node.compositionGroupId === expected.compositionGroupId &&
    node.textSnapshotId === null;
  if (!commonFieldsAreEmpty) {
    return false;
  }
  if (node.outputBoardId !== null) {
    return (
      outputType !== undefined &&
      node.kind === OUTPUT_KIND[outputType] &&
      node.id === managedOutputNodeId(outputType, node.outputBoardId) &&
      node.prompt === null &&
      node.modelProfileId === null &&
      recordsEqual(node.parameters, {})
    );
  }
  if (
    outputType !== undefined &&
    outputType !== "sku" &&
    node.id === managedOutputNodeId(outputType)
  ) {
    return true;
  }
  return (
    node.prompt === null &&
    node.modelProfileId === null &&
    recordsEqual(node.parameters, {})
  );
}

function expectedBoardMap(project: CanvasProjectState): Map<string, OutputBoard> {
  const boards = new Map<string, OutputBoard>();
  for (const outputType of project.semanticState.completeSet.selectedOutputTypes) {
    const outputs = project.semanticState.completeSet.outputs.filter(
      (output) => output.outputType === outputType,
    );
    for (const output of outputs) {
      for (let ordinal = 1; ordinal <= (output.quantity ?? 0); ordinal += 1) {
        const id = managedBoardId(output.outputType, ordinal, output.skuId);
        boards.set(id, {
          id,
          outputNodeId: managedOutputNodeId(output.outputType, id),
          outputType: output.outputType,
          skuId: output.skuId,
          sortOrder: boards.size,
          selectedResultAssetId: null,
        });
      }
    }
  }
  return boards;
}

function expectedManagedState(project: CanvasProjectState): {
  nodes: CanvasNode[];
  edges: TypedEdge[];
  boards: Map<string, OutputBoard>;
} {
  const groups = project.semanticState.completeSet.selectedOutputTypes.map(canonicalManagedGroup);
  const nodes = groups.flatMap((group) => group.nodes);
  const edges = groups.flatMap((group) => group.edges);
  const boards = expectedBoardMap(project);
  for (const board of boards.values()) {
    const output = emptyManagedNode(board.outputNodeId, OUTPUT_KIND[board.outputType]);
    output.outputBoardId = board.id;
    output.skuId = board.skuId;
    const configuration = project.semanticState.completeSet.outputs.find(
      (candidate) => (
        candidate.outputType === board.outputType && candidate.skuId === board.skuId
      ),
    );
    output.compositionGroupId = configuration?.compositionGroupId ?? null;
    nodes.push(output);
    edges.push({
      id: `complete-set:${board.outputType}:edge:output:${board.id}`,
      kind: "output_image",
      sourceNodeId: `complete-set:${board.outputType}:generation`,
      sourcePort: "output",
      targetNodeId: output.id,
      targetPort: "input",
      skuId: null,
    });
  }
  return { nodes, edges, boards };
}

export function isCompleteSetTopologyRepresentable(
  project: CanvasProjectState,
): boolean {
  const expectedState = expectedManagedState(project);
  const expectedNodes = expectedState.nodes;
  const expectedNodeMap = new Map(expectedNodes.map((node) => [node.id, node]));
  const managedNodes = project.semanticState.nodes.filter(
    (node) => node.managedBy === "complete-set",
  );
  if (managedNodes.length !== expectedNodes.length) {
    return false;
  }
  for (const node of managedNodes) {
    const expected = expectedNodeMap.get(node.id);
    if (expected === undefined || expected.kind !== node.kind) {
      return false;
    }
    const outputType = project.semanticState.completeSet.selectedOutputTypes.find(
      (candidate) => node.id.startsWith(`complete-set:${candidate}:`),
    );
    if (!managedNodeFieldsAreRepresentable(node, outputType, expected)) {
      return false;
    }
  }

  const managedNodeIds = new Set(managedNodes.map((node) => node.id));
  const expectedEdges = expectedState.edges;
  const expectedEdgeMap = new Map(expectedEdges.map((edge) => [edge.id, edge]));
  const managedEdges = project.semanticState.edges.filter(
    (edge) =>
      edge.id.startsWith("complete-set:") ||
      managedNodeIds.has(edge.sourceNodeId) ||
      managedNodeIds.has(edge.targetNodeId),
  );
  if (managedEdges.length !== expectedEdges.length) {
    return false;
  }
  for (const edge of managedEdges) {
    const expected = expectedEdgeMap.get(edge.id);
    if (
      expected === undefined ||
      edge.kind !== expected.kind ||
      edge.sourceNodeId !== expected.sourceNodeId ||
      edge.sourcePort !== expected.sourcePort ||
      edge.targetNodeId !== expected.targetNodeId ||
      edge.targetPort !== expected.targetPort ||
      edge.skuId !== expected.skuId
    ) {
      return false;
    }
  }

  const expectedBoards = expectedState.boards;
  const managedOutputNodeIds = new Set(
    [...expectedBoards.values()].map((board) => board.outputNodeId),
  );
  const managedBoards = project.semanticState.outputBoards.filter(
    (board) => managedOutputNodeIds.has(board.outputNodeId),
  );
  if (managedBoards.length !== expectedBoards.size) {
    return false;
  }
  return managedBoards.every((board) => {
    const expected = expectedBoards.get(board.id);
    return (
      expected !== undefined &&
      board.outputNodeId === expected.outputNodeId &&
      board.outputType === expected.outputType &&
      board.skuId === expected.skuId &&
      board.sortOrder === expected.sortOrder &&
      project.semanticState.nodes.some(
        (node) => node.id === board.outputNodeId && node.outputBoardId === board.id,
      )
    );
  });
}

function projectManagedOutputFields(project: CanvasProjectState): void {
  for (const outputType of project.semanticState.completeSet.selectedOutputTypes) {
    if (outputType === "sku") {
      continue;
    }
    const outputNode = project.semanticState.nodes.find(
      (node) => node.id === managedOutputNodeId(outputType),
    );
    if (outputNode === undefined) {
      continue;
    }
    for (const output of project.semanticState.completeSet.outputs) {
      if (output.outputType !== outputType) {
        continue;
      }
      output.prompt = outputNode.prompt ?? "";
      output.modelProfileId = outputNode.modelProfileId;
      output.modelParameters = structuredClone(outputNode.parameters);
    }
  }
  for (const board of project.semanticState.outputBoards) {
    const output = project.semanticState.completeSet.outputs.find(
      (candidate) => (
        candidate.outputType === board.outputType && candidate.skuId === board.skuId
      ),
    );
    const outputNode = project.semanticState.nodes.find(
      (node) => node.id === board.outputNodeId,
    );
    if (output !== undefined && outputNode !== undefined) {
      outputNode.compositionGroupId = output.compositionGroupId;
    }
  }
}

export function synchronizeCompleteSetProjection(project: CanvasProjectState): void {
  projectManagedOutputFields(project);
  project.semanticState.advancedCustomized =
    !isCompleteSetTopologyRepresentable(project);
}

export function selectCompleteSetForm(
  project: CanvasProjectState,
): CompleteSetFormProjection {
  return {
    readOnly: project.semanticState.advancedCustomized,
    advancedCustomized: project.semanticState.advancedCustomized,
    selectedOutputTypes: structuredClone(
      project.semanticState.completeSet.selectedOutputTypes,
    ),
    outputs: structuredClone(project.semanticState.completeSet.outputs),
    outputBoards: structuredClone(project.semanticState.outputBoards),
  };
}

export function createProjectViews(store: ProjectStore): {
  completeSet: {
    store: ProjectStore;
    getForm(): CompleteSetFormProjection;
    dispatch: ProjectStore["dispatch"];
  };
  advanced: {
    store: ProjectStore;
    getState(): ProjectStoreState;
    dispatch: ProjectStore["dispatch"];
  };
} {
  return {
    completeSet: {
      store,
      getForm: () => selectCompleteSetForm(store.getState().project),
      dispatch: (action) => store.dispatch(action),
    },
    advanced: {
      store,
      getState: () => store.getState(),
      dispatch: (action) => store.dispatch(action),
    },
  };
}
