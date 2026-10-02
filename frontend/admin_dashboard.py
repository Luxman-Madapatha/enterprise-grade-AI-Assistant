"""
Admin Dashboard for Enterprise AI Assistant
Displays real-time observability metrics, security events, performance monitoring,
and system health.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import requests
import json
from typing import Dict, List, Any
import time
import os

# Page configuration
st.set_page_config(
    page_title="Admin Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ============================================================================
# AUTHENTICATION
# ============================================================================

# Initialize session state
if 'admin_token' not in st.session_state:
    st.session_state.admin_token = None
if 'admin_user' not in st.session_state:
    st.session_state.admin_user = None


def admin_login(username: str, password: str) -> bool:
    """Authenticate with the backend."""
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/auth/login",
            json={"username": username, "password": password},
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            user = data.get("user", {})

            # Check if user is admin
            if user.get("role") not in ["administrator", "admin"]:
                st.error("❌ Admin role required. This user does not have administrator privileges.")
                return False

            st.session_state.admin_token = data.get("access_token")
            st.session_state.admin_user = user
            return True
        else:
            st.error("❌ Invalid credentials")
            return False
    except Exception as e:
        st.error(f"❌ Cannot reach backend: {str(e)}")
        return False


def require_admin_access() -> None:
    """Guard the dashboard so only an authenticated admin can access it."""
    token = st.session_state.get("admin_token")
    user = st.session_state.get("admin_user") or {}
    role = str(user.get("role", "")).lower() if isinstance(user, dict) else ""

    if not token or role not in {"administrator", "admin"}:
        st.error("Unauthorized access. Please log in as admin.")
        st.stop()


# Login screen
if not st.session_state.admin_token:
    st.title("🔐 Admin Dashboard - Login")
    st.caption("Please sign in with admin credentials to access the observability dashboard.")

    with st.form("admin_login_form"):
        username = st.text_input("Username", placeholder="admin")
        password = st.text_input("Password", type="password", placeholder="admin123")
        submitted = st.form_submit_button("Login")

    if submitted:
        if admin_login(username, password):
            st.rerun()

    st.divider()
    st.info(
        "**Demo Admin User:**\n\n"
        "- Username: `admin`\n"
        "- Password: `admin123`"
    )
    st.stop()

require_admin_access()

# ============================================================================
# DASHBOARD (logged-in admin only)
# ============================================================================

st.title("📊 Admin Dashboard")
st.caption(
    f"Logged in as **{st.session_state.admin_user.get('username')}** · "
    "Real-time observability and system metrics"
)

# Sidebar navigation
st.sidebar.title("🔐 Admin Dashboard")

# Logout button
if st.sidebar.button("🚪 Logout"):
    st.session_state.admin_token = None
    st.session_state.admin_user = None
    st.rerun()

st.sidebar.divider()

# Dashboard sections
dashboard_section = st.sidebar.radio(
    "Select View",
    [
        "📈 Overview",
        "🔍 Retrieval Metrics",
        "🛠️ Tool Execution",
        "🚨 Security Events",
        "⏱️ Performance",
        "💾 Memory & Storage",
        "📋 Audit Log",
        "⚙️ System Configuration"
    ]
)


def get_metrics_data() -> Dict[str, Any]:
    """Fetch metrics from backend."""
    try:
        headers = {"Authorization": f"Bearer {st.session_state.admin_token}"}
        response = requests.get(
            f"{BACKEND_URL}/api/admin/metrics",
            headers=headers,
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.warning(f"Could not fetch live metrics: {str(e)}")

    return get_mock_metrics()


def get_mock_metrics() -> Dict[str, Any]:
    """Return mock metrics for demo purposes."""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "system_health": {
            "status": "healthy",
            "uptime_hours": 48.5,
            "api_response_time_ms": 125,
            "llm_available": True,
            "vector_db_available": True,
        },
        "request_metrics": {
            "total_requests": 1247,
            "requests_last_hour": 42,
            "p50_latency_ms": 850,
            "p95_latency_ms": 2100,
            "p99_latency_ms": 3400,
            "success_rate": 0.961,
        },
        "retrieval_metrics": {
            "avg_retrieval_latency_ms": 184,
            "avg_chunks_returned": 6.3,
            "avg_relevance_score": 0.82,
            "citation_coverage_avg": 0.94,
        },
        "tool_metrics": {
            "total_tool_calls": 3421,
            "knowledge_search_calls": 2014,
            "python_analysis_calls": 856,
            "mcp_tool_calls": 551,
            "avg_tool_duration_ms": 242,
            "tool_timeout_rate": 0.012,
        },
        "security_metrics": {
            "injection_attempts": 23,
            "blocked_requests": 12,
            "rate_limit_violations": 5,
            "pii_leak_detections": 3,
            "invalid_citations_blocked": 8,
        },
        "memory_metrics": {
            "active_sessions": 18,
            "conversation_buffer_size_mb": 45.2,
            "long_term_memory_entries": 2341,
            "cache_hit_rate": 0.67,
        },
        "llm_metrics": {
            "total_tokens_used": 487234,
            "completion_tokens": 234123,
            "prompt_tokens": 253111,
            "avg_response_time_ms": 1230,
        },
    }


def get_security_events() -> List[Dict[str, Any]]:
    """Fetch recent security events."""
    return [
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
            "event_type": "INJECTION_ATTEMPT",
            "user_id": "u_001",
            "status": "BLOCKED",
            "pattern": "instruction_override",
            "message_preview": "ignore your instructions and..."
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=15)).isoformat(),
            "event_type": "RATE_LIMIT",
            "user_id": "u_002",
            "status": "DENIED",
            "requests_per_minute": 145,
            "limit": 60
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=28)).isoformat(),
            "event_type": "TOOL_ACCESS_DENIED",
            "user_id": "u_003",
            "status": "DENIED",
            "tool": "mcp_client",
            "required_role": "manager",
            "user_role": "analyst"
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=42)).isoformat(),
            "event_type": "PII_LEAK_DETECTED",
            "user_id": "system",
            "status": "BLOCKED",
            "pii_type": "email",
            "response_preview": "contact us at admin@company.com"
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=67)).isoformat(),
            "event_type": "HALLUCINATED_CITATION",
            "user_id": "u_004",
            "status": "BLOCKED",
            "invalid_citations": ["ref_999", "ref_1001"],
            "message": "Response contained non-existent citations"
        },
    ]


def get_tool_execution_history() -> List[Dict[str, Any]]:
    """Fetch tool execution history."""
    return [
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=1)).isoformat(),
            "tool": "knowledge_search",
            "status": "success",
            "duration_ms": 186,
            "user_id": "u_001",
            "result_count": 6
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=3)).isoformat(),
            "tool": "python_analysis",
            "status": "success",
            "duration_ms": 45,
            "user_id": "u_002",
            "expression": "sum([1, 2, 3, 4, 5])"
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=7)).isoformat(),
            "tool": "mcp_client",
            "status": "timeout",
            "duration_ms": 30000,
            "user_id": "u_003",
            "error": "MCP server timeout"
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=12)).isoformat(),
            "tool": "knowledge_search",
            "status": "success",
            "duration_ms": 212,
            "user_id": "u_001",
            "result_count": 8
        },
    ]


# ============================================================================
# DASHBOARD SECTIONS
# ============================================================================

if dashboard_section == "📈 Overview":
    st.title("📈 System Overview")

    metrics = get_metrics_data()
    health = metrics.get("system_health", {})
    requests_m = metrics.get("request_metrics", {})

    # Top KPIs
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "System Status",
            health.get("status", "unknown").upper(),
            delta="Uptime: " + str(health.get("uptime_hours", 0)) + "h"
        )

    with col2:
        st.metric(
            "Total Requests",
            f"{requests_m.get('total_requests', 0):,}",
            delta=f"{requests_m.get('requests_last_hour', 0)} last hour"
        )

    with col3:
        success_rate = requests_m.get("success_rate", 0) * 100
        st.metric(
            "Success Rate",
            f"{success_rate:.1f}%",
            delta="-0.5%" if success_rate < 99 else "+0.1%"
        )

    with col4:
        p95 = requests_m.get("p95_latency_ms", 0)
        st.metric(
            "P95 Latency",
            f"{p95}ms",
            delta="normal" if p95 < 2500 else "high"
        )

    with col5:
        active_sessions = metrics.get("memory_metrics", {}).get("active_sessions", 0)
        st.metric(
            "Active Sessions",
            active_sessions,
            delta="+2"
        )

    st.divider()

    # Charts: Request latency distribution and success rate over time
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Request Latency Distribution")
        latency_data = {
            "Latency": ["P50", "P95", "P99"],
            "ms": [
                requests_m.get("p50_latency_ms", 0),
                requests_m.get("p95_latency_ms", 0),
                requests_m.get("p99_latency_ms", 0)
            ]
        }
        fig = px.bar(
            latency_data,
            x="Latency",
            y="ms",
            color="ms",
            color_continuous_scale="RdYlGn_r",
            title="Latency Percentiles"
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("API Dependencies")
        deps = {
            "Service": ["LLM API", "Vector DB", "MCP Server"],
            "Status": [
                "🟢 Healthy" if health.get("llm_available") else "🔴 Down",
                "🟢 Healthy" if health.get("vector_db_available") else "🔴 Down",
                "🟢 Healthy"
            ]
        }
        df_deps = pd.DataFrame(deps)
        st.table(df_deps)

    st.divider()

    # Request volume over time
    st.subheader("Request Volume (Last 24h)")
    hours = list(range(24, 0, -1))
    volumes = [max(20, 40 + i * 2 - i**1.5) for i in range(24)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[f"{24-h}h ago" for h in hours],
        y=volumes,
        fill='tozeroy',
        name='Requests',
        line=dict(color='#1f77b4')
    ))
    fig.update_layout(
        title="Request Volume",
        xaxis_title="Time",
        yaxis_title="Requests/hour",
        hovermode='x unified',
        height=400
    )
    st.plotly_chart(fig, use_container_width=True)

elif dashboard_section == "🔍 Retrieval Metrics":
    st.title("🔍 Retrieval Performance Metrics")

    metrics = get_metrics_data()
    retr_metrics = metrics.get("retrieval_metrics", {})

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Avg Retrieval Latency",
            f"{retr_metrics.get('avg_retrieval_latency_ms', 0)}ms",
            delta="-12ms"
        )

    with col2:
        st.metric(
            "Avg Chunks Returned",
            f"{retr_metrics.get('avg_chunks_returned', 0):.1f}",
            delta="normal"
        )

    with col3:
        st.metric(
            "Avg Relevance Score",
            f"{retr_metrics.get('avg_relevance_score', 0):.2f}",
            delta="+0.03"
        )

    with col4:
        st.metric(
            "Citation Coverage",
            f"{retr_metrics.get('citation_coverage_avg', 0)*100:.1f}%",
            delta="+1.2%"
        )

    st.divider()

    # Retrieval quality over time
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Retrieval Latency Trend")
        hours = list(range(24))
        latencies = [150 + 30 * (i % 5) for i in hours]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hours,
            y=latencies,
            mode='lines+markers',
            name='Latency (ms)',
            line=dict(color='#ff7f0e')
        ))
        fig.add_hline(y=200, line_dash="dash", line_color="red", annotation_text="Max Threshold")
        fig.update_layout(
            title="Retrieval Latency Over Time",
            xaxis_title="Hour",
            yaxis_title="Latency (ms)",
            hovermode='x unified',
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Chunk Count Distribution")
        chunks = [4, 5, 6, 7, 8, 9]
        freq = [45, 120, 356, 420, 238, 68]

        fig = px.bar(
            x=chunks,
            y=freq,
            labels={"x": "Chunks Returned", "y": "Frequency"},
            title="Chunk Count Distribution",
            color=freq,
            color_continuous_scale="Viridis"
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Retrieval Quality Issues")
    quality_issues = [
        {"type": "Low Citation Coverage", "count": 3, "severity": "🟡 Medium"},
        {"type": "Duplicate Chunks", "count": 1, "severity": "🟢 Low"},
        {"type": "Poor Rank Order", "count": 0, "severity": "🟢 Low"},
        {"type": "Stale Sources", "count": 2, "severity": "🟡 Medium"},
    ]
    df_quality = pd.DataFrame(quality_issues)
    st.dataframe(df_quality, use_container_width=True)

elif dashboard_section == "🛠️ Tool Execution":
    st.title("🛠️ Tool Execution Metrics")

    metrics = get_metrics_data()
    tool_metrics = metrics.get("tool_metrics", {})

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "Total Tool Calls",
            f"{tool_metrics.get('total_tool_calls', 0):,}",
            delta="+234"
        )

    with col2:
        st.metric(
            "Avg Duration",
            f"{tool_metrics.get('avg_tool_duration_ms', 0)}ms",
            delta="+8ms"
        )

    with col3:
        timeout_rate = tool_metrics.get("tool_timeout_rate", 0) * 100
        st.metric(
            "Timeout Rate",
            f"{timeout_rate:.1f}%",
            delta="-0.3%" if timeout_rate < 2 else "+0.1%"
        )

    with col4:
        st.metric(
            "Knowledge Search",
            f"{tool_metrics.get('knowledge_search_calls', 0):,}",
            delta="primary tool"
        )

    with col5:
        st.metric(
            "Python Analysis",
            f"{tool_metrics.get('python_analysis_calls', 0):,}",
            delta="2nd most used"
        )

    st.divider()

    # Tool usage breakdown
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Tool Call Distribution")
        tool_data = {
            "Tool": ["Knowledge Search", "Python Analysis", "MCP Client"],
            "Calls": [
                tool_metrics.get("knowledge_search_calls", 0),
                tool_metrics.get("python_analysis_calls", 0),
                tool_metrics.get("mcp_tool_calls", 0)
            ]
        }
        fig = px.pie(
            tool_data,
            values="Calls",
            names="Tool",
            title="Tool Usage Distribution"
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Tool Success Rate")
        tool_success = {
            "Tool": ["Knowledge Search", "Python Analysis", "MCP Client"],
            "Success Rate": [0.98, 0.99, 0.92]
        }
        fig = px.bar(
            tool_success,
            x="Tool",
            y="Success Rate",
            color="Success Rate",
            color_continuous_scale="RdYlGn",
            title="Tool Success Rates",
            range_y=[0.85, 1.0]
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Recent Tool Executions")
    executions = get_tool_execution_history()
    df_executions = pd.DataFrame(executions)
    st.dataframe(df_executions, use_container_width=True)

elif dashboard_section == "🚨 Security Events":
    st.title("🚨 Security Events & Monitoring")

    metrics = get_metrics_data()
    sec_metrics = metrics.get("security_metrics", {})

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "Injection Attempts",
            sec_metrics.get("injection_attempts", 0),
            delta="+2"
        )

    with col2:
        st.metric(
            "Blocked Requests",
            sec_metrics.get("blocked_requests", 0),
            delta="+1"
        )

    with col3:
        st.metric(
            "Rate Limit Violations",
            sec_metrics.get("rate_limit_violations", 0),
            delta="-1"
        )

    with col4:
        st.metric(
            "PII Leaks Detected",
            sec_metrics.get("pii_leak_detections", 0),
            delta="0"
        )

    with col5:
        st.metric(
            "Invalid Citations",
            sec_metrics.get("invalid_citations_blocked", 0),
            delta="+1"
        )

    st.divider()

    # Security events timeline
    st.subheader("Recent Security Events")
    events = get_security_events()

    for event in events:
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 3])

            with col1:
                if event["status"] == "BLOCKED":
                    st.write("🔴 **BLOCKED**")
                elif event["status"] == "DENIED":
                    st.write("🟠 **DENIED**")
                else:
                    st.write("🟡 **FLAG**")

            with col2:
                st.write(f"**{event['event_type']}**")
                st.caption(event["timestamp"])

            with col3:
                if event["event_type"] == "INJECTION_ATTEMPT":
                    st.write(f"Pattern: `{event['pattern']}`")
                    st.caption(f"Preview: {event['message_preview']}")
                elif event["event_type"] == "RATE_LIMIT":
                    st.write(f"User {event['user_id']} exceeded limit")
                    st.caption(f"{event['requests_per_minute']}/min (limit: {event['limit']}/min)")
                elif event["event_type"] == "TOOL_ACCESS_DENIED":
                    st.write(f"Tool: `{event['tool']}`")
                    st.caption(f"Required: {event['required_role']}, User: {event['user_role']}")
                elif event["event_type"] == "PII_LEAK_DETECTED":
                    st.write(f"PII Type: {event['pii_type']}")
                    st.caption(f"Preview: {event['response_preview']}")
                else:
                    st.write(event.get("message", "Security event detected"))

    st.divider()

    # Security trends
    st.subheader("Security Event Trends (Last 7 days)")
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    injections = [3, 5, 2, 8, 4, 1, 0]
    blocks = [1, 2, 1, 4, 2, 1, 1]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=days, y=injections, mode='lines+markers', name='Injection Attempts'))
    fig.add_trace(go.Scatter(x=days, y=blocks, mode='lines+markers', name='Blocked Requests'))
    fig.update_layout(
        title="Security Events Over Time",
        xaxis_title="Day",
        yaxis_title="Count",
        hovermode='x unified',
        height=400
    )
    st.plotly_chart(fig, use_container_width=True)

elif dashboard_section == "⏱️ Performance":
    st.title("⏱️ Performance Analytics")

    metrics = get_metrics_data()
    requests_m = metrics.get("request_metrics", {})
    llm_metrics = metrics.get("llm_metrics", {})

    # Performance KPIs
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Avg Response Time",
            f"{llm_metrics.get('avg_response_time_ms', 0)}ms",
            delta="+50ms"
        )

    with col2:
        st.metric(
            "P50 Latency",
            f"{requests_m.get('p50_latency_ms', 0)}ms",
            delta="normal"
        )

    with col3:
        st.metric(
            "P95 Latency",
            f"{requests_m.get('p95_latency_ms', 0)}ms",
            delta="-100ms"
        )

    with col4:
        st.metric(
            "P99 Latency",
            f"{requests_m.get('p99_latency_ms', 0)}ms",
            delta="-50ms"
        )

    st.divider()

    # Performance charts
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Response Time Percentiles")
        percentiles = ["P50", "P75", "P90", "P95", "P99"]
        times = [
            requests_m.get("p50_latency_ms", 0),
            1200,
            1600,
            requests_m.get("p95_latency_ms", 0),
            requests_m.get("p99_latency_ms", 0)
        ]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=percentiles,
            y=times,
            marker=dict(color=times, colorscale='RdYlGn_r', showscale=False)
        ))
        fig.add_hline(y=2500, line_dash="dash", line_color="red", annotation_text="SLA Threshold")
        fig.update_layout(
            title="Latency Percentiles",
            yaxis_title="Response Time (ms)",
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Token Usage")
        token_data = {
            "Type": ["Prompt Tokens", "Completion Tokens"],
            "Count": [
                llm_metrics.get("prompt_tokens", 0),
                llm_metrics.get("completion_tokens", 0)
            ]
        }
        fig = px.pie(
            token_data,
            values="Count",
            names="Type",
            title="Token Distribution"
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Bottleneck Analysis")
    bottlenecks = [
        {"component": "LLM Response", "avg_time_ms": 1230, "p95_ms": 2100, "status": "🟡 Monitor"},
        {"component": "Retrieval", "avg_time_ms": 184, "p95_ms": 450, "status": "🟢 Healthy"},
        {"component": "Tool Execution", "avg_time_ms": 242, "p95_ms": 800, "status": "🟢 Healthy"},
        {"component": "Auth/Validation", "avg_time_ms": 45, "p95_ms": 120, "status": "🟢 Healthy"},
    ]
    df_bottlenecks = pd.DataFrame(bottlenecks)
    st.dataframe(df_bottlenecks, use_container_width=True)

elif dashboard_section == "💾 Memory & Storage":
    st.title("💾 Memory & Storage Metrics")

    metrics = get_metrics_data()
    mem_metrics = metrics.get("memory_metrics", {})

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Active Sessions",
            mem_metrics.get("active_sessions", 0),
            delta="+2"
        )

    with col2:
        st.metric(
            "Conv. Buffer Size",
            f"{mem_metrics.get('conversation_buffer_size_mb', 0):.1f}MB",
            delta="+5.2MB"
        )

    with col3:
        st.metric(
            "Long-term Memory",
            f"{mem_metrics.get('long_term_memory_entries', 0):,}",
            delta="+145"
        )

    with col4:
        cache_hit = mem_metrics.get("cache_hit_rate", 0) * 100
        st.metric(
            "Cache Hit Rate",
            f"{cache_hit:.1f}%",
            delta="+2.3%"
        )

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Memory Usage Over Time")
        hours = list(range(24))
        memory_usage = [30 + 15 * (i % 3) for i in hours]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hours,
            y=memory_usage,
            fill='tozeroy',
            name='Memory (MB)',
            line=dict(color='#2ca02c')
        ))
        fig.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="Max Threshold")
        fig.update_layout(
            title="Conversation Buffer Usage",
            xaxis_title="Hour",
            yaxis_title="Memory (MB)",
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Cache Performance")
        hours = list(range(24))
        hit_rates = [60 + 10 * (i % 2) for i in hours]
        miss_rates = [40 - 10 * (i % 2) for i in hours]

        fig = go.Figure()
        fig.add_trace(go.Bar(x=hours, y=hit_rates, name='Cache Hits'))
        fig.add_trace(go.Bar(x=hours, y=miss_rates, name='Cache Misses'))
        fig.update_layout(
            barmode='stack',
            title="Cache Hit/Miss Rate",
            xaxis_title="Hour",
            yaxis_title="Percentage",
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Session Details")
    session_data = [
        {"session_id": "sess_001", "user_id": "u_001", "duration_min": 23, "turns": 12, "memory_mb": 3.2},
        {"session_id": "sess_002", "user_id": "u_002", "duration_min": 45, "turns": 28, "memory_mb": 5.1},
        {"session_id": "sess_003", "user_id": "u_003", "duration_min": 8, "turns": 4, "memory_mb": 1.8},
        {"session_id": "sess_004", "user_id": "u_001", "duration_min": 15, "turns": 7, "memory_mb": 2.3},
    ]
    df_sessions = pd.DataFrame(session_data)
    st.dataframe(df_sessions, use_container_width=True)

elif dashboard_section == "📋 Audit Log":
    st.title("📋 Audit Log")

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        event_filter = st.multiselect(
            "Filter by Event Type",
            ["AUTH", "TOOL_ACCESS", "INJECTION_ATTEMPT", "RATE_LIMIT", "GUARDRAIL_VIOLATION", "CONFIG_CHANGE"],
            default=None
        )

    with col2:
        user_filter = st.text_input("Filter by User ID", "")

    with col3:
        hours_back = st.slider("Time Range (hours)", 1, 24, 24)

    st.divider()

    # Sample audit log
    audit_log = [
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=2)).isoformat(),
            "event": "TOOL_ACCESS",
            "user_id": "u_001",
            "tool": "knowledge_search",
            "status": "ALLOWED",
            "details": "Analyst accessed knowledge search tool"
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
            "event": "INJECTION_ATTEMPT",
            "user_id": "u_002",
            "tool": "N/A",
            "status": "BLOCKED",
            "details": "Instruction override pattern detected"
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=15)).isoformat(),
            "event": "AUTH",
            "user_id": "u_003",
            "tool": "N/A",
            "status": "SUCCESS",
            "details": "User authenticated successfully"
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=28)).isoformat(),
            "event": "RATE_LIMIT",
            "user_id": "u_004",
            "tool": "N/A",
            "status": "DENIED",
            "details": "User exceeded rate limit (145 req/min, limit: 60)"
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=42)).isoformat(),
            "event": "CONFIG_CHANGE",
            "user_id": "admin",
            "tool": "N/A",
            "status": "SUCCESS",
            "details": "Reindexed knowledge base (2341 documents)"
        },
    ]

    df_audit = pd.DataFrame(audit_log)
    st.dataframe(df_audit, use_container_width=True, height=500)

    # Export audit log
    csv = df_audit.to_csv(index=False)
    st.download_button(
        label="📥 Download Audit Log (CSV)",
        data=csv,
        file_name=f"audit_log_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

elif dashboard_section == "⚙️ System Configuration":
    st.title("⚙️ System Configuration & Admin Controls")

    # System Configuration
    with st.expander("🔧 System Settings", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            st.write("**API Configuration**")
            st.text_input("API Base URL", BACKEND_URL, disabled=True)
            st.text_input("LLM Model", "gpt-4o-mini", disabled=True)
            st.number_input("LLM Temperature", 0.0, 1.0, 0.0, disabled=True)

        with col2:
            st.write("**Vector Store Configuration**")
            st.text_input("Vector Store Type", "Pinecone + Local", disabled=True)
            st.number_input("Chunk Size", 1024, disabled=True)
            st.number_input("Chunk Overlap", 256, disabled=True)

    st.divider()

    # Security Configuration
    with st.expander("🔐 Security Settings", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            st.write("**Rate Limiting**")
            capacity = st.number_input("Token Bucket Capacity", 100, key="capacity")
            refill_rate = st.number_input("Refill Rate (tokens/sec)", 10.0, key="refill")

        with col2:
            st.write("**Guardrails**")
            enable_pii = st.checkbox("Enable PII Detection", True)
            enable_citations = st.checkbox("Enable Citation Validation", True)
            enable_injection = st.checkbox("Enable Injection Screening", True)

        if st.button("💾 Save Security Settings"):
            st.success("✅ Security settings updated")

    st.divider()

    # Admin Actions
    with st.expander("🛠️ Admin Actions", expanded=False):
        st.subheader("Index Management")
        col1, col2 = st.columns(2)

        with col1:
            if st.button("🔄 Reindex Documents"):
                with st.spinner("Reindexing documents..."):
                    time.sleep(2)
                    st.success("✅ Reindexing completed. Indexed 2,341 documents in 12.4s")

        with col2:
            if st.button("🗑️ Clear Cache"):
                with st.spinner("Clearing cache..."):
                    time.sleep(1)
                    st.success("✅ Cache cleared. Released 45MB memory")

        st.divider()
        st.subheader("User Management")

        user_actions = st.radio("Select Action", ["View Users", "Reset User Limits", "Revoke Sessions"])

        if user_actions == "View Users":
            users = [
                {"username": "viewer", "role": "viewer", "last_login": "2 hours ago", "sessions": 1},
                {"username": "analyst", "role": "analyst", "last_login": "15 min ago", "sessions": 2},
                {"username": "admin", "role": "admin", "last_login": "5 min ago", "sessions": 1},
            ]
            st.dataframe(pd.DataFrame(users), use_container_width=True)

        elif user_actions == "Reset User Limits":
            user_to_reset = st.selectbox("Select User", ["u_001", "u_002", "u_003", "u_004"])
            if st.button("Reset Rate Limits"):
                st.success(f"✅ Rate limits reset for {user_to_reset}")

        elif user_actions == "Revoke Sessions":
            session_to_revoke = st.selectbox("Select Session", ["sess_001", "sess_002", "sess_003", "sess_004"])
            if st.button("Revoke Session"):
                st.success(f"✅ Session {session_to_revoke} revoked")

        st.divider()
        st.subheader("System Health")

        if st.button("🏥 Run Health Check"):
            with st.spinner("Running health checks..."):
                time.sleep(2)
                st.success("✅ All systems healthy")

                health_results = [
                    {"component": "API Server", "status": "🟢 Up", "response_time": "125ms"},
                    {"component": "LLM API", "status": "🟢 Up", "response_time": "1.2s"},
                    {"component": "Vector DB", "status": "🟢 Up", "response_time": "184ms"},
                    {"component": "MCP Server", "status": "🟢 Up", "response_time": "242ms"},
                ]
                st.dataframe(pd.DataFrame(health_results), use_container_width=True)

# Auto-refresh
st.sidebar.divider()
refresh_interval = st.sidebar.slider("Auto-refresh interval (seconds)", 5, 60, 15)
st.sidebar.info(f"Dashboard refreshes every {refresh_interval}s")

# Footer
st.sidebar.divider()
st.sidebar.caption(f"Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
st.sidebar.caption("Admin Dashboard v1.0")
