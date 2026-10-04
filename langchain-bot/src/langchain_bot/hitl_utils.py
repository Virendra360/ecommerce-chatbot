import sqlite3
from pathlib import Path
from datetime import datetime

from langgraph.types import Command

from langchain_bot.agent import get_agent


def get_db_path():
    return Path(__file__).resolve().parents[2] / "ecommerce.db"


def get_pending_actions(thread_id=None, status="PENDING"):
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row

        if thread_id:
            rows = conn.execute(
                """
                SELECT *
                FROM pending_actions
                WHERE thread_id = ?
                  AND status = ?
                ORDER BY created_at DESC
                """,
                (thread_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM pending_actions
                WHERE status = ?
                ORDER BY created_at DESC
                """,
                (status,),
            ).fetchall()

    return [dict(row) for row in rows]


def has_pending_action(thread_id, action_type, order_id):
    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute(
            """
            SELECT id
            FROM pending_actions
            WHERE thread_id = ?
              AND action_type = ?
              AND order_id = ?
              AND status = 'PENDING'
            LIMIT 1
            """,
            (thread_id, action_type, order_id),
        ).fetchone()

    return row is not None


def handle_interrupt(result, thread_id, user_email):
    """
    Detect an HITL interrupt, persist the business action in
    pending_actions, and return markdown for the Streamlit UI.

    Returns None when the agent result does not contain an interrupt.
    """

    interrupts = result.get("__interrupt__")

    if not interrupts:
        return None

    interrupt = interrupts[0]

    # HumanInTheLoopMiddleware provides the requested actions
    # inside the interrupt value.
    interrupt_value = interrupt.value

    if isinstance(interrupt_value, dict):
        action_requests = interrupt_value.get("action_requests", [])
    else:
        action_requests = []

    if not action_requests:
        return "### Approval required\n\nA pending action requires admin approval."

    messages = []

    with sqlite3.connect(get_db_path()) as conn:

        for request in action_requests:

            tool_name = request.get("name")
            args = request.get("arguments", {})

            if tool_name == "cancel_order_action":
                action_type = "CANCEL_ORDER"
                order_id = args.get("order_id")
                product_name = None
                reason = None

            elif tool_name == "create_return_action":
                action_type = "CREATE_RETURN"
                order_id = args.get("order_id")
                product_name = args.get("product_name")
                reason = args.get("reason")

            else:
                continue

            if order_id is None:
                continue

            # Prevent duplicate pending requests.
            existing = conn.execute(
                """
                SELECT id
                FROM pending_actions
                WHERE thread_id = ?
                  AND action_type = ?
                  AND order_id = ?
                  AND status = 'PENDING'
                LIMIT 1
                """,
                (
                    thread_id,
                    action_type,
                    order_id,
                ),
            ).fetchone()

            if existing:
                messages.append(
                    f"⏳ Your {action_type.lower()} request for "
                    f"order #{order_id} is already awaiting approval."
                )
                continue

            now = datetime.now().isoformat()

            conn.execute(
                """
                INSERT INTO pending_actions (
                    thread_id,
                    user_email,
                    action_type,
                    order_id,
                    product_name,
                    reason,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
                """,
                (
                    thread_id,
                    user_email,
                    action_type,
                    order_id,
                    product_name,
                    reason,
                    now,
                    now,
                ),
            )

            if action_type == "CANCEL_ORDER":
                messages.append(
                    f"### Cancellation request submitted\n\n"
                    f"Order **#{order_id}** is waiting for admin approval."
                )

            else:
                messages.append(
                    f"### Return request submitted\n\n"
                    f"Return for **{product_name}** on order "
                    f"**#{order_id}** is waiting for admin approval."
                )

        conn.commit()

    return "\n\n".join(messages)


def update_pending_status(thread_id, decision):
    """
    Update pending action status after an admin decision.
    """

    status = "APPROVED" if decision == "approve" else "REJECTED"

    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            """
            UPDATE pending_actions
            SET status = ?,
                updated_at = ?
            WHERE thread_id = ?
              AND status = 'PENDING'
            """,
            (
                status,
                datetime.now().isoformat(),
                thread_id,
            ),
        )
        conn.commit()


def resume_with_decision(
    thread_id,
    decision,
    user_email=None,
):
    """
    Resume the interrupted LangGraph thread with an admin decision.

    decision must be:
        approve
        reject
    """

    if decision not in ("approve", "reject"):
        raise ValueError("decision must be 'approve' or 'reject'")

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    agent = get_agent()

    result = agent.invoke(
        Command(
            resume={
                "decisions": [
                    {
                        "type": decision,
                        "message": (
                            "Admin approved the requested action."
                            if decision == "approve"
                            else "Admin rejected the requested action."
                        ),
                    }
                ]
            }
        ),
        config=config,
    )

    update_pending_status(thread_id, decision)

    return result