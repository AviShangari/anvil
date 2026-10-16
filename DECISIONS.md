# DECISIONS.md

One line per choice: what, why, and what was rejected.

## Phase 4

- **Model prices:** Haiku 4.5 at $1.00 / M input and $5.00 / M output (`engine.py`). Used for dev per PLAN rule 10; output costs 5x input so the two are counted separately.
- **Cost ceiling:** $0.25 per user turn in chat, $0.50 per scenario in `test_agent.py`. A normal bug fix costs about $0.02-0.03 (scenario A: $0.0243), so the ceiling only fires on a runaway.
- **Over-budget overshoot:** the check runs before each model call, so the call that crosses the ceiling still happens. The overshoot is at most one call's cost (about $0.01 on this fixture). Checked there, not right after the call, so the context always ends on a complete tool_result message.
- **Max model calls:** 20 per turn. A fix takes about 8 calls, so 20 leaves room to recover from errors but stops loops early.
- **Tool definition cost:** 1143 input tokens (58 for "hi" with no tools, 1201 with the four tools). Includes the small fixed tool-use instructions the API adds whenever tools are sent. Paid on every call, so about 9,000 extra input tokens across an 8-call fix.
- **Clearing unit:** "keep the newest N" counts tool-result *messages* (batches of parallel calls), not individual results. Rejected: counting blocks. Scenario G failed 3/3 with it (`keep_recent=2`, status `hit_limit`): the model reads 4 files in one parallel batch, only 2 survived, so it re-read them, they were cleared again, and it looped to the 20-call limit. After the change G passed 3/3.
- **Clearing threshold:** 20,000 input tokens, keep the newest 3 result messages. Fixture tasks peak far below this, so clearing stays off on small jobs and starts long before the 200k window fills. The check uses the previous call's `usage.input_tokens`, so the first call of a turn never clears. Only `content` is replaced; tool_use/tool_result blocks stay.
- **Blocklist:** recursive deletes (rm/rmdir/del/Remove-Item with -r or /s), `git push`, and network tools (curl, wget, iwr, irm, Invoke-WebRequest/RestMethod). Matched on the lowercased, whitespace-collapsed command. Never complete (e.g. a .NET `[IO.Directory]::Delete` call is not caught), so edits and commands also ask for confirmation in chat, and Phase 6 adds a real sandbox.
- **Other stop reasons:** anything that is not `tool_use`, `end_turn` or `max_tokens` (e.g. `refusal`) ends the turn with that reason as the status. Rejected: sending an empty tool_result message, which the API rejects.
- **Test `can_run`:** allows read, search and edit, and allows commands unless blocklisted. It shares `is_blocked` with the chat version so the test checks the real blocklist.

## Still owed (yours to write, the reasons are yours)

- Phase 2: why timezone is required.
- Why `MAX_LINES = 500` and `MAX_RESULTS = 50`.
