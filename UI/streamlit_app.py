import streamlit as st
import httpx
import uuid
import time
import os

# =====================================================
# PAGE CONFIG
# =====================================================

st.set_page_config(
    page_title="EY Knowledge Assistant",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================
# CUSTOM CSS — Clean white, EY brand, professional
# =====================================================

st.markdown("""
<style>

/* ---------- Reset & Base ---------- */
*, *::before, *::after { box-sizing: border-box; }

html, body, .stApp {
    background-color: #ffffff;
    color: #1a1a1a;
    font-family: "Inter", "ui-sans-serif", "system-ui", -apple-system, sans-serif;
}

/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }
[data-testid="stToolbar"] { display: none; }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
    background-color: #f9f9f9;
    border-right: 1px solid #e8e8e8;
    width: 260px !important;
}

[data-testid="stSidebar"] .block-container {
    padding: 1.25rem 0.85rem;
}

/* Sidebar brand */
.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 0.5rem 1.25rem;
    margin-bottom: 0.25rem;
    border-bottom: 1px solid #e8e8e8;
}

.sidebar-logo {
    width: 32px;
    height: 32px;
    background: #FFE600;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 800;
    color: #1a1a1a;
    flex-shrink: 0;
    letter-spacing: -0.5px;
}

.sidebar-name {
    font-size: 14px;
    font-weight: 600;
    color: #1a1a1a;
    letter-spacing: -0.2px;
}

.sidebar-name span {
    display: block;
    font-size: 11px;
    font-weight: 400;
    color: #888;
    letter-spacing: 0;
    margin-top: 1px;
}

/* New Chat button */
[data-testid="stSidebar"] .stButton:first-of-type > button {
    background-color: #FFE600;
    border: none;
    color: #1a1a1a;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    padding: 0.55rem 0.9rem;
    width: 100%;
    text-align: center;
    transition: background 0.15s, box-shadow 0.15s;
    margin: 1rem 0 0.5rem;
    cursor: pointer;
    letter-spacing: -0.1px;
}

[data-testid="stSidebar"] .stButton:first-of-type > button:hover {
    background-color: #f5db00;
    box-shadow: 0 2px 8px rgba(255,230,0,0.35);
}

/* Section label in sidebar */
.history-label {
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #aaa;
    padding: 0 0.6rem;
    margin: 1rem 0 0.4rem;
    display: block;
}

/* Chat history item buttons */
div[data-testid="column"]:first-child .stButton > button {
    background: transparent;
    border: none;
    color: #444;
    font-size: 13px;
    padding: 0.45rem 0.7rem;
    width: 100%;
    text-align: left;
    border-radius: 7px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: background 0.12s, color 0.12s;
    font-weight: 400;
}

div[data-testid="column"]:first-child .stButton > button:hover {
    background: #f0f0f0;
    color: #1a1a1a;
}

/* Delete button */
div[data-testid="column"]:last-child .stButton > button {
    background: transparent;
    border: none;
    color: #ccc;
    font-size: 16px;
    padding: 0.3rem 0.4rem;
    border-radius: 5px;
    line-height: 1;
    transition: color 0.12s, background 0.12s;
}

div[data-testid="column"]:last-child .stButton > button:hover {
    color: #e53e3e;
    background: #fff0f0;
}

[data-testid="stSidebar"] hr {
    border-color: #e8e8e8;
    margin: 0.5rem 0;
}

/* ---------- Main area ---------- */
.block-container {
    max-width: 780px;
    margin: 0 auto;
    padding: 2.5rem 1.5rem 9rem;
}

/* Page header */
.page-header {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 0.4rem;
    padding-bottom: 1.25rem;
    border-bottom: 1px solid #f0f0f0;
    margin-bottom: 1.5rem;
}

.page-header-logo {
    width: 40px;
    height: 40px;
    background: #FFE600;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    font-weight: 800;
    color: #1a1a1a;
    flex-shrink: 0;
}

.page-title {
    font-size: 22px;
    font-weight: 700;
    color: #1a1a1a;
    letter-spacing: -0.5px;
    line-height: 1.2;
}

.page-subtitle {
    font-size: 13px;
    color: #888;
    margin-top: 2px;
    font-weight: 400;
}

/* ---------- Messages ---------- */

/* User bubble */
.user-msg {
    display: flex;
    justify-content: flex-end;
    margin: 1.25rem 0 0.75rem;
}

.user-bubble {
    background-color: #1a1a1a;
    color: #fff;
    border-radius: 18px 18px 4px 18px;
    padding: 12px 18px;
    max-width: 78%;
    font-size: 14.5px;
    line-height: 1.6;
}

/* Assistant bubble */
.assistant-msg {
    display: flex;
    gap: 12px;
    margin: 0.75rem 0;
    align-items: flex-start;
}

.assistant-avatar {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    background: #FFE600;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 800;
    color: #1a1a1a;
    margin-top: 1px;
    letter-spacing: -0.3px;
}

.assistant-bubble {
    color: #1a1a1a;
    font-size: 14.5px;
    line-height: 1.75;
    max-width: calc(100% - 44px);
    padding: 4px 0;
}

.assistant-bubble p { margin: 0 0 0.75em; }
.assistant-bubble p:last-child { margin: 0; }

.assistant-bubble ul, .assistant-bubble ol {
    margin: 0.5em 0;
    padding-left: 1.4em;
}

.assistant-bubble li { margin-bottom: 0.3em; }

.assistant-bubble strong { color: #1a1a1a; font-weight: 600; }

.assistant-bubble code {
    background: #f4f4f4;
    border: 1px solid #e8e8e8;
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 13px;
    font-family: "SF Mono", "Consolas", monospace;
}

/* ---------- Sources ---------- */
.sources-wrap {
    margin-left: 44px;
    margin-top: 0.6rem;
    margin-bottom: 1.25rem;
}

.sources-label {
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #aaa;
    margin-bottom: 0.45rem;
    font-weight: 500;
}

.sources-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.source-pill {
    background: #fafafa;
    border: 1px solid #e8e8e8;
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 12px;
    color: #666;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 220px;
    transition: border-color 0.12s, color 0.12s, background 0.12s;
}

.source-pill:hover {
    border-color: #FFE600;
    background: #fffce0;
    color: #333;
}

/* ---------- Message divider ---------- */
.msg-divider {
    border: none;
    border-top: 1px solid #f0f0f0;
    margin: 0.25rem 0;
}

/* ---------- Chat input ---------- */
[data-testid="stChatInput"] {
    position: fixed;
    bottom: 0;
    left: 260px;
    right: 0;
    padding: 1rem 2rem 1.5rem;
    background: linear-gradient(to top, #ffffff 75%, rgba(255,255,255,0));
    z-index: 100;
}

[data-testid="stChatInput"] > div {
    max-width: 780px;
    margin: 0 auto;
}

[data-testid="stChatInputTextArea"] {
    background: #f7f7f7 !important;
    border: 1.5px solid #e0e0e0 !important;
    border-radius: 14px !important;
    color: #1a1a1a !important;
    font-size: 14.5px !important;
    padding: 14px 18px !important;
    box-shadow: none !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}

[data-testid="stChatInputTextArea"]:focus {
    border-color: #FFE600 !important;
    box-shadow: 0 0 0 3px rgba(255,230,0,0.15) !important;
    background: #fff !important;
}

/* ---------- Empty state ---------- */
.empty-state {
    text-align: center;
    padding: 4rem 1rem 2rem;
    color: #bbb;
}

.empty-icon {
    width: 56px;
    height: 56px;
    background: #f5f5f5;
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    margin: 0 auto 1rem;
}

.empty-title {
    font-size: 16px;
    font-weight: 600;
    color: #444;
    margin-bottom: 0.4rem;
}

.empty-sub {
    font-size: 13.5px;
    color: #aaa;
    max-width: 340px;
    margin: 0 auto;
    line-height: 1.6;
}

/* ---------- Suggestion chips ---------- */
.chips-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    margin-top: 1.5rem;
}

.chip {
    background: #fafafa;
    border: 1px solid #e8e8e8;
    border-radius: 20px;
    padding: 7px 16px;
    font-size: 13px;
    color: #555;
    cursor: pointer;
    transition: border-color 0.12s, background 0.12s, color 0.12s;
}

.chip:hover {
    border-color: #FFE600;
    background: #fffce0;
    color: #1a1a1a;
}

/* ---------- Error message ---------- */
.error-bubble {
    background: #fff5f5;
    border: 1px solid #fecaca;
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 13.5px;
    color: #c0392b;
    margin-top: 0.5rem;
}

/* ---------- Thinking indicator ---------- */
.thinking-dots {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    padding: 6px 2px;
}
.thinking-dots span {
    width: 6px;
    height: 6px;
    background: #ccc;
    border-radius: 50%;
    animation: bounce 1.2s infinite ease-in-out;
}
.thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
    0%, 80%, 100% { transform: scale(0.7); opacity: 0.4; }
    40% { transform: scale(1); opacity: 1; }
}

/* ---------- Scrollbar ---------- */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: #f9f9f9; }
::-webkit-scrollbar-thumb { background: #e0e0e0; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #ccc; }

/* ---------- Active chat in sidebar ---------- */
.active-chat-btn button {
    background: #fff !important;
    color: #1a1a1a !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08) !important;
}

</style>
""", unsafe_allow_html=True)


# =====================================================
# HELPERS
# =====================================================

def new_chat_id():
    return str(uuid.uuid4())


def truncate_title(text, max_len=38):
    text = text.strip()
    return (text[:max_len] + "…") if len(text) > max_len else text


def safe_html(text):
    """Escape user content to prevent XSS when rendered in HTML blocks."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# =====================================================
# SESSION STATE INIT
# =====================================================

if "session_id" not in st.session_state:
    st.session_state.session_id = f"streamlit_{uuid.uuid4()}"

if "chats" not in st.session_state:
    cid = new_chat_id()
    st.session_state.chats = {
        cid: {"title": "New conversation", "messages": []}
    }
    st.session_state.current_chat = cid

# Guard: ensure current_chat key still exists
if st.session_state.current_chat not in st.session_state.chats:
    st.session_state.current_chat = list(st.session_state.chats.keys())[0]


# =====================================================
# SIDEBAR
# =====================================================

with st.sidebar:

    st.markdown("""
    <div class="sidebar-brand">
        <div class="sidebar-logo">EY</div>
        <div class="sidebar-name">
            Knowledge
            <span>Middle East</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("＋  New conversation", key="new_chat_btn"):
        cid = new_chat_id()
        st.session_state.chats[cid] = {"title": "New conversation", "messages": []}
        st.session_state.current_chat = cid
        st.rerun()

    st.markdown('<span class="history-label">Recent</span>', unsafe_allow_html=True)

    for chat_id, chat_data in list(reversed(list(st.session_state.chats.items()))):
        is_active = (chat_id == st.session_state.current_chat)
        title = chat_data["title"]

        col1, col2 = st.columns([10, 1], gap="small")

        with col1:
            label = f"**{title}**" if is_active else title
            btn_key = f"open_{chat_id}"
            if st.button(label, key=btn_key, use_container_width=True):
                st.session_state.current_chat = chat_id
                st.rerun()

        with col2:
            if st.button("×", key=f"del_{chat_id}"):
                del st.session_state.chats[chat_id]
                if not st.session_state.chats:
                    cid = new_chat_id()
                    st.session_state.chats[cid] = {"title": "New conversation", "messages": []}
                    st.session_state.current_chat = cid
                else:
                    st.session_state.current_chat = list(st.session_state.chats.keys())[-1]
                st.rerun()


# =====================================================
# MAIN AREA
# =====================================================

current_chat = st.session_state.chats[st.session_state.current_chat]
messages = current_chat["messages"]

# Header
st.markdown("""
<div class="page-header">
    <div class="page-header-logo">EY</div>
    <div>
        <div class="page-title">Knowledge Assistant</div>
        <div class="page-subtitle">Ask anything about EY Middle East projects and knowledge base</div>
    </div>
</div>
""", unsafe_allow_html=True)


# =====================================================
# DISPLAY MESSAGES
# =====================================================



for i, msg in enumerate(messages):
    if msg["role"] == "user":
        st.markdown(f"""
        <div class="user-msg">
            <div class="user-bubble">{safe_html(msg["content"])}</div>
        </div>
        """, unsafe_allow_html=True)

    else:
        is_error = msg["content"].startswith("⚠️")
        if is_error:
            st.markdown(f"""
            <div class="assistant-msg">
                <div class="assistant-avatar">EY</div>
                <div class="error-bubble">{safe_html(msg["content"])}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="assistant-msg">
                <div class="assistant-avatar">EY</div>
                <div class="assistant-bubble">{msg["content"]}</div>
            </div>
            """, unsafe_allow_html=True)

        citations = msg.get("citations", [])
        if citations:
            pills_html = "".join(
                f'<div class="source-pill">📄 {safe_html(s.get("source_file", "Source"))}</div>'
                for s in citations
            )
            st.markdown(f"""
            <div class="sources-wrap">
                <div class="sources-label">Sources</div>
                <div class="sources-row">{pills_html}</div>
            </div>
            """, unsafe_allow_html=True)


# =====================================================
# CHAT INPUT
# =====================================================

prompt = st.chat_input("Ask about EY Middle East…")

if prompt and prompt.strip():
    prompt = prompt.strip()

    # Auto-title from first user message
    if current_chat["title"] == "New conversation":
        current_chat["title"] = truncate_title(prompt)

    current_chat["messages"].append({"role": "user", "content": prompt})
    st.rerun()


# =====================================================
# CALL BACKEND & STREAM RESPONSE
# =====================================================

# Re-read messages after possible append above
messages = current_chat["messages"]

if messages and messages[-1]["role"] == "user":
    last_q = messages[-1]["content"]

    # Show thinking animation
    thinking_placeholder = st.empty()
    thinking_placeholder.markdown("""
    <div class="assistant-msg">
        <div class="assistant-avatar">EY</div>
        <div class="assistant-bubble">
            <div class="thinking-dots">
                <span></span><span></span><span></span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    try:
        api_url = os.getenv("API_URL", "http://api:8000")
        response = httpx.post(
            f"{api_url}/chat",
            json={
                "question": last_q,
                "session_id": st.session_state.session_id
            },
            timeout=120
        )
        response.raise_for_status()
        data = response.json()

        answer = data.get("answer", "No answer returned.")
        citations = data.get("citations", [])

        # Stream word by word
        words = answer.split()
        streamed = ""

        for word in words:
            streamed += word + " "
            thinking_placeholder.markdown(f"""
            <div class="assistant-msg">
                <div class="assistant-avatar">EY</div>
                <div class="assistant-bubble">{streamed}<span style="opacity:0.3">▌</span></div>
            </div>
            """, unsafe_allow_html=True)
            time.sleep(0.012)

        # Final render — clear thinking placeholder
        thinking_placeholder.empty()

        current_chat["messages"].append({
            "role": "assistant",
            "content": answer,
            "citations": citations
        })

    except httpx.TimeoutException:
        thinking_placeholder.empty()
        current_chat["messages"].append({
            "role": "assistant",
            "content": "⚠️ The request timed out. Please try again.",
            "citations": []
        })

    except httpx.ConnectError:
        thinking_placeholder.empty()
        current_chat["messages"].append({
            "role": "assistant",
            "content": "⚠️ Could not connect to the server. Make sure the API is running.",
            "citations": []
        })

    except Exception as e:
        thinking_placeholder.empty()
        current_chat["messages"].append({
            "role": "assistant",
            "content": f"⚠️ Something went wrong: {str(e)}",
            "citations": []
        })

    st.rerun()