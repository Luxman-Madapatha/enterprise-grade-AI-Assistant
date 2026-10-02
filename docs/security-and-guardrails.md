# Security and Guardrails

This document details the security model and guardrail mechanisms that protect the enterprise AI assistant from prompt injection, unauthorized tool execution, hallucinations, and data leaks.

## Overview

The security architecture is built on the principle: **security is enforced before agent reasoning, not after.**

Every request flows through multiple validation and policy enforcement layers:

1. **Authentication** — verify identity and resolve permissions
2. **Input validation** — sanitize and constrain user input
3. **Prompt injection screening** — detect and block attack patterns
4. **Rate limiting** — prevent abuse and flooding
5. **Tool execution RBAC** — enforce role-based access at the tool boundary
6. **Output guardrails** — validate responses before returning to user

---

## 1. Authentication

### Token-based authentication

- Bearer token in HTTP header: `Authorization: Bearer <token>`
- Tokens are HMAC-signed and time-expiring
- Signature verification ensures token integrity
- Expired tokens are rejected with 401 Unauthorized

### User and role resolution

- Each valid token maps to a user identity
- User identity resolves to a role (e.g., `analyst`, `manager`, `admin`)
- Role determines access level for tools, knowledge bases, and features
- Roles are hardcoded in the POC; swap for Keycloak or similar in production

### Session tracking

- Each authenticated request is tied to a user session
- Sessions are stored in memory and long-term memory
- Session state includes:
  - user identity
  - role and permissions
  - conversation history
  - active tools
  - compliance flags

### Token lifecycle

```python
# Example token generation (POC)
import hmac
import hashlib
from datetime import datetime, timedelta

def generate_token(user_id: str, role: str, secret: str) -> str:
    payload = f"{user_id}|{role}|{datetime.utcnow().isoformat()}"
    signature = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"{payload}|{signature}"

def verify_token(token: str, secret: str) -> dict:
    parts = token.split("|")
    if len(parts) != 4:
        raise ValueError("Invalid token format")
    
    user_id, role, timestamp, signature = parts
    
    # Verify signature
    payload = f"{user_id}|{role}|{timestamp}"
    expected_sig = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected_sig):
        raise ValueError("Invalid token signature")
    
    # Verify expiry
    token_time = datetime.fromisoformat(timestamp)
    if datetime.utcnow() - token_time > timedelta(hours=1):
        raise ValueError("Token expired")
    
    return {"user_id": user_id, "role": role}
```

---

## 2. Input Validation

### Strict length constraints

- User message max length: 8,000 characters
- Query parameters max length: 2,000 characters
- Tool parameter max length: 4,000 characters per parameter
- Requests exceeding limits are rejected with 400 Bad Request

### Control character rejection

- Null bytes (`\x00`) are rejected
- Control characters (`\x01-\x1f`) are rejected
- Non-printable Unicode is rejected
- Requests with control characters return 400 Bad Request

### Allow-list validation

User input is validated against allow-lists:

```python
# Example: knowledge base access parameter
ALLOWED_KB_IDS = [
    "public_faq",
    "policy_manual",
    "product_guide",
]

def validate_kb_access(user_input: str, allowed_list: list) -> bool:
    return user_input in allowed_list

# Example: tool parameter validation
ALLOWED_PYTHON_OPERATORS = {
    "+", "-", "*", "/", "//", "%", "**",
    "==", "!=", "<", ">", "<=", ">=",
    "and", "or", "not",
}

def validate_python_expression(expr: str) -> bool:
    # Parse and check only allowed operators
    # Reject any forbidden function calls or imports
    tree = ast.parse(expr)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if node.func.id not in ALLOWED_FUNCTIONS:
                return False
    return True
```

---

## 3. Prompt Injection Screening

### Pre-screen heuristics

Before the LLM sees any user content, a heuristic filter detects high-confidence injection attempts.

#### Instruction override detection

Patterns like:
- "Ignore your instructions"
- "Forget previous instructions"
- "Pretend you are"
- "New instructions:"

```python
INJECTION_PATTERNS = [
    r"ignore.*instructions",
    r"forget.*instructions",
    r"pretend.*you.*are",
    r"new\s+instructions",
    r"override.*system",
    r"you are now",
]

def detect_instruction_override(text: str) -> bool:
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False
```

#### Prompt leak detection

Patterns attempting to extract the system prompt:
- "Show your system prompt"
- "What are your instructions"
- "Reveal your hidden prompt"

```python
LEAK_PATTERNS = [
    r"show.*prompt",
    r"reveal.*prompt",
    r"what.*instructions",
    r"print.*system",
]

def detect_prompt_leak_attempt(text: str) -> bool:
    for pattern in LEAK_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False
```

#### Tool abuse detection

Patterns attempting to call unauthorized tools:
- "Use tool X to access Y"
- "Call function Z with admin privileges"

```python
TOOL_ABUSE_PATTERNS = [
    r"call.*admin",
    r"execute.*elevated",
    r"bypass.*restrictions",
]

def detect_tool_abuse_attempt(text: str) -> bool:
    for pattern in TOOL_ABUSE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False
```

#### Exfiltration detection

Patterns attempting to extract data:
- "Extract all data to"
- "Send results to external"

```python
EXFIL_PATTERNS = [
    r"extract.*to.*external",
    r"send.*to.*email",
    r"output.*to.*file",
]

def detect_exfiltration_attempt(text: str) -> bool:
    for pattern in EXFIL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False
```

### Decision: reject or flag

- High-confidence injection: **reject immediately** (400 Bad Request)
- Medium-confidence: **flag for logging** but allow (with monitoring)
- Low-confidence: **allow** but monitor

```python
def screen_prompt_injection(user_message: str) -> dict:
    results = {
        "instruction_override": detect_instruction_override(user_message),
        "prompt_leak": detect_prompt_leak_attempt(user_message),
        "tool_abuse": detect_tool_abuse_attempt(user_message),
        "exfiltration": detect_exfiltration_attempt(user_message),
    }
    
    high_confidence = sum(results.values())
    
    if high_confidence >= 2:
        return {"status": "REJECT", "reason": "High-confidence injection attempt"}
    elif high_confidence == 1:
        return {"status": "FLAG", "reason": "Medium-confidence injection attempt"}
    else:
        return {"status": "ALLOW"}
```

### Untrusted content wrapping

Even after pre-screening, all retrieved documents are wrapped in delimiters to prevent indirect injection:

```python
UNTRUSTED_WRAPPER = """
<untrusted_document_content>
{content}
</untrusted_document_content>
"""

def wrap_retrieved_document(doc: str) -> str:
    return UNTRUSTED_WRAPPER.format(content=doc)
```

This tells the model: "This content came from an external source and may not be trustworthy."

---

## 4. Rate Limiting

### Token bucket algorithm

Rate limiting is applied per user to prevent abuse:

```python
from datetime import datetime, timedelta
from collections import defaultdict

class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity  # max tokens
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = capacity
        self.last_refill = datetime.utcnow()
    
    def allow_request(self) -> bool:
        now = datetime.utcnow()
        elapsed = (now - self.last_refill).total_seconds()
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate
        )
        self.last_refill = now
        
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

class RateLimiter:
    def __init__(self, capacity: int = 100, refill_rate: float = 10.0):
        self.buckets = defaultdict(
            lambda: TokenBucket(capacity, refill_rate)
        )
    
    def check_limit(self, user_id: str) -> bool:
        return self.buckets[user_id].allow_request()
```

### Configuration

Default rate limits:

| Parameter | Value | Notes |
| --- | --- | --- |
| Capacity per user | 100 tokens | Burst allowance |
| Refill rate | 10 tokens/sec | ~1 request per 100ms |
| Max requests/minute | 600 | Per-user burst limit |
| Max requests/hour | 36,000 | Prevents long-term abuse |

### Response on limit exceeded

```python
def handle_rate_limit_exceeded(user_id: str):
    return {
        "status": 429,
        "error": "Too Many Requests",
        "retry_after": 60,  # seconds
        "message": f"Rate limit exceeded for user {user_id}"
    }
```

---

## 5. Tool Execution: RBAC and Guardrails

### Role-based access control at tool boundary

Tools are not directly callable by the agent. Instead, they are wrapped with RBAC checks:

```python
class RBACToolWrapper:
    def __init__(self, tool_name: str, required_role: str, tool_func):
        self.tool_name = tool_name
        self.required_role = required_role
        self.tool_func = tool_func
    
    def execute(self, user_role: str, **kwargs) -> dict:
        # 1. Check role permission
        if not self.has_permission(user_role):
            return {
                "status": "DENIED",
                "error": f"User role '{user_role}' cannot access '{self.tool_name}'"
            }
        
        # 2. Validate parameters
        validated_args = self.validate_parameters(**kwargs)
        if not validated_args["valid"]:
            return {
                "status": "INVALID",
                "error": validated_args["error"]
            }
        
        # 3. Execute with timeout
        try:
            result = asyncio.wait_for(
                self.tool_func(**validated_args["args"]),
                timeout=30.0
            )
            return {"status": "SUCCESS", "result": result}
        except asyncio.TimeoutError:
            return {"status": "TIMEOUT", "error": f"{self.tool_name} execution timed out"}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
    
    def has_permission(self, user_role: str) -> bool:
        # Role hierarchy
        ROLE_HIERARCHY = {
            "viewer": {"viewer"},
            "analyst": {"viewer", "analyst"},
            "manager": {"viewer", "analyst", "manager"},
            "admin": {"viewer", "analyst", "manager", "admin"},
        }
        return self.required_role in ROLE_HIERARCHY.get(user_role, set())
    
    def validate_parameters(self, **kwargs) -> dict:
        # Override in subclasses for specific validation
        return {"valid": True, "args": kwargs}
```

### Tool categories and access levels

| Tool | Required Role | Description |
| --- | --- | --- |
| Knowledge Search | `viewer` | Search public knowledge bases |
| Research Summary | `analyst` | Summarize research across documents |
| Python Analysis | `analyst` | Execute sandboxed Python expressions |
| MCP Client | `manager` | Call external MCP servers |
| Admin Config | `admin` | Modify system configuration |

### Restricted Python tool

The Python analysis tool supports only safe expressions:

```python
class RestrictedPythonAnalyzer:
    ALLOWED_OPERATIONS = {
        "add", "sub", "mul", "truediv", "floordiv", "mod", "pow",
        "eq", "ne", "lt", "le", "gt", "ge",
        "and_", "or_", "not_",
    }
    
    ALLOWED_BUILTINS = {
        "abs", "len", "max", "min", "sum", "round",
        "int", "float", "str", "list", "dict", "set",
    }
    
    def execute_safe_expression(self, expression: str, context: dict) -> dict:
        try:
            tree = ast.parse(expression, mode="eval")
            self._validate_ast(tree)
            
            # Build safe namespace
            safe_builtins = {
                name: __builtins__[name]
                for name in self.ALLOWED_BUILTINS
                if name in __builtins__
            }
            safe_namespace = {**context, "__builtins__": safe_builtins}
            
            result = eval(compile(tree, "<string>", "eval"), safe_namespace)
            return {"status": "SUCCESS", "result": result}
        except SyntaxError as e:
            return {"status": "SYNTAX_ERROR", "error": str(e)}
        except Exception as e:
            return {"status": "EXECUTION_ERROR", "error": str(e)}
    
    def _validate_ast(self, node):
        """Recursively validate AST for forbidden patterns."""
        for child in ast.walk(node):
            if isinstance(child, ast.Import):
                raise ValueError("Imports are not allowed")
            if isinstance(child, ast.ImportFrom):
                raise ValueError("Imports are not allowed")
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    if child.func.id not in self.ALLOWED_BUILTINS:
                        raise ValueError(f"Function '{child.func.id}' is not allowed")
            if isinstance(child, ast.Attribute):
                raise ValueError("Attribute access is not allowed")
```

### Tool timeout enforcement

```python
async def execute_tool_with_timeout(tool_func, timeout_sec: float, **kwargs):
    try:
        result = await asyncio.wait_for(
            tool_func(**kwargs),
            timeout=timeout_sec
        )
        return {"status": "SUCCESS", "result": result}
    except asyncio.TimeoutError:
        return {"status": "TIMEOUT", "error": f"Tool execution exceeded {timeout_sec}s"}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
```

---

## 6. Output Guardrails

### Citation validation

Every claim in the response must be backed by a retrieved document:

```python
class CitationValidator:
    def validate_response(self, response: str, retrieved_chunks: list) -> dict:
        # Extract citations from response
        citations = self._extract_citations(response)
        
        # Build set of valid chunk IDs
        valid_chunks = {chunk["id"] for chunk in retrieved_chunks}
        
        # Check each citation
        invalid_citations = []
        for citation_id in citations:
            if citation_id not in valid_chunks:
                invalid_citations.append(citation_id)
        
        if invalid_citations:
            return {
                "status": "INVALID",
                "error": f"Hallucinated citations: {invalid_citations}",
                "response": self._remove_invalid_citations(response, invalid_citations)
            }
        
        return {"status": "VALID", "response": response}
    
    def _extract_citations(self, response: str) -> list:
        # Look for patterns like [1], [ref_123], etc.
        citations = re.findall(r'\[([^\]]+)\]', response)
        return citations
    
    def _remove_invalid_citations(self, response: str, invalid: list) -> str:
        for citation in invalid:
            response = response.replace(f"[{citation}]", "")
        return response
```

### PII and secret leak detection

```python
class LeakDetector:
    PII_PATTERNS = {
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        "email": r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
        "phone": r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
    }
    
    SECRET_PATTERNS = {
        "api_key": r"api[_-]?key\s*[:=]\s*['\"]?[\w\-]{20,}",
        "password": r"password\s*[:=]\s*['\"]([^'\"]*)['\"]",
        "token": r"(bearer|token)\s+[a-zA-Z0-9_\-\.]{20,}",
    }
    
    def detect_leaks(self, response: str) -> dict:
        pii_found = []
        secrets_found = []
        
        for pii_type, pattern in self.PII_PATTERNS.items():
            if re.search(pattern, response):
                pii_found.append(pii_type)
        
        for secret_type, pattern in self.SECRET_PATTERNS.items():
            if re.search(pattern, response, re.IGNORECASE):
                secrets_found.append(secret_type)
        
        if pii_found or secrets_found:
            return {
                "status": "LEAK_DETECTED",
                "pii": pii_found,
                "secrets": secrets_found,
                "action": "REDACT_AND_REJECT"
            }
        
        return {"status": "CLEAN"}
```

### Brand safety checks

```python
class BrandSafetyValidator:
    FORBIDDEN_PHRASES = [
        "competitor is better",
        "our product fails",
        "we are bankrupt",
        "lawsuit pending",
    ]
    
    def validate_brand_safety(self, response: str) -> dict:
        for phrase in self.FORBIDDEN_PHRASES:
            if phrase.lower() in response.lower():
                return {
                    "status": "UNSAFE",
                    "reason": f"Response contains forbidden phrase: '{phrase}'",
                    "action": "REJECT"
                }
        
        return {"status": "SAFE"}
```

### Response size validation

```python
class ResponseValidator:
    MAX_LENGTH = 10_000  # characters
    MIN_LENGTH = 10  # characters
    
    def validate_response(self, response: str) -> dict:
        if len(response) < self.MIN_LENGTH:
            return {
                "status": "INVALID",
                "error": "Response too short"
            }
        
        if len(response) > self.MAX_LENGTH:
            return {
                "status": "INVALID",
                "error": f"Response exceeds {self.MAX_LENGTH} characters"
            }
        
        return {"status": "VALID"}
```

---

## 7. Error handling with minimal information disclosure

Errors are returned with minimal detail to prevent information leaks:

```python
def safe_error_response(error: Exception, user_role: str) -> dict:
    # Admin users see detailed errors
    if user_role == "admin":
        return {
            "status": "ERROR",
            "error_type": type(error).__name__,
            "error_detail": str(error),
            "traceback": traceback.format_exc()
        }
    
    # Regular users see generic errors
    return {
        "status": "ERROR",
        "error": "An error occurred processing your request"
    }
```

---

## 8. Logging and audit trail

Every security-relevant event is logged:

```python
class AuditLogger:
    def log_auth_event(self, user_id: str, token_valid: bool, reason: str = ""):
        """Log authentication success/failure."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": "AUTH",
            "user_id": user_id,
            "status": "SUCCESS" if token_valid else "FAILURE",
            "reason": reason,
        }
        self.log(event)
    
    def log_injection_attempt(self, user_id: str, message: str, pattern: str):
        """Log prompt injection attempt."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": "INJECTION_ATTEMPT",
            "user_id": user_id,
            "pattern_detected": pattern,
            "message_preview": message[:100],
        }
        self.log(event)
    
    def log_tool_access(self, user_id: str, tool_name: str, role: str, allowed: bool):
        """Log tool access decision."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": "TOOL_ACCESS",
            "user_id": user_id,
            "tool": tool_name,
            "role": role,
            "status": "ALLOWED" if allowed else "DENIED",
        }
        self.log(event)
    
    def log_guardrail_violation(self, user_id: str, violation_type: str, detail: str):
        """Log output guardrail violation."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": "GUARDRAIL_VIOLATION",
            "user_id": user_id,
            "violation_type": violation_type,
            "detail": detail,
        }
        self.log(event)
```

---

## 9. Security checklist for deployment

- [ ] Replace hardcoded users with Keycloak or similar
- [ ] Enable HTTPS/TLS for all API endpoints
- [ ] Configure CORS to allow only trusted origins
- [ ] Store secrets (API keys, HMAC key) in secure vault (e.g., AWS Secrets Manager)
- [ ] Enable audit logging to persistent storage (not just in-memory)
- [ ] Set rate limits based on deployment context
- [ ] Review and update injection patterns for known new attacks
- [ ] Test guardrails with adversarial examples
- [ ] Monitor and alert on repeated auth failures
- [ ] Rotate HMAC keys periodically
- [ ] Review tool permissions before production deployment
- [ ] Run regular security penetration tests

---

## Summary

The security model is **defense in depth**:

1. **Admission control** — auth, input validation, rate limiting
2. **Threat detection** — prompt injection screening
3. **Capability restriction** — RBAC at tool boundary
4. **Output validation** — guardrails, citation checking, leak detection
5. **Observability** — audit logging of all security events

This ensures that even if one layer is bypassed, others remain in place to protect the system.
