import sqlite3
from pathlib import Path
from datetime import datetime

from langchain_core.tools import tool
from langchain.tools import ToolRuntime

from langchain_bot.context import SessionContext


def get_db_path():
    return Path(__file__).resolve().parents[2] / "ecommerce.db"


@tool
def cancel_order_action(
    order_id: int,
    runtime: ToolRuntime[SessionContext],
) -> str:
    """
    Cancel an order after admin approval.

    Verifies that the order belongs to the logged-in user and that
    the order status is PLACED. Then marks the order as CANCELLED,
    refunds the payment, and creates a support ticket.
    """

    context = runtime.context

    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row

        # Verify ownership and order status
        order = conn.execute(
            """
            SELECT o.id, o.status, o.user_id, u.email
            FROM orders o
            JOIN users u ON o.user_id = u.id
            WHERE o.id = ?
              AND u.email = ?
            """,
            (order_id, context.user_email),
        ).fetchone()

        if order is None:
            return "Order not found or does not belong to the logged-in user."

        if order["status"] != "PLACED":
            return (
                f"Order #{order_id} cannot be cancelled because "
                f"its current status is {order['status']}."
            )

        now = datetime.now().isoformat()

        # Cancel order
        conn.execute(
            """
            UPDATE orders
            SET status = 'CANCELLED'
            WHERE id = ?
            """,
            (order_id,),
        )

        # Refund payment
        conn.execute(
            """
            UPDATE payments
            SET status = 'REFUNDED'
            WHERE order_id = ?
            """,
            (order_id,),
        )

        # Create ticket
        conn.execute(
            """
            INSERT INTO tickets (
                user_id,
                return_id,
                subject,
                status,
                thread_id,
                user_email,
                created_at,
                updated_at
            )
            VALUES (?, NULL, ?, 'OPEN', ?, ?, ?, ?)
            """,
            (
                order["user_id"],
                f"Cancellation request for order #{order_id}",
                context.conversation_id,
                context.user_email,
                now,
                now,
            ),
        )

        conn.commit()

    return (
        f"Order #{order_id} has been cancelled successfully. "
        "The payment has been refunded."
    )


@tool
def create_return_action(
    order_id: int,
    product_name: str,
    reason: str,
    runtime: ToolRuntime[SessionContext],
) -> str:
    """
    Create a return after admin approval.

    Verifies that the order belongs to the logged-in user and that
    the order is SHIPPED or DELIVERED. PLACED orders cannot be
    returned and should be cancelled instead.
    """

    context = runtime.context

    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row

        # Verify ownership and order status
        order = conn.execute(
            """
            SELECT o.id, o.status, o.user_id, u.email
            FROM orders o
            JOIN users u ON o.user_id = u.id
            WHERE o.id = ?
              AND u.email = ?
            """,
            (order_id, context.user_email),
        ).fetchone()

        if order is None:
            return "Order not found or does not belong to the logged-in user."

        if order["status"] == "PLACED":
            return (
                f"Order #{order_id} is currently PLACED. "
                "Please cancel the order instead of creating a return."
            )

        if order["status"] not in ("SHIPPED", "DELIVERED"):
            return (
                f"Order #{order_id} cannot be returned because "
                f"its current status is {order['status']}."
            )

        # Find the requested product in the order
        item = conn.execute(
            """
            SELECT
                oi.id AS order_item_id,
                p.id AS product_id,
                p.name AS product_name
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
              AND p.name = ?
            """,
            (order_id, product_name),
        ).fetchone()

        if item is None:
            return (
                f"Product '{product_name}' was not found in order "
                f"#{order_id}."
            )

        now = datetime.now().isoformat()

        # Create return
        cursor = conn.execute(
            """
            INSERT INTO returns (
                order_id,
                order_item_id,
                user_id,
                reason,
                status,
                requested_at,
                resolved_at,
                admin_id
            )
            VALUES (?, ?, ?, ?, 'APPROVED', ?, ?, NULL)
            """,
            (
                order_id,
                item["order_item_id"],
                order["user_id"],
                reason,
                now,
                now,
            ),
        )

        return_id = cursor.lastrowid

        # Refund payment
        conn.execute(
            """
            UPDATE payments
            SET status = 'REFUNDED'
            WHERE order_id = ?
            """,
            (order_id,),
        )

        # Create ticket
        conn.execute(
            """
            INSERT INTO tickets (
                user_id,
                return_id,
                subject,
                status,
                thread_id,
                user_email,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?)
            """,
            (
                order["user_id"],
                return_id,
                f"Return request for {product_name}",
                context.conversation_id,
                context.user_email,
                now,
                now,
            ),
        )

        conn.commit()

    return (
        f"Return for '{product_name}' from order #{order_id} "
        "has been created successfully. The payment has been refunded."
    )

@tool
def verify_order_for_cancellation(
    order_id: int,
    runtime: ToolRuntime[SessionContext],
) -> str:
    """
    Verify that an order belongs to the authenticated customer
    and is eligible for cancellation.
    """

    context = runtime.context

    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row

        order = conn.execute(
            """
            SELECT
                o.id,
                o.status,
                o.user_id,
                u.email
            FROM orders o
            JOIN users u
                ON o.user_id = u.id
            WHERE o.id = ?
              AND u.email = ?
            """,
            (
                order_id,
                context.user_email,
            ),
        ).fetchone()

    if order is None:
        return (
            f"Order #{order_id} was not found or does not "
            f"belong to the authenticated user."
        )

    if order["status"] != "PLACED":
        return (
            f"Order #{order_id} belongs to the authenticated user "
            f"but its current status is {order['status']}. "
            f"Only PLACED orders can be cancelled."
        )

    return (
        f"Order #{order_id} is valid for cancellation. "
        f"The order belongs to the authenticated user and "
        f"its status is PLACED."
    )

def get_verification_tools():
    return [
        verify_order_for_cancellation,
    ]


def get_action_tools():
    return [
        cancel_order_action,
        create_return_action,
    ]