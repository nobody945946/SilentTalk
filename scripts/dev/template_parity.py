"""Training must render chats exactly as llama-server does at inference.

For every assistant turn of a chat (system, user, tool calls, tool results,
tool definitions), renders the prompt the model gets for that turn with the
HF tokenizer's chat template and with llama-server's /apply-template for the
GGUF, and prints the first difference. Run it before training on a new base
or chat format.

    .runtime/train-venv/bin/python scripts/dev/template_parity.py \
        --hf .runtime/hf/gemma-4-E4B-it-qat \
        --gguf .runtime/models/llm/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf [--request recorded.json]
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from serve_wait import start

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / ".runtime/tools/llama.cpp-b11193-src/build-cuda/bin/llama-server"
SAMPLE = {
    "messages": [
        {"role": "system", "content": "You are a coding agent. Use tools."},
        {"role": "user", "content": "parser.py 的 parse_kv 遇到等號會切錯，請修好。"},
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "call_1", "type": "function",
            "function": {"name": "read", "arguments": json.dumps({"path": "parser.py"})}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "def parse_kv(line):\n    ..."},
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "call_2", "type": "function",
            "function": {"name": "read", "arguments": json.dumps({"path": "test_parser.py"})}}]},
        {"role": "tool", "tool_call_id": "call_2", "content": "def test_kv(): ..."},
        {"role": "assistant", "content": "已修正：改用 split('=', 1)，測試通過。"},
    ],
    "tools": [{"type": "function", "function": {
        "name": "read", "description": "Read a file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}}],
}


def hf_messages(messages: list[dict]) -> list[dict]:
    """OpenAI wire format -> what HF templates expect: tool-call arguments as
    objects (llama-server parses the JSON string the same way)."""
    result = []
    for message in messages:
        calls = message.get("tool_calls")
        if calls:
            message = {**message, "tool_calls": [
                {**call, "function": {**call["function"], "arguments": json.loads(
                    call["function"]["arguments"] or "{}")}}
                if isinstance(call["function"].get("arguments"), str) else call
                for call in calls]}
        result.append(message)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hf", required=True)
    parser.add_argument("--gguf", required=True)
    parser.add_argument("--request", type=Path, help="a body recorded by bench/relay.py --record")
    parser.add_argument("--port", type=int, default=18230)
    args = parser.parse_args()
    body = json.loads(args.request.read_text(encoding="utf-8")) if args.request else SAMPLE
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.hf)
    bos = tokenizer.bos_token or ""
    messages, tools = body["messages"], body.get("tools")
    # What training needs: the prompt before every assistant turn, exactly as
    # the server builds it when it asks the model for that turn.
    turns = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
    server = start(
        [str(SERVER), "--model", args.gguf, "--port", str(args.port), "--host", "127.0.0.1",
         "--jinja", "--n-gpu-layers", "0", "--ctx-size", "4096"], timeout=600)
    failures = 0
    try:
        for index in turns:
            prefix = messages[:index]
            hf = tokenizer.apply_chat_template(
                hf_messages(prefix), tools=tools, tokenize=False,
                add_generation_prompt=True, enable_thinking=False)
            # llama.cpp adds BOS when it tokenizes; HF templates write it as text.
            if bos and hf.startswith(bos):
                hf = hf[len(bos):]
            request = urllib.request.Request(
                f"http://127.0.0.1:{args.port}/apply-template",
                json.dumps({"messages": prefix, "tools": tools,
                            "chat_template_kwargs": {"enable_thinking": False}}).encode(),
                {"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=120) as response:
                served = json.loads(response.read())["prompt"]
            if hf == served:
                print(f"turn {index}: identical ({len(hf)} chars)")
                continue
            failures += 1
            at = next(i for i, (a, b) in enumerate(zip(hf + "\0", served + "\0", strict=False))
                      if a != b)
            print(f"turn {index}: DIFFERENT at char {at} (hf {len(hf)}, server {len(served)})")
            print("  hf    :", repr(hf[max(0, at - 100): at + 100]))
            print("  server:", repr(served[max(0, at - 100): at + 100]))
    finally:
        server.terminate()
        server.wait(timeout=60)
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
