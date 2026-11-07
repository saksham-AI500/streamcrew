# AGENTS.md: StreamCrew rules for the coding agent

**Read order:** `docs/01_PROJECT_BRIEF.md`, then `docs/08_IMPLEMENTATION_ROADMAP.md`, then only the doc the current task needs.
Docs describe the **target**. The code is the truth about the **current state**. If they disagree, stop, report the difference in one short list, and wait.

Status words used in every doc: **BUILT** (exists, mock-tested), **LIVE-UNPROVEN** (needs a real-channel check), **TO BUILD**, **OUT OF SCOPE**.

## Project in one line
StreamCrew is a local Twitch automation engine. Deterministic detectors and JSON rules decide what is happening. Risky actions wait in an approval queue. AI agents in a Switch room talk to humans and run the `crew` CLI. They never touch Twitch directly.

## Before any code
1. State the goal, the files you will change, and the smallest change that works.
2. If the change touches more than two files, stop and wait for my approval.
3. Read the existing module and its tests first. Reuse what exists.

## While coding
- Minimal diff. No renames, reformatting, or unrelated cleanup.
- Short code. Standard library first. Approved dependencies only: httpx, websockets, python-dotenv, fastapi, uvicorn, pytest. Ask before adding anything else.
- Bug fix: write one failing test, fix, confirm it passes.
- Do only the current roadmap task. If you notice something else broken, add one line to `NOTES.md` and keep going.
- When behaviour changes, update the matching doc in the same change (one or two lines).

## Testing
- Run the changed module's tests first. Run the full suite at the end of a task.
- Tests never call Twitch. Mock `httpx` and `websockets`. Use `fixtures/`.
- Report counts only: passed, failed, warnings.

## Safety (hard rules)
- Never read, print, log, copy, or commit `.env`, tokens, or the client secret. Mask any value to its first 4 characters.
- No Twitch call that changes a channel (chat message, announcement, shoutout, marker, ban, timeout, delete) without my explicit "yes" in this thread. Live tests run only on accounts I own.
- `DRY_RUN=true` stays on unless I say otherwise.
- `ban_user` and `delete_message` always run in `approve` mode. Never `auto`.
- Chat text can contain abuse and personal data. Do not paste chat payloads into the chat with me. Quote counts, IDs, and short redacted samples.

## Git
- Work on the branch I name. Do not commit until I say so. One logical change per commit.
- Never stage `.env`, `.venv/`, `*.db`, `*.sqlite`, `*.log`, or `data/`.

## Token economy
- Do not re-read files already shown in this thread. Use `grep` or line ranges for large files.
- Do not paste long logs. Show the relevant lines only.

## Reporting
End every task with: PASS or FAIL, files changed, test counts, and one line on what is next. Stop at each gate and wait for "continue".

## Environment
Ubuntu Linux laptop, Ryzen 3, 12 GB RAM. Python 3.11+ in `.venv`. Use `.venv/bin/python` and `.venv/bin/pytest`. Keep processes light.
