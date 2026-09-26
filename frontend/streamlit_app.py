"""Streamlit frontend.

A lightweight, functional chat UI with a real-time Agent Activity panel. UI
beauty is intentionally not a priority — the focus is on transparency: the
evaluator can watch every agent node, tool call, retrieval, memory update,
validation and the final answer as they happen.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Iterator

import httpx
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Enterprise AI Assistant",
    page_icon="🤖",
    layout="wide",
)

# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
_DEFAULTS: dict[str, Any] = {
    "token": None,
    "user": None,
    "messages": [],
    "activity": [],
    "session_id": None,
}
for _key, _val in _DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _val


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def login(username: str, password: str) -> bool:
    try:
        resp = httpx.post(
            f"{BACKEND_URL}/api/auth/login",
            json={"username": username, "password": password},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        st.error(f"Cannot reach backend: {exc}")
        return False
    if resp.status_code == 200:
        data = resp.json()
        st.session_state.token = data["access_token"]
        st.session_state.user = data["user"]
        st.session_state.session_id = str(uuid.uuid4())
        return True
    return False


def stream_chat(message: str) -> Iterator[dict]:
    """Yield typed events from the backend SSE stream."""
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    with httpx.stream(
        "POST",
        f"{BACKEND_URL}/api/chat",
        json={"message": message, "session_id": st.session_state.session_id},
        headers=headers,
        timeout=None,
    ) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                try:
                    yield json.loads(line[len("data: "):])
                except json.JSONDecodeError:
                    continue


def render_activity_event(event: dict) -> str:
    """Format one activity event as a compact markdown line."""
    etype = event["type"]
    payload = event.get("payload", {})
    if etype == "agent_state":
        node = payload.get("node", "?")
        msg = payload.get("message", "")
        icon = "🧭" if node == "supervisor" else "🔄"
        return f"**`{node}`** — {msg}"
    if etype == "tool_call":
        status = payload.get("status", "?")
        tool = payload.get("tool", "?")
        if status == "started":
            return f"🛠️ Tool call `{tool}` started…"
        if status == "success":
            return f"✅ Tool `{tool}` completed in {payload.get('duration_ms', 0)} ms"
        if status == "denied":
            return f"⛔ Tool `{tool}` DENIED: {payload.get('error', '')}"
        return f"❌ Tool `{tool}` failed: {payload.get('error', '')}"
    if etype == "retrieval":
        return f"🔎 Retrieval — {payload.get('hits', 0)} hits ({payload.get('status', '?')})"
    if etype == "memory":
        return f"🧠 Memory — {payload.get('message', '')}"
    if etype == "validation":
        status = payload.get("status", "?")
        return f"🛡️ Validation — {status}"
    if etype == "final":
        return "🎯 Final response generated."
    if etype == "error":
        return f"💥 Error — {payload.get('message', '')}"
    return f"• {etype}"


# --------------------------------------------------------------------------- #
# Login screen
# --------------------------------------------------------------------------- #
if not st.session_state.token:
    st.title("🤖 Enterprise AI Assistant")
    st.caption("Sign in to continue. Demo users are listed below.")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        if login(username, password):
            st.rerun()
        else:
            st.error("Invalid credentials.")
    st.info(
        "Demo users:\n\n"
        "- `viewer` / `viewer123` — chat + search only\n"
        "- `analyst` / `analyst123` — search, analytics, MCP tools\n"
        "- `admin` / `admin123` — all tools"
    )
    st.stop()

# --------------------------------------------------------------------------- #
# Main UI
# --------------------------------------------------------------------------- #
user = st.session_state.user
st.title("🤖 Enterprise AI Assistant")
st.caption(
    f"Signed in as **{user['username']}** (role: `{user['role']}`) · "
    "Activity panel on the right shows exactly what the agent is doing."
)

col_chat, col_activity = st.columns([3, 2])

with col_activity:
    st.subheader("Agent Activity")
    activity_box = st.empty()

with col_chat:
    chat_box = st.container()

    # Render history.
    with chat_box:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("citations"):
                    st.caption("Sources: " + ", ".join(f"`{c}`" for c in msg["citations"]))

    prompt = st.chat_input("Ask about policies, incidents, architecture, employees…")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_box:
            with st.chat_message("user"):
                st.markdown(prompt)

        # Clear activity for the new turn.
        st.session_state.activity = []
        answer = ""
        citations: list[str] = []
        answer_placeholder = None

        with chat_box:
            with st.chat_message("assistant"):
                answer_placeholder = st.empty()

        def _render_activity() -> None:
            lines = [render_activity_event(e) for e in st.session_state.activity]
            activity_box.markdown("\n\n".join(lines[-25:]) or "_waiting for events…_")

        try:
            for event in stream_chat(prompt):
                st.session_state.activity.append(event)
                _render_activity()
                if event["type"] == "final":
                    answer = event["payload"].get("answer", "")
                    citations = event["payload"].get("citations", [])
                elif event["type"] == "error":
                    answer = f"⚠️ {event['payload'].get('message', 'error')}"
        except httpx.HTTPError as exc:
            answer = f"⚠️ Backend connection error: {exc}"

        # Streaming display of the final answer.
        if answer_placeholder is not None:
            words = answer.split(" ")
            displayed = ""
            for i in range(0, len(words), 4):
                displayed = " ".join(words[: i + 4])
                answer_placeholder.markdown(displayed)
                time.sleep(0.02)
            answer_placeholder.markdown(answer)
            if citations:
                answer_placeholder.caption("Sources: " + ", ".join(f"`{c}`" for c in citations))

        st.session_state.messages.append(
            {"role": "assistant", "content": answer, "citations": citations}
        )

with col_activity:
    st.caption(
        "Event types: `agent_state`, `tool_call`, `retrieval`, `memory`, "
        "`validation`, `final`, `error`."
    )
