"""Training data for the character-mode LoRA of the machine spirit (the
app's own character, written by machine_spirit.py builtin).

Its chat lines are written by the laptop's agent with its own model (the
owner's decision, 2026-10-06): each chat is a skeleton (who says what kind
of line, by construction of the product's Discord design) and the writer's
words. The steps (each resumes; files under $CHARDATA_DIR):

    external-check   on the writer's machine: every answer assembles and
                     passes the script checks, or exit 1 (no data dir)
    external-import  the answers join scripts.jsonl, stamped with their writer
    render           the app's own requests as training rows: the gates
                     (chat work? change or read?) and the lines, with
                     speech-recognition noise on the others' lines
    student          the student model (E4B) answers the same requests
    check            the checker compares, blind and in both orders
    filter           only rows that pass the hard check train (HARD_CHECK)

A line is for the character only when it says its name (or is a typed
@/reply); every such line is first asked the chat-work question. Calls are
labelled talk / work / computer; work comes with the Agent's instructions and
result, the acceptance and later the report. Thread scripts are the owner's
typed work, labelled whether it changes anything.

The checker is an open-weight model; Claude may only evaluate
(handoff/dev-box.md). Names and scenes of the eval sets are excluded.
Everything is synthetic; no real conversation is involved.

This file is the command line; each step lives in its own module beside it:
chardata_external (external-check, external-import), chardata_render,
chardata_check (student, check) and chardata_filter, on the script rules
(chardata_scripts), the app's requests (chardata_requests) and the data
directory (chardata_store).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# The steps import the app (silenttalk) from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import chardata_store as store  # noqa: E402  (scripts/dev)
import provenance  # noqa: E402
from chardata_check import make_check, make_student  # noqa: E402
from chardata_external import make_external_check, make_external_import  # noqa: E402
from chardata_filter import HARD_CHECK, make_filter  # noqa: E402
from chardata_render import make_render  # noqa: E402

# Exit code for "these files were made under other rules": blocked at once.
MIXED_EXIT = 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=("external-check", "external-import", "render", "student", "check",
                                         "filter"))
    parser.add_argument("--tasks", help="external-check/import: the chats' persona and skeletons (.json)")
    parser.add_argument("--file", help="external-check/import: the writer's answers (JSONL)")
    parser.add_argument("--student-url", default="http://127.0.0.1:18210")
    parser.add_argument("--teacher-url", default="http://127.0.0.1:18200", help="check: the checker")
    parser.add_argument("--rows", default="train.jsonl", help="student/check/filter: rows file in the data dir")
    parser.add_argument("--min-gate-agree", type=float, default=HARD_CHECK["gate_agree"])
    parser.add_argument("--min-lines", type=int, default=HARD_CHECK["lines_kept"])
    parser.add_argument("--max-gate-rows", type=int, default=4000)
    parser.add_argument("--lines-by-rules", action="store_true",
                        help="check: compare no lines; filter: keep every line that passes the app's rules")
    parser.add_argument("--workers", type=int, default=4, help="match llama-server --parallel")
    parser.add_argument("--max-chars", type=int, default=72)
    parser.add_argument("--max-prompt-chars", type=int, default=3400)
    args = parser.parse_args()
    if args.step == "external-check":
        # Runs on the machine that wrote the answers: no data directory.
        return make_external_check(args)
    store.OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every file this step reads or extends must come from these rules.
    problems = provenance.require_same(
        [store.OUT_DIR / name for name in {*store.DATA_FILES, args.rows}], store.rules_version())
    if problems:
        print("REFUSED, data made under other rules (start a new data directory): "
              + "; ".join(problems), flush=True)
        return MIXED_EXIT
    if args.step == "filter":
        return make_filter(args)
    {"external-import": make_external_import, "render": make_render, "student": make_student,
     "check": make_check}[args.step](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
