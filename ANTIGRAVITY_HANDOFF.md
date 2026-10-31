# Antigravity — start here

You are the **implementation agent**. Claude is the architect and reviewer. You execute handovers exactly. You do not
design, change architecture decisions, or invent requirements.

1. Read `AGENTS.md`, then `context.md` (CURRENT STATE and NEXT ACTION).
2. Read `docs/handovers/HANDOVER_PROTOCOL.md` in full. It defines how you work, what you may not do, how to ask
   questions (`docs/handovers/QUESTIONS.md`), and how to hand back.
3. Open the active phase handover named in `context.md` (starting with `docs/handovers/P00_foundation.md`), and
   execute its work items in order, committing on `master` (no branches).
4. Verify with the commands in `docs/08_TESTING_AND_EVIDENCE.md` §3 (after P0: `scripts\verify_all.ps1`).
5. Before you stop: update the handover's Progress table, `context.md` (replace CURRENT STATE / NEXT ACTION; mirror to
   `E:\GameForge\context.md`) and `docs/00_STATUS.md`. Leave the tree committed.

**Never:** edit `graders/protected/`; weaken a gate or test; claim PASS without evidence from this session; use
`tests/doubles/` or `simulated: True` code as evidence; install, download or send data out without the user's approval;
put large artifacts on C:.

Superseded instructions (the 2026-10-27 small-task list and the M8–M20 playbook) are in git history and
`docs/history/`. Do not follow them.
