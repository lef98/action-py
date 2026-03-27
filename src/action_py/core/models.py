from __future__ import annotations

from dataclasses import dataclass, field

from action_py.core.conditions import Condition, AndCondition, FactCondition
from action_py.core.effects import Effect
from action_py.core.world import WorldState


@dataclass(frozen=True)
class Action:
    """An action the planner can choose.

    Actions are the building blocks of a plan.  Each action declares
    what must be true before it can fire (:attr:`preconditions`) and
    what changes it makes to the world (:attr:`effects`).

    Attributes:
        name: Human-readable label.
        preconditions: Condition tree that must hold **before** the action fires.
        effects: Effect tree that transforms the world state **after** firing.
        cost: Numeric cost used for weighted planning (default ``1.0``).

    Example::

        chop = Action(
            name="chop_tree",
            preconditions=ALL(EQ("has_axe", True)),
            effects=DO(SET("has_wood", True)),
        )
    """

    name: str
    preconditions: Condition
    effects: Effect
    cost: float = 1.0

    def is_applicable(self, state: WorldState) -> bool:
        """Check whether preconditions are met in *state*.

        Args:
            state: The current world state.

        Returns:
            ``True`` if the action can fire.
        """
        return self.preconditions.is_met(state)

    def apply(self, state: WorldState) -> WorldState:
        """Apply this action's effects to *state*.

        Args:
            state: The current world state.

        Returns:
            A new :class:`~page.core.world.WorldState` with effects applied.
        """
        return self.effects.apply(state)

    @property
    def effects_as_facts(self) -> dict[str, object]:
        """Flat dict view of the effects for planner reasoning."""
        return self.effects.as_facts()

    def __repr__(self) -> str:
        return f"Action({self.name!r})"


@dataclass
class Goal:
    """A desired world state expressed as a condition tree.

    Attributes:
        name: Human-readable label.
        condition: The condition tree that defines *goal met*.
        priority: Static priority (higher = more important).  Reserved
            for future goal-selection via scoring functions.

    Example::

        goal = Goal(name="get_wood", condition=EQ("has_wood"))
    """

    name: str
    condition: Condition
    priority: float = 1.0

    def is_satisfied(self, state: WorldState) -> bool:
        """Check whether *state* satisfies this goal.

        Args:
            state: The current world state.

        Returns:
            ``True`` if the goal condition holds.
        """
        return self.condition.is_met(state)

    def __repr__(self) -> str:
        return f"Goal({self.name!r})"


@dataclass
class Plan:
    """An ordered sequence of actions leading to a goal.

    Attributes:
        actions: The steps of the plan, in execution order.
    """

    actions: list[Action] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        """Sum of :attr:`Action.cost` across all actions in the plan."""
        return sum(a.cost for a in self.actions)

    @property
    def is_empty(self) -> bool:
        """``True`` when the plan contains no actions."""
        return len(self.actions) == 0

    def __len__(self) -> int:
        return len(self.actions)

    def __iter__(self):
        return iter(self.actions)

    def __repr__(self) -> str:
        names = " -> ".join(a.name for a in self.actions)
        return f"Plan([{names}] cost={self.total_cost})"


# -- legacy helpers (still work, delegate to operator constructors) ----------

def fact(key: str, value: object = True) -> FactCondition:
    """Shortcut for :func:`~page.core.conditions.EQ`.

    Args:
        key: The fact name.
        value: Expected value (default ``True``).

    Returns:
        A :class:`~page.core.conditions.FactCondition`.
    """
    return FactCondition(key, value)


def facts(**kwargs: object) -> Condition:
    """Create an AND condition from keyword arguments.

    Convenience alias for ``ALL(EQ(k, v), ...)``.

    Args:
        **kwargs: Fact key/value pairs.

    Returns:
        A :class:`~page.core.conditions.Condition` (single
        :class:`~page.core.conditions.FactCondition` when only one
        kwarg is given, :class:`~page.core.conditions.AndCondition`
        otherwise).

    Example::

        cond = facts(has_wood=True, has_axe=True)
    """
    conds = [FactCondition(k, v) for k, v in kwargs.items()]
    if len(conds) == 1:
        return conds[0]
    return AndCondition(conds)
