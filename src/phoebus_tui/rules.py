"""Evaluation of Phoebus rule expressions (JavaScript-like boolean/arithmetic expressions)."""

from __future__ import annotations

import ast
import operator
import re
from functools import lru_cache
from typing import Any

from .formatting import as_number, format_value
from .pv import PVState


class RuleError(ValueError):
    pass


_TOKEN_RE = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|===|!==|&&|\|\||!=|==|!|[^\"'&|!=]+|.", re.S)
_LITERALS = {"true": "True", "false": "False", "null": "None"}
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}
_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


@lru_cache(maxsize=512)
def _parse(expression: str) -> ast.expr:
    parts = []
    for token in _TOKEN_RE.findall(expression):
        if token == "&&":
            parts.append(" and ")
        elif token == "||":
            parts.append(" or ")
        elif token in ("===", "!=="):
            parts.append(token[:2])
        elif token == "!":
            parts.append(" not ")
        elif token[0] in "\"'":
            parts.append(token)
        else:
            parts.append(re.sub(r"\b(true|false|null)\b", lambda m: _LITERALS[m.group(1)], token))
    try:
        return ast.parse("".join(parts).strip(), mode="eval").body
    except (SyntaxError, ValueError, RecursionError, MemoryError) as e:
        raise RuleError(f"Cannot parse rule expression {expression!r}") from e


def _eval(node: ast.expr, variables: dict[str, Any]) -> Any:
    match node:
        case ast.Constant(value=value) if value is None or isinstance(value, (int, float, str, bool)):
            return value
        case ast.Name(id=name):
            if name not in variables:
                raise RuleError(f"Unknown variable {name!r}")
            return variables[name]
        case ast.BoolOp(op=ast.And(), values=values):
            result: Any = True
            for value in values:
                result = _eval(value, variables)
                if not result:
                    break
            return result
        case ast.BoolOp(op=ast.Or(), values=values):
            result = False
            for value in values:
                result = _eval(value, variables)
                if result:
                    break
            return result
        case ast.UnaryOp(op=ast.Not(), operand=operand):
            return not _eval(operand, variables)
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return -_eval(operand, variables)
        case ast.UnaryOp(op=ast.UAdd(), operand=operand):
            return +_eval(operand, variables)
        case ast.BinOp(left=left, op=op, right=right) if type(op) in _BIN_OPS:
            return _BIN_OPS[type(op)](_eval(left, variables), _eval(right, variables))
        case ast.Compare(left=left, ops=ops, comparators=comparators):
            current = _eval(left, variables)
            for op, comparator in zip(ops, comparators):
                if type(op) not in _CMP_OPS:
                    break
                right = _eval(comparator, variables)
                if not _CMP_OPS[type(op)](current, right):
                    return False
                current = right
            else:
                return True
    raise RuleError(f"Unsupported rule expression: {ast.dump(node)[:80]}")


def evaluate(expression: str, variables: dict[str, Any]) -> Any:
    """Evaluate a Phoebus rule expression without using `eval`."""
    try:
        return _eval(_parse(expression), variables)
    except RuleError:
        raise
    except (TypeError, ZeroDivisionError, ArithmeticError, RecursionError) as e:
        raise RuleError(f"Cannot evaluate {expression!r}: {e}") from e


def rule_variables(states: list[PVState]) -> dict[str, Any]:
    """The pvN/pvStrN/pvIntN/pvSevN variables Phoebus provides to rule expressions."""
    variables: dict[str, Any] = {}
    for i, state in enumerate(states):
        number = as_number(state.value)
        text = format_value(state, show_units=False)
        variables[f"pv{i}"] = number if number is not None else text
        variables[f"pvStr{i}"] = text
        variables[f"pvInt{i}"] = int(number) if number is not None and number == number else 0
        variables[f"pvSev{i}"] = state.severity if state.connected else -1
    return variables
