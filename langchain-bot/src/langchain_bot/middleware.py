from datetime import datetime

from langchain.agents.middleware import (
    wrap_model_call,
    wrap_tool_call,
)


def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@wrap_model_call
def model_logging_middleware(request, handler):
    messages = request.state.get("messages", [])

    print(f"[{_ts()}] MODEL CALL - messages={len(messages)}")

    if messages:
        last_message = messages[-1]
        print(
            f"[{_ts()}] MODEL INPUT - "
            f"{str(last_message.content)[:200]}"
        )

    try:
        response = handler(request)

        response_messages = response.result

        if response_messages:
            last_response = response_messages[-1]

            print(
                f"[{_ts()}] MODEL RESPONSE - "
                f"{str(last_response.content)[:200]}"
            )

            tool_calls = getattr(last_response, "tool_calls", None)

            if tool_calls:
                print(
                    f"[{_ts()}] MODEL TOOL CALLS - "
                    f"{tool_calls}"
                )

        return response

    except Exception as e:
        print(f"[{_ts()}] MODEL ERROR - {e}")
        raise

@wrap_tool_call
def tool_logging_middleware(request, handler):
    messages = request.state.get("messages", [])

    if messages:
        last_message = messages[-1]
        tool_calls = getattr(last_message, "tool_calls", None)

        if tool_calls:
            print(
                f"[{_ts()}] TOOL CALLS - "
                f"{tool_calls}"
            )

    try:
        result = handler(request)

        print(f"[{_ts()}] TOOL SUCCESS")

        return result

    except Exception as e:
        print(f"[{_ts()}] TOOL ERROR - {e}")
        raise


def get_logging_middleware():
    return [
        model_logging_middleware,
        tool_logging_middleware,
    ]