from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from action_py.core.models import Action, Plan
from action_py.core.world import WorldState


class ExecutionStatus(Enum):
    """Runtime status returned by the plan executor."""

    SUCCESS = "success"
    RUNNING = "running"
    FAILED = "failed"
    FAILURE = "failed"

    @classmethod
    def coerce(cls, value: ExecutionStatus | str | None) -> ExecutionStatus:
        if value is None:
            return cls.RUNNING
        if isinstance(value, ExecutionStatus):
            return value
        value = value.strip().lower()
        if value == "failure":
            return cls.FAILED
        try:
            return cls(value)
        except ValueError as exc:
            valid = ", ".join(status.value for status in cls)
            raise ValueError(f"Unknown execution status {value!r}; expected {valid}") from exc


@dataclass(frozen=True)
class ActionResult:
    """Result returned by an action callback.

    Args:
        status: ``success``, ``running`` or ``failed``.
        facts: Observed fact updates to merge into the executor belief.
        belief: Full belief snapshot to replace the executor belief.
        apply_effects: When successful, apply the action model's effects before
            merging observed ``facts``. Set to ``False`` when the callback
            returns a complete observed ``belief``.
    """

    status: ExecutionStatus | str | None
    facts: dict[str, object] | None = None
    belief: WorldState | None = None
    apply_effects: bool = True


@dataclass(frozen=True)
class ExecutionContext:
    """Context passed to action callbacks."""

    action: Action
    index: int
    belief: WorldState

    def success(
        self,
        *,
        facts: dict[str, object] | None = None,
        belief: WorldState | None = None,
        apply_effects: bool = True,
    ) -> ActionResult:
        return ActionResult(
            ExecutionStatus.SUCCESS,
            facts=facts,
            belief=belief,
            apply_effects=apply_effects,
        )

    def running(
        self,
        *,
        facts: dict[str, object] | None = None,
        belief: WorldState | None = None,
    ) -> ActionResult:
        return ActionResult(ExecutionStatus.RUNNING, facts=facts, belief=belief)

    def failed(
        self,
        *,
        facts: dict[str, object] | None = None,
        belief: WorldState | None = None,
    ) -> ActionResult:
        return ActionResult(ExecutionStatus.FAILED, facts=facts, belief=belief)


ActionCallback = Callable[
    [ExecutionContext],
    ActionResult | ExecutionStatus | str | None,
]


@dataclass
class _ActionCallbacks:
    on_start: ActionCallback | None = None
    on_running: ActionCallback | None = None


class PlanExecutor:
    """BehaviorTree.CPP-style executor for a planned action sequence.

    The executor ticks one action at a time. When an action becomes active, its
    ``on_start`` callback is called. If the callback returns ``running``, later
    ticks either call the optional ``on_running`` callback or keep returning
    ``running`` until :meth:`complete_current` is called.

    The executor owns a mutable belief pointer. ``WorldState`` remains
    immutable; every update replaces :attr:`belief` with a derived snapshot.
    Successful actions apply their declared effects by default, and callbacks
    can merge observed fact updates to keep runtime belief ready for future
    replanning.
    """

    def __init__(
        self,
        plan: Plan,
        belief: WorldState,
        callbacks: dict[str, ActionCallback] | None = None,
    ) -> None:
        self.plan = plan
        self.belief = belief.copy()
        self._index = 0
        self._active = False
        self._terminal_status: ExecutionStatus | None = None
        self._callbacks: dict[str, _ActionCallbacks] = {}

        if callbacks:
            for name, callback in callbacks.items():
                self.on_start(name, callback)

    @property
    def index(self) -> int:
        """Index of the next or currently running action."""
        return self._index

    @property
    def current_action(self) -> Action | None:
        """The active action, or the next action if none is running."""
        if self._index >= len(self.plan.actions):
            return None
        return self.plan.actions[self._index]

    @property
    def is_running(self) -> bool:
        return self._active

    @property
    def is_done(self) -> bool:
        return self._index >= len(self.plan.actions)

    def on_start(self, action_name: str, callback: ActionCallback) -> None:
        """Register a callback called when an action starts."""
        self._callbacks.setdefault(action_name, _ActionCallbacks()).on_start = callback

    def on_running(self, action_name: str, callback: ActionCallback) -> None:
        """Register a callback called while a running action is active."""
        self._callbacks.setdefault(action_name, _ActionCallbacks()).on_running = callback

    def add_callback(self, action_name: str, callback: ActionCallback) -> None:
        """Alias for :meth:`on_start`."""
        self.on_start(action_name, callback)

    def update_belief(
        self,
        facts: dict[str, object] | None = None,
        *,
        belief: WorldState | None = None,
    ) -> WorldState:
        """Replace or merge the executor belief and return the new snapshot."""
        if facts is not None and belief is not None:
            raise ValueError("Pass either facts or belief, not both")
        if belief is not None:
            self.belief = belief.copy()
        elif facts:
            self.belief = self.belief.apply_dict(facts)
        return self.belief

    def tick(self) -> ExecutionStatus:
        """Advance the executor by one behavior-tree tick."""
        if self._terminal_status is not None:
            return self._terminal_status
        if self.is_done:
            return ExecutionStatus.SUCCESS

        action = self.current_action
        if action is None:
            return ExecutionStatus.SUCCESS

        if not self._active:
            if not action.is_applicable(self.belief):
                self._terminal_status = ExecutionStatus.FAILED
                return self._terminal_status
            self._active = True
            callback = self._callbacks.get(action.name, _ActionCallbacks()).on_start
            result = self._call(callback, action)
            return self._apply_result(action, result)

        callback = self._callbacks.get(action.name, _ActionCallbacks()).on_running
        if callback is None:
            return ExecutionStatus.RUNNING
        result = self._call(callback, action)
        return self._apply_result(action, result)

    def complete_current(
        self,
        status: ExecutionStatus | str = ExecutionStatus.SUCCESS,
        *,
        facts: dict[str, object] | None = None,
        belief: WorldState | None = None,
        apply_effects: bool = True,
    ) -> ExecutionStatus:
        """Complete the active running action from external code."""
        action = self.current_action
        if action is None or not self._active:
            raise RuntimeError("No action is currently running")
        result = ActionResult(
            status,
            facts=facts,
            belief=belief,
            apply_effects=apply_effects,
        )
        return self._apply_result(action, result)

    def reset(self, belief: WorldState | None = None) -> None:
        """Reset progress while optionally replacing belief."""
        if belief is not None:
            self.belief = belief.copy()
        self._index = 0
        self._active = False
        self._terminal_status = None

    def _call(
        self,
        callback: ActionCallback | None,
        action: Action,
    ) -> ActionResult | ExecutionStatus | str | None:
        if callback is None:
            return ExecutionStatus.SUCCESS
        context = ExecutionContext(action=action, index=self._index, belief=self.belief)
        return callback(context)

    def _apply_result(
        self,
        action: Action,
        raw_result: ActionResult | ExecutionStatus | str | None,
    ) -> ExecutionStatus:
        result = self._normalize_result(raw_result)
        self._merge_observations(result)

        if result.status == ExecutionStatus.RUNNING:
            if result.facts:
                self.belief = self.belief.apply_dict(result.facts)
            return ExecutionStatus.RUNNING

        if result.status == ExecutionStatus.FAILED:
            if result.facts:
                self.belief = self.belief.apply_dict(result.facts)
            self._active = False
            self._terminal_status = ExecutionStatus.FAILED
            return self._terminal_status

        if result.apply_effects:
            self.belief = action.apply(self.belief)
        if result.facts:
            self.belief = self.belief.apply_dict(result.facts)

        self._index += 1
        self._active = False
        if self.is_done:
            self._terminal_status = ExecutionStatus.SUCCESS
            return self._terminal_status
        return ExecutionStatus.RUNNING

    def _merge_observations(self, result: ActionResult) -> None:
        if result.belief is not None:
            self.belief = result.belief.copy()

    def _normalize_result(
        self,
        raw_result: ActionResult | ExecutionStatus | str | None,
    ) -> ActionResult:
        if isinstance(raw_result, ActionResult):
            return ActionResult(
                ExecutionStatus.coerce(raw_result.status),
                facts=raw_result.facts,
                belief=raw_result.belief,
                apply_effects=raw_result.apply_effects,
            )
        return ActionResult(ExecutionStatus.coerce(raw_result))


BTExecutor = PlanExecutor
BehaviorTreeExecutor = PlanExecutor


__all__ = [
    "ActionCallback",
    "ActionResult",
    "BTExecutor",
    "BehaviorTreeExecutor",
    "ExecutionContext",
    "ExecutionStatus",
    "PlanExecutor",
]
