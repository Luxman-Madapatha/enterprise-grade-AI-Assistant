"""Tests for the restricted Python analysis tool."""
from __future__ import annotations

import pytest

from app.auth.rbac import TOOL_PYTHON_ANALYSIS
from app.models.schemas import Role
from app.tools.python_analysis import PythonAnalysisTool, UnsafeCodeError


async def test_safe_expression():
    tool = PythonAnalysisTool()
    result = await tool.run(Role.ANALYST, {"code": "sum(data['items'])", "data": {"items": [1, 2, 3]}})
    assert result.success
    assert result.output["result"] == 6


async def test_import_rejected():
    tool = PythonAnalysisTool()
    result = await tool.run(Role.ANALYST, {"code": "__import__('os').system('id')"})
    assert not result.success


async def test_viewer_denied():
    tool = PythonAnalysisTool()
    result = await tool.run(Role.VIEWER, {"code": "len(data)"})
    assert result.denied
