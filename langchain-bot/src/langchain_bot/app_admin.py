import sqlite3
from pathlib import Path

import streamlit as st

from langchain_bot.auth import authenticate_user
from langchain_bot.hitl_utils import (
    get_pending_actions,
    resume_with_decision,
)


DB_PATH = Path(__file__).resolve().parents[2] / "ecommerce.db"


def get_all_actions(status=None, email=None):
    query = """
        SELECT
            id,
            thread_id,
            user_email,
            action_type,
            order_id,
            product_name,
            reason,
            status,
            created_at,
            updated_at
        FROM pending_actions
        WHERE 1 = 1
    """

    params = []

    if status and status != "ALL":
        query += " AND status = ?"
        params.append(status)

    if email:
        query += " AND user_email LIKE ?"
        params.append(f"%{email}%")

    query += " ORDER BY created_at DESC"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]


def init_session():
    st.session_state.setdefault("admin_email", None)
    st.session_state.setdefault("admin_role", None)


def login_page():
    st.title("Admin Login")

    with st.form("admin_login"):
        email = st.text_input("Email")
        password = st.text_input(
            "Password",
            type="password"
        )

        login = st.form_submit_button("Login")

        if login:
            user = authenticate_user(
                email,
                password,
                role="admin"
            )

            if user:
                st.session_state.admin_email = user["email"]
                st.session_state.admin_role = user["role"]
                st.rerun()
            else:
                st.error("Invalid admin credentials.")


def admin_page():
    st.title("Admin - Pending Actions")
    st.caption(
        f"Logged in as: {st.session_state.admin_email}"
    )

    if st.button("Logout"):
        st.session_state.admin_email = None
        st.session_state.admin_role = None
        st.rerun()

    st.divider()

    # Filters
    col1, col2 = st.columns(2)

    with col1:
        status = st.selectbox(
            "Status",
            ["PENDING", "APPROVED", "REJECTED", "ALL"]
        )

    with col2:
        email = st.text_input(
            "Customer email",
            placeholder="Optional"
        )

    actions = get_all_actions(
        status=status,
        email=email,
    )

    st.subheader(
        f"Actions ({len(actions)})"
    )

    if not actions:
        st.info("No actions found.")
        return

    for action in actions:

        with st.container(border=True):

            st.markdown(
                f"### {action['action_type']} "
                f"- Order #{action['order_id']}"
            )

            col1, col2 = st.columns(2)

            with col1:
                st.write(
                    f"**User:** {action['user_email']}"
                )
                st.write(
                    f"**Order ID:** {action['order_id']}"
                )
                st.write(
                    f"**Action:** {action['action_type']}"
                )
                st.write(
                    f"**Status:** {action['status']}"
                )

            with col2:
                st.write(
                    f"**Thread ID:** {action['thread_id']}"
                )
                st.write(
                    f"**Product:** "
                    f"{action['product_name'] or '-'}"
                )
                st.write(
                    f"**Reason:** "
                    f"{action['reason'] or '-'}"
                )
                st.write(
                    f"**Created:** {action['created_at']}"
                )

            if action["status"] == "PENDING":

                approve_col, reject_col = st.columns(2)

                with approve_col:
                    if st.button(
                        "Approve",
                        key=f"approve_{action['id']}",
                        type="primary",
                    ):
                        try:
                            result = resume_with_decision(
                                thread_id=action["thread_id"],
                                decision="approve",
                            )

                            st.success(
                                "Action approved successfully."
                            )

                            st.write(
                                "Agent result:"
                            )
                            st.write(result)

                            st.rerun()

                        except Exception as e:
                            st.error(
                                f"Failed to approve action: {e}"
                            )

                with reject_col:
                    if st.button(
                        "Reject",
                        key=f"reject_{action['id']}",
                    ):
                        try:
                            result = resume_with_decision(
                                thread_id=action["thread_id"],
                                decision="reject",
                            )

                            st.warning(
                                "Action rejected."
                            )

                            st.write(
                                "Agent result:"
                            )
                            st.write(result)

                            st.rerun()

                        except Exception as e:
                            st.error(
                                f"Failed to reject action: {e}"
                            )


def main():
    st.set_page_config(
        page_title="Admin - LangChain Bot",
        page_icon="🛠️",
        layout="wide",
    )

    init_session()

    if not st.session_state.admin_email:
        login_page()
        return

    admin_page()


if __name__ == "__main__":
    main()