# Claude ⇄ Antigravity Handover Protocol

**Roles.** Claude is the principal architect and reviewer. It designs, decides, writes handovers and reviews
results. **Antigravity is the implementation agent.** It executes handovers exactly. It does not design, does not
change architecture decisions and does not invent requirements. If Antigravity makes a mistake because a handover
was ambiguous, that is Claude's defect, so Antigravity must stop and ask instead of guessing.

---

## 1. Start of every Antigravity session (in this order)

1. `AGENTS.md` → `context.md` (the "CURRENT STATE" and "NEXT ACTION" blocks).
2. `docs/04_ROADMAP.md` §3 for the active phase, then that phase's handover file
   (`docs/handovers/P<nn>_*.md`). Read the **whole** handover before touching code.
3. `docs/handovers/QUESTIONS.md`: open questions may block items.
4. Check the environment:
   ```powershell
   git status; git branch --show-current
   python --version          # expect 3.14.x
   python -c "import PySide6, numpy, PIL; print('deps ok')"
   ```
5. Verify the baseline before changing anything:
   ```powershell
   powershell -File scripts\verify_all.ps1 -Quick      # after P0; before P0 use the two pytest commands
   ```
   If the baseline is red, **stop**. Record the failure in `QUESTIONS.md` and in `context.md`, and do not start new work.

## 2. Executing a work item

Each handover is a list of work items `WI-<phase>.<n>`. For each item:

1. Set the item's row in the handover's **Progress** table to `IN PROGRESS` with an ISO timestamp.
2. Implement **exactly** the listed steps, in order, touching only the listed files. If you must touch another file
   (an import fix, for example), say so in the commit message.
3. Code in the handover is canonical. Copy it, then adapt names only where the handover says "adapt". Keep the
   surrounding code's style: type hints, `from __future__ import annotations`, pydantic v2, no new dependencies unless
   the item lists them.
4. Write the tests listed for the item. A test must fail without the change. Check this once by temporarily
   reverting the change, or by explaining in the commit message why that is impossible.
5. Run the item's **verification** commands and paste the result summary (pass counts, exit codes, evidence paths) into
   the Progress table's "Evidence" column.
6. Commit on the phase branch: `git commit -m "P<n> WI-<n>.<k>: <summary>"`. One work item per commit. Do not push
   unless the user asks.
7. Set the row to `DONE` only if every acceptance bullet of the item is green. Otherwise set `PARTIAL` or `BLOCKED` with the
   reason.

## 3. Hard rules (any violation invalidates the phase)

- Never edit `graders/protected/`. Never weaken a gate, threshold, predicate or test to make something pass.
- Never mark anything PASS without an evidence file or a test result produced **in this session**.
- Never use anything under `tests/doubles/` or marked `simulated: True` as evidence.
- Engine runs use disposable projects under `E:\GameForge\validation\<phase>_<topic>_<yyyymmdd>\`, never `GFProbe`
  itself or a user project.
- No installs, downloads, paid services or data egress without explicit user approval in chat. If approval is
  missing, mark the item `BLOCKED (needs approval: <what>)`.
- Ollama calls always pass `"think": false` and an explicit `num_ctx`.
- Large artifacts go on `E:` only.
- If the user says to shut down the PC: `shutdown /s /t 0` immediately (AGENTS.md).
- Do not refactor code that is not in the item. Do not "improve" architecture. Write ideas in `QUESTIONS.md`.

## 4. When a handover is unclear or wrong

Stop that item. Append to `docs/handovers/QUESTIONS.md`:

```markdown
## Q-<yyyymmdd>-<n> (P<n> WI-<n>.<k>) — <one line>
- Observed: <exact error / file:line / contradiction>
- Handover says: <quote>
- Options I can see: (a) … (b) …
- Blocking: yes/no (what else I can do meanwhile)
```

Then continue with the next work item that does **not** depend on the blocked one. Never pick an option yourself.

## 5. End of every Antigravity session

1. Update the handover's Progress table.
2. Update `context.md`: replace the CURRENT STATE and NEXT ACTION blocks (do not append another log entry at the top),
   and add one line to the *Session log* section with the ISO time, items done and test counts. Mirror the file to
   `E:\GameForge\context.md` and check the copy with `Get-FileHash`.
3. Update the affected rows of `docs/00_STATUS.md`.
4. Leave the tree committed. A dirty tree at hand-back is a defect.

## 6. Claude review procedure (when Claude resumes)

1. `git log --oneline master..phase/P<n>-*`, then `git diff master...phase/P<n>-* --stat`.
2. For each commit: read the diff against the work item. Check that only listed files changed, the code matches the
   handover's interfaces, tests fail without the change, and no gate was weakened. Grep the diff for
   `simulated`, `skip`, `xfail`, `satisfied=True`, `except Exception: pass`, `time.sleep(` in tests, hard-coded `E:\`.
3. Re-run `scripts\verify_all.ps1` (full, including engine gates for engine items) and compare with the claimed
   evidence. **Evidence that does not reproduce is treated as false.**
4. Write the verdict in the handover's **Review log**: `ACCEPT`, `ACCEPT WITH FIXES (listed)` or `REJECT (reasons)`, with
   timestamp. Only `ACCEPT` allows a merge to `master`.
5. Answer `QUESTIONS.md` entries. If an answer changes a handover, edit the handover and note the change in its
   "Revisions" section.

## 7. Mid-phase handover (Claude's limits approaching)

When Claude's usage or context may run out in the middle of a phase, Claude appends a block to the active handover:

```markdown
## SESSION HANDOVER <ISO time> (Claude → Antigravity)
- State: <what is done, committed SHA, branch>
- In-flight: <exact file + function being changed, what remains, the exact next edit>
- Do next: WI-x.y steps k..m (unchanged) — OR — revised steps:
  1. …
- Do NOT do: <items that need Claude's review first>
- Verification to run before stopping: <commands>
```

Antigravity executes only what the block says, and it follows sections 2–5.

## 8. Status vocabulary

Work items: `TODO`, `IN PROGRESS`, `DONE`, `PARTIAL`, `BLOCKED`. Capabilities: `PASS`, `PARTIAL`, `FAIL`,
`BLOCKED`, `NOT VERIFIED`, `EXPERIMENTAL`, `PLANNED`. Evidence states: `[VERIFIED]`, `[REPORTED]`,
`[UNVERIFIED]`, `[BLOCKED]`, `[SUPERSEDED]`.
