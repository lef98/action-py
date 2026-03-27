from __future__ import annotations

from typing import Iterator


class WorldState:
    """Immutable snapshot of the world represented as key/value facts.

    Create a state from a plain dict and derive new states via
    :meth:`apply_dict` or :meth:`copy`.  The original is never mutated.

    Args:
        facts: Initial fact mapping.  ``None`` creates an empty state.

    Example::

        state = WorldState({"alive": True, "hp": 100})
    """

    def __init__(self, facts: dict[str, object] | None = None) -> None:
        self._facts: dict[str, object] = dict(facts) if facts else {}

    def get(self, key: str, default: object = None) -> object:
        """Look up a fact value.

        Args:
            key: The fact name.
            default: Returned when *key* is not present.

        Returns:
            The fact value, or *default*.
        """
        return self._facts.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self._facts

    def __iter__(self) -> Iterator[str]:
        return iter(self._facts)

    def items(self) -> Iterator[tuple[str, object]]:
        """Iterate over ``(key, value)`` pairs of all facts."""
        yield from self._facts.items()

    def apply_dict(self, changes: dict[str, object]) -> WorldState:
        """Derive a new state with *changes* merged in.

        Args:
            changes: Fact key/value pairs to add or overwrite.

        Returns:
            A **new** :class:`WorldState`.  The original is unchanged.
        """
        merged = {**self._facts, **changes}
        return WorldState(merged)

    def copy(self) -> WorldState:
        """Return a shallow copy of this state."""
        return WorldState(self._facts)

    # -- dunder helpers --------------------------------------------------------

    def __repr__(self) -> str:
        return f"WorldState({self._facts!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WorldState):
            return NotImplemented
        return self._facts == other._facts

    def __hash__(self) -> int:
        return hash(tuple(sorted(self._facts.items())))
