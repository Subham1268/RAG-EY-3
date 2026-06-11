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
# CUSTOM CSS
# =====================================================

st.markdown("""
<style>

/* Dark Theme */

.stApp {
    background-color: #0f172a;
    color: white;
}

/* Main content width */

.block-container {
    max-width: 1100px;
    padding-top: 2rem;
}

/* Sidebar */

[data-testid="stSidebar"] {
    background-color: #111827;
}

/* User Message */

.user-msg {
    background-color: #1e293b;
    padding: 18px;
    border-radius: 12px;
    margin-top: 12px;
    margin-bottom: 12px;
    border: 1px solid #334155;
}

/* Assistant Message */

.assistant-msg {
    background-color: #111827;
    padding: 18px;
    border-radius: 12px;
    margin-top: 12px;
    margin-bottom: 12px;
    border: 1px solid #374151;
}

/* Source Cards */

.source-card {
    background-color: #111827;
    border: 1px solid #374151;
    border-radius: 12px;
    padding: 15px;
    text-align: center;
    margin-bottom: 10px;
    min-height: 80px;
}

/* Sidebar Buttons */

.stButton > button {
    width: 100%;
}

/* Chat Input */

[data-testid="stChatInput"] {
    margin-top: 20px;
}

</style>
""", unsafe_allow_html=True)

# =====================================================
# SESSION
# =====================================================

if "session_id" not in st.session_state:
    st.session_state.session_id = f"streamlit_{uuid.uuid4()}"

if "chats" not in st.session_state:

    first_chat = str(uuid.uuid4())

    st.session_state.chats = {
        first_chat: {
            "title": "New Chat",
            "messages": []
        }
    }

    st.session_state.current_chat = first_chat

# =====================================================
# SIDEBAR
# =====================================================

with st.sidebar:

    st.markdown("## EY Knowledge Assistant")

    if st.button("New Chat"):

        new_chat = str(uuid.uuid4())

        st.session_state.chats[new_chat] = {
            "title": "New Chat",
            "messages": []
        }

        st.session_state.current_chat = new_chat

        st.rerun()

    st.divider()

    chat_ids = list(st.session_state.chats.keys())

    for chat_id in chat_ids:

        title = st.session_state.chats[chat_id]["title"]

        col1, col2 = st.columns([5,1])

        with col1:

            if st.button(
                title,
                key=f"open_{chat_id}"
            ):
                st.session_state.current_chat = chat_id
                st.rerun()

        with col2:

            if st.button(
                "×",
                key=f"delete_{chat_id}"
            ):

                del st.session_state.chats[chat_id]

                if not st.session_state.chats:

                    new_chat = str(uuid.uuid4())

                    st.session_state.chats[new_chat] = {
                        "title": "New Chat",
                        "messages": []
                    }

                    st.session_state.current_chat = new_chat

                else:

                    st.session_state.current_chat = list(
                        st.session_state.chats.keys()
                    )[0]

                st.rerun()

# =====================================================
# MAIN AREA
# =====================================================

st.markdown("# EY Middle East Knowledge Assistant")

current_chat = st.session_state.chats[
    st.session_state.current_chat
]

messages = current_chat["messages"]

# =====================================================
# DISPLAY HISTORY
# =====================================================

for msg in messages:

    if msg["role"] == "user":

        st.markdown(
            f"""
            <div class="user-msg">
            {msg['content']}
            </div>
            """,
            unsafe_allow_html=True
        )

    else:

        st.markdown(
            f"""
            <div class="assistant-msg">
            {msg['content']}
            </div>
            """,
            unsafe_allow_html=True
        )

        citations = msg.get("citations", [])

        if citations:

            cols = st.columns(
                min(len(citations), 4)
            )

            for i, source in enumerate(citations):

                source_name = source.get(
                    "source_file",
                    "Unknown Source"
                )

                with cols[i % len(cols)]:

                    st.markdown(
                        f"""
                        <div class="source-card">
                        {source_name}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

# =====================================================
# USER INPUT
# =====================================================

prompt = st.chat_input(
    "Ask about EY Middle East projects..."
)

if prompt:

    # Auto title from first query

    if current_chat["title"] == "New Chat":

        title = prompt.strip()

        if len(title) > 40:
            title = title[:40] + "..."

        current_chat["title"] = title

    # Save user message

    current_chat["messages"].append({
        "role": "user",
        "content": prompt
    })

    st.rerun()

# =====================================================
# HANDLE LAST USER MESSAGE
# =====================================================

messages = current_chat["messages"]

if (
    messages
    and messages[-1]["role"] == "user"
):

    last_question = messages[-1]["content"]

    try:

        API_URL = os.getenv("API_URL", "http://localhost:8000")

        response = httpx.post(
            f"{API_URL}/chat",
            json={
                "question": last_question,
                "session_id": st.session_state.session_id
            },
            timeout=120
        )

        response.raise_for_status()

        data = response.json()

        answer = data.get(
            "answer",
            "No answer returned."
        )

        citations = data.get(
            "citations",
            []
        )

        placeholder = st.empty()

        streamed = ""

        for word in answer.split():

            streamed += word + " "

            placeholder.markdown(
                f"""
                <div class="assistant-msg">
                {streamed}
                </div>
                """,
                unsafe_allow_html=True
            )

            time.sleep(0.01)

        current_chat["messages"].append({
            "role": "assistant",
            "content": answer,
            "citations": citations
        })

        st.rerun()

    except Exception as e:

        current_chat["messages"].append({
            "role": "assistant",
            "content": f"Error: {str(e)}"
        })

        st.rerun()