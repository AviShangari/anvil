import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096
SYS_PROMPT = "You are a coding assistant working in a project. Use 'search' and 'read_file' to find files and other things. Use 'edit_file' to edit files. You can also run tests to check your work."


client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)


def ask_model(context, tools):
    return client.messages.create(
        max_tokens=MAX_TOKENS,
        messages=context,
        model=MODEL,
        tools=tools,
        system=SYS_PROMPT
    )


def run_agent(context, user_message, tool_definitions, registry, can_run, on_event, max_calls):

    context.append({"role": "user", "content": user_message})
    model_calls = 0
    status = "done"

    # start the user-assistant interaction loop
    while True:

        if model_calls >= max_calls:
            status = "hit_limit"
            context.append({"role": "assistant", "content": "I stopped because I hit the model call limit."})
            break

        response = ask_model(context, tool_definitions)
        model_calls += 1
        on_event("model_call", {})
        context.append({"role":"assistant", "content": response.content})

        if response.stop_reason == "max_tokens":
            status = "cut_off"
            break

        elif response.stop_reason == "end_turn":
            status = "done"
            break

        else: pass

        # the model asked for tools: run each one and collect a result for every tool_use block
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            on_event("tool_started", {"name": block.name, "input": block.input})

            # the engine only asks; can_run decides
            if not can_run(block.name, block.input):
                on_event("tool_denied", {"name": block.name, "input": block.input})
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "This action was not allowed.",
                    "is_error": True,
                })
                continue

            try:
                output = registry[block.name](**block.input)
                on_event("tool_finished", {"name": block.name, "output": output})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})

            except Exception as e:
                error_text = f"Error: {type(e).__name__}: {e}"
                on_event("tool_error", {"name": block.name, "error": error_text})
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": error_text,
                    "is_error": True,
                })

        # all results from one assistant message go back together in a single user message
        context.append({"role": "user", "content": results})

    final_output = ""
    last_message = context[-1]

    if isinstance(last_message['content'], str):
        final_output = last_message['content']
    else:
        for c in last_message['content']:
            if c.type == "text":
                final_output += c.text

    on_event('run_finished', {'status': status, 'model_calls': model_calls})
    return final_output, status
           