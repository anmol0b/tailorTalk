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

# No emails in prompts — agent will ask for missing details naturally
EXAMPLE_PROMPTS = [
    ("📅", "Book a meeting",    "Book a 30-minute call tomorrow at 3 PM about design review"),
    ("📋", "Show my schedule",  "Show my upcoming meetings"),
    ("⏰", "Plan next week",    "Schedule a 1-hour sprint planning next Monday at 10 AM"),
    ("❓", "Get help",          "What can you do?"),
]


def inject_styles():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] { font-family: 'Sora', sans-serif !important; }

/* ── Background ── */
[data-testid="stAppViewContainer"] { background: #080810; }
[data-testid="stAppViewContainer"] > .main { background: transparent; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0d0d16 !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
[data-testid="stSidebar"] section { padding-top: 1.25rem !important; }

/* ── Header ── */
.tt-header {
    position: relative;
    overflow: hidden;
    background: linear-gradient(135deg, #0d1b3e 0%, #0a1628 40%, #060d1f 100%);
    border: 1px solid rgba(99,179,237,0.15);
    border-radius: 20px;
    padding: 1.75rem 2rem;
    margin-bottom: 1.5rem;
}
.tt-header::before {
    content: '';
    position: absolute; top: -80px; right: -80px;
    width: 280px; height: 280px;
    background: radial-gradient(circle, rgba(99,179,237,0.08) 0%, transparent 65%);
    border-radius: 50%; pointer-events: none;
}
.tt-header::after {
    content: '';
    position: absolute; bottom: -40px; left: 30%;
    width: 180px; height: 180px;
    background: radial-gradient(circle, rgba(167,139,250,0.06) 0%, transparent 65%);
    border-radius: 50%; pointer-events: none;
}
.tt-eyebrow {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem; letter-spacing: 0.18em;
    text-transform: uppercase; color: #63b3ed; opacity: 0.85;
    margin-bottom: 0.6rem;
}
.tt-heading {
    font-size: clamp(1.4rem, 2.5vw, 1.9rem);
    font-weight: 700; color: #eef2ff;
    margin: 0 0 0.45rem; line-height: 1.15; letter-spacing: -0.02em;
}
.tt-heading span {
    background: linear-gradient(90deg, #63b3ed, #a78bfa);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}
.tt-sub { font-size: 0.875rem; color: #4a5568; margin: 0 0 1rem; }
.tt-chips { display: flex; gap: 0.45rem; flex-wrap: wrap; }
.tt-chip {
    font-family: 'JetBrains Mono', monospace; font-size: 0.62rem;
    padding: 0.22rem 0.65rem; border-radius: 999px;
    border: 1px solid rgba(99,179,237,0.2);
    color: #63b3ed; background: rgba(99,179,237,0.05);
}
.tt-chip.online  { border-color: rgba(72,187,120,0.3); color: #48bb78; background: rgba(72,187,120,0.06); }
.tt-chip.offline { border-color: rgba(252,129,129,0.3); color: #fc8181; background: rgba(252,129,129,0.06); }

/* ── Status card ── */
.tt-status {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px; padding: 0.8rem 1rem; margin-bottom: 1rem;
}
.tt-status-row {
    display: flex; align-items: center; gap: 0.5rem;
    font-size: 0.82rem; color: #a0aec0;
}
.tt-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.tt-dot-on  { background: #48bb78; box-shadow: 0 0 8px rgba(72,187,120,0.5); }
.tt-dot-off { background: #fc8181; box-shadow: 0 0 8px rgba(252,129,129,0.5); }
.tt-latency {
    margin-left: auto; font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem; color: #2d3748;
}
.tt-cal-name {
    font-size: 0.72rem; color: #2d3748; margin-top: 0.35rem;
    font-family: 'JetBrains Mono', monospace; padding-left: 1.2rem;
}

/* ── Sidebar labels ── */
[data-testid="stSidebar"] h3 {
    font-size: 0.68rem !important; font-weight: 600 !important;
    letter-spacing: 0.14em !important; text-transform: uppercase !important;
    color: #2d3748 !important; font-family: 'JetBrains Mono', monospace !important;
    margin-bottom: 0.5rem !important;
}

/* ── Prompt buttons ── */
.stButton > button {
    width: 100% !important;
    background: rgba(255,255,255,0.02) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 10px !important;
    color: #718096 !important;
    font-size: 0.78rem !important;
    font-family: 'Sora', sans-serif !important;
    text-align: left !important;
    padding: 0.55rem 0.85rem !important;
    transition: all 0.12s ease !important;
    white-space: normal !important;
    height: auto !important; line-height: 1.4 !important;
}
.stButton > button:hover {
    background: rgba(99,179,237,0.06) !important;
    border-color: rgba(99,179,237,0.25) !important;
    color: #90cdf4 !important;
    transform: translateX(2px) !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    background: rgba(255,255,255,0.025) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 14px !important;
    margin-bottom: 0.5rem !important;
}

/* ── Chat input ── */
[data-testid="stChatInputTextArea"] textarea {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 14px !important;
    color: #e2e8f0 !important;
    font-family: 'Sora', sans-serif !important;
    font-size: 0.9rem !important;
    transition: border-color 0.15s !important;
}
[data-testid="stChatInputTextArea"] textarea:focus {
    border-color: rgba(99,179,237,0.4) !important;
    box-shadow: 0 0 0 2px rgba(99,179,237,0.08) !important;
}

/* ── Offline banner ── */
.tt-offline {
    background: rgba(254,100,100,0.05);
    border: 1px solid rgba(252,129,129,0.18);
    border-radius: 12px; padding: 0.75rem 1rem;
    color: #fc8181; font-size: 0.85rem; margin-bottom: 1.25rem;
}
.tt-offline code {
    background: rgba(255,255,255,0.08);
    padding: 0.1rem 0.35rem; border-radius: 4px;
    font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
}

/* ── Welcome ── */
.tt-welcome {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 4rem 1rem 3rem; text-align: center;
}
.tt-welcome-glyph { font-size: 2.8rem; margin-bottom: 1rem; opacity: 0.4; }
.tt-welcome-msg { font-size: 0.92rem; color: #2d3748; max-width: 300px; line-height: 1.65; }
.tt-welcome-hint {
    font-size: 0.72rem; color: #1a202c; margin-top: 0.6rem;
    font-family: 'JetBrains Mono', monospace;
}

/* ── Footer ── */
.tt-foot {
    text-align: center; color: #1a202c; font-size: 0.68rem;
    font-family: 'JetBrains Mono', monospace;
    margin-top: 2rem; padding-top: 1rem;
    border-top: 1px solid rgba(255,255,255,0.04);
    letter-spacing: 0.08em;
}

hr { border-color: rgba(255,255,255,0.05) !important; }
</style>
    """, unsafe_allow_html=True)


def init_state():
    for k, v in {
        "messages": [],
        "backend_url": DEFAULT_BACKEND_URL,
        "queued_prompt": None,
        "pending_booking": None,
        "attempt_count": 0,
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v


def check_backend() -> Tuple[str, Optional[Dict], Optional[int]]:
    url = f"{st.session_state.backend_url.rstrip('/')}/health"
    t0 = time.perf_counter()
    try:
        r = requests.get(url, timeout=3)
        ms = int((time.perf_counter() - t0) * 1000)
        return ("online", r.json(), ms) if r.status_code == 200 else ("offline", None, ms)
    except Exception:
        return "offline", None, None


def send_message(user_input: str, history: List) -> Tuple[str, bool, Any, int]:
    url = f"{st.session_state.backend_url.rstrip('/')}/chat"
    try:
        payload = {
            "user_input": user_input,
            "chat_history": history,
            "pending_booking": st.session_state.pending_booking,
            "attempt_count": st.session_state.attempt_count,
        }
        r = requests.post(url, json=payload, timeout=35)
        if r.status_code != 200:
            return f"Backend error ({r.status_code})", False, None, 0
        body = r.json() if r.content else {}
        text     = (body.get("response") or "No response received.").strip()
        pending  = body.get("pending_booking")
        attempts = body.get("attempt_count", 0)
        return text, True, pending, attempts
    except requests.Timeout:
        return "Request timed out — please try again.", False, st.session_state.pending_booking, st.session_state.attempt_count
    except requests.ConnectionError:
        return "Cannot reach backend. Make sure `python start.py` is running.", False, None, 0
    except Exception as e:
        return f"Unexpected error: {e}", False, None, 0


def append_msg(role: str, content: str, success: Optional[bool] = None):
    st.session_state.messages.append({
        "role": role, "content": content,
        "ts": datetime.now().strftime("%H:%M"), "success": success,
    })


def process_input(text: str):
    append_msg("user", text)
    history = [(m["role"], m["content"]) for m in st.session_state.messages[:-1]]
    with st.spinner(""):
        response, ok, pending, attempts = send_message(text, history)
    st.session_state.pending_booking = pending
    st.session_state.attempt_count   = attempts
    append_msg("assistant", response, success=ok)


def render_sidebar(status: str, health: Optional[Dict], latency: Optional[int]):
    with st.sidebar:
        st.markdown("### Status")

        dot = "tt-dot-on" if status == "online" else "tt-dot-off"
        lat = f"{latency}ms" if latency else "n/a"
        cal_html = ""
        if health and isinstance(health.get("calendar"), dict):
            name = health["calendar"].get("summary", "")
            if name:
                cal_html = f'<div class="tt-cal-name">📅 {name}</div>'

        st.markdown(f"""
<div class="tt-status">
  <div class="tt-status-row">
    <span class="tt-dot {dot}"></span>
    <span>Backend <strong style="color:#e2e8f0">{status}</strong></span>
    <span class="tt-latency">{lat}</span>
  </div>
  {cal_html}
</div>
        """, unsafe_allow_html=True)

        with st.expander("⚙️ Backend URL", expanded=False):
            with st.form("url_form"):
                url_in = st.text_input("URL", value=st.session_state.backend_url, label_visibility="collapsed")
                if st.form_submit_button("Apply", use_container_width=True):
                    st.session_state.backend_url = url_in.rstrip("/")
                    st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            if st.button("↺ Refresh", use_container_width=True):
                st.rerun()
        with c2:
            if st.button("✕ Clear", use_container_width=True):
                st.session_state.messages = []
                st.session_state.pending_booking = None
                st.session_state.attempt_count = 0
                st.rerun()

        st.markdown("---")
        st.markdown("### Quick actions")
        for i, (icon, label, prompt) in enumerate(EXAMPLE_PROMPTS):
            if st.button(f"{icon}  {label}", key=f"qp_{i}", use_container_width=True):
                st.session_state.queued_prompt = prompt
                st.rerun()

        if health:
            st.markdown("---")
            st.markdown("### Services")
            st.json({
                "calendar": "✅ connected" if health.get("calendar_available") else "❌ unavailable",
                "agent":    "✅ ready"     if health.get("agent_available")    else "❌ unavailable",
            })


def render_header(status: str):
    chip = '<span class="tt-chip online">● Connected</span>' if status == "online" \
           else '<span class="tt-chip offline">● Offline</span>'
    st.markdown(f"""
<div class="tt-header">
  <div class="tt-eyebrow">TailorTalk · Calendar Assistant</div>
  <h1 class="tt-heading">Book meetings in <span>plain English</span></h1>
  <p class="tt-sub">Just describe what you need — I'll handle the rest.</p>
  <div class="tt-chips">
    {chip}
    <span class="tt-chip">Google Calendar</span>
    <span class="tt-chip">LLaMA 4 Scout</span>
    <span class="tt-chip">FastAPI</span>
  </div>
</div>
    """, unsafe_allow_html=True)


def render_messages():
    if not st.session_state.messages:
        st.markdown("""
<div class="tt-welcome">
  <div class="tt-welcome-glyph">🗓️</div>
  <div class="tt-welcome-msg">Describe a meeting and I'll book it — or ask to see your schedule.</div>
  <div class="tt-welcome-hint">← try a quick action to start</div>
</div>
        """, unsafe_allow_html=True)
        return

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("ts"):
                suffix = (" · ✓" if msg.get("success") else " · error") if msg["role"] == "assistant" else ""
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
  ⚠️ Backend offline — run <code>python start.py</code> and check your <code>.env</code>
</div>
        """, unsafe_allow_html=True)

    render_messages()

    if st.session_state.queued_prompt:
        prompt = st.session_state.queued_prompt
        st.session_state.queued_prompt = None
        process_input(prompt)
        st.rerun()

    if user_input := st.chat_input("Describe a meeting or ask about your schedule..."):
        process_input(user_input)
        st.rerun()

    st.markdown('<div class="tt-foot">TAILORTALK · AI CALENDAR ASSISTANT</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()