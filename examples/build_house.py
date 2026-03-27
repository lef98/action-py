"""action-py playground — run this to see the planner in action."""

from action_py import Action, Goal, WorldState, Planner, EQ, ALL, SET, DO


def main() -> None:
    # -- define actions --------------------------------------------------------

    go_to_forest = Action(
        name="go_to_forest",
        preconditions=EQ("at_home"),
        effects=DO(SET("at_home", False), SET("at_forest", True)),
    )

    get_axe = Action(
        name="get_axe",
        preconditions=EQ("at_home"),
        effects=DO(SET("has_axe", True)),
    )

    chop_tree = Action(
        name="chop_tree",
        preconditions=ALL(EQ("has_axe"), EQ("at_forest")),
        effects=DO(SET("has_wood", True)),
    )

    build_house = Action(
        name="build_house",
        preconditions=ALL(EQ("has_wood"), EQ("has_nails")),
        effects=DO(SET("has_house", True)),
    )

    buy_nails = Action(
        name="buy_nails",
        preconditions=EQ("has_money"),
        effects=DO(SET("has_nails", True), SET("has_money", False)),
    )

    actions = [go_to_forest, get_axe, chop_tree, build_house, buy_nails]

    # -- initial world state ---------------------------------------------------

    initial_state = WorldState({
        "at_home": True,
        "at_forest": False,
        "has_axe": False,
        "has_wood": False,
        "has_nails": False,
        "has_money": True,
        "has_house": False,
    })

    # -- define goal -----------------------------------------------------------

    goal = Goal(name="build_a_house", condition=EQ("has_house"))

    # -- plan ------------------------------------------------------------------

    planner = Planner(actions=actions)
    plan = planner.plan(initial_state, goal, seed=42)

    # -- print results ---------------------------------------------------------

    print("=== action-py — Python Action Planning Engine ===\n")
    print(f"Initial state: {initial_state}\n")
    print(f"Goal: {goal}\n")

    if plan is None:
        print("No plan found!")
        return

    print(f"Plan found! ({len(plan)} steps, cost={plan.total_cost})\n")

    state = initial_state
    for i, action in enumerate(plan, 1):
        print(f"  Step {i}: {action.name}")
        print(f"          preconditions met: {action.is_applicable(state)}")
        state = action.apply(state)
        print(f"          state after: {state}")

    print(f"\nGoal satisfied: {goal.is_satisfied(state)}")


if __name__ == "__main__":
    main()
