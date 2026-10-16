import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096
SYS_PROMPT = "You are a coding assistant working in a project. Use 'search' and 'read_file' to find files and other things. Use 'edit_file' to edit files. You can also run tests to check your work."

# Claude Haiku 4.5, dollars per million tokens (input and output are priced differently)
INPUT_PRICE_PER_M = 1.00
OUTPUT_PRICE_PER_M = 5.00

# once the last call's input passes this many tokens, old tool results get shrunk
CLEAR_THRESHOLD = 20_000
# tool results from this many of the newest tool-result messages (one message = one batch of parallel calls) are never shrunk
KEEP_RECENT = 3
CLEARED_NOTE = "[old output removed]"


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


def calc_cost(input_tokens, output_tokens) -> float:
    return input_tokens / 1_000_000 * INPUT_PRICE_PER_M + output_tokens / 1_000_000 * OUTPUT_PRICE_PER_M


def clear_old_tool_results(context, keep_recent) -> int:
    """Shrink the content of every tool result except those in the newest `keep_recent` result messages.
    Returns how many were shrunk.

    Counted in messages, not blocks: the model often makes several parallel calls in one turn, and keeping
    only part of a batch makes it re-read what was just cleared, in a loop.
    Only `content` changes. Every tool_use / tool_result block stays, so the pairs the API checks stay intact.
    """
    batches = []
    for message in context:
        # tool results live in user messages whose content is a list of dicts (assistant content is SDK objects)
        if message["role"] != "user" or isinstance(message["content"], str):
            continue
        blocks = [b for b in message["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
        if blocks:
            batches.append(blocks)

    old = batches[:-keep_recent] if keep_recent > 0 else batches

    cleared = 0
    for block in (b for batch in old for b in batch):
        if block["content"] != CLEARED_NOTE:
            block["content"] = CLEARED_NOTE
            cleared += 1
    return cleared


def run_agent(context, user_message, tool_definitions, registry, can_run, on_event, max_calls, max_cost,
              clear_threshold=CLEAR_THRESHOLD, keep_recent=KEEP_RECENT):

    context.append({"role": "user", "content": user_message})
    model_calls = 0
    total_input = 0
    total_output = 0
    last_input = 0
    status = "done"

    # start the user-assistant interaction loop
    while True:

        if model_calls >= max_calls:
            status = "hit_limit"
            context.append({"role": "assistant", "content": "I stopped because I hit the model call limit."})
            break

        # checked before the next call, so the context always ends on a finished tool_result message.
        # The call that crossed the ceiling already happened, so the overshoot is at most one call.
        if calc_cost(total_input, total_output) >= max_cost:
            status = "over_budget"
            context.append({"role": "assistant", "content": "I stopped because I hit the cost limit."})
            break

        # input size of the previous call is the best measure of how big the context is now
        if last_input > clear_threshold:
            cleared = clear_old_tool_results(context, keep_recent)
            if cleared:
                on_event("results_cleared", {"cleared": cleared, "input_tokens": last_input})

        response = ask_model(context, tool_definitions)
        model_calls += 1
        on_event("model_call", {})
        context.append({"role":"assistant", "content": response.content})

        last_input = response.usage.input_tokens
        total_input += last_input
        total_output += response.usage.output_tokens
        on_event("cost_updated", {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost": calc_cost(total_input, total_output),
        })

        if response.stop_reason == "max_tokens":
            status = "cut_off"
            break

        elif response.stop_reason == "end_turn":
            status = "done"
            break

        # anything else that is not a tool request (e.g. refusal) ends the turn: there are no tool results to send back
        elif response.stop_reason != "tool_use":
            status = response.stop_reason
            break

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

    on_event('run_finished', {'status': status, 'model_calls': model_calls, 'cost': calc_cost(total_input, total_output)})
    return final_output, status
