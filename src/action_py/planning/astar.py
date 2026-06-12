from __future__ import annotations

from action_py.planning.planner import Planner


class AStarPlanner(Planner):
    """Compatibility planner placeholder.

    The public package already exported ``AStarPlanner`` but the module was
    missing.  Until a real A* implementation is added, this class preserves the
    import surface and behaves like the base planner.
    """

