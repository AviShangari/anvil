import re
import shutil
import sys
import tempfile

from engine import run_agent
from tools import tool_schemas, build_registry

MAX_CALLS = 20
FIXTURE_DIR = "fixture"

# Matched against the lowercased, whitespace-collapsed command. Never complete: that's why commands also ask for confirmation.
BLOCKLIST = [
    r"\b(remove-item|ri|rm|rmdir|rd|del|erase)\b.*(\s-r[a-z]*\b|\s/s\b)",  # recursive deletes
    r"\bgit\s+push\b",
    r"\b(curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod)\b",
]

NEEDS_CONFIRMATION = ["edit_file", "run_command"]
OUTPUT_PREVIEW_CHARS = 150


def can_run(tool_name, tool_input) -> bool:

    if tool_name in ['read_file', 'search']: return True

    if tool_name == "run_command":
        normalized = " ".join(tool_input.get("command", "").lower().split())
        for pattern in BLOCKLIST:
            if re.search(pattern, normalized):
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

    elif event_type == "run_finished":
        print(f"[finished] status={data['status']}, model calls={data['model_calls']}")

    # unknown event types are ignored on purpose (e.g. cost_updated arrives in Task 3)


def main():
    # work on a project path given on the command line, otherwise on a throwaway copy of the fixture
    if len(sys.argv) > 1:
        root = sys.argv[1]
    else:
        root = tempfile.mkdtemp(prefix="anvil_")
        shutil.copytree(FIXTURE_DIR, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    print(f"Working in {root}. Type 'exit' to quit.")

    registry = build_registry(root)
    context = []

    while True:
        user_message = input("\nyou> ").strip()
        if user_message.lower() in ("exit", "quit"):
            break
        if not user_message:
            continue

        final_output, status = run_agent(context, user_message, tool_schemas, registry, can_run, on_event, MAX_CALLS)
        print(f"\nagent> {final_output}")


if __name__ == "__main__":
    main()
