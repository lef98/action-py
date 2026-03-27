from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from action_py.core.world import WorldState


class Condition(ABC):
    """Base class for all condition operators.

    Subclass this to add new logical operators (``OR``, ``NOT``,
    comparison, etc.).  Every subclass must implement :meth:`is_met`
    and :meth:`unsatisfied_facts`.

    Conditions can be combined with the ``&`` operator to produce an
    :class:`AndCondition`::

        combined = EQ("a", True) & EQ("b", True)
    """

    @abstractmethod
    def is_met(self, state: WorldState) -> bool:
        """Check whether this condition is satisfied.

        Args:
            state: The current world state to evaluate against.

        Returns:
            ``True`` if the condition holds in *state*.
        """
        ...

    @abstractmethod
    def unsatisfied_facts(self, state: WorldState) -> dict[str, object]:
        """Return the fact key/value pairs that are not yet satisfied.

        Args:
            state: The current world state to evaluate against.

        Returns:
            A dict mapping fact keys to their required values for every
            sub-condition that is **not** met.
        """
        ...

    def __and__(self, other: Condition) -> AndCondition:
        left = self._flatten_and()
        right = other._flatten_and()
        return AndCondition(left + right)

    def _flatten_and(self) -> list[Condition]:
        return [self]


class FactCondition(Condition):
    """A single fact equality check: ``state[key] == value``.

    Typically created via the :func:`EQ` constructor rather than
    instantiated directly.

    Args:
        key: The name of the fact to check.
        value: The expected value.
    """

    def __init__(self, key: str, value: object) -> None:
        self.key = key
        self.value = value

    def is_met(self, state: WorldState) -> bool:
        return state.get(self.key) == self.value

    def unsatisfied_facts(self, state: WorldState) -> dict[str, object]:
        if self.is_met(state):
            return {}
        return {self.key: self.value}

    def __repr__(self) -> str:
        return f"Fact({self.key!r}={self.value!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FactCondition):
            return NotImplemented
        return self.key == other.key and self.value == other.value

    def __hash__(self) -> int:
        return hash((self.key, self.value))


class AndCondition(Condition):
    """Logical AND over a list of child conditions.

    All children must be satisfied for this condition to hold.
    Typically created via :func:`ALL` or the ``&`` operator.

    Args:
        conditions: Child conditions that must all be met.
    """

    def __init__(self, conditions: list[Condition]) -> None:
        self.conditions = conditions

    def is_met(self, state: WorldState) -> bool:
        return all(c.is_met(state) for c in self.conditions)

    def unsatisfied_facts(self, state: WorldState) -> dict[str, object]:
        result: dict[str, object] = {}
        for c in self.conditions:
            result.update(c.unsatisfied_facts(state))
        return result

    def _flatten_and(self) -> list[Condition]:
        return list(self.conditions)

    def __repr__(self) -> str:
        inner = " & ".join(repr(c) for c in self.conditions)
        return f"ALL({inner})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AndCondition):
            return NotImplemented
        return self.conditions == other.conditions

    def __hash__(self) -> int:
        return hash(tuple(self.conditions))


# -- public constructors (DSL-style) ----------------------------------------

def EQ(key: str, value: object = True) -> FactCondition:
    """Create an equality condition.

    Args:
        key: The fact name to check.
        value: The expected value.  Defaults to ``True``.

    Returns:
        A :class:`FactCondition` that checks ``state[key] == value``.

    Example::

        precondition = EQ("has_axe", True)
    """
    return FactCondition(key, value)


def ALL(*conditions: Condition) -> Condition:
    """Combine conditions with logical AND.

    If only one condition is given it is returned as-is (no wrapping).

    Args:
        *conditions: One or more :class:`Condition` instances.

    Returns:
        A single :class:`Condition`.  An :class:`AndCondition` when
        two or more inputs are provided.

    Example::

        precondition = ALL(EQ("has_axe"), EQ("near_tree"))
    """
    if len(conditions) == 1:
        return conditions[0]
    flat: list[Condition] = []
    for c in conditions:
        flat.extend(c._flatten_and())
    return AndCondition(flat)
