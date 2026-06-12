from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValueNode:
    kind: str
    value: object
    line: int


@dataclass(frozen=True)
class FactRef:
    name: str
    args: tuple[str, ...] = ()
    line: int = 0


@dataclass(frozen=True)
class FactAssignment:
    fact: FactRef
    value: ValueNode
    line: int


@dataclass(frozen=True)
class ConditionNode:
    kind: str
    fact: FactRef | None = None
    value: ValueNode | None = None
    children: tuple["ConditionNode", ...] = ()
    line: int = 0


@dataclass(frozen=True)
class EffectNode:
    kind: str
    fact: FactRef
    value: ValueNode
    line: int


@dataclass(frozen=True)
class WhereComparison:
    left: str
    op: str
    right: str
    line: int


@dataclass(frozen=True)
class WhereNode:
    comparisons: tuple[WhereComparison, ...]
    line: int


@dataclass(frozen=True)
class Param:
    name: str
    type_name: str
    line: int


@dataclass(frozen=True)
class ObjectDecl:
    type_name: str
    values: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class WorldDecl:
    name: str
    facts: tuple[FactAssignment, ...]
    line: int


@dataclass(frozen=True)
class GoalDecl:
    name: str
    conditions: tuple[ConditionNode, ...]
    priority: float = 1.0
    line: int = 0


@dataclass(frozen=True)
class ActionDecl:
    name: str
    params: tuple[Param, ...]
    preconditions: tuple[ConditionNode, ...]
    effects: tuple[EffectNode, ...]
    cost: float = 1.0
    where: WhereNode | None = None
    line: int = 0


@dataclass(frozen=True)
class Program:
    domain_name: str | None = None
    imports: tuple[str, ...] = ()
    objects: tuple[ObjectDecl, ...] = ()
    worlds: tuple[WorldDecl, ...] = ()
    goals: tuple[GoalDecl, ...] = ()
    actions: tuple[ActionDecl, ...] = ()
    line: int = 0
