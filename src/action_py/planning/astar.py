from __future__ import annotations

import heapq
import itertools
import math
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any

from action_py.core.models import Action, Goal, Plan
from action_py.core.world import WorldState
from action_py.planning.planner import Planner


Heuristic = Callable[[WorldState, Goal], float]
CostFunction = Callable[[Action, WorldState, WorldState], float]
StateKey = Hashable


@dataclass
class AStarPlanner(Planner):
    """Forward A* planner over executable world states.

    This planner expands only actions whose preconditions are satisfied in the
    current state, then ranks candidate paths by ``g + h`` where ``g`` is the
    accumulated action cost and ``h`` is the estimated remaining cost.

    The default heuristic is ``0``.  That makes the planner equivalent to
    uniform-cost search, which keeps results cost-optimal for the current fact
    based model.  Pass ``heuristic`` or override :meth:`_heuristic` when a
    domain-specific estimate is available.

    ``cost_fn`` and :meth:`_state_key` are explicit extension points for future
    resource-aware and numeric planning.  For example, a cost function can price
    actions from resource levels in ``from_state``/``to_state`` without changing
    the search loop.
    """

    heuristic: Heuristic | None = None
    cost_fn: CostFunction | None = None

    def plan(
        self,
        state: WorldState,
        goal: Goal,
        *,
        seed: int | None = None,
    ) -> Plan | None:
        """Find the lowest-cost executable plan that satisfies *goal*.

        Args:
            state: The initial world state.
            goal: The goal to achieve.
            seed: Accepted for API compatibility with :class:`Planner`.

        Returns:
            A :class:`~action_py.core.models.Plan` if one is found, otherwise
            ``None``.
        """
        del seed  # A* is deterministic; tie-breaking follows action order.

        if goal.is_satisfied(state):
            return Plan()

        counter = itertools.count()
        frontier: list[
            tuple[float, float, int, int, WorldState, tuple[Action, ...]]
        ] = []

        start_key = self._state_key(state)
        best_cost: dict[StateKey, float] = {start_key: 0.0}
        start_estimate = self._estimate_remaining_cost(state, goal)

        heapq.heappush(
            frontier,
            (start_estimate, 0.0, 0, next(counter), state, ()),
        )

        while frontier:
            _, path_cost, depth, _, current_state, actions = heapq.heappop(frontier)
            current_key = self._state_key(current_state)

            if path_cost > best_cost.get(current_key, math.inf):
                continue

            if goal.is_satisfied(current_state):
                return Plan(actions=list(actions))

            if depth >= self.max_depth:
                continue

            for action in self._applicable_actions(current_state):
                next_state = action.apply(current_state)
                step_cost = self._action_cost(action, current_state, next_state)
                next_cost = path_cost + step_cost
                next_key = self._state_key(next_state)

                if next_cost >= best_cost.get(next_key, math.inf):
                    continue

                best_cost[next_key] = next_cost
                next_actions = actions + (action,)
                estimate = next_cost + self._estimate_remaining_cost(next_state, goal)
                heapq.heappush(
                    frontier,
                    (
                        estimate,
                        next_cost,
                        depth + 1,
                        next(counter),
                        next_state,
                        next_actions,
                    ),
                )

        return None

    # -- extension hooks ------------------------------------------------------

    def _applicable_actions(self, state: WorldState) -> list[Action]:
        """Return actions that can execute in *state*.

        Override this when future domain models need extra applicability checks
        beyond boolean preconditions, such as resource availability.
        """
        return [action for action in self.actions if action.is_applicable(state)]

    def _action_cost(
        self,
        action: Action,
        from_state: WorldState,
        to_state: WorldState,
    ) -> float:
        """Return the non-negative cost of applying *action*.

        The default uses ``action.cost`` unless ``cost_fn`` was supplied.
        """
        raw_cost = (
            self.cost_fn(action, from_state, to_state)
            if self.cost_fn is not None
            else action.cost
        )
        return self._validate_search_cost(raw_cost, f"cost for action {action.name!r}")

    def _heuristic(self, state: WorldState, goal: Goal) -> float:
        """Estimate remaining cost from *state* to *goal*.

        The default ``0`` heuristic preserves optimality for arbitrary action
        effects.  Domain planners can override this with an admissible heuristic
        when they have stronger knowledge.
        """
        return 0.0

    def _estimate_remaining_cost(self, state: WorldState, goal: Goal) -> float:
        raw_estimate = (
            self.heuristic(state, goal)
            if self.heuristic is not None
            else self._heuristic(state, goal)
        )
        return self._validate_search_cost(raw_estimate, "heuristic estimate")

    def _state_key(self, state: WorldState) -> StateKey:
        """Return a stable, hashable identity for duplicate-state pruning.

        ``WorldState`` values are usually simple hashable facts, but future
        resource models may store lists, dicts, or other structured values.  The
        default key handles common containers and can be overridden for richer
        numeric/resource state abstractions.
        """
        return tuple(
            (key, self._freeze_value(value))
            for key, value in sorted(state.items(), key=lambda item: item[0])
        )

    def _freeze_value(self, value: Any) -> Hashable:
        if isinstance(value, dict):
            return (
                "dict",
                tuple(
                    (self._freeze_value(key), self._freeze_value(inner_value))
                    for key, inner_value in sorted(
                        value.items(), key=lambda item: repr(item[0])
                    )
                ),
            )
        if isinstance(value, list):
            return ("list", tuple(self._freeze_value(item) for item in value))
        if isinstance(value, tuple):
            return ("tuple", tuple(self._freeze_value(item) for item in value))
        if isinstance(value, set):
            return (
                "set",
                tuple(
                    sorted(
                        (self._freeze_value(item) for item in value),
                        key=repr,
                    )
                ),
            )

        try:
            hash(value)
        except TypeError:
            return ("repr", repr(value))
        return value

    def _validate_search_cost(self, value: float, label: str) -> float:
        try:
            cost = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"A* requires a numeric {label}; got {value!r}") from exc

        if not math.isfinite(cost) or cost < 0:
            raise ValueError(
                f"A* requires a non-negative finite {label}; got {value!r}"
            )
        return cost
