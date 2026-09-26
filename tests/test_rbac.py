"""Tests for role based access control."""
from __future__ import annotations

import pytest

from app.auth.rbac import assert_tool_allowed, is_tool_allowed
from app.auth.rbac import TOOL_KNOWLEDGE_SEARCH, TOOL_MCP_EMPLOYEE, TOOL_PYTHON_ANALYSIS, TOOL_ADMIN_REINDEX
from app.models.schemas import Role


def test_viewer_permissions():
    assert is_tool_allowed(Role.VIEWER, TOOL_KNOWLEDGE_SEARCH)
    assert not is_tool_allowed(Role.VIEWER, TOOL_MCP_EMPLOYEE)
    assert not is_tool_allowed(Role.VIEWER, TOOL_PYTHON_ANALYSIS)
    assert not is_tool_allowed(Role.VIEWER, TOOL_ADMIN_REINDEX)


def test_analyst_permissions():
    assert is_tool_allowed(Role.ANALYST, TOOL_MCP_EMPLOYEE)
    assert is_tool_allowed(Role.ANALYST, TOOL_PYTHON_ANALYSIS)
    assert not is_tool_allowed(Role.ANALYST, TOOL_ADMIN_REINDEX)


def test_admin_permissions():
    assert is_tool_allowed(Role.ADMINISTRATOR, TOOL_ADMIN_REINDEX)


def test_assert_raises_for_unauthorized():
    with pytest.raises(PermissionError):
        assert_tool_allowed(Role.VIEWER, TOOL_PYTHON_ANALYSIS)
