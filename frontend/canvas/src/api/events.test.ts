import { describe, expect, test, vi } from "vitest";

import { createEmptyProjectState } from "../domain/types";
import type { ProjectSnapshot } from "./client";
import { openProjectEvents } from "./events";

class FakeEventSource extends EventTarget {
  closeCalls = 0;

  close(): void {
    this.closeCalls += 1;
  }

  emit(type: string, data: unknown): void {
    this.dispatchEvent(
      new MessageEvent(type, { data: JSON.stringify(data) }),
    );
  }
}

function snapshot(): ProjectSnapshot {
  const state = createEmptyProjectState();
  return {
    project: {
      id: "project-a",
      name: "Project A",
      status: "active",
      schemaVersion: 1,
      revision: 3,
      createdAt: null,
      updatedAt: null,
      archivedAt: null,
      semanticState: state.semanticState,
      layoutState: state.layoutState,
    },
    skus: [],
    revision: 3,
  };
}

describe("Canvas project events", () => {
  test("listens to named project, SKU and snapshot events", () => {
    const source = new FakeEventSource();
    const factory = vi.fn(() => source);
    const received = vi.fn();
    const errors = vi.fn();
    const stream = openProjectEvents({
      apiBase: "/api/canvas/",
      projectId: "project a",
      eventSourceFactory: factory,
      onEvent: received,
      onError: errors,
    });

    expect(factory).toHaveBeenCalledWith(
      "/api/canvas/projects/project%20a/events",
    );
    source.emit("project.updated", {
      projectId: "project a",
      revision: 2,
      status: "active",
    });
    source.emit("sku.created", {
      projectId: "project a",
      revision: 3,
      status: "active",
      skuId: "sku-a",
    });
    const matchingSnapshot = snapshot();
    matchingSnapshot.project.id = "project a";
    source.emit("snapshot", matchingSnapshot);
    source.emit("message", { revision: 999 });

    expect(errors).not.toHaveBeenCalled();

    expect(received.mock.calls.map(([event]) => event)).toEqual([
      {
        type: "project.updated",
        projectId: "project a",
        revision: 2,
        status: "active",
      },
      {
        type: "sku.created",
        projectId: "project a",
        revision: 3,
        status: "active",
        skuId: "sku-a",
      },
      { type: "snapshot", snapshot: matchingSnapshot, operations: [] },
    ]);
    stream.close();
  });

  test("normalizes asset and cutout operation events without inventing a project revision", () => {
    const source = new FakeEventSource();
    const received = vi.fn();
    const stream = openProjectEvents({
      apiBase: "/api/canvas",
      projectId: "project-a",
      eventSourceFactory: () => source,
      onEvent: received,
    });

    source.emit("asset.uploaded", {
      projectId: "project-a",
      sourceAssetId: "source-a",
      workingAssetId: "working-a",
      previewAssetId: "preview-a",
      transparencyStatus: "opaque",
    });
    source.emit("operation.queued", {
      inputAssetId: "working-a",
      operationId: "operation-a",
      operationType: "cutout",
      status: "queued",
    });
    source.emit("operation.running", {
      attemptCount: 1,
      operationId: "operation-a",
      operationType: "cutout",
      status: "running",
    });
    source.emit("operation.succeeded", {
      attemptCount: 1,
      operationId: "operation-a",
      operationType: "cutout",
      outputAssetId: "cutout-a",
      status: "succeeded",
    });

    expect(received.mock.calls.map(([event]) => event)).toEqual([
      {
        type: "asset.uploaded",
        projectId: "project-a",
        sourceAssetId: "source-a",
        workingAssetId: "working-a",
        previewAssetId: "preview-a",
        transparencyStatus: "opaque",
      },
      {
        type: "operation.queued",
        projectId: "project-a",
        operation: {
          id: "operation-a",
          projectId: "project-a",
          operationType: "cutout",
          status: "queued",
          inputAssetId: "working-a",
        },
      },
      {
        type: "operation.running",
        projectId: "project-a",
        operation: {
          id: "operation-a",
          projectId: "project-a",
          operationType: "cutout",
          status: "running",
          attemptCount: 1,
        },
      },
      {
        type: "operation.succeeded",
        projectId: "project-a",
        operation: {
          id: "operation-a",
          projectId: "project-a",
          operationType: "cutout",
          status: "succeeded",
          attemptCount: 1,
          outputAssetId: "cutout-a",
        },
      },
    ]);
    stream.close();
  });

  test("accepts retention-gap snapshots with normalized operation summaries", () => {
    const source = new FakeEventSource();
    const received = vi.fn();
    const stream = openProjectEvents({
      apiBase: "/api/canvas",
      projectId: "project-a",
      eventSourceFactory: () => source,
      onEvent: received,
    });
    source.emit("snapshot", {
      ...snapshot(),
      operations: [{
        id: "operation-a",
        projectId: "project-a",
        type: "cutout",
        status: "failed",
        attemptCount: 2,
        inputAssetId: "working-a",
        outputAssetId: null,
        error: { code: "cutout_failed", message: "抠图失败", retryable: true },
        createdAt: null,
        updatedAt: null,
        startedAt: null,
        completedAt: null,
      }],
    });

    expect(received).toHaveBeenCalledWith({
      type: "snapshot",
      snapshot: snapshot(),
      operations: [{
        id: "operation-a",
        projectId: "project-a",
        operationType: "cutout",
        status: "failed",
        attemptCount: 2,
        inputAssetId: "working-a",
        outputAssetId: null,
        safeError: { code: "cutout_failed", message: "抠图失败", retryable: true },
      }],
    });
    stream.close();
  });

  test("hydrates persisted generation progress from a fresh stream snapshot", () => {
    const source = new FakeEventSource();
    const received = vi.fn();
    const stream = openProjectEvents({
      apiBase: "/api/canvas",
      projectId: "project-a",
      eventSourceFactory: () => source,
      onEvent: received,
    });

    source.emit("snapshot", {
      ...snapshot(),
      generations: [{
        id: "generation-a",
        status: "cancel_requested",
        mode: "complete_set",
        totalItems: 1,
        succeededItems: 0,
        failedItems: 0,
        cancelledItems: 0,
        unknownItems: 0,
        safeStorageBlockReason: null,
        createdAt: null,
        updatedAt: null,
        completedAt: null,
        items: [{
          id: "item-a",
          ordinal: 0,
          outputType: "main",
          boardId: "board-a",
          nodeId: "node-a",
          status: "cancel_requested",
          attemptCount: 1,
          latestBackgroundAssetId: null,
          latestComposedAssetId: null,
          safeErrorCode: null,
          safeErrorSummary: null,
          latestAttempt: null,
        }],
      }],
    });

    expect(received).toHaveBeenCalledWith({
      type: "snapshot",
      snapshot: snapshot(),
      operations: [],
      generations: [{
        id: "generation-a",
        status: "cancel_requested",
        totalItems: 1,
        succeededItems: 0,
        failedItems: 0,
        cancelledItems: 0,
        unknownItems: 0,
        safeStorageBlockReason: null,
      }],
    });
    stream.close();
  });

  test("close is idempotent and invalidates callbacks already captured by the old stream", () => {
    const source = new FakeEventSource();
    const received = vi.fn();
    const stream = openProjectEvents({
      apiBase: "/api/canvas",
      projectId: "project-a",
      eventSourceFactory: () => source,
      onEvent: received,
    });

    const captured = source.emit.bind(source, "project.state_saved", {
      projectId: "project-a",
      revision: 2,
      status: "active",
    });
    stream.close();
    stream.close();
    captured();

    expect(source.closeCalls).toBe(1);
    expect(received).not.toHaveBeenCalled();
  });

  test("rejects malformed and cross-project event payloads before callbacks", () => {
    const source = new FakeEventSource();
    const received = vi.fn();
    const errors = vi.fn();
    const stream = openProjectEvents({
      apiBase: "/api/canvas",
      projectId: "project-a",
      eventSourceFactory: () => source,
      onEvent: received,
      onError: errors,
    });

    source.emit("project.updated", {
      projectId: "project-b",
      revision: 2,
      status: "active",
    });
    source.emit("sku.created", {
      projectId: "project-a",
      revision: 2,
      status: "active",
    });
    source.emit("project.state_saved", {
      projectId: "project-a",
      revision: 2,
      status: "active",
      summary: { nodeCount: -1, edgeCount: 0, outputBoardCount: 0 },
    });
    const mismatched = snapshot();
    mismatched.project.revision = 2;
    source.emit("snapshot", mismatched);

    expect(received).not.toHaveBeenCalled();
    expect(errors).toHaveBeenCalledTimes(4);
    stream.close();
  });
});
