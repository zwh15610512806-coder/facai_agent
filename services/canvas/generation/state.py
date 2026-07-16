"""Central legal state transitions for durable Canvas generation work."""
from __future__ import annotations

from collections.abc import Sequence


class InvalidGenerationTransition(ValueError):
    pass


_ATTEMPT_TRANSITIONS = {
    "queued": {"submitting", "cancelled"},
    "submitting": {"polling", "succeeded", "failed", "unknown", "cancel_requested"},
    "polling": {"polling", "succeeded", "failed", "unknown", "cancel_requested"},
    "cancel_requested": {"cancelled", "polling", "succeeded", "failed", "unknown"},
    "failed": set(),
    "succeeded": set(),
    "unknown": set(),
    "cancelled": set(),
}
_ITEM_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"composing", "failed", "unknown", "cancel_requested", "cancelled"},
    "composing": {"succeeded", "failed", "cancel_requested", "cancelled"},
    "cancel_requested": {"cancelled", "composing", "succeeded", "failed", "unknown"},
    "failed": {"queued", "composing"},
    "unknown": {"queued", "composing", "cancelled"},
    "succeeded": set(),
    "cancelled": set(),
}
_GENERATION_TRANSITIONS = {
    "queued": {"running", "cancel_requested", "cancelled", "failed"},
    "running": {
        "succeeded", "partially_failed", "failed", "unknown",
        "cancel_requested", "cancelled", "interrupted",
    },
    "partially_failed": {"running", "cancel_requested"},
    "unknown": {"running", "cancel_requested", "cancelled"},
    "cancel_requested": {"cancelled", "succeeded", "partially_failed", "failed", "unknown"},
    "interrupted": {"running", "unknown", "cancel_requested"},
    "succeeded": set(),
    "failed": {"running"},
    "cancelled": set(),
}


def _transition(current: str, target: str, table: dict[str, set[str]], *, label: str) -> None:
    if current == target:
        return
    if target not in table.get(current, set()):
        raise InvalidGenerationTransition(f"illegal {label} transition: {current} -> {target}")


def transition_attempt(current: str, target: str) -> None:
    _transition(current, target, _ATTEMPT_TRANSITIONS, label="Attempt")


def transition_item(current: str, target: str) -> None:
    _transition(current, target, _ITEM_TRANSITIONS, label="Item")


def transition_generation(current: str, target: str) -> None:
    _transition(current, target, _GENERATION_TRANSITIONS, label="Generation")


def aggregate_generation_status(item_statuses: Sequence[str], generation_status: str) -> str:
    if not item_statuses:
        return "failed"
    statuses = list(item_statuses)
    if any(status == "unknown" for status in statuses):
        return "unknown"
    non_terminal = {"queued", "running", "composing", "cancel_requested"}
    if any(status in non_terminal for status in statuses):
        return "cancel_requested" if generation_status == "cancel_requested" else "running"
    succeeded = statuses.count("succeeded")
    failed = statuses.count("failed")
    cancelled = statuses.count("cancelled")
    if succeeded == len(statuses):
        return "succeeded"
    if cancelled == len(statuses):
        return "cancelled"
    if succeeded:
        return "partially_failed"
    if failed:
        return "failed"
    return "cancelled"


__all__ = [
    "InvalidGenerationTransition",
    "aggregate_generation_status",
    "transition_attempt",
    "transition_generation",
    "transition_item",
]
