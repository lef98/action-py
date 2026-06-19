# action-py DSL Reference

This document describes the V1 text DSL implemented by `action_py.dsl`.
The DSL defines planning domains and compiles them into the existing
`action-py` runtime classes: `WorldState`, `Goal`, `Action`, `Condition`, and
`Effect`.

## Quick Start

```python
from action_py import Planner
from action_py.dsl import load_domain

domain = load_domain("build_house.goap")
planner = Planner(domain.actions)
plan = planner.plan(domain.worlds["initial"], domain.goals["build_a_house"])
```

Plans can be executed with callbacks:

```python
from action_py import ExecutionStatus, PlanExecutor

if plan is None:
    raise RuntimeError("No plan found")

executor = PlanExecutor(plan, domain.worlds["initial"])

def start_chop_tree(context):
    # Start the real operation here: send a robot command, call a service,
    # schedule an animation, enqueue a job, etc.
    return ExecutionStatus.RUNNING

executor.on_start("chop_tree", start_chop_tree)

status = executor.tick()
```

You can also compile from a string:

```python
from action_py.dsl import compile_domain

domain = compile_domain(source_text)
```

## Complete Example

```goap
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
```

## File Structure

A DSL file is a sequence of top-level statements:

```goap
domain NAME

objects:
  TYPE: OBJECT, OBJECT

world NAME:
  FACT = VALUE

goal NAME:
  CONDITION

action NAME:
  precondition:
    CONDITION
  effect:
    FACT := VALUE
```

Blank lines and full-line comments are ignored:

```goap
# This is a comment.
```

Tabs are not allowed for indentation. Use spaces.

## Names And Values

Names such as domains, worlds, goals, actions, facts, object types, and
parameters use lowercase identifiers:

```text
build_house
has_wood
initial
```

Object values and symbolic values are bare words:

```goap
A
table
forest
none
```

Supported value literals:

```goap
true
false
none
42
3.5
"a string"
A
table
```

Value semantics:

- `true` compiles to Python `True`.
- `false` compiles to Python `False`.
- `none` compiles to Python `None`.
- Numbers compile to `int` or `float`.
- Quoted strings compile to Python strings.
- Bare symbols compile to strings, unless they are action parameters being
  grounded.

## Facts

A fact is a state slot. Facts can be plain:

```goap
has_wood
holding
```

or structured:

```goap
on(A)
clear(A)
at(agent)
```

The V1 runtime still stores facts as string keys. The default compiler encodes
structured facts like this:

```text
holding   -> "holding"
on(A)     -> "on_A"
clear(A)  -> "clear_A"
```

This is why the DSL can use readable structured facts while the existing
planner still sees normal `WorldState` keys.

## Domain Declaration

```goap
domain build_house
```

The `domain` statement names the compiled domain. It is optional, but
recommended.

Compilation result:

```python
compiled.name == "build_house"
```

If multiple `domain` statements are present, the last one wins.

## Objects

Objects define static sets used to ground parameterized actions.

```goap
objects:
  block: A, B, C
  location: home, forest
```

Compilation result:

```python
compiled.objects == {
    "block": ["A", "B", "C"],
    "location": ["home", "forest"],
}
```

Semantic rules:

- Object type names must be unique.
- Object values within one type must be unique.
- Parameterized actions can only reference declared object types.

## Worlds

A `world` block defines an initial or named world state.

```goap
world initial:
  at_home = true
  has_wood = false
  holding = none
  on(A) = table
```

World facts use `=` because the block constructs a `WorldState`.

Compilation result:

```python
WorldState({
    "at_home": True,
    "has_wood": False,
    "holding": None,
    "on_A": "table",
})
```

Semantic rules:

- World names must be unique.
- A world cannot assign the same compiled fact key more than once.
- `==` and `:=` are not valid in `world` blocks.

## Goals

A `goal` block defines a named desired condition.

```goap
goal build_a_house:
  has_house
```

Goals can have a priority:

```goap
goal build_a_house priority 10:
  has_house
```

Priority is compiled into `Goal.priority`. The current planner does not use it
for search by itself.

A bare fact condition means the fact must equal `true`:

```goap
goal build_a_house:
  has_house
```

is equivalent to:

```goap
goal build_a_house:
  has_house == true
```

Multiple condition lines are an implicit AND:

```goap
goal tower:
  on(A) == B
  on(B) == C
```

You can also write the AND explicitly:

```goap
goal tower:
  all:
    on(A) == B
    on(B) == C
```

Compilation result:

```python
Goal(
    name="tower",
    condition=ALL(EQ("on_A", "B"), EQ("on_B", "C")),
)
```

Semantic rules:

- Goal names must be unique.
- V1 supports equality conditions and `all:`.
- `any:` and `not` can be parsed, but compilation rejects them in V1.

## Actions

An `action` defines a planner operator.

```goap
action chop_tree cost 1:
  precondition:
    all:
      has_axe
      at_forest
  effect:
    has_wood := true
```

Compilation result:

```python
Action(
    name="chop_tree",
    cost=1.0,
    preconditions=ALL(EQ("has_axe", True), EQ("at_forest", True)),
    effects=SET("has_wood", True),
)
```

The `cost` clause is optional. If omitted, cost is `1.0`.

Every action must have:

- exactly one `precondition:` block
- exactly one `effect:` block

### Preconditions

Preconditions are tests that must be true before an action can run.

```goap
precondition:
  at_home
```

means:

```python
EQ("at_home", True)
```

Equality conditions use `==`:

```goap
precondition:
  holding == none
  on(A) == table
```

Multiple condition lines are implicit AND. `all:` is the explicit AND form:

```goap
precondition:
  all:
    holding == none
    clear(A)
```

### Effects

Effects describe the fact changes an action makes.

```goap
effect:
  has_wood := true
  at_home := false
```

Effects use `:=` because they represent state transition, not initial-state
construction or condition checking.

Compilation result:

```python
DO(SET("has_wood", True), SET("at_home", False))
```

Effects are applied in source order. If the same fact is assigned more than
once, the last assignment wins, matching `DO(SET(...), SET(...))` behavior.

The parser also accepts this form:

```goap
effect:
  set has_wood true
```

Prefer `fact := value` in new files.

## Parameterized Actions

Actions can declare parameters typed by object sets:

```goap
objects:
  block: A, B, C

action put_down(x: block):
  precondition:
    holding == x
  effect:
    holding := none
    on(x) := table
    clear(x) := true
```

The compiler grounds this template into one action per object:

```text
put_down(A)
put_down(B)
put_down(C)
```

Inside the action body, parameter references are replaced with the current
grounded object value.

For `put_down(A)`, this effect:

```goap
on(x) := table
```

compiles to:

```python
SET("on_A", "table")
```

Semantic rules:

- Parameter names must be unique within one action.
- Parameter types must exist in `objects:`.
- Grounded action names must be unique.

## Where Filters

`where` filters invalid parameter combinations during template grounding.
It is compile-time only. It is not a runtime precondition.

```goap
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
```

With:

```goap
objects:
  block: A, B, C
```

the compiler considers every `(x, y)` pair, then removes pairs where `x == y`.
The generated actions are:

```text
stack(A,B)
stack(A,C)
stack(B,A)
stack(B,C)
stack(C,A)
stack(C,B)
```

V1 supports:

```goap
where x != y:
where x == y:
where x != y and y != z:
```

The `where` line can also be written inline before the action colon:

```goap
action stack(x: block, y: block) where x != y:
  precondition:
    holding == x
  effect:
    on(x) := y
```

Semantic rules:

- `where` can only reference action parameters.
- V1 supports only `==`, `!=`, and `and`.
- Use `where` for static domain constraints.
- Use `precondition:` for facts that can change during planning.

## Blocksworld Example

```goap
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
```

This compiles to 18 grounded actions:

- 3 `pick_up(...)`
- 3 `put_down(...)`
- 6 `stack(...,...)`
- 6 `unstack(...,...)`

## Executing Plans

The DSL defines planning domains. Execution is handled by the Python runtime:
compile a domain, ask a planner for a `Plan`, then tick a `PlanExecutor`.

```python
from action_py import ExecutionStatus, PlanExecutor, Planner
from action_py.dsl import load_domain

domain = load_domain("build_house.goap")
initial = domain.worlds["initial"]
goal = domain.goals["build_a_house"]

plan = Planner(domain.actions).plan(initial, goal)
if plan is None:
    raise RuntimeError("No plan found")

executor = PlanExecutor(plan, initial)
```

`PlanExecutor` is a small BehaviorTree.CPP-style executor. It advances one
action at a time and returns one of:

```python
ExecutionStatus.SUCCESS
ExecutionStatus.RUNNING
ExecutionStatus.FAILED
```

`ExecutionStatus.FAILURE` and the string `"failure"` are accepted aliases for
`FAILED`.

### Start Callbacks

Register callbacks by compiled action name:

```python
def start_go_to_forest(context):
    print(f"starting {context.action.name}")
    return ExecutionStatus.SUCCESS

executor.on_start("go_to_forest", start_go_to_forest)
```

The callback is called when that action becomes active. The `context` contains:

```python
context.action   # Action being executed
context.index    # index in the plan
context.belief   # executor's current WorldState belief
```

If an action has no callback, the executor treats it as immediately successful.
On success, the action's declared DSL effects are applied to the executor
belief.

### Running Actions

Return `RUNNING` for actions that take more than one tick:

```python
def start_chop_tree(context):
    send_robot_command("chop_tree")
    return ExecutionStatus.RUNNING

executor.on_start("chop_tree", start_chop_tree)
```

While an action is running, repeated `tick()` calls keep returning `RUNNING`
unless an `on_running` callback is registered:

```python
def poll_chop_tree(context):
    if robot_command_done("chop_tree"):
        return context.success()
    return context.running()

executor.on_running("chop_tree", poll_chop_tree)
```

External code can also complete the active action:

```python
executor.complete_current(
    ExecutionStatus.SUCCESS,
    facts={"tree_sensor_confirmed": True},
)
```

### Belief Updates

The executor keeps its own `belief` as a `WorldState`. This is separate from
the original world object, because `WorldState` snapshots are immutable.

On successful action completion:

1. The action's declared effects are applied to `executor.belief`.
2. Observed facts returned by the callback are merged after the model effects.

This means real observations can override expected effects:

```python
def inspect_door(context):
    return context.success(facts={
        "door_open": False,
        "door_jammed": True,
    })

executor.on_start("inspect_door", inspect_door)
```

Callbacks can also update belief while running or failing:

```python
def open_door(context):
    return context.failed(facts={"door_blocked": True})
```

These observed facts are useful for future replanning: when execution fails,
you can pass `executor.belief` back to a planner as the new starting state.

You can manually merge observations at any time:

```python
executor.update_belief({"battery_low": True})
```

or replace the belief snapshot:

```python
executor.update_belief(belief=new_world_state)
```

### Callback Return Values

Callbacks may return:

```python
ExecutionStatus.SUCCESS
ExecutionStatus.RUNNING
ExecutionStatus.FAILED
"success"
"running"
"failed"
None
```

Returning `None` means `RUNNING`, which is useful for callbacks that only start
an asynchronous action.

For observed facts or a full belief replacement, return an `ActionResult` or
use the helper methods on `ExecutionContext`:

```python
return context.success(facts={"has_wood": True})
return context.running(facts={"saw_tree": True})
return context.failed(facts={"axe_broken": True})
```

A complete callback example:

```python
def start_buy_nails(context):
    if context.belief.get("shop_open") is not True:
        return context.failed(facts={"needs_shop_open": True})
    order_nails()
    return context.running()

def poll_buy_nails(context):
    if nails_arrived():
        return context.success(facts={"receipt_id": "N-123"})
    return context.running()

executor.on_start("buy_nails", start_buy_nails)
executor.on_running("buy_nails", poll_buy_nails)
```

A simple execution loop:

```python
while True:
    status = executor.tick()
    if status == ExecutionStatus.SUCCESS:
        break
    if status == ExecutionStatus.FAILED:
        # Future replanning can start from executor.belief.
        break
```

## Python API

### `parse_domain(source)`

Parses DSL text into a syntax tree.

```python
from action_py.dsl import parse_domain

program = parse_domain(source)
```

Use this when you want to inspect or transform the DSL before compilation.

### `compile_domain(source_or_program)`

Compiles DSL text or a parsed program into runtime objects.

```python
from action_py.dsl import compile_domain

domain = compile_domain(source)
```

The returned object has:

```python
domain.name       # str | None
domain.objects    # dict[str, list[str]]
domain.worlds     # dict[str, WorldState]
domain.goals      # dict[str, Goal]
domain.actions    # list[Action]
```

### `load_domain(path)`

Reads and compiles a domain file.

```python
from action_py.dsl import load_domain

domain = load_domain("blocksworld.goap")
```

### `PlanExecutor(plan, belief, callbacks=None)`

Executes a `Plan` returned by a planner.

```python
from action_py import PlanExecutor

executor = PlanExecutor(plan, initial_world)
```

Important attributes:

```python
executor.belief          # current WorldState belief
executor.index           # current action index
executor.current_action  # active or next Action, or None
executor.is_running      # True while an action is active
executor.is_done         # True when all actions completed
```

Important methods:

```python
executor.on_start(action_name, callback)
executor.on_running(action_name, callback)
executor.tick()
executor.complete_current(status, facts=None, belief=None)
executor.update_belief(facts)
executor.reset(belief=None)
```

`BTExecutor` and `BehaviorTreeExecutor` are aliases for `PlanExecutor`.

### `ExecutionStatus`

Executor result enum:

```python
ExecutionStatus.SUCCESS
ExecutionStatus.RUNNING
ExecutionStatus.FAILED
```

Each status has a lowercase string value: `"success"`, `"running"`, or
`"failed"`.

### `ActionResult(status, facts=None, belief=None, apply_effects=True)`

Detailed callback result.

Use `facts` for observed fact updates:

```python
return ActionResult(ExecutionStatus.SUCCESS, facts={"has_wood": True})
```

Use `belief` to replace the executor belief with a full `WorldState`.

When a result succeeds, `apply_effects=True` applies the action's declared DSL
effects before merging observed facts. Set it to `False` if the callback
already returns the complete observed state.

### Custom Fact Encoding

The default encoder maps `on(A)` to `"on_A"`. You can provide a custom encoder:

```python
from action_py.dsl import FactKeyEncoder, compile_domain

class DottedEncoder(FactKeyEncoder):
    def encode(self, ref, binding=None):
        binding = binding or {}
        args = [binding.get(arg, arg) for arg in ref.args]
        if not args:
            return ref.name
        return f"{ref.name}." + ".".join(args)

domain = compile_domain(source, encoder=DottedEncoder())
```

## Error Handling

The DSL exposes three error classes:

```python
from action_py.dsl import DSLError, DSLParseError, DSLSemanticError
```

`DSLParseError` means the text is not valid DSL syntax.

`DSLSemanticError` means the text parsed, but cannot compile to V1 runtime
objects. Examples:

- duplicate object type
- unknown parameter type
- unknown parameter in `where`
- duplicate world or goal
- unsupported `any:` or `not`

Both error types include line numbers when available.

## V1 Grammar Summary

```ebnf
program        : statement*
statement      : domain_decl
               | import_decl
               | objects_decl
               | world_decl
               | goal_decl
               | action_decl

domain_decl    : "domain" NAME
import_decl    : "import" dotted_name

objects_decl   : "objects" ":" INDENT object_decl+ DEDENT
object_decl    : NAME ":" SYMBOL ("," SYMBOL)*

world_decl     : "world" NAME ":" INDENT fact_assignment+ DEDENT
fact_assignment: fact_ref "=" value

goal_decl      : "goal" NAME ["priority" NUMBER] ":"
                 INDENT condition_stmt+ DEDENT

action_decl    : "action" NAME [params] ["cost" NUMBER] [where_clause] ":"
                 INDENT precondition_block effect_block DEDENT

params         : "(" param ("," param)* ")"
param          : NAME ":" NAME
where_clause   : "where" where_expr

precondition_block
               : "precondition" ":" INDENT condition_stmt+ DEDENT
effect_block   : "effect" ":" INDENT effect_stmt+ DEDENT

condition_stmt : condition
               | "all" ":" INDENT condition_stmt+ DEDENT
               | "any" ":" INDENT condition_stmt+ DEDENT

condition      : fact_ref
               | fact_ref "==" value
               | "not" condition

effect_stmt    : fact_ref ":=" value
               | "set" fact_ref value

where_expr     : NAME ("==" | "!=") NAME
               | where_expr "and" where_expr

fact_ref       : NAME ["(" NAME_OR_SYMBOL ("," NAME_OR_SYMBOL)* ")"]
value          : "true" | "false" | "none" | NUMBER | STRING | SYMBOL
```

## V1 Limitations

The V1 compiler intentionally keeps the language aligned with the current
backward planner.

Supported:

- equality conditions
- `all:` condition groups
- implicit AND from multiple condition lines
- static assignment effects
- parameter grounding from object declarations
- compile-time `where` filters using `==`, `!=`, and `and`

Parsed but rejected during compilation:

- `any:`
- `not`

Not supported in V1:

- OR/XOR planning semantics
- numeric comparisons
- arithmetic or computed expressions
- dynamic effects such as increment/decrement
- inline comments after statements
- tabs for indentation
- runtime `where` predicates
- object inheritance or tags
