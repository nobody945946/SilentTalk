"""The machine spirit's lines, base E4B against an adapter, for a blind
comparison on chats no training ever saw.

For every line row of a data folder (render's train.jsonl: the app's own
line requests), both models answer the request as the student step does
(temperature 0.65, top_p 0.85, 90 tokens, as LocalReplyModel): first the base E4B, then the same server
started with the adapter. The pairs are written in random order to
<out>.pairs.json (what the judge reads: the chat and A/B) and the key to
<out>.key.json; `score` joins the judge's verdicts to the key.

    CHARDATA_DIR=.runtime/dev/chardata-ms-eval .venv/bin/python scripts/dev/line_ab.py lines \\
        --lora .runtime/models/llm/machine-spirit-v1.q8_0.gguf --out .runtime/dev/line-ab/ms1
    .venv/bin/python scripts/dev/line_ab.py score --out .runtime/dev/line-ab/ms1 --verdicts verdicts.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.request
from pathlib import Path

# The character data modules import the app (silenttalk) from the repository root.
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parent)]
import chardata_check  # noqa: E402
import chardata_requests  # noqa: E402
import chardata_store  # noqa: E402
from eval_server import MODEL, serve  # noqa: E402

PORT = 18414


def ask(row: dict, lora: bool) -> str:
    """The app's line request, as LocalReplyModel sends it: the server applies
    an adapter only to a request that names it."""
    body = {"messages": row["messages"][:-1], "temperature": 0.65, "top_p": 0.85, "max_tokens": 90,
            "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False},
            **({"lora": [{"id": 0, "scale": 1.0}]} if lora else {})}
    request = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions",
                                     json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return chardata_check.clean_line(json.loads(response.read())["choices"][0]["message"]["content"] or "")


def answers(rows: list[dict], lora: Path | None) -> dict[str, str]:
    process = serve(MODEL, PORT, lora)
    try:
        return {chardata_store.row_key(row): ask(row, lora is not None) for row in rows}
    finally:
        process.terminate()
        process.wait(timeout=60)


def lines(args: argparse.Namespace) -> None:
    rows = [r for r in chardata_store.read_rows(chardata_store.OUT_DIR / "train.jsonl")
            if r["kind"] in chardata_requests.LINE_KINDS]
    persona = chardata_store.persona_of(next(iter(chardata_store.read_rows(chardata_store.OUT_DIR / "personas.jsonl"))))
    base, tuned = answers(rows, None), answers(rows, args.lora)
    rng = random.Random(7)
    pairs, key = [], {}
    for n, row in enumerate(rows, 1):
        k = chardata_store.row_key(row)
        a, b = (base[k], tuned[k]) if rng.random() < 0.5 else (tuned[k], base[k])
        pairs.append({"n": n, "chat": chardata_check.chat_text(row, persona.name), "A": a, "B": b})
        key[str(n)] = "A" if a == tuned[k] and a != base[k] else "B" if b == tuned[k] and b != base[k] else "same"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix(".pairs.json").write_text(json.dumps(pairs, ensure_ascii=False, indent=1), encoding="utf-8")
    args.out.with_suffix(".key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"{len(pairs)} pairs -> {args.out.with_suffix('.pairs.json')}")


def score(args: argparse.Namespace) -> None:
    key = json.loads(args.out.with_suffix(".key.json").read_text(encoding="utf-8"))
    verdicts = json.loads(args.verdicts.read_text(encoding="utf-8"))  # {"n": "A"|"B"|"tie"}
    judged = [(n, v) for n, v in verdicts.items() if key.get(n) in ("A", "B")]
    wins = sum(v == key[n] for n, v in judged)
    ties = sum(v == "tie" for _, v in judged)
    losses = len(judged) - wins - ties
    print(json.dumps({"pairs": len(judged), "adapter_wins": wins, "ties": ties, "base_wins": losses,
                      "same_line": sum(v == "same" for v in key.values())}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=("lines", "score"))
    parser.add_argument("--lora", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verdicts", type=Path)
    args = parser.parse_args()
    (lines if args.step == "lines" else score)(args)


if __name__ == "__main__":
    main()
