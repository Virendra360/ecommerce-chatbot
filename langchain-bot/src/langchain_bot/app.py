import json
from pathlib import Path
from uuid import uuid4

import streamlit as st
from dotenv import load_dotenv

from langchain_bot.agent import (
    get_agent,
    get_thread_config,
    reset_agent,
)
from langchain_bot.auth import authenticate_user
from langchain_bot.context import SessionContext
from langchain_bot.gmail_tools import (
    initialize_gmail,
    is_gmail_available,
)
from langchain_bot.hitl_utils import handle_interrupt
from langchain_bot.rag_tool import initialize_vector_store


THREADS_PATH = (
    Path(__file__).resolve().parents[2]
    / "chat_threads.json"
)


def init_session():
    st.session_state.setdefault("user_email", None)
    st.session_state.setdefault("user_role", None)
    st.session_state.setdefault("conversation_id", None)
    st.session_state.setdefault("vector_store_ready", False)
    st.session_state.setdefault("gmail_ready", False)
    st.session_state.setdefault("hitl_message", None)


def render_history():
    user_email = st.session_state.user_email
    conversation_id = st.session_state.conversation_id

    if not user_email or not conversation_id:
        return

    config = get_thread_config(
        user_email,
        conversation_id,
    )

    snapshot = get_agent().get_state(config)

    for msg in snapshot.values.get("messages", []):

        if msg.type == "human":
            with st.chat_message("user"):
                st.markdown(msg.content)

        elif msg.type == "ai" and msg.content:
            with st.chat_message("assistant"):
                st.markdown(msg.content)


def load_threads(user_email):
    if not THREADS_PATH.exists():
        return []

    data = json.loads(
        THREADS_PATH.read_text(
            encoding="utf-8"
        )
    )

    return data.get(user_email, [])


def save_threads(user_email, threads):
    data = {}

    if THREADS_PATH.exists():
        data = json.loads(
            THREADS_PATH.read_text(
                encoding="utf-8"
            )
        )

    data[user_email] = threads

    THREADS_PATH.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def add_thread(user_email, conversation_id):
    threads = load_threads(user_email)

    threads.append(
        {
            "id": conversation_id,
            "label": f"Chat {conversation_id[:8]}",
        }
    )

    save_threads(
        user_email,
        threads,
    )


def start_new_conversation():
    conversation_id = str(uuid4())

    add_thread(
        st.session_state.user_email,
        conversation_id,
    )

    st.session_state.conversation_id = conversation_id

    # Clear any old HITL message when starting a new thread.
    st.session_state.hitl_message = None


def render_pending_message():
    message = st.session_state.get(
        "hitl_message"
    )

    if message:
        with st.chat_message("assistant"):
            st.markdown(message)

        st.session_state.hitl_message = None


def chat_round(user_input):
    user_email = st.session_state.user_email
    conversation_id = st.session_state.conversation_id

    if not user_email or not conversation_id:
        st.error("No active conversation.")
        return

    context = SessionContext(
        user_email=user_email,
        conversation_id=conversation_id,
        role=st.session_state.user_role or "customer",
    )

    config = get_thread_config(
        user_email,
        conversation_id,
    )

    agent = get_agent()

    try:
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": user_input,
                    }
                ]
            },
            config=config,
            context=context,
        )

        thread_id = config["configurable"]["thread_id"]

        # -------------------------------------------------
        # Check whether the graph was interrupted by HITL.
        # -------------------------------------------------

        interrupts = result.get("__interrupt__")

        if interrupts:

            interrupt_message = handle_interrupt(
                result=result,
                thread_id=thread_id,
                user_email=user_email,
            )

            if interrupt_message:
                st.session_state.hitl_message = (
                    interrupt_message
                )

            # IMPORTANT:
            # The graph is paused here.
            #
            # DO NOT invoke the agent again.
            #
            # Admin must resume this exact thread using
            # Command(resume=...).
            st.rerun()

        # -------------------------------------------------
        # Normal completed agent execution.
        # -------------------------------------------------

        st.rerun()

    except Exception as e:
        st.error(
            f"Failed to process your request: {e}"
        )


def main():
    st.set_page_config(
        page_title="LangChain Bot",
        page_icon="🤖",
    )

    st.title("LangChain Bot")
    st.caption("A simple LangChain chatbot")

    load_dotenv()

    init_session()

    # =====================================================
    # Initialize Gmail
    # =====================================================

    if not st.session_state.gmail_ready:

        st.session_state.gmail_ready = (
            initialize_gmail()
        )

        # Agent tools depend on Gmail availability,
        # so recreate the singleton after initialization.
        reset_agent()

    # =====================================================
    # Initialize policy vector store
    # =====================================================

    if not st.session_state.vector_store_ready:

        try:

            with st.spinner(
                "Initializing knowledge base..."
            ):
                initialize_vector_store()

            st.session_state.vector_store_ready = True

        except Exception as e:

            st.error(
                f"Failed to initialize knowledge base: {e}"
            )

            st.stop()

    # =====================================================
    # Login
    # =====================================================

    user_email = st.session_state.user_email

    if not user_email:

        with st.form("login_form"):

            email = st.text_input("Email")

            password = st.text_input(
                "Password",
                type="password",
            )

            role = st.selectbox(
                "Role",
                ["customer", "admin"],
            )

            login = st.form_submit_button(
                "Login"
            )

            if login:

                user = authenticate_user(
                    email,
                    password,
                    role,
                )

                if user:

                    st.session_state.user_email = (
                        user["email"]
                    )

                    st.session_state.user_role = (
                        user["role"]
                    )

                    threads = load_threads(
                        user["email"]
                    )

                    if threads:

                        st.session_state.conversation_id = (
                            threads[0]["id"]
                        )

                    else:

                        start_new_conversation()

                    st.success(
                        "Login successful!"
                    )

                    st.rerun()

                else:

                    st.error(
                        "Invalid email, password, or role."
                    )

        return

    # =====================================================
    # Sidebar
    # =====================================================

    with st.sidebar:

        st.header("Conversations")

        if is_gmail_available():

            st.success("Gmail Enabled")

        else:

            st.warning(
                "Gmail Not configured"
            )

        if st.button(
            "Start new conversation"
        ):

            start_new_conversation()

            st.rerun()

        threads = load_threads(
            st.session_state.user_email
        )

        if threads:

            thread_ids = [
                thread["id"]
                for thread in threads
            ]

            thread_labels = {
                thread["id"]: thread["label"]
                for thread in threads
            }

            current_id = (
                st.session_state.conversation_id
            )

            selected_id = st.selectbox(
                "Select conversation",
                thread_ids,
                index=(
                    thread_ids.index(current_id)
                    if current_id in thread_ids
                    else 0
                ),
                format_func=lambda x: (
                    thread_labels[x]
                ),
            )

            if (
                selected_id
                != st.session_state.conversation_id
            ):

                st.session_state.conversation_id = (
                    selected_id
                )

                # Each conversation has its own HITL state.
                st.session_state.hitl_message = None

                st.rerun()

        else:

            st.caption(
                "No conversations yet."
            )

    # =====================================================
    # Conversation information
    # =====================================================

    conversation_id = (
        st.session_state.conversation_id
        or "—"
    )

    st.info(
        f"Logged in as: "
        f"{st.session_state.user_email} | "
        f"Role: "
        f"{st.session_state.user_role} | "
        f"Conversation: "
        f"{conversation_id}"
    )

    # =====================================================
    # Chat history
    # =====================================================

    render_history()

    # =====================================================
    # HITL pending message
    # =====================================================

    render_pending_message()

    # =====================================================
    # Chat input
    # =====================================================

    prompt = st.chat_input(
        "Ask a question"
    )

    if prompt:

        with st.chat_message("user"):
            st.markdown(prompt)

        chat_round(prompt)


if __name__ == "__main__":
    main()