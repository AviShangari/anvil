import re
import shutil
import sys
import tempfile

from engine import run_agent
from tools import tool_schemas, build_registry

MAX_CALLS = 20
MAX_COST = 0.25  # dollars per user turn
FIXTURE_DIR = "fixture"

# Matched against the lowercased, whitespace-collapsed command. Never complete: that's why commands also ask for confirmation.
BLOCKLIST = [
    r"\b(remove-item|ri|rm|rmdir|rd|del|erase)\b.*(\s-r[a-z]*\b|\s/s\b)",  # recursive deletes
    r"\bgit\s+push\b",
    r"\b(curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod)\b",
]

NEEDS_CONFIRMATION = ["edit_file", "run_command"]
OUTPUT_PREVIEW_CHARS = 150


def is_blocked(command) -> bool:
    normalized = " ".join(command.lower().split())
    return any(re.search(pattern, normalized) for pattern in BLOCKLIST)


def copy_fixture() -> str:
    # every run works on a throwaway copy, never on the original fixture
    root = tempfile.mkdtemp(prefix="anvil_")
    shutil.copytree(FIXTURE_DIR, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return root


def can_run(tool_name, tool_input) -> bool:

    if tool_name in ['read_file', 'search']: return True

    if tool_name == "run_command" and is_blocked(tool_input.get("command", "")):
        return False

    if tool_name in NEEDS_CONFIRMATION:
        answer = input(f"Allow {tool_name} with {tool_input}? [y/N] ")
        return answer.strip().lower() == "y"

    # unknown tool: fail closed
    return False


def on_event(event_type, data):

    if event_type == "model_call":
        print("[model call]")

    elif event_type == "tool_started":
        print(f"[tool] {data['name']} {data['input']}")

    elif event_type == "tool_finished":
        output = str(data["output"])
        suffix = "..." if len(output) > OUTPUT_PREVIEW_CHARS else ""
        print(f"[done] {data['name']}: {output[:OUTPUT_PREVIEW_CHARS]}{suffix}")

    elif event_type == "tool_error":
        print(f"[error] {data['name']}: {data['error']}")

    elif event_type == "tool_denied":
        print(f"[denied] {data['name']}")

    elif event_type == "cost_updated":
        print(f"[cost] ${data['cost']:.4f} ({data['input_tokens']} in, {data['output_tokens']} out)")

    elif event_type == "results_cleared":
        print(f"[cleared] {data['cleared']} old tool results (last input was {data['input_tokens']} tokens)")

    elif event_type == "run_finished":
        print(f"[finished] status={data['status']}, model calls={data['model_calls']}, cost=${data['cost']:.4f}")

    # unknown event types are ignored on purpose


def main():
    # work on a project path given on the command line, otherwise on a throwaway copy of the fixture
    if len(sys.argv) > 1:
        root = sys.argv[1]
    else:
        root = copy_fixture()
    print(f"Working in {root}. Type 'exit' to quit.")

    registry = build_registry(root)
    context = []

    while True:
        user_message = input("\nyou> ").strip()
        if user_message.lower() in ("exit", "quit"):
            break
        if not user_message:
            continue

        final_output, status = run_agent(context, user_message, tool_schemas, registry, can_run, on_event, MAX_CALLS, MAX_COST)
        print(f"\nagent> {final_output}")


if __name__ == "__main__":
    main()
