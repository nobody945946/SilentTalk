---
name: handoff
description: Hand work in this repo to another agent, machine or session (the user's laptop Codex, the next dev-box session). Use when writing or updating handoff docs, a TODO for another machine, or when the user says 交接 / handoff / 給筆電 / 讓 agent 處理 / 寫 TODO. Enforces a single entry point (AGENTS.md) and one self-contained work file per machine.
---

# Handoff: one entry, one work file per machine, one way back

The user hands work to agents that start cold: Codex on the Windows laptop,
Claude Code on the Linux dev box. They read whatever the repo shows them
first. Two documents that both look like "the" instructions = a confused
agent and a polluted context. So the layout is fixed:

```
AGENTS.md              the only entry. Codex auto-loads it. Routes by machine, universal rules. Short.
CLAUDE.md              one line: @AGENTS.md  (Claude Code loads the same text)
handoff/dev-box.md     work file for the Linux dev box (RTX 3090)
handoff/laptop.md      work file for the Windows laptop (RTX 3050 Ti)
handoff/reports/       where a machine writes its report (on its report branch)
archive/               old versions, dev box only, gitignored
```

## Rules

1. **Never add another agent-facing file at the repo root.** New machine or role → a new row in AGENTS.md's routing table and a new `handoff/<role>.md`.
2. **A work file is self-contained.** Everything that machine needs is in it: state, steps, commands, pass criteria, what to report. It names what *not* to read. It may point to a specific section elsewhere only when unavoidable.
3. **Rewrite, don't patch.** When a work file's situation has changed (a phase ended, the plan changed), copy the old one to `archive/<NAME>-<date>[-am|-pm].md` and write the new one from scratch with only the current state. Small factual updates (a number, a checkbox) are fine in place; accreting history is not.
4. **One way back.** A machine writes `handoff/reports/<role>.md` and pushes it to branch `<role>-report` (force push is fine, the branch holds nothing else). The dev box reads it with `git fetch origin <role>-report && git show origin/<role>-report:handoff/reports/<role>.md`. Never ask the user to copy-paste unless the push fails.
5. **Reports carry no conversation content**: numbers, event names, the user's own comments. Give the machine a script that produces the numbers (e.g. `scripts/dev/log_summary.py`) instead of letting it read raw logs.
6. **The user only talks, listens and decides.** Installing, running, collecting, debugging belong to the agent.
7. **Universal rules live in AGENTS.md only;** work files hold machine-specific rules. Don't copy rules between files.

## Before telling the user it is ready

Simulate a fresh agent on that machine:
- Open the repo root: is AGENTS.md the only thing that could be read as instructions? (README and ARCHITECTURE are for humans; AGENTS.md says not to read them.)
- Does AGENTS.md route that machine to exactly one file?
- Can every step in the work file run with only what the file says (paths, commands, branch names exist)?
- Is the report path/branch in the work file the same as in AGENTS.md's table?
- Committed and pushed to `copilot-story-mode`?

Then tell the user one line: pull, and tell the agent 「開工」 (it will follow AGENTS.md).
