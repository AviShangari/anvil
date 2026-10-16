from pathlib import Path
import subprocess
from functools import partial

MAX_LINES = 500
MAX_RESULTS = 50
COMMAND_TIMEOUT = 60
MAX_OUTPUT_CHARS = 10000

tool_schemas = [
    {
        "name": "read_file",
        "description": "Read a file, with optional line ranges. Returns text with line numbers. Returns at most 500 lines at a time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file to read, relative to the project root, e.g. pricing.py or tests/test_cart.py"
                },
                "start_line": {
                    "type": "integer",
                    "description": "Line number to start reading from (inclusive). If omitted, starts at line 1."
                },
                "end_line": {
                    "type": "integer",
                    "description": "Line number to stop reading at (inclusive). If omitted, reads to the end of the file (at most 500 lines)."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "search",
        "description": "Search the contents of files for a pattern using ripgrep. Returns up to 50 matches as file:line:text. It does not match file names; to list files, use run_command. Use path to limit it to a file or folder. Use this to find where something is before reading it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The pattern to search for."
                },
                "path": {
                    "type": "string",
                    "description": "File or folder to search, relative to the project root. Use . for the whole project (default)."
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "edit_file",
        "description": "Edit a file by replacing one occurrence of old text with new text. Read the file first and copy the text exactly. Returns an error if the old text is not found exactly once, including indentation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file to edit relative to the project root, e.g. pricing.py"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to replace (must appear exactly once in the file)."
                },
                "new_text": {
                    "type": "string",
                    "description": "The new text to replace the old text with."
                }
            },
            "required": ["path", "old_text", "new_text"]
        }
    },
    {
        "name": "run_command",
        "description": "Run a Windows PowerShell command and return the output. Long output is cut in the middle, keeping the start and the end. Do not use bash syntax (no &&, rm -rf, export). Stops after 60 seconds. Includes stdout, stderr, and exit code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to run (will be executed in a PowerShell subshell)."
                }
            },
            "required": ["command"]
        }
    }
]


def build_registry(root) -> dict:
    return {
        "read_file": partial(read_file, root),
        "search": partial(search, root),
        "edit_file": partial(edit_file, root),
        "run_command": partial(run_command, root)
    }


def resolve_path(root, path)-> Path:
    root = Path(root).resolve()
    full = (root / path).resolve()

    if full.is_relative_to(root):
        return full
    raise ValueError(f'Path {path} is outside the sandbox {root}')


def read_file(root, path, start_line=1, end_line=None) -> str:

    truncated = False

    full = resolve_path(root, path)

    if not full.is_file():
        raise ValueError(f'Path {full} is not a file')

    lines = full.read_text(encoding='utf-8').splitlines()
    if end_line is None:
        end_line = len(lines)
    total_lines = len(lines)
    
    if (end_line - start_line + 1) > MAX_LINES:
        end_line = start_line + MAX_LINES - 1
        truncated = True

    lines = lines[start_line - 1:end_line]

    return_text = ""
    for i, line in enumerate(lines, start=start_line):
        return_text += f"{i}: {line}\n"
    
    if truncated:
        return_text += f"\n[Showing lines {start_line}-{end_line} out of {total_lines} lines total. Call read_file with start_line={end_line+1} to continue...]\n"

    return return_text


def search(root, pattern, path=".", max_results=MAX_RESULTS) -> str:
    
    root_path = Path(root).resolve()
    relative = resolve_path(root_path, path).relative_to(root_path)

    command = ["rg", "--line-number", "--no-heading", "--color", "never", "-e", pattern, str(relative)]
    result = subprocess.run(command, capture_output=True, cwd=str(root_path), text=True, timeout=30)

    exit_code = result.returncode

    if exit_code == 0:
        pass
    elif exit_code == 1:
        return f"No matches found for '{pattern}'."
    elif exit_code == 2:
        raise ValueError(f"Error: {result.stderr}")

    matches = result.stdout.splitlines()
    total_matches = len(matches)
    truncated = False

    if total_matches > max_results:
        truncated = True
        matches = matches[:max_results]
    
    return_text = ""
    for match in matches:
        return_text += f"{match}\n"

    if truncated:
        return_text += f"\n[Showing {max_results} of {total_matches} matches. Narrow the 'pattern' or search a specific file with 'path'.]\n"

    return return_text


def edit_file(root, path, old_text, new_text) -> str:
    full = resolve_path(root, path)
    if not full.is_file():
        raise ValueError(f"Path {full} is not a file.")
    
    if old_text == "": raise ValueError("old_text cannot be empty")

    content = full.read_text(encoding="utf-8")

    count = content.count(old_text)
    if count == 0:
        raise ValueError(f"No matches found for '{old_text}' in {path}. Check indentation and whitespace and use read_file to copy the exact text.")
    
    elif count > 1:
        raise ValueError(f"Found {count} occurrences of '{old_text}'. Include more surrounding lines so it matches only once.")
    
    new_content = content.replace(old_text, new_text)
    full.write_text(new_content, encoding="utf-8")
    return f"Successfully replaced 1 occurrence in {path}."


def run_command(root, command, timeout=COMMAND_TIMEOUT) -> str:
    root_path = Path(root).resolve()
    cmd_list = ["powershell", "-NoProfile", "-Command", command]

    try:
        result = subprocess.run(cmd_list, cwd=str(root_path), timeout=timeout, capture_output=True, text=True, encoding="utf-8", errors='replace')
    except subprocess.TimeoutExpired:
        raise ValueError(f"Command timed out after {timeout} seconds.")
    
    return_text = f"Command '{command}' completed with exit code {result.returncode}.\n"

    if result.stdout:
        return_text += f"----STDOUT----\n{result.stdout}\n"
    
    if result.stderr:
        return_text += f"----STDERR----\n{result.stderr}\n"
    
    if len(return_text) > MAX_OUTPUT_CHARS:
        removed_chars = len(return_text) - MAX_OUTPUT_CHARS
        note = f"[...Output truncated by {removed_chars} characters...]"
        return_text = return_text[0:(MAX_OUTPUT_CHARS - len(note))//2] + note + return_text[-(MAX_OUTPUT_CHARS - len(note))//2:]
    
    return return_text