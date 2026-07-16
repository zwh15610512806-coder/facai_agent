export interface HistoryState<Snapshot> {
  past: Snapshot[];
  future: Snapshot[];
}

export interface HistoryStep<Snapshot> {
  history: HistoryState<Snapshot>;
  snapshot: Snapshot;
}

export function createHistoryState<Snapshot>(): HistoryState<Snapshot> {
  return { past: [], future: [] };
}

export function recordHistory<Snapshot>(
  history: HistoryState<Snapshot>,
  snapshot: Snapshot,
): HistoryState<Snapshot> {
  return { past: [...history.past, snapshot], future: [] };
}

export function undoHistory<Snapshot>(
  history: HistoryState<Snapshot>,
  current: Snapshot,
): HistoryStep<Snapshot> | null {
  const snapshot = history.past.at(-1);
  if (snapshot === undefined) {
    return null;
  }
  return {
    snapshot,
    history: {
      past: history.past.slice(0, -1),
      future: [current, ...history.future],
    },
  };
}

export function redoHistory<Snapshot>(
  history: HistoryState<Snapshot>,
  current: Snapshot,
): HistoryStep<Snapshot> | null {
  const [snapshot, ...remaining] = history.future;
  if (snapshot === undefined) {
    return null;
  }
  return {
    snapshot,
    history: {
      past: [...history.past, current],
      future: remaining,
    },
  };
}
