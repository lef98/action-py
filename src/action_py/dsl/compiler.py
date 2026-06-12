from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path

from action_py.core.conditions import ALL, EQ, Condition
from action_py.core.effects import DO, SET, Effect
from action_py.core.models import Action, Goal
from action_py.core.world import WorldState
from action_py.dsl import ast as dsl_ast
from action_py.dsl.errors import DSLSemanticError
from action_py.dsl.parser import parse_domain


@dataclass(frozen=True)
class CompiledDomain:
    name: str | None
    objects: dict[str, list[str]]
    worlds: dict[str, WorldState]
    goals: dict[str, Goal]
    actions: list[Action]


class FactKeyEncoder:
    """Encode structured DSL fact references into current string fact keys."""

    def encode(self, ref: dsl_ast.FactRef, binding: dict[str, str] | None = None) -> str:
        binding = binding or {}
        if not ref.args:
            return ref.name
        args = [binding.get(arg, arg) for arg in ref.args]
        return "_".join([ref.name, *args])


@dataclass
class _CompileContext:
    objects: dict[str, list[str]]
    encoder: FactKeyEncoder


def compile_domain(
    source_or_program: str | dsl_ast.Program,
    *,
    encoder: FactKeyEncoder | None = None,
) -> CompiledDomain:
    """Compile DSL source or a parsed program into runtime planning objects."""
    program = parse_domain(source_or_program) if isinstance(source_or_program, str) else source_or_program
    encoder = encoder or FactKeyEncoder()
    objects = _compile_objects(program.objects)
    context = _CompileContext(objects=objects, encoder=encoder)

    worlds = _compile_worlds(program.worlds, context)
    goals = _compile_goals(program.goals, context)
    actions = _compile_actions(program.actions, context)

    return CompiledDomain(
        name=program.domain_name,
        objects=objects,
        worlds=worlds,
        goals=goals,
        actions=actions,
    )


def load_domain(path: str | Path, *, encoder: FactKeyEncoder | None = None) -> CompiledDomain:
    """Load and compile a DSL domain file."""
    source = Path(path).read_text(encoding="utf-8")
    return compile_domain(source, encoder=encoder)


def _compile_objects(decls: tuple[dsl_ast.ObjectDecl, ...]) -> dict[str, list[str]]:
    objects: dict[str, list[str]] = {}
    for decl in decls:
        if decl.type_name in objects:
            raise DSLSemanticError(f"duplicate object type {decl.type_name!r}", decl.line)
        seen: set[str] = set()
        for value in decl.values:
            if value in seen:
                raise DSLSemanticError(
                    f"duplicate object value {value!r} in type {decl.type_name!r}",
                    decl.line,
                )
            seen.add(value)
        objects[decl.type_name] = list(decl.values)
    return objects


def _compile_worlds(
    decls: tuple[dsl_ast.WorldDecl, ...],
    context: _CompileContext,
) -> dict[str, WorldState]:
    worlds: dict[str, WorldState] = {}
    for decl in decls:
        if decl.name in worlds:
            raise DSLSemanticError(f"duplicate world {decl.name!r}", decl.line)
        facts: dict[str, object] = {}
        for assignment in decl.facts:
            key = context.encoder.encode(assignment.fact)
            if key in facts:
                raise DSLSemanticError(f"duplicate fact {key!r} in world {decl.name!r}", assignment.line)
            facts[key] = _compile_value(assignment.value, {})
        worlds[decl.name] = WorldState(facts)
    return worlds


def _compile_goals(
    decls: tuple[dsl_ast.GoalDecl, ...],
    context: _CompileContext,
) -> dict[str, Goal]:
    goals: dict[str, Goal] = {}
    for decl in decls:
        if decl.name in goals:
            raise DSLSemanticError(f"duplicate goal {decl.name!r}", decl.line)
        goals[decl.name] = Goal(
            name=decl.name,
            priority=decl.priority,
            condition=_compile_condition_list(decl.conditions, context, {}),
        )
    return goals


def _compile_actions(
    decls: tuple[dsl_ast.ActionDecl, ...],
    context: _CompileContext,
) -> list[Action]:
    actions: list[Action] = []
    action_names: set[str] = set()
    for decl in decls:
        _validate_action_decl(decl, context)
        for binding in _ground_bindings(decl, context):
            action_name = _ground_action_name(decl, binding)
            if action_name in action_names:
                raise DSLSemanticError(f"duplicate action {action_name!r}", decl.line)
            action_names.add(action_name)
            actions.append(
                Action(
                    name=action_name,
                    cost=decl.cost,
                    preconditions=_compile_condition_list(decl.preconditions, context, binding),
                    effects=_compile_effect_list(decl.effects, context, binding),
                )
            )
    return actions


def _validate_action_decl(decl: dsl_ast.ActionDecl, context: _CompileContext) -> None:
    param_names: set[str] = set()
    for param in decl.params:
        if param.name in param_names:
            raise DSLSemanticError(f"duplicate parameter {param.name!r}", param.line)
        param_names.add(param.name)
        if param.type_name not in context.objects:
            raise DSLSemanticError(f"unknown object type {param.type_name!r}", param.line)
    if decl.where is not None:
        for comparison in decl.where.comparisons:
            if comparison.left not in param_names:
                raise DSLSemanticError(f"unknown where parameter {comparison.left!r}", comparison.line)
            if comparison.right not in param_names:
                raise DSLSemanticError(f"unknown where parameter {comparison.right!r}", comparison.line)


def _ground_bindings(
    decl: dsl_ast.ActionDecl,
    context: _CompileContext,
) -> list[dict[str, str]]:
    if not decl.params:
        return [{}]

    names = [param.name for param in decl.params]
    value_sets = [context.objects[param.type_name] for param in decl.params]
    bindings: list[dict[str, str]] = []
    for values in product(*value_sets):
        binding = dict(zip(names, values))
        if decl.where is None or _where_matches(decl.where, binding):
            bindings.append(binding)
    return bindings


def _where_matches(where: dsl_ast.WhereNode, binding: dict[str, str]) -> bool:
    for comparison in where.comparisons:
        left = binding[comparison.left]
        right = binding[comparison.right]
        if comparison.op == "==" and left != right:
            return False
        if comparison.op == "!=" and left == right:
            return False
    return True


def _ground_action_name(decl: dsl_ast.ActionDecl, binding: dict[str, str]) -> str:
    if not decl.params:
        return decl.name
    args = ",".join(binding[param.name] for param in decl.params)
    return f"{decl.name}({args})"


def _compile_condition_list(
    nodes: tuple[dsl_ast.ConditionNode, ...],
    context: _CompileContext,
    binding: dict[str, str],
) -> Condition:
    if not nodes:
        raise DSLSemanticError("condition block cannot be empty")
    conditions = [_compile_condition(node, context, binding) for node in nodes]
    return ALL(*conditions)


def _compile_condition(
    node: dsl_ast.ConditionNode,
    context: _CompileContext,
    binding: dict[str, str],
) -> Condition:
    if node.kind == "eq":
        if node.fact is None or node.value is None:
            raise DSLSemanticError("invalid equality condition", node.line)
        return EQ(context.encoder.encode(node.fact, binding), _compile_value(node.value, binding))
    if node.kind == "all":
        return _compile_condition_list(node.children, context, binding)
    if node.kind == "any":
        raise DSLSemanticError("'any:' conditions are not supported in DSL V1", node.line)
    if node.kind == "not":
        raise DSLSemanticError("'not' conditions are not supported in DSL V1", node.line)
    raise DSLSemanticError(f"unsupported condition kind {node.kind!r}", node.line)


def _compile_effect_list(
    nodes: tuple[dsl_ast.EffectNode, ...],
    context: _CompileContext,
    binding: dict[str, str],
) -> Effect:
    if not nodes:
        raise DSLSemanticError("effect block cannot be empty")
    effects = [_compile_effect(node, context, binding) for node in nodes]
    return DO(*effects)


def _compile_effect(
    node: dsl_ast.EffectNode,
    context: _CompileContext,
    binding: dict[str, str],
) -> Effect:
    if node.kind != "assign":
        raise DSLSemanticError(f"unsupported effect kind {node.kind!r}", node.line)
    return SET(context.encoder.encode(node.fact, binding), _compile_value(node.value, binding))


def _compile_value(node: dsl_ast.ValueNode, binding: dict[str, str]) -> object:
    if node.kind == "symbol" and isinstance(node.value, str):
        return binding.get(node.value, node.value)
    return node.value

