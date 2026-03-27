"""Blocksworld — a classic planning benchmark implemented in action-py.

Blocks sit on a table or on top of each other.  A robot arm can pick
up and put down one block at a time.  The goal is to rearrange blocks
from an initial configuration into a target stack.

State encoding:
    "on_A"       → "B"    means block A is on block B
    "on_A"       → "table" means block A is on the table
    "clear_A"    → True   means nothing is on top of A
    "clear_table"→ True   (the table always has room)
    "holding"    → None   means the arm is empty
    "holding"    → "A"    means the arm is holding block A
"""

from action_py import Action, Goal, WorldState, Planner, EQ, ALL, SET, DO


def make_actions(blocks: list[str]) -> list[Action]:
    """Generate all Blocksworld actions for a set of block names.

    Four action templates, instantiated for every valid combination:

    - **pick_up(X)** — pick block X up from the table
    - **put_down(X)** — put block X down on the table
    - **stack(X, Y)** — place block X (held) onto block Y
    - **unstack(X, Y)** — pick up block X from on top of block Y
    """
    actions: list[Action] = []

    for x in blocks:
        # pick_up(X): arm empty, X on table, X is clear → hold X
        actions.append(Action(
            name=f"pick_up({x})",
            preconditions=ALL(
                EQ("holding", "none"),
                EQ(f"on_{x}", "table"),
                EQ(f"clear_{x}", True),
            ),
            effects=DO(
                SET("holding", x),
                SET(f"on_{x}", "hand"),
                SET(f"clear_{x}", False),
            ),
        ))

        # put_down(X): holding X → X on table, arm empty
        actions.append(Action(
            name=f"put_down({x})",
            preconditions=EQ("holding", x),
            effects=DO(
                SET("holding", "none"),
                SET(f"on_{x}", "table"),
                SET(f"clear_{x}", True),
            ),
        ))

        for y in blocks:
            if x == y:
                continue

            # stack(X, Y): holding X, Y is clear → X on Y, arm empty
            actions.append(Action(
                name=f"stack({x},{y})",
                preconditions=ALL(
                    EQ("holding", x),
                    EQ(f"clear_{y}", True),
                ),
                effects=DO(
                    SET("holding", "none"),
                    SET(f"on_{x}", y),
                    SET(f"clear_{x}", True),
                    SET(f"clear_{y}", False),
                ),
            ))

            # unstack(X, Y): arm empty, X on Y, X is clear → hold X, Y clear
            actions.append(Action(
                name=f"unstack({x},{y})",
                preconditions=ALL(
                    EQ("holding", "none"),
                    EQ(f"on_{x}", y),
                    EQ(f"clear_{x}", True),
                ),
                effects=DO(
                    SET("holding", x),
                    SET(f"on_{x}", "hand"),
                    SET(f"clear_{x}", False),
                    SET(f"clear_{y}", True),
                ),
            ))

    return actions


def print_stacks(state: WorldState, blocks: list[str]) -> None:
    """Pretty-print the current block configuration."""
    # Build a mapping: base → ordered stack above it
    on_table = [b for b in blocks if state.get(f"on_{b}") == "table"]
    child_of: dict[str, str | None] = {}
    for b in blocks:
        loc = state.get(f"on_{b}")
        if loc not in ("table", "hand", None):
            child_of[loc] = b  # type: ignore[assignment]

    for base in on_table:
        tower = [base]
        current = base
        while current in child_of:
            current = child_of[current]
            tower.append(current)
        print("    " + " | ".join(f"[{b}]" for b in tower) + "  (table)")

    held = state.get("holding")
    if held != "none":
        print(f"    Arm holding: [{held}]")
    else:
        print("    Arm: empty")


# ---------------------------------------------------------------------------
# Scenario 1: simple 3-block problem
# ---------------------------------------------------------------------------

def scenario_simple() -> None:
    """3 blocks: rearrange A-on-B, C-on-table → A-on-B-on-C.

    Initial:          Goal:
      [A]               [A]
      [B]  [C]          [B]
      --------          [C]
       table            --------
                         table

    Optimal plan is 4 steps:
      unstack(A,B) → put_down(A) → stack(B,C) → stack(A,B)
    """
    blocks = ["A", "B", "C"]
    actions = make_actions(blocks)

    initial = WorldState({
        "on_A": "B",
        "on_B": "table",
        "on_C": "table",
        "clear_A": True,
        "clear_B": False,
        "clear_C": True,
        "holding": "none",
    })

    goal = Goal(
        name="stack_A_B_C",
        condition=ALL(EQ("on_A", "B"), EQ("on_B", "C")),
    )

    run_scenario("Simple 3-block", blocks, actions, initial, goal)


# ---------------------------------------------------------------------------
# Scenario 2: harder 4-block problem
# ---------------------------------------------------------------------------

def scenario_four_blocks() -> None:
    """4 blocks: all on table → D-on-C-on-B-on-A.

    Initial:                  Goal:
      [A] [B] [C] [D]          [D]
      ------------------        [C]
           table                [B]
                                [A]
                                -----
                                table

    Optimal plan is 6 steps.
    """
    blocks = ["A", "B", "C", "D"]
    actions = make_actions(blocks)

    initial = WorldState({
        "on_A": "table",
        "on_B": "table",
        "on_C": "table",
        "on_D": "table",
        "clear_A": True,
        "clear_B": True,
        "clear_C": True,
        "clear_D": True,
        "holding": "none",
    })

    goal = Goal(
        name="tower_D_C_B_A",
        condition=ALL(
            EQ("on_B", "A"),
            EQ("on_C", "B"),
            EQ("on_D", "C"),
        ),
    )

    run_scenario("4-block tower", blocks, actions, initial, goal)


# ---------------------------------------------------------------------------
# Scenario 3: reversal
# ---------------------------------------------------------------------------

def scenario_reverse() -> None:
    """3 blocks: reverse a stack  A-on-B-on-C → C-on-B-on-A.

    Optimal plan is 6 steps.
    """
    blocks = ["A", "B", "C"]
    actions = make_actions(blocks)

    initial = WorldState({
        "on_A": "B",
        "on_B": "C",
        "on_C": "table",
        "clear_A": True,
        "clear_B": False,
        "clear_C": False,
        "holding": "none",
    })

    goal = Goal(
        name="reverse_stack",
        condition=ALL(
            EQ("on_C", "B"),
            EQ("on_B", "A"),
            EQ("on_A", "table"),
        ),
    )

    run_scenario("Reverse 3-block stack", blocks, actions, initial, goal)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_scenario(
    title: str,
    blocks: list[str],
    actions: list[Action],
    initial: WorldState,
    goal: Goal,
) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")
    print(f"\n  Actions available: {len(actions)}")
    print(f"  Goal: {goal.name}\n")

    print("  Initial:")
    print_stacks(initial, blocks)

    planner = Planner(actions=actions, max_depth=100)

    # Try several seeds since the random planner isn't optimal
    best_plan = None
    for seed in range(50):
        plan = planner.plan(initial, goal, seed=seed)
        if plan is not None and (best_plan is None or len(plan) < len(best_plan)):
            best_plan = plan

    if best_plan is None:
        print("\n  No plan found!")
        return

    print(f"\n  Best plan found: {len(best_plan)} steps (cost={best_plan.total_cost})\n")

    state = initial
    for i, action in enumerate(best_plan, 1):
        assert action.is_applicable(state), f"{action.name} not applicable!"
        state = action.apply(state)
        print(f"    Step {i}: {action.name}")

    print(f"\n  Final:")
    print_stacks(state, blocks)
    print(f"\n  Goal satisfied: {goal.is_satisfied(state)}")


def main() -> None:
    print("=== action-py Blocksworld Benchmark ===")
    scenario_simple()
    scenario_four_blocks()
    scenario_reverse()


if __name__ == "__main__":
    main()
