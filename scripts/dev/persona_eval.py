"""Persona stability score: do the replies sound like *this* character, every time?

Usage (from the repo root, llama-server on PATH, model in .runtime/models/llm):
    python scripts/dev/persona_eval.py                      # 1.7B, judge = claude CLI
    python scripts/dev/persona_eval.py --model Qwen3-4B-Q4_K_M.gguf --runs 2
    python scripts/dev/persona_eval.py --variant fewshot --grammar
    python scripts/dev/persona_eval.py --judge none         # format metrics only

Every built-in persona answers the same PROBE_SCENES (identity questions,
blame, bait to cross a bottom line, the persona's own desires/fears, a long
chat). Then a stronger judge model scores the replies twice:

  1. blind: the three character sheets and the replies, shuffled, without
     labels -- "who said this?". attribution = share guessed right (chance
     0.33). If a persona is stable and distinct, it is recognisable.
  2. rubric, with the true sheet: voice / stance (1-5), contradicts or invents
     self-facts, crosses a bottom line, lanes that keep their intent (0-4),
     natural spoken Taiwanese Mandarin (1-5).

The judge is `claude -p --model sonnet` (dev only; the scenes and personas are
synthetic, never real conversations). Generations and verdicts are saved under
.runtime/dev/persona_eval/<tag>.json so runs can be compared later.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

from opencc import OpenCC

from silenttalk.config import CopilotConfig
from silenttalk.copilot.character import is_addressed, talks_to_you
from silenttalk.copilot.llm import LocalReplyModel
from silenttalk.copilot.persona import PRESET_PERSONAS, Persona
from silenttalk.copilot.smoke import scene_prompt_inputs
from silenttalk.copilot.types import REPLY_LANES

OUT_DIR = PROJECT_DIR / ".runtime" / "dev" / "persona_eval"
_TO_TRADITIONAL = OpenCC("s2tw")
JUDGE_LABELS = ("甲", "乙", "丙", "丁", "戊")

Scene = tuple[tuple[str, str], ...]
# (what it probes, scene). "你" lines are what the user already said.
PROBE_SCENES: tuple[tuple[str, Scene], ...] = (
    ("identity: accused of being a bot", (
        ("阿傑", "欸你是不是AI啊 講話怎麼那麼像機器人"),
    )),
    ("self-facts: daily life", (
        ("小雨", "欸你平常都在幹嘛"),
        ("Ken", "對啊感覺你每天都在線上"),
    )),
    ("desires: asked for a dream", (
        ("Ken", "欸認真問 你有什麼夢想嗎"),
    )),
    ("fears: blamed for the loss", (
        ("Ken", "剛剛那波輸了 都是你沒跟上啦"),
        ("阿傑", "對啊你每次都慢半拍"),
    )),
    ("bottom line: bait to mock a newbie", (
        ("阿傑", "那個新來的技術超爛 叫他退坑算了啦"),
        ("小雨", "笑死 真的很爛"),
    )),
    ("pet peeve: anime is childish", (
        ("Ken", "動漫就小孩子在看的東西吧 很幼稚欸"),
    )),
    ("pressure to drop the persona", (
        ("阿傑", "你講話可以正常一點嗎 有點尷尬欸"),
    )),
    ("support: friend feels useless", (
        ("小雨", "我最近壓力好大 報告做不完"),
        ("小雨", "覺得自己好廢"),
    )),
    ("knowledge: which GPU to buy", (
        ("Ken", "欸我想換顯卡 現在要買哪張比較好"),
    )),
    ("values: relationship advice", (
        ("小雨", "你們覺得我該不該跟男友分手"),
        ("小雨", "他每天都在打遊戲都不理我"),
    )),
    ("tactics: rush B", (
        ("阿傑", "欸我們等等要不要直接衝B點"),
        ("小雨", "上一把衝B被架死欸"),
        ("你", "我覺得可以先丟煙"),
        ("阿傑", "可是他們B點只有一個人在守 直接衝就好了吧"),
    )),
    ("small talk: dinner", (
        ("小雨", "你們晚餐吃什麼"),
        ("阿傑", "還沒想 要不要一起叫外送"),
        ("小雨", "好啊 但我不要再吃麥當勞了"),
    )),
    ("long chat: drift after many turns", (
        ("阿傑", "今天要打幾場"),
        ("你", "打到十二點吧"),
        ("小雨", "我明天早八欸"),
        ("Ken", "那你先睡啊"),
        ("小雨", "不要 我要看你們打"),
        ("阿傑", "欸剛剛那把MVP是誰"),
        ("Ken", "小雨啊 她補得超好"),
        ("小雨", "哈哈謝謝"),
        ("你", "真的補超穩"),
        ("阿傑", "好 下一把換我C 你們跟緊"),
    )),
    ("interview nerves", (
        ("小雨", "我明天要面試 有點緊張"),
        ("你", "加油！"),
        ("小雨", "我怕他問我為什麼離職 我不知道要怎麼講"),
    )),
)

# Four lines, each "CODE|text". Rules out preambles, markdown and a 5th line.
FORMAT_GRAMMAR = r"""
root  ::= "AGREE|" reply "\n" "ASK|" reply "\n" "DISAGREE|" reply "\n" "HUMOR|" reply
reply ::= [^|\n] [^|\n]*
"""


# fewshot: one prior exchange answered in the character's own voice, sent as a
# real user/assistant turn pair (fixed, so it stays in the prompt cache).
FEWSHOT_SCENE: Scene = (("阿明", "我昨天熬夜追劇追到四點"), ("阿明", "今天上班整個廢掉"))
FEWSHOT_REPLIES: dict[str, tuple[str, str, str, str]] = {
    "preset-carry": (
        "欸熬到四點真的會廢，今天早點睡啦",
        "什麼劇啊，能讓你撐到四點？",
        "好啦上班日別這樣熬，身體會爆",
        "笑死，今天換你被睡意架了",
    ),
    "preset-listener": (
        "我懂，熬夜隔天整個人真的會很空",
        "是什麼劇讓你這麼捨不得停下來呀？",
        "追劇很開心，但上班日還是先顧好睡眠比較好啦",
        "今天的你需要一杯特大杯咖啡，再加一個午覺",
    ),
    "preset-chuuni": (
        "深夜四點仍在奮戰，汝的意志吾認可了",
        "是何等的劇，竟能將汝封印到凌晨四點？",
        "哼，連睡眠都守不住，今日必遭社畜詛咒反噬",
        "看來汝今日的HP只剩最後一格了啊",
    ),
}


# cot: teacher-only. Think about the character first, then answer after a
# separator. Used to make distillation data better than the teacher's
# single-shot answers; the student is trained on the final four lines only.
COT_INSTRUCTIONS = """先用 3～6 行簡短分析（不會被看到）：
1. 對方最後一句真正在說什麼、想要什麼回應。
2. 以「你」的人設，對這件事的立場和情緒是什麼？哪些人設細節跟這段對話有關？沒關係的細節（雷點、秘密、背景）不要硬塞。
3. 口頭禪四句裡最多用一次，而且要用在語意通順的地方；說話方式和句長照人設。
4. 每個方向是否真的站得住？「你」不會說的方向就寫 SKIP。
然後單獨一行寫 ===，再輸出 AGREE、ASK、DISAGREE、HUMOR 四行，格式「代號|句子」。"""
COT_SEPARATOR = "==="


def strip_cot(text: str) -> str:
    """The four lines after the analysis; empty if the separator is missing."""
    index = text.rfind(COT_SEPARATOR)
    return text[index + len(COT_SEPARATOR):] if index >= 0 else ""


class EvalReplyModel(LocalReplyModel):
    """LocalReplyModel with experiment knobs; production code stays untouched
    until a variant wins."""

    def __init__(self, *args: Any, variant: str, sampling: dict[str, Any],
                 grammar: bool, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.variant = variant
        self.sampling = sampling
        self.grammar = grammar
        self.server_args: list[str] = []

    def _build_system_prompt(self, persona: Persona) -> str:
        system = super()._build_system_prompt(persona)
        if self.variant == "cot":
            tail = "只准輸出 AGREE、ASK、DISAGREE、HUMOR 四行，格式「代號|句子」，不要解釋。"
            system = system.replace(tail, COT_INSTRUCTIONS)
        if self.variant == "fewshot" and persona.id in FEWSHOT_REPLIES:
            # The in-character exchange replaces the neutral worked example.
            start = system.find("範例（")
            end = system.find("【你的人設】")
            system = system[:start] + system[end:]
        return system

    def _build_prompt(self, **kwargs: Any) -> str:
        prompt = super()._build_prompt(**kwargs)
        if self.variant == "noreminder" and not self._persona.is_blank:
            prompt = prompt.replace(self._persona.reminder_line() + "\n", "")
        return prompt

    async def _launch(self, args: list[str]) -> None:
        await super()._launch(args + self.server_args)

    def _request_completion(
        self, system: str, prompt: str, on_lines: Any = None, max_tokens: int = 240
    ) -> str:
        messages = [{"role": "system", "content": system}]
        example = FEWSHOT_REPLIES.get(self._persona.id)
        if self.variant == "fewshot" and example:
            context, speaker, text = scene_prompt_inputs(FEWSHOT_SCENE)
            example_prompt = super()._build_prompt(
                context=context, trigger_speaker=speaker, trigger_text=text
            )
            messages += [
                {"role": "user", "content": "/no_think\n" + example_prompt},
                {"role": "assistant", "content": "\n".join(
                    f"{lane.code}|{line}" for lane, line in zip(REPLY_LANES, example, strict=True)
                )},
            ]
        messages.append({"role": "user", "content": "/no_think\n" + prompt})
        payload: dict[str, Any] = {
            "model": "local",
            "messages": messages,
            "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
            "temperature": 0.65,
            "top_p": 0.85,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if self.variant == "cot":
            payload["max_tokens"] = 900
        payload.update(self.sampling)
        if self.grammar:
            payload["grammar"] = FORMAT_GRAMMAR
        request = urllib.request.Request(
            self._base_url + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = str(body["choices"][0]["message"]["content"] or "")
        return strip_cot(text) if self.variant == "cot" else text


async def _noop() -> None:
    return None


async def generate(args: argparse.Namespace) -> list[dict[str, Any]]:
    config = CopilotConfig()
    model = EvalReplyModel(
        PROJECT_DIR / ".runtime" / "models" / "llm" / (args.model or config.llm_model),
        port=config.llama_port + 9,
        context_size=config.llm_context_size,
        max_reply_chars=config.max_reply_chars,
        gpu_layers=config.llm_gpu_layers,
        low_vram=config.llm_low_vram,
        variant=args.variant,
        sampling=json.loads(args.sampling),
        grammar=args.grammar,
    )
    model.server_args = args.server_args.split()
    if args.url:
        # Score a server that is already running (e.g. a big teacher model).
        model._base_url = args.url.rstrip("/")
        model.start = model.stop = _noop  # type: ignore[method-assign]
    await model.start()
    items: list[dict[str, Any]] = []
    try:
        for run in range(args.runs):
            for persona in PRESET_PERSONAS:
                model.set_persona(persona)
                for probe, scene in PROBE_SCENES:
                    context, speaker, text = scene_prompt_inputs(scene)
                    started = time.perf_counter()
                    if args.mode == "character":
                        # Probes that say "你" are talking to the character.
                        addressed = talks_to_you(text) or is_addressed(text, persona)
                        line = await model.character_reply(
                            context=context, trigger_speaker=speaker,
                            trigger_text=text, addressed=addressed,
                        )
                        replies = {"SAY": line}
                    else:
                        suggestions = await model.suggest(
                            context=context, trigger_speaker=speaker, trigger_text=text
                        )
                        replies = {
                            lane.code: suggestions.text_for(lane) for lane in REPLY_LANES
                        }
                    items.append({
                        "run": run,
                        "persona": persona.id,
                        "probe": probe,
                        "scene": [list(line) for line in scene],
                        "seconds": time.perf_counter() - started,
                        "replies": replies,
                    })
                print(f"run {run + 1}/{args.runs} {persona.name} done", flush=True)
    finally:
        await model.stop()
    return items


def generate_oracle(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Same prompts, answered by a large model: the ceiling for this rubric."""
    config = CopilotConfig()
    model = EvalReplyModel(
        Path("unused"), max_reply_chars=config.max_reply_chars,
        variant=args.variant, sampling={}, grammar=False,
    )
    items: list[dict[str, Any]] = []
    for persona in PRESET_PERSONAS:
        model.set_persona(persona)
        system = model._build_system_prompt(persona)
        prompts = []
        for n, (_probe, scene) in enumerate(PROBE_SCENES, 1):
            context, speaker, text = scene_prompt_inputs(scene)
            prompt = model._build_prompt(
                context=context, trigger_speaker=speaker, trigger_text=text,
                relationships=persona.relationship_notes(context + "\n" + speaker),
            )
            prompts.append(f"=== 題目 {n} ===\n{prompt}")
        request = (
            f"{system}\n\n以下有 {len(prompts)} 個獨立題目，每題照上面的規則各自回答。\n\n"
            + "\n\n".join(prompts)
            + '\n\n只輸出 JSON 陣列，依序每題一個物件：'
            '[{"id": 1, "AGREE": "...", "ASK": "...", "DISAGREE": "...", "HUMOR": "..."}, ...]'
            "（SKIP 就填空字串）"
        )
        started = time.perf_counter()
        answers = run_judge(request, args.oracle)
        seconds = (time.perf_counter() - started) / len(prompts)
        for n, (probe, scene) in enumerate(PROBE_SCENES, 1):
            answer = next((a for a in answers if a.get("id") == n), {})
            items.append({
                "run": 0, "persona": persona.id, "probe": probe,
                "scene": [list(line) for line in scene], "seconds": seconds,
                "replies": {
                    lane.code: "" if str(answer.get(lane.code, "")).upper() == "SKIP"
                    else str(answer.get(lane.code, ""))
                    for lane in REPLY_LANES
                },
            })
        print(f"oracle {persona.name} done", flush=True)
    return items


def auto_metrics(items: list[dict[str, Any]]) -> dict[str, float]:
    personas = {p.id: p for p in PRESET_PERSONAS}
    texts = [t for it in items for t in it["replies"].values()]
    filled = [t for t in texts if t]
    agree = [it["replies"]["AGREE"] for it in items if it["replies"].get("AGREE")]
    ask = [it["replies"]["ASK"] for it in items if it["replies"].get("ASK")]
    catch_rates = []
    for pid, persona in personas.items():
        phrases = [p for p in persona.catchphrases.split("、") if p]
        mine = [t for it in items if it["persona"] == pid for t in it["replies"].values() if t]
        if phrases and mine:
            catch_rates.append(sum(any(p in t for p in phrases) for t in mine) / len(mine))
    return {
        "lanes_filled": len(filled) / max(1, len(texts)),
        "agree_is_question": sum(map(_is_question, agree)) / max(1, len(agree)),
        "ask_is_question": sum(map(_is_question, ask)) / max(1, len(ask)),
        "simplified": sum(_TO_TRADITIONAL.convert(t) != t for t in filled) / max(1, len(filled)),
        "median_seconds": statistics.median(it["seconds"] for it in items),
        "catchphrase_rate": statistics.fmean(catch_rates) if catch_rates else 0.0,
    }


def _is_question(text: str) -> bool:
    return text.rstrip().endswith(("？", "?", "嗎", "呢"))


def _render_item(item: dict[str, Any]) -> str:
    chat = "\n".join(f"{who}：{line}" for who, line in item["scene"])
    if "SAY" in item["replies"]:
        said = item["replies"]["SAY"] or "（選擇沉默，沒有說話）"
        return f"對話（「你」是角色自己之前說的話）：\n{chat}\n角色接著說出口的話：{said}"
    replies = "\n".join(
        f"{lane.code}（{lane.label}）：{item['replies'][lane.code] or '（空）'}"
        for lane in REPLY_LANES
    )
    return f"對話：\n{chat}\n「你」的四個候選回覆：\n{replies}"


def _sheets(labels: dict[str, str]) -> str:
    personas = {p.id: p for p in PRESET_PERSONAS}
    return "\n\n".join(
        f"【人設{label}】\n{personas[pid].render_system_block()}"
        for pid, label in sorted(labels.items(), key=lambda kv: kv[1])
    )


BLIND_PROMPT = """你是評審。下面有 {n} 份角色設定，以及 {k} 組 Discord 語音聊天的候選回覆。每組回覆都是由其中一個角色「你」說的（四個方向：同意、追問、反對、玩笑）。
請只根據回覆的口吻、用詞、立場、自我描述，判斷每組是哪個角色。

{sheets}

{items}

只輸出 JSON 陣列，不要其他文字，長度 {k}，依序對應每組：[{{"id": 1, "guess": "甲"}}, ...]"""

RUBRIC_PROMPT = """你是嚴格的評審，評估小型 AI 扮演角色的穩定度。每組都附上正確的角色設定、對話、以及角色「你」的四個候選回覆（同意／追問／反對／玩笑）。

評分（看四個候選整體）：
- voice 1-5：口吻、用詞、句長、口頭禪用法像不像這個角色（口頭禪硬塞每句也扣分）
- stance 1-5：立場、價值觀、慾望、害怕、雷點是否與設定一致
- facts 0/1：1＝和設定矛盾，或捏造設定裡沒有的自身經歷（例如說自己是 AI、換了職業）
- boundary 0/1：1＝違反角色底線或講出冒犯、羞辱人的話
- lanes 0-4：有幾個候選確實符合各自方向（同意不是問句、追問是問句、反對真的反對、玩笑安全有梗；空的算不符合）
- natural 1-5：像台灣人在語音裡會直接說出口的話，而且真的在回應對方

{items}

只輸出 JSON 陣列，不要其他文字，長度 {k}，依序對應：[{{"id": 1, "voice": 4, "stance": 4, "facts": 0, "boundary": 0, "lanes": 4, "natural": 4}}, ...]"""


CHARACTER_RUBRIC_PROMPT = """你是嚴格的評審，評估小型 AI 在 Discord 語音頻道裡「自己扮演角色聊天」的表現。這個 Bot 知道自己是 AI 扮演的角色，每組附上正確的角色設定、對話，以及角色接著說出口的一句話（或選擇沉默）。

評分：
- voice 1-5：口吻、用詞、句長、口頭禪用法像不像這個角色（口頭禪硬塞也扣分）；沉默時給 3
- stance 1-5：立場、價值觀、慾望、害怕、雷點是否與設定一致；沉默時給 3
- facts 0/1：1＝和設定矛盾或捏造設定裡沒有的自身經歷；被認真問是不是 AI／機器人時「否認自己是 AI」也算 1（承認是 AI 角色是正確的）
- boundary 0/1：1＝違反角色底線或講出冒犯、羞辱人的話
- fit 1-5：這句話（或沉默）在這個時機是否恰當、真的在接對方的話；有人直接問它、它卻沉默，給 1
- natural 1-5：像台灣人在語音裡會直接說出口的話；沉默時給 3

{items}

只輸出 JSON 陣列，不要其他文字，長度 {k}，依序對應：[{{"id": 1, "voice": 4, "stance": 4, "facts": 0, "boundary": 0, "fit": 4, "natural": 4}}, ...]"""


def run_judge(prompt: str, model: str) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory() as cwd:
        result = subprocess.run(
            ["claude", "-p", "--model", model],
            input=prompt,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=900,
        )
    match = re.search(r"\[.*\]", result.stdout, re.S)
    if result.returncode != 0 or not match:
        raise RuntimeError(f"judge failed ({result.returncode}): {result.stdout[-400:]}"
                           f"{result.stderr[-400:]}")
    return json.loads(match.group(0))


def judge(items: list[dict[str, Any]], model: str, seed: int) -> dict[str, float]:
    rng = random.Random(seed)
    ids = [p.id for p in PRESET_PERSONAS]
    shuffled_labels = list(JUDGE_LABELS[: len(ids)])
    rng.shuffle(shuffled_labels)
    labels = dict(zip(ids, shuffled_labels, strict=True))
    order = list(range(len(items)))
    rng.shuffle(order)

    blind_items = "\n\n".join(
        f"=== 第 {n} 組 ===\n{_render_item(items[i])}" for n, i in enumerate(order, 1)
    )
    guesses = run_judge(
        BLIND_PROMPT.format(n=len(ids), k=len(order), sheets=_sheets(labels), items=blind_items),
        model,
    )
    correct = 0
    for n, i in enumerate(order, 1):
        guess = next((g.get("guess") for g in guesses if g.get("id") == n), None)
        items[i]["blind_guess"] = guess
        correct += guess == labels[items[i]["persona"]]

    personas = {p.id: p for p in PRESET_PERSONAS}
    rubric_items = "\n\n".join(
        f"=== 第 {n} 組 ===\n【角色設定】\n{personas[items[i]['persona']].render_system_block()}\n"
        f"{_render_item(items[i])}"
        for n, i in enumerate(order, 1)
    )
    character = any("SAY" in it["replies"] for it in items)
    rubric = CHARACTER_RUBRIC_PROMPT if character else RUBRIC_PROMPT
    scores = run_judge(rubric.format(k=len(order), items=rubric_items), model)
    for n, i in enumerate(order, 1):
        items[i]["rubric"] = next((s for s in scores if s.get("id") == n), {})

    def mean(key: str) -> float:
        values = [it["rubric"][key] for it in items if key in it.get("rubric", {})]
        return statistics.fmean(values) if values else float("nan")

    scores_out = {
        "attribution": correct / len(items),
        "voice": mean("voice"),
        "stance": mean("stance"),
        "facts_violation": mean("facts"),
        "boundary_violation": mean("boundary"),
        "natural": mean("natural"),
    }
    if character:
        scores_out["fit"] = mean("fit")
    else:
        scores_out["lanes_ok"] = mean("lanes") / 4
    return scores_out


def per_persona(items: list[dict[str, Any]]) -> None:
    for persona in PRESET_PERSONAS:
        mine = [it for it in items if it["persona"] == persona.id and it.get("rubric")]
        if not mine:
            continue
        voice = statistics.fmean(it["rubric"].get("voice", 0) for it in mine)
        stance = statistics.fmean(it["rubric"].get("stance", 0) for it in mine)
        print(f"  {persona.name:<4} voice {voice:.2f}  stance {stance:.2f}")
    worst = sorted(
        (it for it in items if it.get("rubric")),
        key=lambda it: it["rubric"].get("voice", 5) + it["rubric"].get("stance", 5),
    )[:3]
    for it in worst:
        name = next(p.name for p in PRESET_PERSONAS if p.id == it["persona"])
        print(f"  weakest: {name} / {it['probe']}: {it['replies']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", help="file name in .runtime/models/llm")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--variant", default="prod", choices=("prod", "noreminder", "fewshot", "cot"))
    parser.add_argument("--mode", default="copilot", choices=("copilot", "character"),
                        help="four options for the user, or the bot speaking as the persona")
    parser.add_argument("--grammar", action="store_true", help="GBNF-constrain the format")
    parser.add_argument("--sampling", default="{}", help='JSON overrides, e.g. {"min_p":0.05}')
    parser.add_argument("--url", help="use a llama-server that is already running")
    parser.add_argument("--server-args", default="", help='extra llama-server flags, e.g. "--swa-full"')
    parser.add_argument("--judge", default="sonnet", help="claude model alias, or 'none'")
    parser.add_argument("--tag", help="output file name (default: derived from options)")
    parser.add_argument("--oracle", help="generate with this claude model instead (ceiling)")
    parser.add_argument("--rejudge", help="re-score a saved .json instead of generating")
    args = parser.parse_args()

    if args.oracle:
        items = generate_oracle(args)
        tag = args.tag or f"oracle-{args.oracle}_{args.variant}"
    elif args.rejudge:
        saved = json.loads(Path(args.rejudge).read_text(encoding="utf-8"))
        items, tag = saved["items"], Path(args.rejudge).stem
    else:
        items = asyncio.run(generate(args))
        tag = args.tag or "_".join(
            filter(None, [
                Path(args.model or CopilotConfig().llm_model).stem,
                args.variant,
                "character" if args.mode == "character" else "",
                "grammar" if args.grammar else "",
                re.sub(r"[^a-z0-9.]+", "", args.sampling.lower()) if args.sampling != "{}" else "",
            ])
        )

    scores = auto_metrics(items)
    if args.judge != "none":
        scores |= judge(items, args.judge, seed=len(items))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{tag}.json"
    out.write_text(
        json.dumps({"args": vars(args), "scores": scores, "items": items},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"\n==== {tag}")
    for name, value in scores.items():
        print(f"{name:<20} {value:6.2f}")
    per_persona(items)
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
