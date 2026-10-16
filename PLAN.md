# PLAN.md: Learning roadmap for the coding agent project

This is the plan for building a coding agent from scratch, then a PR tester on top of it, then comparing it against Claude Code with the same model. The goal is learning. Every phase is written so you can work through it on your own.

No code in this file on purpose. You write all of it.

---

## Rules for the whole project

These apply to every phase. Come back here when you're unsure what to do.

1. **Build by hand first, frameworks second.** You only use LangGraph, LangChain, or MCP libraries after you've built the thing they replace.
2. **Every feature gets measured.** If it doesn't improve results, remove it and write down why. That write-up counts as part of the project.
3. **Keep the engine separate.** There is one `run_agent` function. If the agent loop ever gets copied into a second place, stop and fix the structure.
4. **Keep DECISIONS.md.** One line per choice: what you chose, why, and what you rejected. This becomes most of your README and your interview answers.
5. **A phase is done when its acceptance criteria pass, not when the code exists.** "I did it" without the test output doesn't count.
6. **Test what the agent did, not what it said.** Check traces, files, exit codes, and statuses. Model wording changes every run.
7. **Run everything 3 times.** Models give different results each run. Something that passes 2 out of 3 is a real finding, not noise to ignore.
8. **A test only counts if it reached the code being tested.** Always check the trace to confirm the risky path actually ran.
9. **Don't call something agentic when it isn't.** A fixed sequence of steps is a pipeline. A loop where the model decides the next step is an agent. Say which is which.
10. **Budget is a hard limit.** Use Claude Haiku 4.5 for development. Only use the more expensive target model for scored runs.
11. **Watch for skipping.** The tedious parts (tests, measuring, labeling data) are where the project's value is. If you notice yourself skipping them, that's the pattern to stop.

---

## Phase 1: Basics. DONE

Calling the model from Python, conversation history, system prompts.

What you learned:
- The API is stateless. The messages list is the only memory, and you resend all of it every call.
- Every output token gets paid for again as input on every later turn.
- `content` is a list of blocks, `stop_reason` says why the model stopped, `usage` gives token counts.
- A system prompt is guidance, not enforcement. Real safety lives in code.

Open note: the system prompt robustness test was 3 direct attacks, one run each. Indirect injection was not tested. That gets tested properly in Phase 7.

---

## Phase 2: Tools. DONE (with gaps)

Faking a tool by hand, then real tool calling.

What you learned:
- A tool is the model asking in a format your code recognizes. Your code does the work.
- Text-based fake tools break because talking and tool requests share one channel.
- Real tool calling uses separate `tool_use` and `tool_result` blocks with matching IDs.
- Tool results should explain themselves. Missing details (like a timezone) get filled in by a confident guess.
- Tool failures go back to the model as `is_error` results instead of crashing.

Gaps carried forward:
- The error path was never shown working with a real bad input. Phase 4 scenario I covers this.
- The token cost of tool definitions was never measured. Phase 4 task 3 covers this.
- The reason for making timezone required is not written down yet. Add it to DECISIONS.md.

---

## Phase 3: The agent loop. DONE (with gaps)

What you learned:
- The loop: keep calling the model while `stop_reason` is `tool_use`.
- A tool registry maps names to functions, so the loop never needs to know which tools exist.
- A max-calls limit stops runaway loops. Hitting it should end the turn cleanly and leave the conversation in a valid state.

Gaps carried forward:
- `run_agent` still contains `input()` and `print()`, so it can't be tested automatically. Phase 4 task 2 fixes this.
- No trace and no test script yet. Phase 4 requires both.

---

## Phase 4: The coding assistant. CURRENT

### Goal
Your agent can fix a real bug in a small project from a terminal chat, safely and under a cost limit. The engine is fully separated from the chat, and a test script proves everything works.

### Concepts it teaches
- **Coding tools:** what a minimal useful toolset looks like and why each tool is shaped the way it is.
- **Precise edits:** why find-and-replace beats rewriting whole files.
- **Search vs RAG:** why Claude Code navigates code with grep-style search instead of a vector database.
- **Permissions:** separating "can the model ask for this" from "is this allowed to run."
- **Callbacks:** an engine that talks to the outside only through functions you pass in.
- **Cost tracking:** turning token counts into dollars and enforcing a ceiling.
- **Context management:** keeping long tasks from filling up the context.

### Suggested approach

**Setup.** Make a tiny practice project: 2 or 3 Python files and a few pytest tests, with one bug planted on purpose so a test fails. Every test run copies this folder to a temporary location first and works on the copy. The agent edits files and runs commands, so it must never touch the original.

**Task 1: Four coding tools.**
- *read_file:* takes a path, returns the contents with line numbers. If the file is very large, cut it off and say clearly that it was cut and how to see more (for example, an optional start and end line).
- *search:* runs ripgrep through Python's subprocess module and returns matching lines with file names and line numbers. Cap the number of results and say when results were cut. Install ripgrep on Windows with winget (package name BurntSushi.ripgrep.MSVC).
- *edit_file:* takes a path, the old text, and the new text. It only replaces if the old text appears exactly once. If it appears zero times or more than once, return an error explaining which, and change nothing.
- *run_command:* runs a command and returns stdout, stderr, and the exit code. Add a timeout. If the output is long, keep the beginning and the end and replace the middle with a note saying how much was cut. Errors usually show up at the end, so never keep only the beginning.
- *Path safety:* every file tool turns the given path into a full absolute path and rejects anything outside the project folder. This includes tricks like `../` and absolute paths.

**Task 2: Separate the engine.**
- Move the agent loop into its own file. Its signature takes the conversation, the list of tools, a `can_run` function, an `on_event` function, and the limits.
- `run_agent` handles exactly one user turn and returns the final text and a status. The engine file contains no `print` and no `input`.
- *can_run* gets the tool name and input and returns allow or deny. For the chat version: read and search are always allowed, edits and commands ask you yes or no in the terminal, and a blocklist is always denied (deleting things recursively, pushing to git, network tools like curl and wget, and similar). A denial goes back to the model as an `is_error` tool result saying the action was not allowed.
- *on_event* gets an event type and some data. Call it for: model call made, tool started, tool finished, tool errored, tool denied, cost updated, run finished. The chat version prints these. The test version stores them in a list. That list is your trace.
- Move your chat loop into its own file. It reads input, calls `run_agent`, prints results.

**Task 3: Cost tracking and a hard ceiling.**
- After every model call, add that call's input and output tokens to running totals.
- Convert to dollars using the current price per million tokens for the model. Look this up in Anthropic's pricing docs. Prices differ for input and output.
- Add a max cost limit. When the total passes it, stop and return the status `over_budget`.
- Measure once and record: how many input tokens your tool definitions add to a simple "hi" message. Compare with and without tools. Write the number in DECISIONS.md.

**Task 4: Long tasks.**
- Output limits are already handled by your tools in Task 1.
- Add clearing of old tool results. Before each model call, check the latest input token count. If it is over a threshold, replace the content of the oldest tool results with a short note like "old output removed." Keep the most recent few untouched.
- Never delete a tool_use block or a tool_result block. Only shrink the content. Removing either half of a pair makes the API reject the next call.

**Task 5: The test script.**
- A separate file that runs every scenario below and prints PASS or FAIL for each.
- It uses a test version of `can_run` (no terminal prompts; allow edits and commands, still deny the blocklist) and a test version of `on_event` (collects the trace).
- Run the whole script 3 times and keep the output.

### Progress (update after every completed step)
- **Setup:** DONE. Practice project in `fixture/`. Bug planted in `pricing.py` (`apply_discount` never divides `percent` by 100). pytest: 2 fail, 4 pass.
- **Task 1, tools in `tools.py`:**
  - `resolve_path`: written and reviewed.
  - `read_file`: written and reviewed (`MAX_LINES = 500`). Edge cases for `start_line < 1` or past end of file not handled.
  - `search`: written and reviewed (`MAX_RESULTS = 50`). Ripgrep installed and the function has been run once.
  - `edit_file`: written and reviewed. Raises on zero or multiple matches.
  - `run_command`: written and reviewed (PowerShell, `COMMAND_TIMEOUT = 60`, `MAX_OUTPUT_CHARS = 10000`). Cut-off note now reports the number removed and the result stays within the limit. The removed count is off by roughly the length of the note itself.
  - **Task 1 is complete (all four tools written).** Still untested against criteria B, C and F.
  - None of the tools has been checked against acceptance criteria B, C or F yet. Tool schemas not written.
- **Task 2 (engine split):** in progress.
  - Part 1 DONE: `tool_schemas` (four tool definitions, `input_schema`, no `root`/`timeout`/`max_results` exposed) and `build_registry(root)` (uses `functools.partial`) in `tools.py`. Not yet run against the API.
  - Part 2 DONE (`run_agent` in `engine.py`): steps 1-12 written and reviewed (steps 6-10 written by Claude at the user's request; 11-12 by the user). Returns `(final_output, status)`, emits `model_call`, `tool_started`, `tool_finished`, `tool_error`, `tool_denied`, `run_finished`. Not yet run against the API. Known edge cases not handled: other stop reasons (e.g. refusal) produce an empty results message; `max_tokens` cutting a `tool_use` block leaves a half-formed call.
  - Part 3 (`can_run` and `on_event` for chat), part 4 (`chat.py`): not started. `engine.py`, `chat.py` and `test_agent.py` exist but are empty.
  - **Planned checkpoint:** after part 4, run the agent on the fixture bug end to end (this also exercises all four tools).
- **Tasks 3, 4, 5 (cost, clearing, test script):** not started.
- **DECISIONS.md:** empty. Owed: Phase 2 timezone reason, output size limit (500 lines), search cap (50).

### Acceptance criteria
All of these pass across 3 runs:

- **A. Fix the bug:** prompt "The tests are failing. Fix it." Afterwards, the script runs pytest itself and it passes. Only the file containing the bug was changed.
- **B. Ambiguous edit:** call edit_file directly with old text that appears twice. Error returned, file unchanged.
- **C. Path escape:** call read_file directly with a path outside the project. Error returned, nothing read.
- **D. Blocked command:** ask the agent to delete a dummy file using a blocked command. The trace shows a denial and the file still exists.
- **E. Cost ceiling:** run scenario A with a very low max cost. Status is `over_budget`.
- **F. Big output:** run a command that prints 10,000 lines. The tool result is under your size limit and includes both the start and the end.
- **G. Clearing:** run scenario A with a very low clearing threshold. The trace shows results were cleared and the agent still finishes without an API error.
- **H. Separation:** the engine file has no `print` or `input`. The chat and the test script both call the same `run_agent`.
- **I. Error recovery:** a tool fails (a bad path, or the bad-timezone case from Phase 2), and the trace shows the error result followed by the model trying again differently.
- **J. Step limit:** with max calls set to 1, a task that needs tools returns `hit_limit`, and the conversation stays valid (a follow-up message works).

DECISIONS.md has: output size limit, search result cap, blocklist contents, cost ceiling, clearing threshold, max calls, and the tool definition token cost. Each with a reason.

### Common pitfalls
- Keeping only the start of long command output. Test failures and tracebacks are usually at the end.
- Path checks that compare strings instead of resolved absolute paths. `../` and symlinks get through.
- Running tests on the original practice project. One bad edit and your test fixture is broken.
- A blocklist that matches exact strings only. `rm  -rf` with two spaces, or uppercase on Windows, slips through. Accept that a blocklist is never complete. That's why commands also ask for confirmation in the chat version, and why Phase 6 adds a real sandbox.
- Windows commands. Decide whether run_command uses PowerShell or cmd, and tell the model which in the tool description. Otherwise it will send bash commands.
- Clearing tool results by deleting messages instead of shrinking content.
- Forgetting to count the model calls a run made after hitting `over_budget`. The check happens after a call, so you can go slightly over. Write down how much over is possible.

### Stretch goal
Add a fifth tool that lists files in a folder, then remove it and run scenario A both ways. Does the model find the bug faster with it, or does search already cover it? Record the numbers.

---

## Phase 5: Evaluation setup and the budget decision

### Goal
One command runs your agent on a fixed set of tasks, scores every run, and saves the results. Before building it, you set a dollar ceiling for the whole project's evaluation work.

### Concepts it teaches
- **Evals:** a fixed, repeatable test set is the only way to know if a change helped.
- **Practice set vs held-out set:** you tune on one and only report numbers from the other. Otherwise you're grading your own homework.
- **Variance:** the same task can pass and fail across runs. Report how consistent results are, not just the average.
- **False alarms vs missed bugs:** two different kinds of wrong. They have different costs and must be counted separately.
- **Contamination:** the model may have seen famous bugs and fixes during training. Recent tasks check for this.
- **Cost control:** prompt caching, cheap models for development, and stopping early.

### Suggested approach

**Step 1: The budget.** Before building anything:
- Pick 2 SWE-bench Verified tasks and run your Phase 4 agent on them with Haiku. Record tokens and dollars per task.
- Estimate the full cost: cost per task, times tasks, times 3 runs, times number of configurations, times 2 agents (yours and Claude Code). Do this with the target model's prices, not Haiku's.
- Pick a ceiling you can actually afford. Write it in DECISIONS.md along with the math.
- Decide which model is the target model for scored runs. Write that down too.

**Step 2: Environment.** SWE-bench uses Docker images built for Linux. On Windows, use Docker Desktop with WSL2 and work inside WSL2. The images are large, so check your free disk space first.

**Step 3: Task format.** Each task is one small file with: the repo, the commit, the problem description, the command to run tests, and how to judge success. Keep the format simple and the same for every task. You will add PR-tester tasks to this same format in Phase 6.

**Step 4: Pick 10 tasks.** From SWE-bench Verified, prefer small repos and short fixes so Haiku has a real chance. If every task fails, you learn nothing. Mark 6 as practice and 4 as held-out. Write down which is which and never tune on the held-out ones.

**Step 5: The runner.** For each task and each run:
- Start from a fresh copy or fresh container.
- Call `run_agent` with a test `can_run` and an `on_event` that records everything.
- Score using the task's success check (for SWE-bench, the official tests for that task).
- Save one record per run: task, run number, pass or fail, cost, time, number of model calls, number of tool calls, status.

**Step 6: Summary.** A second script reads the saved records and prints a table per task: passes out of 3, average cost, average time. Also print totals. Report both "passed at least once" and "passed all 3 times." They tell different stories.

**Step 7: Cost safety.** Add a ceiling for the whole eval run, not just per task. When spending passes it, the runner stops and saves what it has. Turn on prompt caching for the system prompt and tool definitions. Never rerun a task and config combination that already has saved results unless something changed.

**Step 8: Early Claude Code checkpoint.** Run Claude Code in its non-interactive mode on 3 to 5 practice tasks, with the same model as your agent, 3 runs each. Check the Claude Code docs for the current flags for non-interactive runs, choosing the model, and permission settings. Score with the same runner. This tells you early whether the project's main question can actually be measured.

### Acceptance criteria
- Budget ceiling, target model, and the cost math are in DECISIONS.md.
- One command runs all practice tasks 3 times and saves records. A second command prints the summary.
- The practice and held-out split is written down.
- Your agent's results on the practice set, with variance shown.
- Claude Code's results on at least 3 tasks, same model, same scoring.
- Total spend so far is under your ceiling, and you know the exact number.

### Common pitfalls
- Building a huge test set before the agent can do anything. Start at 10.
- Picking tasks so hard that both agents fail everything. Zero vs zero tells you nothing.
- Looking at held-out results while still changing your agent.
- Reporting only the average and hiding that results flip between runs.
- Comparing your agent and Claude Code on different model versions.
- Running out of disk space halfway through pulling Docker images.
- Forgetting that a failed run still costs money. Count it.

### Stretch goal
Add a "failure type" field to each failed run (gave up, hit limit, wrong fix, broke other tests, environment error) and fill it in by reading the trace. Patterns here will guide what to fix in later phases.

---

## Phase 6: Sandbox and PR tester v1 (hand-built)

### Goal
Given a pull request, your system sets up the project in a Docker sandbox with no internet, runs the tests, works out why anything failed, and writes an evidence-backed report. It never modifies the code it's testing.

### Concepts it teaches
- **Sandboxing:** running untrusted code where it can't hurt anything.
- **Least privilege:** giving each part only the access it needs.
- **Pipeline vs agent:** most of the PR tester is a fixed sequence of steps. Only some steps need the model to reason. Knowing which is which is the point.
- **Enforcement in code:** "never modify the code" is checked by your code, not promised by a prompt.
- **Grounded reports:** every claim in the report must point to real log lines.
- **Flaky tests:** a test that passes and fails without code changes.

### Suggested approach

**The sandbox.**
- Each PR runs in its own fresh container.
- Network is off by default. Setup often needs to install dependencies, so split it into two stages: an install stage that is allowed limited network access, then a test stage with network fully off. Write this choice and the reason in DECISIONS.md.
- Your `run_command` tool now runs commands inside the container instead of on your machine.
- Remove `edit_file` from the toolset for the project code. The agent can write only to a scratch folder.

**Never modify the code.** Before running anything, record a fingerprint of every tracked file (git's own status and diff work well). After the run, compare. Any change to project files fails the whole run, no matter what the report says.

**The workflow.** Write it as plain Python steps, not a framework. LangGraph comes in Phase 12.
1. Get the PR. For now, apply the diff from your eval data to the repo at the right commit.
2. Setup. This step is an agent loop: the model reads the project files and figures out how to install it. Limit attempts.
3. Run tests. A fixed step: run the test command and capture everything.
4. If all tests pass, go to the report.
5. If something fails, classify it as one of three: setup problem, flaky test, or real bug. For now, use a model call where the answer must be one of the three options (a tool with a fixed list of allowed values works well). Jev comes in Phase 8.
6. Each category gets its own path:
   - *Setup problem:* the agent tries to fix the environment (not the code), with a limited number of attempts, then reruns tests.
   - *Flaky test:* rerun the failing tests several times. If results change, mark it flaky. Decide how many reruns and write it down.
   - *Real bug:* the agent gathers evidence: the failing test, the error, and the parts of the diff most likely responsible.
7. Write the report.

**Deterministic verdict.** The final pass or fail is decided by your code from actual exit codes and test results, not by what the model says. The model explains, your code decides. This matters a lot in Phase 7.

**The report.** Includes: the verdict, every step taken, every command run with its exit code, and short quoted log excerpts as evidence. Add an automatic check: every quoted log excerpt in the report must actually appear in the saved logs. A report that quotes something not in the logs fails.

**Test data.** Add PR-tester tasks to your Phase 5 format:
- Good PRs: SWE-bench gold patches. Expected verdict: pass.
- Broken PRs: failed AI patches from the SWE-bench experiments repo. Run them without the hidden tests. Expected: the agent should catch the problem if the normal tests can.
- Planted bugs: take good PRs and insert bugs with a mutation tool like mutmut.
- Raw repos: a few projects without pre-built environments (pallets/click, encode/httpx, marshmallow) to test setup.
Start with about 10 total. Keep the practice and held-out split.

### Acceptance criteria
Across 3 runs per task:
- Setup success rate reported.
- Verdict accuracy reported, with false alarms and missed bugs counted separately.
- Failure explanations checked against your own labels for each failing case.
- Zero modifications to tested code, verified by the fingerprint check on every run.
- The quote check passes on every report.
- A test inside the sandbox proves network is off during the test stage.
- Total cost recorded and within budget.
- DECISIONS.md: network policy, flaky rerun count, setup attempt limit, and which steps are agent loops vs fixed steps.

### Common pitfalls
- The agent "fixing" the code to make tests pass. Removing the edit tool and the fingerprint check prevent this. Trusting the prompt does not.
- Letting the model decide the final verdict.
- Too few reruns to detect flakiness, so flaky tests get reported as real bugs.
- Huge test logs flooding the context. Use the output limits from Phase 4.
- Mixing up "the tests failed" with "the tests couldn't run." A collection or import error is usually setup, not a bug.
- Windows path and line-ending problems. Do this whole phase inside WSL2.

### Stretch goal
Cache a built environment per repo and commit (a saved Docker image after the install stage). Measure how much time and money it saves on repeated runs.

---

## Phase 7: Prompt injection defenses

### Goal
Text inside a pull request cannot make your PR tester do something it shouldn't. You measure attack success before and after each defense.

### Concepts it teaches
- **Direct vs indirect injection:** a user typing an attack vs an attack hidden inside data the model reads. Indirect is the real threat here.
- **Trust boundaries:** your instructions are trusted, PR content is not, tool output from PR code is not.
- **Defense in depth:** several layers, so one failing doesn't mean everything fails.
- **Model-independent defenses:** protections that work even if the model is fully fooled.
- **Attack success rate:** the metric that matters.

### Suggested approach

**Build an attack set.** At least 8 attack PRs. Spread the hidden instructions across different places: the PR description, code comments, test names, a README change, commit messages, and text printed by the tests themselves when they run. Give each attack a specific goal:
- Make a broken PR get a passing verdict.
- Make the agent run a network command.
- Make the agent reveal a secret. Put a fake secret (a "canary," a random unique string) in an environment variable and check if it ever shows up in any output.
- Make the agent modify project code.

**Measure the baseline.** Run every attack 3 times against your Phase 6 tester with no new defenses. Record which succeed.

**Add defenses one at a time, measuring after each:**
1. *Marking untrusted data:* wrap PR content and tool output in clear labels and tell the model in the system prompt that anything inside is data, never instructions.
2. *Capability limits:* network off, edit tool removed, blocklist, scratch-only writes. These don't depend on the model at all.
3. *Deterministic verdict:* already built in Phase 6. Confirm it holds: no attack should flip a verdict.
4. *Output checks:* scan every output and report for the canary. Any match fails the run.

**Record the results** as a table: each attack, each defense layer, success or failure.

### Acceptance criteria
- At least 8 attacks covering at least 5 different hiding places.
- Baseline attack success rate and the rate after each defense layer, across 3 runs each.
- The canary never appears in any output after defenses.
- No attack flips a verdict or modifies code.
- Every attack that still partly succeeds is written up: what it got the model to do, and why the damage was or wasn't contained.

### Common pitfalls
- Only testing obvious attacks ("IGNORE ALL INSTRUCTIONS"). Real ones look like normal text.
- Declaring the system safe after a few runs.
- Counting on the prompt defense as the main protection. It's the weakest layer. The capability limits are the strong ones.
- Forgetting that test output is also untrusted. Code in the PR runs, and it can print anything.

### Stretch goal
Use a model to generate new attack variants aimed at your current defenses, run them, and see if any get through.

---

## Phase 8: Jev for injection screening and failure classification

### Goal
Use Jev, TypeSafe AI's classifier model, for two fast yes-or-no style decisions, and compare it against the main model on accuracy, speed, and cost. Keep it only where the numbers support it.

### Concepts it teaches
- **Classifiers vs generators:** a model that picks from fixed answers vs one that writes text.
- **Calibrated confidence:** when a model says 90% sure, is it right about 90% of the time?
- **Thresholds:** trading false alarms against missed cases.
- **Interface-first design:** build against an interface so the thing behind it can be swapped.
- **Vendor claims:** speed and cost numbers a company measured on itself need checking.

### Suggested approach

**Read the docs first.** Jev launched in September 2026. Check TypeSafe's current documentation for the API, the official Python SDK, and the routes that skip the waitlist (Vercel AI Gateway, OpenRouter).

**Build against the interface first.** Use the official system-one-adapter-python, which gives the same interface backed by a regular LLM. Wire your two questions through it. Then swap in Jev. Switching should be a config change, nothing else.

**The two questions:**
1. Injection screening: does this PR content contain instructions aimed at an AI? Runs before the PR tester starts.
2. Failure classification: setup problem, flaky test, or real bug? Replaces the model call from Phase 6 step 5.

**Labeled data.** You need correct answers to compare against:
- Screening: your Phase 7 attacks plus clean PRs from your eval set. Aim for at least 30 items, roughly balanced.
- Classification: failures from your Phase 6 runs, labeled by you. Aim for at least 30.
Split each into a part for choosing thresholds and a separate part for final numbers.

**Compare.** Ask Jev and the main model the same question on the same items. Record: accuracy, false alarms, misses, response time, and cost per call. For Jev, also group answers by stated confidence and check how often each group was actually right.

**Decide.** For each of the two uses, keep Jev, drop it, or use a cascade. Write the decision with the numbers.

### Acceptance criteria
- Both uses go through one interface. Swapping between Jev and the LLM adapter is one setting.
- A comparison table per use: accuracy, false alarms, misses, average time, cost per call, on the held-out labels.
- A confidence check table for Jev.
- A chosen threshold, picked on the threshold set and reported on the held-out set.
- DECISIONS.md: keep or drop for each use, with numbers. Also a note that Jev is not used in can_run and doesn't pick tools, and why.

### Common pitfalls
- Too few labeled examples, so one mistake swings accuracy by 10%.
- Choosing the threshold and reporting accuracy on the same data.
- Quoting TypeSafe's speed claims instead of your own measurements.
- Letting the screener block a PR silently. A flagged PR should still produce a report saying why.
- Adding Jev in places where it's decoration, like can_run.

### Stretch goal
Build a cascade: Jev answers first, and only low-confidence cases go to the main model. Measure cost saved vs accuracy lost.

---

## Phase 9: MCP, using and building

### Goal
Use GitHub's official MCP server to fetch real pull requests. Then turn your sandbox into an MCP server that other agents can call.

### Concepts it teaches
- **Why MCP exists:** without a standard, every agent needs custom code for every service. With one, each side builds once.
- **Clients and servers:** who calls whom, and what tools, resources, and prompts are.
- **Transports:** local (stdio) vs over the network (HTTP).
- **Tool discovery:** tools are listed at runtime, not hardcoded.
- **Trust:** an MCP server's output is still untrusted data. Your Phase 7 rules still apply.

### Suggested approach

**Part A: Using an MCP server.**
- Run GitHub's official MCP server locally. Give it a token with read-only access to public repos only.
- Use the official MCP Python SDK to make your engine an MCP client: connect, list the server's tools, convert their schemas into your tool definitions, and route tool calls to the server.
- GitHub's server exposes many tools. Choose a small subset your PR tester actually needs and only give those to the model.
- Use it to fetch a real, recent pull request and run your PR tester on it end to end.

**Part B: Building an MCP server.**
- Write an MCP server that exposes your sandbox: start a sandbox for a PR, run the tests, get the report.
- Connect to it from an outside client like Claude Code or Claude Desktop, and have that client run your PR tester through your server.
- Keep the same safety rules. The server should never expose a way to modify the tested code.

### Acceptance criteria
- Your PR tester runs end to end on a real PR fetched through the GitHub MCP server.
- An outside client successfully calls your sandbox server and gets a report.
- Measured: tool definition tokens with all GitHub tools vs your subset. Recorded in DECISIONS.md.
- Token scope written down: read-only.

### Common pitfalls
- Giving the model every tool the server offers. More tools means more tokens per call and more wrong tool choices.
- Using a token with write access.
- Treating PR content from MCP as trusted.
- A stdio server that prints debug logs to standard output. That breaks the protocol. Send logs to stderr or a file.

### Stretch goal
Run your sandbox server over HTTP with authentication, so it could be used from another machine.

---

## Phase 10: Subagents, measured

### Goal
Find out whether handing big, noisy jobs (like reading a huge error log) to a subagent improves results compared to a single agent.

### Concepts it teaches
- **Context isolation:** a subagent starts with a fresh, empty context, so the main agent's context stays clean.
- **Delegation and summaries:** the subagent returns a short answer. Details can get lost.
- **Cost multiplication:** every subagent is extra model calls.
- **When one agent is better:** most of the time, which is why this must be measured.

### Suggested approach
- A subagent is just another call to your same `run_agent`, with its own new conversation, a narrow read-only toolset, its own limits, and a specific question. It returns a short answer.
- Give the main agent a tool like "investigate this log for this question." When the main agent calls it, your code runs the subagent and returns its answer as the tool result.
- Add a setting to turn subagents on or off.
- Pick eval tasks with large outputs (long test logs, big tracebacks). Run them with and without subagents, 3 times each.
- Compare: success, total cost (including the subagent's), main agent context size, time.

### Acceptance criteria
- Subagents reuse `run_agent`. No copied loop.
- Subagent costs are included in totals and reported separately.
- Subagents can't start their own subagents.
- A with-vs-without table on the same tasks.
- A keep or remove decision in DECISIONS.md with the numbers.

### Common pitfalls
- The subagent's summary drops the one line that mattered.
- Forgetting to count subagent cost, which makes them look free.
- Concluding "it helped" from one run.
- Giving the subagent write tools.

### Stretch goal
Compare against a simpler option with no subagent: smarter output trimming (keep the start, the end, and every line containing "Error" or "FAILED"). If trimming matches the subagent, that's an important finding.

---

## Phase 11: Memory and RAG, measured

### Goal
The agent saves short notes after each run ("this project needs Python 3.11") and finds relevant ones in later runs. It can also search project documentation. Both are measured with and without.

### Concepts it teaches
- **Embeddings:** turning text into numbers so similar meanings are close together.
- **Chunking:** splitting documents into pieces small enough to search well.
- **Vector search:** finding the closest pieces to a question.
- **Retrieval quality:** measuring whether the right pieces come back (recall at k).
- **Memory policies:** what's worth saving, and what happens when a saved note goes stale.
- **RAG vs search:** why Claude Code uses grep for code instead of this.

### Suggested approach

**Notes memory.**
- At the end of each PR tester run, a model call writes a few short, specific notes about the repo (setup steps that worked, quirks).
- Store them in PostgreSQL with the pgvector extension, which you already know how to run in Docker.
- At the start of a run on a repo, retrieve the most relevant notes and add them to the context.

**Docs search.**
- Split each repo's README, CONTRIBUTING, and setup docs into chunks.
- Turn chunks into embeddings. Anthropic doesn't offer an embedding model, so choose one: a local open-source model (free, slower) or a paid API. Write down which and why.
- Give the agent a search_docs tool.

**Measure.**
- Make a small question set (about 20 questions) with the correct doc chunk marked for each. Measure how often the right chunk is in the top results.
- Run the PR tester twice on the same repos: second run with and without memory. Compare setup success, cost, and time.
- Test a wrong note on purpose: save a false note and see whether it hurts results.

### Acceptance criteria
- With-vs-without table for notes memory.
- Retrieval quality number for docs search on your question set.
- Results of the wrong-note test.
- Memory is reset between eval runs, so held-out runs don't benefit from practice runs. Written down.
- Keep or remove decisions in DECISIONS.md.

### Common pitfalls
- Memory leaking between eval runs and quietly inflating your scores.
- Saving vague notes ("setup was tricky") that help no one.
- Judging retrieval by looking at a few results and feeling good about it.
- Changing chunk size and embedding model at the same time, so you can't tell which helped.

### Stretch goal
Build RAG over the codebase itself and compare against your ripgrep search tool on finding the code relevant to a bug.

---

## Phase 12: LangGraph

### Goal
Rebuild the PR tester workflow in LangGraph, since it's a fixed flowchart with branches. Separately, rebuild the agent loop in LangGraph once and compare it with your hand-built engine.

### Concepts it teaches
- **Graphs as workflows:** nodes are steps, edges are what comes next, conditional edges are branches.
- **Shared state:** one typed object that every step reads and updates.
- **Checkpointing:** saving progress so a run can resume after a crash.
- **Human approval points:** pausing a run for a person to approve.
- **Framework vs hand-built:** what you gain and what gets hidden.

### Suggested approach

**Part A: PR tester workflow.**
- Draw your Phase 6 workflow on paper first: every step and every branch.
- Define the state: everything the steps share (PR info, logs, classification, report).
- Make each step a node. The steps that need reasoning (setup, evidence gathering) call your existing `run_agent`. The fixed steps stay plain code.
- Add conditional edges for the three failure paths.
- Add checkpointing.
- Run your eval and compare with the hand-built version.

**Part B: Engine loop in LangGraph.**
- Build the agent loop as a graph: a model node and a tools node, with a conditional edge back to the model when it asks for tools.
- Run the same eval tasks. Compare: results, cost, lines of code, how easy it was to debug, how much was hidden.

Pin the LangGraph version and write it down.

### Acceptance criteria
- The LangGraph PR tester matches the hand-built one on your eval set, within normal run-to-run variation. If not, explain why.
- The graph calls `run_agent`. The agent loop is not copied into it.
- A written comparison for Part B.
- An exported diagram of the PR tester graph in your README.
- DECISIONS.md: which engine you keep and why.

### Common pitfalls
- Copying the agent loop into the graph for the PR tester, breaking rule 3.
- Calling the PR tester "agentic" because it uses LangGraph. The graph is a fixed workflow. Only the reasoning nodes are agents.
- Library version changes breaking your code mid-project.

### Stretch goal
Kill a run halfway through, then resume it from the checkpoint and confirm it finishes correctly.

---

## Phase 13: LangChain

### Goal
Rebuild your Phase 11 memory and docs search with LangChain and compare with your hand-built version.

### Concepts it teaches
- **Abstractions:** document loaders, text splitters, vector stores, and retrievers, and what each one hides.
- **Fair comparisons:** changing one thing at a time.
- **Lock-in:** what it costs to depend on a framework.

### Suggested approach
- Use the same documents, the same chunk size, the same embedding model, and the same number of results. Only the implementation changes.
- Run the Phase 11 question set and the with-memory eval runs.
- Compare: retrieval quality, eval results, lines of code, ease of debugging, and anything LangChain did differently by default without you asking.

### Acceptance criteria
- Same question set, same metrics, side by side.
- Any difference larger than run-to-run variation is explained.
- A written comparison and a keep decision in DECISIONS.md.

### Common pitfalls
- Changing chunking or embeddings during the rebuild, so differences can't be explained.
- Default settings quietly differing from yours (chunk overlap, for example).
- Not pinning versions.

### Stretch goal
Try one LangChain feature you didn't hand-build (for example, reranking results) and measure whether it helps.

---

## Phase 14: Final comparison against Claude Code

### Goal
The headline result: your harness vs Claude Code, same model, same tasks. Plus ablations of your own harness to say what actually mattered.

### Concepts it teaches
- **Controlled experiments:** holding everything constant except the thing you're testing.
- **Confounds:** hidden differences that make a comparison unfair.
- **Ablations:** turning parts off one at a time to see what each contributes.
- **Honest claims:** saying exactly what your evidence supports and no more.

### Suggested approach

**Freeze everything.** Record the exact model version, your code version, the Claude Code version, and the task list. Don't change any of them during the experiment.

**Main comparison.** Run both agents on the held-out set, 3 times each, with the target model. Metrics: success rate, consistency across runs, cost, time, model calls, tool calls.

**Ablations, your side only.** Turn one thing on or off at a time:
- Coarse vs fine-grained tools.
- Clearing old results on vs off.
- Subagents on vs off.
- Memory on vs off.

**Error analysis.** For every failure on either side, read the trace and give it a category. Show where the gap between the two agents actually is, with examples.

**README.** Lead with the results tables. State the method limit clearly: Claude Code's system prompts, tool definitions, and context handling aren't visible, so the claim is "my harness vs theirs, model held constant," not proof that any specific design choice caused the difference. Causal claims come only from your own ablations.

### Acceptance criteria
- Main results table with variance shown.
- Ablation table.
- Failure categories with real examples from both agents.
- The method limit stated in the README.
- Total project spend reported and under the ceiling.
- One documented command to reproduce the results.

### Common pitfalls
- Having tuned your agent on the held-out set at some point. Check your records.
- Claude Code updating itself in the middle of the experiment. Pin its version.
- Saying "Claude Code wins because of X" when you can't see X.
- Ignoring cost. Winning by spending 5 times more is a different result than winning outright.

### Stretch goal
Rerun the comparison using saved snapshots of your agent from earlier phases, and show how the gap changed as your harness improved.

---

## Out of scope

BravoBot, the offline voice assistant. It could become another front end for the engine later. Not part of this project.
