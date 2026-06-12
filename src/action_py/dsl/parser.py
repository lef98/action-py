from __future__ import annotations

import ast as py_ast
import re
from dataclasses import dataclass

from action_py.dsl.ast import (
    ActionDecl,
    ConditionNode,
    EffectNode,
    FactAssignment,
    FactRef,
    GoalDecl,
    ObjectDecl,
    Param,
    Program,
    ValueNode,
    WhereComparison,
    WhereNode,
    WorldDecl,
)
from action_py.dsl.errors import DSLParseError


_NAME = r"[a-z_][a-zA-Z0-9_]*"
_SYMBOL = r"[A-Za-z_][a-zA-Z0-9_]*"
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+\.\d+|\d+)$")
_ACTION_RE = re.compile(
    rf"^(?P<name>{_NAME})(?P<params>\([^)]*\))?"
    rf"(?:\s+cost\s+(?P<cost>[+-]?(?:\d+\.\d+|\d+)))?"
    rf"(?:\s+where\s+(?P<where>.+))?$"
)
_FACT_RE = re.compile(rf"^(?P<name>{_NAME})(?:\((?P<args>[^)]*)\))?$")


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    text: str


def parse_domain(source: str) -> Program:
    """Parse DSL source into a syntax tree."""
    return _Parser(source).parse()


class _Parser:
    def __init__(self, source: str) -> None:
        self.lines = self._lex(source)
        self.index = 0

    def parse(self) -> Program:
        domain_name: str | None = None
        imports: list[str] = []
        objects: list[ObjectDecl] = []
        worlds: list[WorldDecl] = []
        goals: list[GoalDecl] = []
        actions: list[ActionDecl] = []

        while not self._eof:
            line = self._peek()
            if line.indent != 0:
                raise DSLParseError("top-level statements must not be indented", line.number)

            if line.text.startswith("domain "):
                domain_name = self._parse_domain_decl(line)
            elif line.text.startswith("import "):
                imports.append(self._parse_import(line))
            elif line.text == "objects:":
                objects.extend(self._parse_objects(line))
            elif line.text.startswith("world "):
                worlds.append(self._parse_world(line))
            elif line.text.startswith("goal "):
                goals.append(self._parse_goal(line))
            elif line.text.startswith("action "):
                actions.append(self._parse_action(line))
            else:
                raise DSLParseError(f"unknown statement {line.text!r}", line.number)

        return Program(
            domain_name=domain_name,
            imports=tuple(imports),
            objects=tuple(objects),
            worlds=tuple(worlds),
            goals=tuple(goals),
            actions=tuple(actions),
        )

    @staticmethod
    def _lex(source: str) -> list[_Line]:
        result: list[_Line] = []
        for number, raw in enumerate(source.splitlines(), 1):
            if "\t" in raw:
                raise DSLParseError("tabs are not allowed for indentation", number)
            text = raw.strip()
            if not text or text.startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            result.append(_Line(number=number, indent=indent, text=text))
        return result

    @property
    def _eof(self) -> bool:
        return self.index >= len(self.lines)

    def _peek(self) -> _Line:
        if self._eof:
            raise DSLParseError("unexpected end of file")
        return self.lines[self.index]

    def _advance(self) -> _Line:
        line = self._peek()
        self.index += 1
        return line

    def _parse_domain_decl(self, line: _Line) -> str:
        self._advance()
        name = line.text.removeprefix("domain ").strip()
        if not re.fullmatch(_NAME, name):
            raise DSLParseError("invalid domain name", line.number)
        return name

    def _parse_import(self, line: _Line) -> str:
        self._advance()
        dotted_name = line.text.removeprefix("import ").strip()
        if not re.fullmatch(rf"{_NAME}(?:\.{_NAME})*", dotted_name):
            raise DSLParseError("invalid import name", line.number)
        return dotted_name

    def _parse_objects(self, line: _Line) -> list[ObjectDecl]:
        self._advance()
        indent = self._require_child_indent(line)
        objects: list[ObjectDecl] = []
        while not self._eof and self._peek().indent >= indent:
            current = self._peek()
            if current.indent != indent:
                raise DSLParseError("unexpected indentation in objects block", current.number)
            self._advance()
            if ":" not in current.text:
                raise DSLParseError("object declaration must use ':'", current.number)
            type_name, values_text = (part.strip() for part in current.text.split(":", 1))
            if not re.fullmatch(_NAME, type_name):
                raise DSLParseError("invalid object type name", current.number)
            values = tuple(v.strip() for v in values_text.split(",") if v.strip())
            if not values:
                raise DSLParseError("object declaration must include at least one value", current.number)
            for value in values:
                if not re.fullmatch(_SYMBOL, value):
                    raise DSLParseError(f"invalid object value {value!r}", current.number)
            objects.append(ObjectDecl(type_name=type_name, values=values, line=current.number))
        return objects

    def _parse_world(self, line: _Line) -> WorldDecl:
        self._advance()
        match = re.fullmatch(rf"world\s+({_NAME}):", line.text)
        if not match:
            raise DSLParseError("world declaration must be 'world NAME:'", line.number)
        facts: list[FactAssignment] = []
        indent = self._require_child_indent(line)
        while not self._eof and self._peek().indent >= indent:
            current = self._peek()
            if current.indent != indent:
                raise DSLParseError("unexpected indentation in world block", current.number)
            self._advance()
            facts.append(self._parse_fact_assignment(current))
        return WorldDecl(name=match.group(1), facts=tuple(facts), line=line.number)

    def _parse_goal(self, line: _Line) -> GoalDecl:
        self._advance()
        match = re.fullmatch(
            rf"goal\s+({_NAME})(?:\s+priority\s+([+-]?(?:\d+\.\d+|\d+)))?:",
            line.text,
        )
        if not match:
            raise DSLParseError("goal declaration must be 'goal NAME [priority NUMBER]:'", line.number)
        priority = float(match.group(2)) if match.group(2) else 1.0
        conditions = self._parse_condition_block(line)
        return GoalDecl(
            name=match.group(1),
            priority=priority,
            conditions=tuple(conditions),
            line=line.number,
        )

    def _parse_action(self, line: _Line) -> ActionDecl:
        self._advance()
        header_text = line.text.removeprefix("action ").strip()
        where: WhereNode | None = None
        colon_line = line

        if header_text.endswith(":"):
            header_text = header_text[:-1].strip()
        else:
            if self._eof:
                raise DSLParseError("action declaration is missing ':'", line.number)
            where_line = self._advance()
            if where_line.indent != line.indent:
                raise DSLParseError("where clause must align with action declaration", where_line.number)
            if not where_line.text.startswith("where ") or not where_line.text.endswith(":"):
                raise DSLParseError("expected 'where EXPR:' after action header", where_line.number)
            where = self._parse_where(where_line.text[6:-1].strip(), where_line.number)
            colon_line = where_line

        name, params, cost, inline_where = self._parse_action_header(header_text, line.number)
        if inline_where is not None:
            if where is not None:
                raise DSLParseError("action has multiple where clauses", line.number)
            where = self._parse_where(inline_where, line.number)

        body_indent = self._require_child_indent(colon_line)
        preconditions: list[ConditionNode] | None = None
        effects: list[EffectNode] | None = None

        while not self._eof and self._peek().indent >= body_indent:
            current = self._peek()
            if current.indent != body_indent:
                raise DSLParseError("unexpected indentation in action body", current.number)
            self._advance()
            if current.text == "precondition:":
                if preconditions is not None:
                    raise DSLParseError("duplicate precondition block", current.number)
                preconditions = self._parse_condition_block(current)
            elif current.text == "effect:":
                if effects is not None:
                    raise DSLParseError("duplicate effect block", current.number)
                effects = self._parse_effect_block(current)
            else:
                raise DSLParseError("action body must contain precondition: or effect:", current.number)

        if preconditions is None:
            raise DSLParseError("action is missing precondition block", line.number)
        if effects is None:
            raise DSLParseError("action is missing effect block", line.number)

        return ActionDecl(
            name=name,
            params=tuple(params),
            preconditions=tuple(preconditions),
            effects=tuple(effects),
            cost=cost,
            where=where,
            line=line.number,
        )

    def _parse_action_header(
        self,
        text: str,
        line_number: int,
    ) -> tuple[str, list[Param], float, str | None]:
        match = _ACTION_RE.fullmatch(text)
        if not match:
            raise DSLParseError("invalid action declaration", line_number)
        params = self._parse_params(match.group("params"), line_number)
        cost = float(match.group("cost")) if match.group("cost") else 1.0
        return match.group("name"), params, cost, match.group("where")

    def _parse_params(self, params_text: str | None, line_number: int) -> list[Param]:
        if not params_text:
            return []
        inner = params_text[1:-1].strip()
        if not inner:
            return []
        params: list[Param] = []
        for raw_param in inner.split(","):
            if ":" not in raw_param:
                raise DSLParseError("parameter must be 'name: type'", line_number)
            name, type_name = (part.strip() for part in raw_param.split(":", 1))
            if not re.fullmatch(_NAME, name):
                raise DSLParseError("invalid parameter name", line_number)
            if not re.fullmatch(_NAME, type_name):
                raise DSLParseError("invalid parameter type", line_number)
            params.append(Param(name=name, type_name=type_name, line=line_number))
        return params

    def _parse_condition_block(self, parent: _Line) -> list[ConditionNode]:
        indent = self._require_child_indent(parent)
        conditions: list[ConditionNode] = []
        while not self._eof and self._peek().indent >= indent:
            current = self._peek()
            if current.indent != indent:
                raise DSLParseError("unexpected indentation in condition block", current.number)
            conditions.append(self._parse_condition_stmt(indent))
        return conditions

    def _parse_condition_stmt(self, indent: int) -> ConditionNode:
        line = self._advance()
        if line.text == "all:":
            children = self._parse_condition_block(line)
            return ConditionNode(kind="all", children=tuple(children), line=line.number)
        if line.text == "any:":
            children = self._parse_condition_block(line)
            return ConditionNode(kind="any", children=tuple(children), line=line.number)
        return self._parse_condition_expr(line.text, line.number)

    def _parse_condition_expr(self, text: str, line_number: int) -> ConditionNode:
        if text.startswith("not "):
            child = self._parse_condition_expr(text[4:].strip(), line_number)
            return ConditionNode(kind="not", children=(child,), line=line_number)
        if "==" in text:
            fact_text, value_text = (part.strip() for part in text.split("==", 1))
            return ConditionNode(
                kind="eq",
                fact=self._parse_fact_ref(fact_text, line_number),
                value=self._parse_value(value_text, line_number),
                line=line_number,
            )
        return ConditionNode(
            kind="eq",
            fact=self._parse_fact_ref(text, line_number),
            value=ValueNode(kind="bool", value=True, line=line_number),
            line=line_number,
        )

    def _parse_effect_block(self, parent: _Line) -> list[EffectNode]:
        indent = self._require_child_indent(parent)
        effects: list[EffectNode] = []
        while not self._eof and self._peek().indent >= indent:
            current = self._peek()
            if current.indent != indent:
                raise DSLParseError("unexpected indentation in effect block", current.number)
            self._advance()
            effects.append(self._parse_effect(current))
        return effects

    def _parse_effect(self, line: _Line) -> EffectNode:
        text = line.text
        if text.startswith("set "):
            parts = text.split(None, 2)
            if len(parts) != 3:
                raise DSLParseError("set effect must be 'set FACT VALUE'", line.number)
            fact_text, value_text = parts[1], parts[2]
        elif ":=" in text:
            fact_text, value_text = (part.strip() for part in text.split(":=", 1))
        else:
            raise DSLParseError("effect must assign with ':='", line.number)
        return EffectNode(
            kind="assign",
            fact=self._parse_fact_ref(fact_text, line.number),
            value=self._parse_value(value_text, line.number),
            line=line.number,
        )

    def _parse_fact_assignment(self, line: _Line) -> FactAssignment:
        if "=" not in line.text or "==" in line.text or ":=" in line.text:
            raise DSLParseError("world fact must assign with '='", line.number)
        fact_text, value_text = (part.strip() for part in line.text.split("=", 1))
        return FactAssignment(
            fact=self._parse_fact_ref(fact_text, line.number),
            value=self._parse_value(value_text, line.number),
            line=line.number,
        )

    def _parse_fact_ref(self, text: str, line_number: int) -> FactRef:
        match = _FACT_RE.fullmatch(text.strip())
        if not match:
            raise DSLParseError(f"invalid fact reference {text!r}", line_number)
        args_text = match.group("args")
        args: tuple[str, ...] = ()
        if args_text is not None:
            args = tuple(arg.strip() for arg in args_text.split(",") if arg.strip())
            if any(not re.fullmatch(_SYMBOL, arg) for arg in args):
                raise DSLParseError(f"invalid fact arguments in {text!r}", line_number)
        return FactRef(name=match.group("name"), args=args, line=line_number)

    def _parse_value(self, text: str, line_number: int) -> ValueNode:
        text = text.strip()
        if text == "":
            raise DSLParseError("missing value", line_number)
        if text == "true":
            return ValueNode(kind="bool", value=True, line=line_number)
        if text == "false":
            return ValueNode(kind="bool", value=False, line=line_number)
        if text == "none":
            return ValueNode(kind="none", value=None, line=line_number)
        if _NUMBER_RE.fullmatch(text):
            value: int | float = float(text) if "." in text else int(text)
            return ValueNode(kind="number", value=value, line=line_number)
        if text.startswith(('"', "'")):
            try:
                value = py_ast.literal_eval(text)
            except (SyntaxError, ValueError) as exc:
                raise DSLParseError("invalid string literal", line_number) from exc
            if not isinstance(value, str):
                raise DSLParseError("only string literals are supported here", line_number)
            return ValueNode(kind="string", value=value, line=line_number)
        if re.fullmatch(_SYMBOL, text):
            return ValueNode(kind="symbol", value=text, line=line_number)
        raise DSLParseError(f"invalid value {text!r}", line_number)

    def _parse_where(self, text: str, line_number: int) -> WhereNode:
        comparisons: list[WhereComparison] = []
        for raw in re.split(r"\s+and\s+", text):
            match = re.fullmatch(rf"({_NAME})\s*(==|!=)\s*({_NAME})", raw.strip())
            if not match:
                raise DSLParseError("where only supports NAME == NAME and NAME != NAME", line_number)
            comparisons.append(
                WhereComparison(
                    left=match.group(1),
                    op=match.group(2),
                    right=match.group(3),
                    line=line_number,
                )
            )
        return WhereNode(comparisons=tuple(comparisons), line=line_number)

    def _require_child_indent(self, parent: _Line) -> int:
        if self._eof:
            raise DSLParseError("expected indented block", parent.number)
        indent = self._peek().indent
        if indent <= parent.indent:
            raise DSLParseError("expected indented block", parent.number)
        return indent

