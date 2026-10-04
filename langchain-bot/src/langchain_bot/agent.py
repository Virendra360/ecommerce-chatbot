import os
import sqlite3

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver

from langchain_bot.context import SessionContext
from langchain_bot.rag_tool import search_policies
from langchain_bot.sql_tools import get_sql_tools
from langchain_bot.middleware import get_logging_middleware
from langchain_bot.gmail_tools import get_gmail_tools
from langchain_bot.action_tools import get_action_tools

from langchain_bot.action_tools import (
    get_action_tools,
    get_verification_tools,
)


load_dotenv()


_checkpointer = None


def get_checkpointer():
    global _checkpointer

    if _checkpointer is None:
        db_path = os.getenv("CHECKPOINTS_DB_PATH", "checkpoints.sqlite")

        conn = sqlite3.connect(
            db_path,
            check_same_thread=False
        )

        _checkpointer = SqliteSaver(conn=conn)
        _checkpointer.setup()

    return _checkpointer


def get_thread_config(user_email, conversation_id):
    return {
        "configurable": {
            "thread_id": f"{user_email}:{conversation_id}"
        },
        "recursion_limit": 20
    }


_agent = None


def create_support_agent():

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.2
    )

    verification_tools = get_verification_tools()
    action_tools = get_action_tools()

    hitl_middleware = HumanInTheLoopMiddleware(
        interrupt_on={
            "cancel_order_action": True,
            "create_return_action": True,
        }
    )

    tools = (
        [search_policies]
        + get_sql_tools()
        + get_gmail_tools()
        + verification_tools
        + action_tools
    )

    system_prompt = """
You are an e-commerce customer support assistant.

You have the following capabilities:

1. POLICY / FAQ
- Use search_policies for return, shipping, refund, and cancellation
  policy questions.
- Do not use SQL for general policy questions.

2. USER-SPECIFIC DATA
- Use SQL tools for orders, order details, payments and returns.
- The authenticated user's email is provided through SessionContext.
- Never ask the LLM to invent or guess the user's email.
- Never access or expose another user's data.
- 3. CANCELLATION FLOW

When customer wants to cancel an order:

Step 1:
Call verify_order_for_cancellation with only the order_id.

Do NOT use sql_db_query to verify cancellation ownership/status.

The verification tool automatically uses the authenticated user's
SessionContext and checks:
- order belongs to authenticated user
- order status is PLACED

Step 2:
If verification says the order is valid, optionally send the
request-received email if Gmail is available.

Step 3:
Call exactly one action tool:
cancel_order_action

Do not directly modify the database using SQL.

4. RETURN FLOW

When customer wants to return an item:

Use the context-aware return verification tool to verify:
- order belongs to authenticated user
- order status
- requested product belongs to the order

Do not use raw SQL to perform ownership verification.

If the order is PLACED, tell the customer to cancel instead.

After successful verification, call exactly one action tool:
create_return_action.

5. HUMAN APPROVAL

Cancellation and return action tools require human approval.

Do not claim that an action has completed before the action tool
actually executes after approval.

6. ONE ACTION TOOL PER TURN

At most ONE action tool may be called for a customer request.

Never call both cancel_order_action and create_return_action.

7. SQL QUERY LIMIT

Use SQL tools for general database questions and non-action
queries.

Do not repeatedly use sql_db_query to perform cancellation or
return ownership verification.

8. GENERAL CONVERSATION

Do not use tools for simple greetings or casual conversation.

Always protect customer data and only operate on the authenticated
customer's records.
"""

    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        context_schema=SessionContext,
        checkpointer=get_checkpointer(),
        middleware=[
            hitl_middleware,
            *get_logging_middleware(),
        ],
    )


def get_agent():
    global _agent

    if _agent is None:
        _agent = create_support_agent()

    return _agent


def reset_agent():
    global _agent
    _agent = None