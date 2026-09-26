"""Python Analysis tool — structured analysis over retrieved data.

Safety model: arbitrary code execution is *not* allowed. Code is parsed with
``ast`` and only a strict allow-list of node types is permitted:

* literals, arithmetic/comparison/boolean operators
* variable reads, attribute/index access, comprehensions
* builtins whitelist: ``len, sum, min, max, sorted, round, abs, list, dict,
  set, str, int, float, bool, any, all, enumerate, zip``
* ``import``, ``eval``, ``exec``, attribute writes, calls to unknown names are
  all rejected.

Data is injected as the ``data`` binding. The tool returns the value of the
final expression.
"""
from __future__ import annotations

import ast
import builtins
from typing import Any

from app.auth.rbac import TOOL_PYTHON_ANALYSIS
from app.tools.base import BaseTool

_ALLOWED_BUILTINS = {
    "len", "sum", "min", "max", "sorted", "round", "abs",
    "list", "dict", "set", "tuple", "str", "int", "float", "bool",
    "any", "all", "enumerate", "zip", "range",
}

_ALLOWED_AST_NODES = {
    ast.Expression, ast.Constant, ast.Name, ast.Load, ast.Store, ast.BinOp,
    ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Attribute, ast.Subscript,
    ast.List, ast.Tuple, ast.Set, ast.Dict, ast.ListComp, ast.SetComp,
    ast.DictComp, ast.GeneratorExp, ast.comprehension, ast.Call, ast.IfExp,
    ast.Slice, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.Pow, ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.keyword, ast.arguments, ast.Lambda, ast.JoinedStr, ast.FormattedValue,
}


class UnsafeCodeError(ValueError):
    pass


def _validate_ast(node: ast.AST) -> None:
    if type(node) not in _ALLOWED_AST_NODES:
        raise UnsafeCodeError(f"Forbidden syntax: {type(node).__name__}")
    # Block dunder access everywhere (e.g. __class__, __globals__, __builtins__).
    if isinstance(node, ast.Name) and node.id.startswith("__"):
        raise UnsafeCodeError("Forbidden dunder name")
    if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
        raise UnsafeCodeError("Forbidden dunder attribute access")
    # Calls may only target whitelisted builtins (or the injected ``data``).
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Name)
            and func.id not in _ALLOWED_BUILTINS
            and func.id != "data"
        ):
            raise UnsafeCodeError(f"Forbidden call: {func.id}")
    for child in ast.iter_child_nodes(node):
        _validate_ast(child)


class PythonAnalysisTool(BaseTool):
    name = TOOL_PYTHON_ANALYSIS
    description = "Run a restricted, read-only Python expression over data."

    async def execute(self, params: dict[str, Any]) -> Any:
        code = params.get("code", "")
        data = params.get("data", {})
        if not code.strip():
            return {"error": "Empty code expression"}

        tree = ast.parse(code, mode="eval")
        _validate_ast(tree)

        namespace: dict[str, Any] = {"data": data, "__builtins__": {}}
        for name in _ALLOWED_BUILTINS:
            namespace[name] = getattr(builtins, name)
        result = eval(compile(tree, "<analysis>", "eval"), namespace)  # noqa: S307
        return {"result": result}
