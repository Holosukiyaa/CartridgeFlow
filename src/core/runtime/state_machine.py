"""Legal implementation-level lifecycle transitions."""

from __future__ import annotations


RUN_TRANSITIONS = {
    "created": {"running", "cancelled", "failed"},
    "running": {"paused", "paused_waiting_user", "completed", "failed", "cancelled", "interrupted"},
    "paused": {"running", "recovering", "cancelled"},
    "paused_waiting_user": {"running", "cancelled"},
    "failed": {"retrying", "recovering", "rolling_back", "cancelled"},
    "interrupted": {"recovering", "rolling_back", "cancelled", "failed"},
    "retrying": {"running", "paused_waiting_user", "completed", "failed", "cancelled", "interrupted"},
    "recovering": {"running", "paused_waiting_user", "completed", "failed", "cancelled", "interrupted"},
    "rolling_back": {"running", "paused_waiting_user", "completed", "failed", "cancelled", "interrupted"},
    "completed": {"rolling_back"},
    "cancelled": set(),
}

NODE_TRANSITIONS = {
    "entered": {"completed", "failed", "paused_waiting_user", "cancelled"},
    "paused_waiting_user": {"entered", "completed", "failed"},
    "failed": {"entered"},
    "completed": set(),
    "cancelled": set(),
}

INTERACTION_TRANSITIONS = {
    "waiting_user": {"answered", "cancelled", "expired"},
    "answered": set(),
    "cancelled": set(),
    "expired": set(),
}

TOOL_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"succeeded", "failed", "timed_out", "cancelled"},
    "failed": {"retrying"},
    "timed_out": {"retrying"},
    "retrying": {"running", "cancelled"},
    "succeeded": set(),
    "cancelled": set(),
}

TRANSITIONS = {
    "run": RUN_TRANSITIONS,
    "node": NODE_TRANSITIONS,
    "interaction": INTERACTION_TRANSITIONS,
    "tool": TOOL_TRANSITIONS,
}


class InvalidStateTransition(ValueError):
    def __init__(self, entity: str, current: str, target: str):
        self.entity = entity
        self.current = current
        self.target = target
        super().__init__(f"Invalid {entity} state transition: {current} -> {target}")


def assert_transition(entity: str, current: str, target: str) -> None:
    current = str(current or "")
    target = str(target or "")
    if current == target:
        return
    table = TRANSITIONS.get(entity)
    if table is None or target not in table.get(current, set()):
        raise InvalidStateTransition(entity, current, target)


def transition(document: dict, target: str, *, entity: str = "run", field: str = "status") -> str:
    current = str(document.get(field) or "")
    assert_transition(entity, current, target)
    document[field] = target
    return target
