from engine import client, MODEL, SYS_PROMPT
from tools import tool_schemas


def input_tokens(tools):
    kwargs = {"tools": tools} if tools else {}
    response = client.messages.create(
        model=MODEL,
        max_tokens=1,
        system=SYS_PROMPT,
        messages=[{"role": "user", "content": "hi"}],
        **kwargs,
    )
    return response.usage.input_tokens


without_tools = input_tokens(None)
with_tools = input_tokens(tool_schemas)
print(f"without tools: {without_tools} input tokens")
print(f"with tools:    {with_tools} input tokens")
print(f"tool definitions add: {with_tools - without_tools} tokens")
