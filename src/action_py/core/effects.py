from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from action_py.core.world import WorldState


class Effect(ABC):
    """Base class for all effect operators.

    Subclass this to add new effect types (``INCREMENT``, ``TOGGLE``,
    etc.).  Every subclass must implement :meth:`apply` and
    :meth:`as_facts`.
    """

    @abstractmethod
    def apply(self, state: WorldState) -> WorldState:
        """Apply this effect to a world state.

        Args:
            state: The current world state.

        Returns:
            A **new** :class:`~page.core.world.WorldState` with the
            effect applied.  The original is not mutated.
        """
        ...

    @abstractmethod
    def as_facts(self) -> dict[str, object]:
        """Return a flat dict of the key/value changes this effect produces.

        Used by the planner to reason about what an action achieves
        during backward search.

        Returns:
            A dict mapping fact keys to the values they will be set to.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class SetEffect(Effect):
    """Set a single fact to a value.

    Typically created via the :func:`SET` constructor.

    Args:
        key: The fact name to set.
        value: The value to assign.
    """

    def __init__(self, key: str, value: object) -> None:
        self.key = key
        self.value = value

    def apply(self, state: WorldState) -> WorldState:
        return state.apply_dict({self.key: self.value})

    def as_facts(self) -> dict[str, object]:
        return {self.key: self.value}

    def __repr__(self) -> str:
        return f"SET({self.key!r}, {self.value!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SetEffect):
            return NotImplemented
        return self.key == other.key and self.value == other.value

    def __hash__(self) -> int:
        return hash((self.key, self.value))


class DoEffect(Effect):
    """Combine multiple effects, applied in order.

    Typically created via the :func:`DO` constructor.

    Args:
        effects: The child effects to apply sequentially.
    """

    def __init__(self, effects: list[Effect]) -> None:
        self.effects = effects

    def apply(self, state: WorldState) -> WorldState:
        for effect in self.effects:
            state = effect.apply(state)
        return state

    def as_facts(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for effect in self.effects:
            result.update(effect.as_facts())
        return result

    def __repr__(self) -> str:
        inner = ", ".join(repr(e) for e in self.effects)
        return f"DO({inner})"


# -- public constructors (DSL-style) ----------------------------------------

def SET(key: str, value: object) -> SetEffect:
    """Create a single set-fact effect.

    Args:
        key: The fact name to set.
        value: The value to assign.

    Returns:
        A :class:`SetEffect`.

    Example::

        effect = SET("has_wood", True)
    """
    return SetEffect(key, value)


def DO(*effects: Effect) -> Effect:
    """Combine multiple effects into one.

    If only one effect is given it is returned as-is (no wrapping).

    Args:
        *effects: One or more :class:`Effect` instances.

    Returns:
        A single :class:`Effect`.  A :class:`DoEffect` when two or
        more inputs are provided.

    Example::

        effect = DO(SET("has_wood", True), SET("near_tree", False))
    """
    if len(effects) == 1:
        return effects[0]
    return DoEffect(list(effects))
