import pytest

from action_py import Planner
from action_py.dsl import DSLSemanticError, compile_domain, parse_domain


BUILD_HOUSE = """
domain build_house

objects:
  location: home, forest

world initial:
  at_home = true
  at_forest = false
  has_axe = false
  has_wood = false
  has_nails = false
  has_money = true
  has_house = false

goal build_a_house priority 1:
  has_house

action go_to_forest cost 1:
  precondition:
    at_home
  effect:
    at_home := false
    at_forest := true

action get_axe:
  precondition:
    at_home
  effect:
    has_axe := true

action chop_tree:
  precondition:
    all:
      has_axe
      at_forest
  effect:
    has_wood := true

action buy_nails:
  precondition:
    has_money
  effect:
    has_nails := true
    has_money := false

action build_house:
  precondition:
    all:
      has_wood
      has_nails
  effect:
    has_house := true
"""


BLOCKSWORLD = """
domain blocksworld

objects:
  block: A, B, C
  place: table

world start:
  on(A) = B
  on(B) = table
  on(C) = table
  clear(A) = true
  clear(B) = false
  clear(C) = true
  holding = none

goal stack_A_B_C:
  all:
    on(A) == B
    on(B) == C

action pick_up(x: block):
  precondition:
    all:
      holding == none
      on(x) == table
      clear(x)
  effect:
    holding := x
    on(x) := hand
    clear(x) := false

action put_down(x: block):
  precondition:
    holding == x
  effect:
    holding := none
    on(x) := table
    clear(x) := true

action stack(x: block, y: block)
where x != y:
  precondition:
    all:
      holding == x
      clear(y)
  effect:
    holding := none
    on(x) := y
    clear(x) := true
    clear(y) := false

action unstack(x: block, y: block)
where x != y:
  precondition:
    all:
      holding == none
      on(x) == y
      clear(x)
  effect:
    holding := x
    on(x) := hand
    clear(x) := false
    clear(y) := true
"""


def test_parse_build_house():
    program = parse_domain(BUILD_HOUSE)
    assert program.domain_name == "build_house"
    assert len(program.worlds) == 1
    assert len(program.goals) == 1
    assert len(program.actions) == 5


def test_compile_build_house_and_plan():
    domain = compile_domain(BUILD_HOUSE)

    assert domain.name == "build_house"
    assert set(domain.worlds) == {"initial"}
    assert set(domain.goals) == {"build_a_house"}
    assert [action.name for action in domain.actions] == [
        "go_to_forest",
        "get_axe",
        "chop_tree",
        "buy_nails",
        "build_house",
    ]
    assert domain.worlds["initial"].get("has_house") is False

    plan = Planner(domain.actions).plan(
        domain.worlds["initial"],
        domain.goals["build_a_house"],
        seed=42,
    )
    assert plan is not None

    state = domain.worlds["initial"]
    for action in plan:
        assert action.is_applicable(state)
        state = action.apply(state)
    assert domain.goals["build_a_house"].is_satisfied(state)


def test_compile_blocksworld_templates():
    domain = compile_domain(BLOCKSWORLD)

    names = {action.name for action in domain.actions}
    assert len(domain.actions) == 18
    assert "pick_up(A)" in names
    assert "put_down(C)" in names
    assert "stack(A,B)" in names
    assert "stack(A,A)" not in names
    assert "unstack(C,B)" in names

    stack_ab = next(action for action in domain.actions if action.name == "stack(A,B)")
    assert stack_ab.effects_as_facts == {
        "holding": None,
        "on_A": "B",
        "clear_A": True,
        "clear_B": False,
    }


def test_unsupported_any_fails_semantically():
    source = """
domain unsupported

world initial:
  a = false

goal g:
  any:
    a
    b

action make_a:
  precondition:
    a
  effect:
    b := true
"""

    with pytest.raises(DSLSemanticError, match="any"):
        compile_domain(source)

