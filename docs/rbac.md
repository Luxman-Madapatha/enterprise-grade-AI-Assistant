# Role-Based Access Control (RBAC)

This repository implements a lightweight, explicit RBAC model for user access and tool execution. The design is intentionally simple and self-contained for a demo application, but the enforcement points are placed in the critical execution path so the agent cannot bypass authorization through prompt logic or tool selection.

## Roles and identities

The canonical roles are defined in `app/models/schemas.py`:

- `viewer`
- `analyst`
- `administrator`

The `Role` enum is a strict `str, Enum`, and each authenticated user is represented by a `User` model that contains:

- `username`
- `full_name`
- `role`

The user table is defined in `app/auth/users.py`:

```python
_USER_TABLE: dict[str, tuple[str, str, Role]] = {
    "viewer": ("viewer123", "Viewer User", Role.VIEWER),
    "analyst": ("analyst123", "Analyst User", Role.ANALYST),
    "admin": ("admin123", "Administrator", Role.ADMINISTRATOR),
}
```

This is a hardcoded identity store for the PoC. `authenticate()` checks both the username and password, while `get_user()` resolves a user by username.

## Authentication flow

User authentication happens in `app/main.py` via the `/api/auth/login` endpoint:

```python
@app.post("/api/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    user = authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return LoginResponse(access_token=issue_token(user), user=user)
```

The access token is generated in `app/auth/tokens.py` using HMAC signing and includes the user identity and role inside the token payload:

```python
body = {
    "sub": user.username,
    "role": user.role.value,
    "name": user.full_name,
    "iat": now,
    "exp": now + settings.token_expiry_minutes * 60,
}
```

`verify_token()` later reconstructs a `User` object from the signed payload and validates the expiration timestamp. The server therefore does not keep a server-side session; the role is carried in the bearer token itself.

## Request-level authorization

Every protected API call depends on `get_current_user()` in `app/main.py`:

```python
async def get_current_user(
    authorization: str | None = Header(default=None),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    user = verify_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user
```

This means the request is associated with a validated `User` before any deeper action is allowed. For routes like `/api/chat`, the role is available in `user.role` and can be used for higher-order checks or downstream tool permissioning.

## Tool authorization is enforced at execution time

The actual RBAC enforcement is centralized in `app/auth/rbac.py`.

### Permission table

The repo declares canonical tool names and the roles allowed to call each one:

```python
TOOL_KNOWLEDGE_SEARCH = "knowledge_search"
TOOL_PYTHON_ANALYSIS = "python_analysis"
TOOL_MCP_EMPLOYEE = "mcp_employee_directory"
TOOL_MCP_SERVICE = "mcp_service_catalog"
TOOL_MCP_INCIDENT = "mcp_incident_records"
TOOL_ADMIN_REINDEX = "admin_reindex"
```

Then a permission map assigns roles to tool sets:

```python
_ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.VIEWER: frozenset({TOOL_KNOWLEDGE_SEARCH}),
    Role.ANALYST: frozenset(
        {
            TOOL_KNOWLEDGE_SEARCH,
            TOOL_PYTHON_ANALYSIS,
            TOOL_MCP_EMPLOYEE,
            TOOL_MCP_SERVICE,
            TOOL_MCP_INCIDENT,
        }
    ),
    Role.ADMINISTRATOR: frozenset(
        {
            TOOL_KNOWLEDGE_SEARCH,
            TOOL_PYTHON_ANALYSIS,
            TOOL_MCP_EMPLOYEE,
            TOOL_MCP_SERVICE,
            TOOL_MCP_INCIDENT,
            TOOL_ADMIN_REINDEX,
        }
    ),
}
```

The key function is:

```python
def assert_tool_allowed(role: Role, tool_name: str) -> None:
    if not is_tool_allowed(role, tool_name):
        raise PermissionError(
            f"Role '{role.value}' is not authorized to use tool '{tool_name}'."
        )
```

This check is intentionally applied in the tool runtime, not in the prompt or agent instructions.

## Tool wrapper enforces RBAC before execution

All tools inherit from `BaseTool` in `app/tools/base.py`.

```python
async def run(self, role: Role, params: dict[str, Any]) -> ToolResult:
    started = time.perf_counter()
    try:
        assert_tool_allowed(role, self.name)
    except PermissionError as exc:
        logger.warning("tool_denied", tool=self.name, role=role.value)
        return ToolResult(
            tool_name=self.name,
            success=False,
            denied=True,
            error=str(exc),
        )
```

Then, after the RBAC check, the wrapper validates arguments and executes the tool with a timeout:

```python
cleaned = validate_tool_params(self.name, params or {})
output = await asyncio.wait_for(
    self.execute(cleaned),
    timeout=settings.tool_timeout_seconds,
)
```

This is a defense-in-depth pattern:

1. user authenticates
2. token asserts role
3. tool wrapper checks role
4. params are validated
5. tool executes with a timeout

This prevents an agent from discovering a privileged tool and invoking it just because the model reasoned it was allowed.

## Admin-only routes

The admin reindex endpoint in `app/main.py` explicitly enforces the admin role:

```python
@app.post("/api/admin/reindex")
async def admin_reindex(user: User = Depends(get_current_user)) -> dict[str, Any]:
    if user.role != Role.ADMINISTRATOR:
        raise HTTPException(status_code=403, detail="Administrator role required")
    count = await index_documents()
    return {"indexed_chunks": count}
```

The same privileges are mirrored in the tool permission table, so even if an admin route is not used, the underlying tool permissions remain consistent.

## Why this design matters

The repository implements RBAC in a way that is easy to reason about:

- identity is mapped to a fixed role set
- tokens carry role claims
- request handlers verify identity and token integrity
- tool wrappers enforce authorization at runtime
- privileged operations fail closed

This is a strong example of security-by-guardrail rather than relying on the LLM to be "well behaved." The agent is never the source of authority; the server enforces it.

## Summary

The RBAC model in this repo is intentionally minimal but correct for a demonstration system:

- `viewer` can perform limited search and read-only actions
- `analyst` gains operational tools and MCP access
- `administrator` can access reindex and all other allowed tools

The enforcement is centralized in `app/auth/rbac.py`, enforced in `BaseTool.run()`, and mirrored in route-level checks where needed.
