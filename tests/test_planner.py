from action_py import (
    Action,
    Goal,
    WorldState,
    Planner,
    fact,
    facts,
    AndCondition,
    FactCondition,
    EQ,
    ALL,
    SET,
    DO,
)


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

class TestFactCondition:
    def test_met(self):
        state = WorldState({"has_wood": True})
        assert fact("has_wood").is_met(state)

    def test_not_met(self):
        state = WorldState({"has_wood": False})
        assert not fact("has_wood").is_met(state)

    def test_missing_key(self):
        state = WorldState()
        assert not fact("has_wood").is_met(state)

    def test_unsatisfied_facts(self):
        state = WorldState({"has_wood": False})
        cond = fact("has_wood")
        assert cond.unsatisfied_facts(state) == {"has_wood": True}


class TestEQ:
    def test_eq_is_fact_condition(self):
        c = EQ("x", 5)
        assert isinstance(c, FactCondition)
        assert c.is_met(WorldState({"x": 5}))
        assert not c.is_met(WorldState({"x": 3}))

    def test_eq_default_true(self):
        c = EQ("alive")
        assert c.is_met(WorldState({"alive": True}))
        assert not c.is_met(WorldState({"alive": False}))


class TestALL:
    def test_single(self):
        c = ALL(EQ("a", True))
        assert isinstance(c, FactCondition)

    def test_multiple(self):
        c = ALL(EQ("a", True), EQ("b", True))
        assert isinstance(c, AndCondition)
        state = WorldState({"a": True, "b": True})
        assert c.is_met(state)

    def test_partial(self):
        c = ALL(EQ("a", True), EQ("b", True))
        state = WorldState({"a": True, "b": False})
        assert not c.is_met(state)

    def test_unsatisfied(self):
        c = ALL(EQ("a", True), EQ("b", True))
        state = WorldState({"a": True, "b": False})
        assert c.unsatisfied_facts(state) == {"b": True}


class TestAndCondition:
    def test_all_met(self):
        state = WorldState({"a": True, "b": True})
        cond = facts(a=True, b=True)
        assert cond.is_met(state)

    def test_partial(self):
        state = WorldState({"a": True, "b": False})
        cond = facts(a=True, b=True)
        assert not cond.is_met(state)

    def test_unsatisfied(self):
        state = WorldState({"a": True, "b": False})
        cond = facts(a=True, b=True)
        assert cond.unsatisfied_facts(state) == {"b": True}

    def test_and_operator(self):
        c = fact("a") & fact("b")
        assert isinstance(c, AndCondition)
        assert len(c.conditions) == 2


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------

class TestSET:
    def test_apply(self):
        s = WorldState({"x": 1})
        s2 = SET("x", 2).apply(s)
        assert s2.get("x") == 2
        assert s.get("x") == 1  # original unchanged

    def test_as_facts(self):
        e = SET("key", "val")
        assert e.as_facts() == {"key": "val"}

    def test_repr(self):
        assert repr(SET("a", True)) == "SET('a', True)"


class TestDO:
    def test_single(self):
        e = DO(SET("a", 1))
        # single effect returned as-is
        assert e.as_facts() == {"a": 1}

    def test_multiple(self):
        e = DO(SET("a", 1), SET("b", 2))
        assert e.as_facts() == {"a": 1, "b": 2}

    def test_apply_order(self):
        e = DO(SET("x", 1), SET("x", 2))
        s = e.apply(WorldState())
        assert s.get("x") == 2  # last write wins

    def test_repr(self):
        e = DO(SET("a", 1), SET("b", 2))
        assert "DO(" in repr(e)


# ---------------------------------------------------------------------------
# WorldState
# ---------------------------------------------------------------------------

class TestWorldState:
    def test_apply_dict(self):
        s = WorldState({"hp": 10})
        s2 = s.apply_dict({"hp": 5, "shield": True})
        assert s2.get("hp") == 5
        assert s2.get("shield") is True
        # original unchanged
        assert s.get("hp") == 10
        assert s.get("shield") is None

    def test_contains(self):
        s = WorldState({"x": 1})
        assert "x" in s
        assert "y" not in s


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------

class TestAction:
    def test_applicable(self):
        a = Action(
            name="chop",
            preconditions=EQ("has_axe"),
            effects=SET("has_wood", True),
        )
        assert a.is_applicable(WorldState({"has_axe": True}))
        assert not a.is_applicable(WorldState())

    def test_apply(self):
        a = Action(
            name="chop",
            preconditions=EQ("has_axe"),
            effects=SET("has_wood", True),
        )
        s = a.apply(WorldState({"has_axe": True}))
        assert s.get("has_wood") is True

    def test_effects_as_facts(self):
        a = Action(
            name="multi",
            preconditions=EQ("ready"),
            effects=DO(SET("a", 1), SET("b", 2)),
        )
        assert a.effects_as_facts == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

def _build_woodcutting_scenario():
    """Classic GOAP example: gather wood."""
    get_axe = Action(
        name="get_axe",
        preconditions=ALL(EQ("at_home", True)),
        effects=DO(SET("has_axe", True)),
    )
    chop_tree = Action(
        name="chop_tree",
        preconditions=ALL(EQ("has_axe", True)),
        effects=DO(SET("has_wood", True)),
    )
    go_home = Action(
        name="go_home",
        preconditions=EQ("alive", True),
        effects=DO(SET("at_home", True)),
    )
    goal = Goal(name="get_wood", condition=EQ("has_wood"))
    initial = WorldState({"alive": True, "at_home": True})
    return [get_axe, chop_tree, go_home], goal, initial


class TestPlanner:
    def test_already_satisfied(self):
        planner = Planner(actions=[])
        goal = Goal(name="done", condition=EQ("done"))
        state = WorldState({"done": True})
        plan = planner.plan(state, goal)
        assert plan is not None
        assert plan.is_empty

    def test_simple_plan(self):
        actions, goal, state = _build_woodcutting_scenario()
        planner = Planner(actions=actions)
        plan = planner.plan(state, goal, seed=42)
        assert plan is not None
        assert not plan.is_empty
        # Verify final state satisfies goal
        current = state
        for action in plan:
            current = action.apply(current)
        assert goal.is_satisfied(current)

    def test_requires_chaining(self):
        """Planner must chain: go_home → get_axe → chop_tree."""
        actions, goal, _ = _build_woodcutting_scenario()
        state = WorldState({"alive": True, "at_home": False})
        planner = Planner(actions=actions)
        plan = planner.plan(state, goal, seed=7)
        assert plan is not None
        current = state
        for action in plan:
            assert action.is_applicable(current), (
                f"{action.name} not applicable in {current}"
            )
            current = action.apply(current)
        assert goal.is_satisfied(current)

    def test_no_plan_possible(self):
        action = Action(
            name="noop",
            preconditions=EQ("impossible"),
            effects=DO(SET("done", True)),
        )
        planner = Planner(actions=[action], max_depth=10)
        goal = Goal(name="done", condition=EQ("done"))
        state = WorldState()
        plan = planner.plan(state, goal, seed=0)
        assert plan is None

    def test_total_cost(self):
        actions, goal, state = _build_woodcutting_scenario()
        planner = Planner(actions=actions)
        plan = planner.plan(state, goal, seed=42)
        assert plan is not None
        assert plan.total_cost == len(plan.actions)
