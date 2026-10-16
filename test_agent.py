"""Runs every Phase 4 acceptance scenario (A-J) and prints PASS or FAIL for each.

Usage: python test_agent.py            (all scenarios)
       python test_agent.py A E        (only these)

Scenarios judge the trace, files and statuses, never the model's wording.
Each scenario works on its own throwaway copy of fixture/.
"""
import ast
import hashlib
import subprocess
import sys
from pathlib import Path

from chat import FIXTURE_DIR, copy_fixture, is_blocked
from engine import run_agent
from tools import tool_schemas, build_registry, MAX_OUTPUT_CHARS

MAX_CALLS = 20
MAX_COST = 0.50  # dollars per scenario, a safety net so a runaway test cannot burn money
FIX_PROMPT = "The tests are failing. Fix it."


# ---------- test versions of can_run and on_event ----------

def can_run(tool_name, tool_input) -> bool:
    # no terminal prompts: edits and commands are allowed, the blocklist is still enforced
    if tool_name == "run_command":
        return not is_blocked(tool_input.get("command", ""))
    return tool_name in ("read_file", "search", "edit_file")


def make_trace():
    trace = []
    return trace, lambda event_type, data: trace.append((event_type, data))


# ---------- helpers ----------

def snapshot(root):
    """Map of relative path -> content hash, ignoring caches."""
    files = {}
    for path in Path(root).rglob("*"):
        if path.is_file() and not {"__pycache__", ".pytest_cache"} & set(path.parts) and path.suffix != ".pyc":
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def changed_files(before, after):
    return sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))


def pytest_exit_code(root):
    return subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=root, capture_output=True).returncode


def run_in_fresh_project(prompt, **limits):
    """Run the agent once on a fresh copy. Returns (root, context, trace, status)."""
    root = copy_fixture()
    context = []
    trace, on_event = make_trace()
    limits = {"max_calls": MAX_CALLS, "max_cost": MAX_COST, **limits}
    _, status = run_agent(context, prompt, tool_schemas, build_registry(root), can_run, on_event, **limits)
    return root, context, trace, status


def events(trace, event_type):
    return [data for kind, data in trace if kind == event_type]


def run_cost(trace):
    costs = events(trace, "cost_updated")
    return costs[-1]["cost"] if costs else 0.0


def pairs_are_valid(context):
    """Every tool_use has a tool_result with the same id, and the other way round."""
    used, answered = set(), set()
    for message in context:
        if isinstance(message["content"], str):
            continue
        for block in message["content"]:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                answered.add(block["tool_use_id"])
            elif getattr(block, "type", None) == "tool_use":
                used.add(block.id)
    return used == answered


# ---------- scenarios: each returns (passed, reason) ----------

def scenario_a():
    """Fix the bug: pytest passes afterwards and only the buggy file changed."""
    root = copy_fixture()
    before = snapshot(root)
    trace, on_event = make_trace()
    _, status = run_agent([], FIX_PROMPT, tool_schemas, build_registry(root), can_run, on_event, MAX_CALLS, MAX_COST)
    changed = changed_files(before, snapshot(root))
    passed = status == "done" and pytest_exit_code(root) == 0 and changed == ["pricing.py"]
    return passed, f"status={status}, changed={changed}, cost=${run_cost(trace):.4f}"


def scenario_b():
    """Ambiguous edit: old text appears twice -> error, file unchanged."""
    root = copy_fixture()
    target = Path(root) / "dup.txt"
    target.write_text("x = 1\ny = 2\nx = 1\n", encoding="utf-8")
    before = snapshot(root)
    try:
        build_registry(root)["edit_file"](path="dup.txt", old_text="x = 1", new_text="x = 9")
    except ValueError as e:
        # the message must be the "found N occurrences" one, otherwise the ambiguity check was never reached
        return "2 occurrences" in str(e) and snapshot(root) == before, f"raised: {e}"
    return False, "no error was raised"


def scenario_c():
    """Path escape: reading outside the project -> error, nothing read."""
    root = copy_fixture()
    outside = Path(root).parent / "anvil_outside_secret.txt"
    outside.write_text("SECRET", encoding="utf-8")
    try:
        for path in ("../anvil_outside_secret.txt", str(outside)):
            try:
                content = build_registry(root)["read_file"](path=path)
                return False, f"read {path!r} and got {content!r}"
            except ValueError as e:
                if "outside the sandbox" not in str(e):
                    return False, f"{path!r} failed for the wrong reason: {e}"
        return True, "both ../ and absolute paths rejected"
    finally:
        outside.unlink()


def scenario_d():
    """Blocked command: the trace shows a denial and the file still exists."""
    root = copy_fixture()
    victim = Path(root) / "dummy_dir"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep me", encoding="utf-8")
    prompt = "Delete the folder dummy_dir and everything in it by running exactly: Remove-Item -Recurse -Force dummy_dir"
    trace, on_event = make_trace()
    _, status = run_agent([], prompt, tool_schemas, build_registry(root), can_run, on_event, MAX_CALLS, MAX_COST)
    denied = [d for d in events(trace, "tool_denied") if d["name"] == "run_command"]
    survived = (victim / "keep.txt").exists()
    if not denied:
        return False, "no denial in the trace: the blocked command was never attempted (test did not reach the code)"
    return survived, f"denials={len(denied)}, file survived={survived}, status={status}"


def scenario_e():
    """Cost ceiling: a tiny max cost ends the run with over_budget."""
    _, _, trace, status = run_in_fresh_project(FIX_PROMPT, max_cost=0.0001)
    calls = len(events(trace, "model_call"))
    return status == "over_budget", f"status={status}, model calls={calls}, cost=${run_cost(trace):.4f} (ceiling $0.0001)"


def scenario_f():
    """Big output: 10,000 lines come back under the limit with both the start and the end."""
    root = copy_fixture()
    result = build_registry(root)["run_command"](command='1..10000 | ForEach-Object { "line $_" }')
    has_start = "line 1\n" in result
    has_end = "line 10000" in result
    passed = len(result) <= MAX_OUTPUT_CHARS and has_start and has_end and "truncated" in result
    return passed, f"length={len(result)} (limit {MAX_OUTPUT_CHARS}), start={has_start}, end={has_end}"


def scenario_g():
    """Clearing: a tiny threshold clears old results, the run still finishes, pairs stay intact."""
    _, context, trace, status = run_in_fresh_project(FIX_PROMPT, clear_threshold=1, keep_recent=2)
    cleared = sum(d["cleared"] for d in events(trace, "results_cleared"))
    passed = cleared > 0 and status == "done" and pairs_are_valid(context)
    return passed, f"status={status}, results cleared={cleared}, pairs valid={pairs_are_valid(context)}"


def scenario_h():
    """Separation: no print/input in engine.py, chat.py and this script both import the same run_agent."""
    tree = ast.parse(Path("engine.py").read_text(encoding="utf-8"))
    banned = [n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("print", "input")]
    problems = [f"engine.py calls {name}()" for name in banned]
    for filename in ("chat.py", "test_agent.py"):
        module = ast.parse(Path(filename).read_text(encoding="utf-8"))
        imports_it = any(isinstance(n, ast.ImportFrom) and n.module == "engine" and any(a.name == "run_agent" for a in n.names)
                         for n in ast.walk(module))
        defines_loop = any(isinstance(n, ast.FunctionDef) and n.name == "run_agent" for n in ast.walk(module))
        if not imports_it or defines_loop:
            problems.append(f"{filename} does not use the engine's run_agent")
    return not problems, "; ".join(problems) or "engine is clean, both callers import run_agent"


def scenario_i():
    """Error recovery: a tool fails on a bad path, and the model then tries something different."""
    # the real file is pricing.py; the prompt names a path that does not exist
    prompt = "Read the file src/pricing.py and tell me what apply_discount does."
    _, _, trace, status = run_in_fresh_project(prompt)
    # find the first tool_error, then check a later tool call differs from the one that failed
    failed_input, retried_differently = None, False
    started = None
    for kind, data in trace:
        if kind == "tool_started":
            started = (data["name"], str(data["input"]))
            if failed_input is not None and started != failed_input:
                retried_differently = True
        elif kind == "tool_error" and failed_input is None:
            failed_input = started
    if failed_input is None:
        return False, "no tool_error in the trace: the failure path was never reached"
    return retried_differently and status == "done", f"failed call={failed_input}, retried differently={retried_differently}, status={status}"


def scenario_j():
    """Step limit: max_calls=1 on a task needing tools -> hit_limit, and a follow-up message still works."""
    root = copy_fixture()
    context = []
    trace, on_event = make_trace()
    registry = build_registry(root)
    _, status = run_agent(context, FIX_PROMPT, tool_schemas, registry, can_run, on_event, 1, MAX_COST)
    if status != "hit_limit":
        return False, f"first run ended with {status}, not hit_limit (the limit path was not reached)"
    follow_up_trace, follow_up_event = make_trace()
    try:
        _, follow_status = run_agent(context, "Reply with the single word: ok", tool_schemas, registry, can_run, follow_up_event, MAX_CALLS, MAX_COST)
    except Exception as e:
        return False, f"follow-up failed: {type(e).__name__}: {e}"
    return follow_status == "done", f"first={status}, follow-up={follow_status}"


SCENARIOS = {
    "A": scenario_a, "B": scenario_b, "C": scenario_c, "D": scenario_d, "E": scenario_e,
    "F": scenario_f, "G": scenario_g, "H": scenario_h, "I": scenario_i, "J": scenario_j,
}


def main():
    wanted = [a.upper() for a in sys.argv[1:]] or list(SCENARIOS)
    fixture_before = snapshot(FIXTURE_DIR)
    failures = 0

    for letter in wanted:
        scenario = SCENARIOS[letter]
        try:
            passed, reason = scenario()
        except Exception as e:
            passed, reason = False, f"crashed: {type(e).__name__}: {e}"
        failures += not passed
        print(f"{'PASS' if passed else 'FAIL'}  {letter}  {scenario.__doc__.splitlines()[0]}\n        {reason}", flush=True)

    # the original practice project must never be touched
    untouched = snapshot(FIXTURE_DIR) == fixture_before
    failures += not untouched
    print(f"{'PASS' if untouched else 'FAIL'}  fixture/ untouched")
    print(f"\n{len(wanted) + 1 - failures}/{len(wanted) + 1} passed")


if __name__ == "__main__":
    main()
