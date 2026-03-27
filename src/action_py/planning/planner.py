from __future__ import annotations

import random
from dataclasses import dataclass

from action_py.core.conditions import Condition
from action_py.core.models import Action, Goal, Plan
from action_py.core.world import WorldState


@dataclass
class Planner:
    """Goal-Oriented Action Planner.

    Uses backward-chaining search with pluggable action selection.
    The default V1 strategy picks randomly among candidate actions;
    override :meth:`_select_action` for smarter heuristics (A*,
    best-first, cost-weighted, etc.).

    Attributes:
        actions: The pool of actions available for planning.
        max_depth: Maximum search depth to prevent infinite loops.
    """

    actions: list[Action]
    max_depth: int = 50

    def plan(
        self,
        state: WorldState,
        goal: Goal,
        *,
        seed: int | None = None,
    ) -> Plan | None:
        """Find a plan that transitions *state* to satisfy *goal*.

        Args:
            state: The initial world state.
            goal: The goal to achieve.
            seed: Optional RNG seed for reproducible plans.

        Returns:
            A :class:`~action_py.core.models.Plan` if one is found, or
            ``None`` if no valid plan exists within :attr:`max_depth`.
        """
        if goal.is_satisfied(state):
            return Plan()

        rng = random.Random(seed)
        return self._backward_plan(state, goal.condition, rng)

    # -- internals -------------------------------------------------------------

    def _backward_plan(
        self,
        initial_state: WorldState,
        goal_condition: Condition,
        rng: random.Random,
        _depth: int = 0,
    ) -> Plan | None:
        """Backward search from goal to initial state.

        Finds actions whose effects satisfy unmet goal facts, then
        recursively plans for those actions' preconditions.

        Args:
            initial_state: The state to start planning from.
            goal_condition: The condition to satisfy.
            rng: Random number generator for action selection.
            _depth: Current recursion depth (internal).

        Returns:
            A :class:`~action_py.core.models.Plan` or ``None``.
        """
        if _depth >= self.max_depth:
            return None

        plan_actions: list[Action] = []
        current_state = initial_state.copy()

        for _ in range(self.max_depth):
            if goal_condition.is_met(current_state):
                return Plan(actions=plan_actions)

            unsatisfied = goal_condition.unsatisfied_facts(current_state)
            candidates = self._find_candidates(current_state, unsatisfied)
            if not candidates:
                return None

            chosen = self._select_action(candidates, rng)
            if not chosen.is_applicable(current_state):
                # Need to satisfy preconditions first — recurse
                sub_plan = self._backward_plan(
                    current_state, chosen.preconditions, rng, _depth + 1
                )
                if sub_plan is None:
                    return None
                for a in sub_plan:
                    plan_actions.append(a)
                    current_state = a.apply(current_state)

            plan_actions.append(chosen)
            current_state = chosen.apply(current_state)

        return None  # exceeded max_depth

    def _find_candidates(
        self,
        state: WorldState,
        unsatisfied: dict[str, object],
    ) -> list[Action]:
        """Return actions whose effects satisfy at least one unsatisfied fact.

        Args:
            state: The current world state (unused in V1 but available
                for future heuristics).
            unsatisfied: Fact key/value pairs that still need to be met.

        Returns:
            List of candidate :class:`~action_py.core.models.Action` instances.
        """
        candidates: list[Action] = []
        for action in self.actions:
            action_facts = action.effects_as_facts
            for key, value in unsatisfied.items():
                if action_facts.get(key) == value:
                    candidates.append(action)
                    break
        return candidates

    def _select_action(
        self,
        candidates: list[Action],
        rng: random.Random,
    ) -> Action:
        """Pick an action from *candidates*.

        Override this method for different selection strategies
        (lowest cost, best heuristic, etc.).

        Args:
            candidates: Non-empty list of applicable actions.
            rng: Random number generator.

        Returns:
            The chosen :class:`~action_py.core.models.Action`.
        """
        return rng.choice(candidates)
