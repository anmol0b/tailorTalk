import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

st.set_page_config(
    page_title="TailorTalk",
    page_icon="🗓️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULT_BACKEND_URL = os.getenv("TAILORTALK_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

EXAMPLE_PROMPTS = [
    "📅 Book a 30-min call tomorrow at 3 PM with john@example.com about design review",
    "📋 Show my upcoming meetings",
    "⏰ Schedule a 1-hour sprint planning next Monday at 10 AM with team@company.com",
    "🔍 What meetings do I have this week?",
]


def inject_styles():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

* { font-family: 'DM Sans', sans-serif; }

[data-testid="stAppViewContainer"] {
    background: #0e0e10;
    color: #e8e8e8;
}
[data-testid="stSidebar"] {
    background: #151518 !important;
    border-right: 1px solid #2a2a2e;
}
[data-testid="stSidebar"] * { color: #c8c8d0 !important; }

/* Header */
.tt-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    border: 1px solid #1e3a5f;
    border-radius: 16px;
    padding: 1.5rem 1.75rem;
    margin-bottom: 1.25rem;
    position: relative;
    overflow: hidden;
}
.tt-header::before {
    content: '';
    position: absolute;
    top: -60px; right: -60px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(99,179,237,0.12) 0%, transparent 70%);
    border-radius: 50%;
}
.tt-badge {
    font-family: 'DM Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #63b3ed;
    margin-bottom: 0.5rem;
}
.tt-title {
    font-size: 1.65rem;
    font-weight: 600;
    color: #f0f4f8;
    margin: 0 0 0.4rem 0;
    line-height: 1.2;
}
.tt-sub {
    font-size: 0.9rem;
    color: #718096;
    margin: 0;
}
.tt-pills {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-top: 1rem;
}
.tt-pill {
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    border: 1px solid #2d4a6b;
    color: #63b3ed;
    background: rgba(99,179,237,0.07);
}

/* Status card */
.tt-status-card {
    background: #1a1a1e;
    border: 1px solid #2a2a2e;
    border-radius: 12px;
    padding: 0.85rem 1rem;
    margin-bottom: 1rem;
}
.tt-status-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
}
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-on  { background: #48bb78; box-shadow: 0 0 6px #48bb7888; }
.dot-off { background: #fc8181; box-shadow: 0 0 6px #fc818188; }
.tt-meta { font-size: 0.75rem; color: #555560; margin-top: 0.35rem; font-family: 'DM Mono', monospace; }

/* Chat messages */
[data-testid="stChatMessage"] {
    background: #18181c !important;
    border: 1px solid #2a2a2e !important;
    border-radius: 12px !important;
}

/* Input */
[data-testid="stChatInputTextArea"] textarea {
    background: #18181c !important;
    border: 1px solid #2a2a2e !important;
    border-radius: 12px !important;
    color: #e8e8e8 !important;
    font-family: 'DM Sans', sans-serif !important;
}
[data-testid="stChatInputTextArea"] textarea:focus {
    border-color: #4a9edd !important;
}

/* Quick prompts */
.stButton > button {
    background: #1a1a1e !important;
    border: 1px solid #2a2a2e !important;
    color: #c8c8d0 !important;
    border-radius: 10px !important;
    font-size: 0.78rem !important;
    text-align: left !important;
    padding: 0.5rem 0.75rem !important;
    transition: all 0.15s ease !important;
    white-space: normal !important;
    height: auto !important;
}
.stButton > button:hover {
    border-color: #4a9edd !important;
    color: #63b3ed !important;
    background: #1a2535 !important;
}

/* Offline banner */
.tt-offline {
    background: #2d1515;
    border: 1px solid #7b2020;
    border-radius: 10px;
    padding: 0.75rem 1rem;
    color: #fc8181;
    font-size: 0.875rem;
    margin-bottom: 1rem;
}

/* Welcome */
.tt-welcome {
    text-align: center;
    padding: 3rem 1rem;
    color: #444450;
}
.tt-welcome-icon { font-size: 3rem; margin-bottom: 0.75rem; }
.tt-welcome-title { font-size: 1.1rem; font-weight: 500; color: #666670; margin-bottom: 0.5rem; }
.tt-welcome-hint { font-size: 0.85rem; color: #3a3a44; }

.tt-foot {
    text-align: center;
    color: #333340;
    font-size: 0.75rem;
    font-family: 'DM Mono', monospace;
    margin-top: 1.5rem;
    padding-top: 1rem;
    border-top: 1px solid #1e1e22;
}
</style>
    """, unsafe_allow_html=True)


def init_state():
    defaults = {
        "messages": [],
        "backend_url": DEFAULT_BACKEND_URL,
        "queued_prompt": None,
        "calendar_id": os.getenv("GOOGLE_CALENDAR_ID", ""),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def check_backend() -> Tuple[str, Optional[Dict], Optional[int]]:
    url = f"{st.session_state.backend_url.rstrip('/')}/health"
    t0 = time.perf_counter()
    try:
        r = requests.get(url, timeout=3)
        ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code == 200:
            return "online", r.json(), ms
        return "offline", None, ms
    except Exception:
        return "offline", None, None


def send_message(user_input: str, history: List) -> Tuple[str, bool]:
    url = f"{st.session_state.backend_url.rstrip('/')}/chat"
    try:
        r = requests.post(url, json={"user_input": user_input, "chat_history": history}, timeout=35)
        if r.status_code != 200:
            return f"Backend error ({r.status_code})", False
        body = r.json() if r.content else {}
        return (body.get("response") or "No response received.").strip(), True
    except requests.Timeout:
        return "Request timed out — please try again.", False
    except requests.ConnectionError:
        return "Cannot reach backend. Make sure `python start.py` is running.", False
    except Exception as e:
        return f"Unexpected error: {e}", False


def append_msg(role: str, content: str, success: Optional[bool] = None):
    st.session_state.messages.append({
        "role": role,
        "content": content,
        "ts": datetime.now().strftime("%H:%M"),
        "success": success,
    })


def process_input(user_input: str):
    append_msg("user", user_input)
    history = [(m["role"], m["content"]) for m in st.session_state.messages[:-1]]
    with st.spinner(""):
        response, ok = send_message(user_input, history)
    append_msg("assistant", response, success=ok)


def render_sidebar(status: str, health: Optional[Dict], latency: Optional[int]):
    with st.sidebar:
        st.markdown("### ⚙️ Settings")

        dot = "dot-on" if status == "online" else "dot-off"
        lat = f"{latency}ms" if latency else "n/a"
        cal_info = ""
        if health and health.get("calendar"):
            cal = health["calendar"]
            cal_name = cal.get("summary", "")
            if cal_name:
                cal_info = f'<div class="tt-meta">📅 {cal_name}</div>'

        st.markdown(f"""
<div class="tt-status-card">
  <div class="tt-status-row">
    <span class="dot {dot}"></span>
    <strong>Backend {status}</strong>
    <span style="margin-left:auto;font-family:'DM Mono',monospace;font-size:0.72rem;color:#555">{lat}</span>
  </div>
  {cal_info}
</div>
        """, unsafe_allow_html=True)

        with st.expander("Backend URL", expanded=False):
            with st.form("url_form"):
                url_input = st.text_input("URL", value=st.session_state.backend_url, label_visibility="collapsed")
                if st.form_submit_button("Apply", use_container_width=True):
                    st.session_state.backend_url = url_input.rstrip("/")
                    st.rerun()

        col1, col2 = st.columns(2)
        with col1:
            if st.button("↺ Refresh", use_container_width=True):
                st.rerun()
        with col2:
            if st.button("✕ Clear", use_container_width=True):
                st.session_state.messages = []
                st.rerun()

        st.markdown("---")
        st.markdown("### 💬 Quick Prompts")
        for i, p in enumerate(EXAMPLE_PROMPTS):
            if st.button(p, key=f"qp_{i}", use_container_width=True):
                # Strip the emoji prefix before sending
                clean = re.sub(r'^[^\w]+', '', p).strip()
                st.session_state.queued_prompt = clean
                st.rerun()

        if health:
            st.markdown("---")
            st.markdown("### 🔍 Health")
            st.json({
                "calendar": health.get("calendar_available"),
                "agent": health.get("agent_available"),
            })


def render_header(status: str):
    status_label = "● Connected" if status == "online" else "● Offline"
    st.markdown(f"""
<div class="tt-header">
  <div class="tt-badge">TailorTalk · Calendar Assistant</div>
  <h1 class="tt-title">Book meetings in plain English</h1>
  <p class="tt-sub">Powered by Google Calendar · LangChain · Groq LLaMA</p>
  <div class="tt-pills">
    <span class="tt-pill">{status_label}</span>
    <span class="tt-pill">Google Calendar</span>
    <span class="tt-pill">LLaMA 4 Scout</span>
    <span class="tt-pill">FastAPI</span>
  </div>
</div>
    """, unsafe_allow_html=True)


def render_messages():
    if not st.session_state.messages:
        st.markdown("""
<div class="tt-welcome">
  <div class="tt-welcome-icon">🗓️</div>
  <div class="tt-welcome-title">No messages yet</div>
  <div class="tt-welcome-hint">Try a quick prompt on the left, or type below</div>
</div>
        """, unsafe_allow_html=True)
        return

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("ts"):
                suffix = ""
                if msg["role"] == "assistant":
                    suffix = " · ✓" if msg.get("success") else " · ✗ error"
                st.caption(f"{msg['ts']}{suffix}")


def main():
    inject_styles()
    init_state()

    status, health, latency = check_backend()
    render_sidebar(status, health, latency)
    render_header(status)

    if status != "online":
        st.markdown("""
<div class="tt-offline">
  ⚠️ Backend offline — run <code>python start.py</code> and make sure your <code>.env</code> is configured.
</div>
        """, unsafe_allow_html=True)

    render_messages()

    # Handle queued prompt from sidebar buttons
    if st.session_state.queued_prompt:
        prompt = st.session_state.queued_prompt
        st.session_state.queued_prompt = None
        process_input(prompt)
        st.rerun()

    if user_input := st.chat_input("Book a meeting, check your schedule..."):
        process_input(user_input)
        st.rerun()

    st.markdown('<div class="tt-foot">TailorTalk · AI Calendar Assistant</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()