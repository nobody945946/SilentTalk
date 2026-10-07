"""The two policies turn_eval.py plays the test set with, line by line with
teacher forcing: "old" (CopilotRuntime._handle_turn/_speak at --old-rev,
with its keyword gate, rules and simulated clock) and "new"
(LocalReplyModel.character_turn from the working tree)."""

from __future__ import annotations

import argparse
import time
from collections import defaultdict
from typing import Any

import turn_eval_model
import turn_eval_set
from turn_eval_model import LeaseStandIn, copilot_config, load_old_modules, make_model
from turn_eval_set import (
    PROJECT_DIR,
    Conversation,
    TestSet,
    agent_persona,
    resolve_persona,
    speaker_ids,
)

# Mirrors silenttalk/copilot/runtime.py at OLD_REV.
_MIN_TRIGGER_CHARS = 2
OWNER_ID = 0
# Filled by --agenda: each conversation's generated concerns, for the result file.
AGENDAS: dict[str, list[str]] = {}
# Filled by --chain: the character's life after each conversation (its prompt block).
STATES: dict[str, str] = {}


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def _forget_generated(model: Any, line: str) -> None:
    """Teacher forcing: the generated line was never said, so it must not count
    as a recently used catchphrase; the scripted line is added instead."""
    recent = recent_lines(model)
    if line and recent and recent[-1] == line:
        recent.pop()


def _remember_said(model: Any, text: str) -> None:
    recent = recent_lines(model)
    if recent is not None:
        recent.append(text)


def recent_lines(model):
    prompts = getattr(model, "prompts", None)
    return prompts.recent_lines if prompts is not None else getattr(model, "_recent_character_lines", None)


async def run_old(args: argparse.Namespace, test_set: TestSet) -> list[dict[str, Any]]:
    old = load_old_modules(args.old_rev)
    config = copilot_config()
    model = make_model(old.llm, args.model_path, config)
    await model.start()
    records: list[dict[str, Any]] = []
    try:
        for conv in test_set.conversations:
            persona = resolve_persona(old.persona, test_set, conv.persona_id)
            model.set_persona(persona)
            recent = recent_lines(model)
            if recent is not None:
                recent.clear()
            store = old.context.ConversationStore(
                recent_turns=int(config["recent_turns"]),
                max_turns=int(config["max_session_turns"]),
                char_budget=int(config["context_char_budget"]),
                older_self_turns=4,
            )
            compact_keep = max(
                int(config["recent_turns"]), int(config["compact_keep_turns"])
            )
            compact_trigger = compact_keep + max(4, int(config["compact_batch_turns"]))
            policy = old.character.CharacterPolicy(
                mode=conv.engagement,
                follow_up_seconds=float(config["character_follow_up_seconds"]),
                cooldown_seconds=float(config["character_cooldown_seconds"]),
                turn_gap=int(config["character_turn_gap"]),
            )
            # set_character_mode(True) starts from a fresh state.
            state = old.character.CharacterState(turns_since_spoke=0)
            ids = speaker_ids(conv)
            now = 0.0
            for index, line in enumerate(conv.lines):
                now += args.seconds_per_line
                if line.get("self"):
                    # record_self(): what the bot actually said aloud.
                    store.append(
                        old.types.ConversationTurn(
                            OWNER_ID,
                            persona.name,
                            line["text"],
                            is_self=True,
                            created_at=now,
                        )
                    )
                    state.spoke(now)
                    _remember_said(model, line["text"])
                    continue
                via = line.get("via", "voice")
                store.append(
                    old.types.ConversationTurn(
                        ids[line["speaker"]],
                        line["speaker"],
                        line["text"],
                        via=via,
                        created_at=now,
                    )
                )
                if (
                    config["compact_context"]
                    and len(store.snapshot()) >= compact_trigger
                ):
                    # Production compacts in the background when idle; here it
                    # runs before the decision and is not counted as latency.
                    await compact(store, model, compact_keep)
                state.heard()
                record = base_record(conv, index, line)
                if len(_compact(line["text"])) < _MIN_TRIGGER_CHARS:
                    records.append(record | {"gate": "short"})
                    continue
                address = old.character.address_of(
                    line["text"], persona, mention=bool(line.get("mention"))
                )
                if not old.character.should_reply(
                    policy,
                    state,
                    line["text"],
                    addressed=address.worth_reading,
                    now=now,
                ):
                    records.append(record | {"gate": "rule"})
                    continue
                if not address.worth_reading:
                    state.follow_ups += 1
                started = time.perf_counter()
                reply = await model.character_reply(
                    context=store.render_for_prompt(),
                    trigger_speaker=line["speaker"],
                    trigger_text=line["text"],
                    addressed=address.called,
                )
                latency = (time.perf_counter() - started) * 1000
                _forget_generated(model, reply)
                records.append(
                    record
                    | {
                        "gate": "model",
                        "addressed": address.called,
                        "spoke": bool(reply),
                        "reply": reply,
                        "latency_ms": round(latency, 1),
                    }
                )
            print(f"  {conv.id}: done", flush=True)
    finally:
        await model.stop()
    return records


async def compact(store: Any, model: Any, keep: int) -> None:
    older = store.pending_compaction(keep)
    if not older:
        return
    transcript = "\n".join(
        f"{'你' if turn.is_self else turn.speaker_name}：{turn.text}" for turn in older
    )
    summary = await model.summarize(transcript, store.summary)
    if summary:
        store.compact(summary, len(older))


async def new_policy_turn(model: Any, turns: list[Any], addressed: bool, engagement: str) -> str:
    """The one call the new architecture makes per heard line. Adjust here if
    the signature of character_turn changes."""
    return await model.character_turn(
        turns=turns, summary="", addressed=addressed, engagement=engagement
    )


async def run_new(args: argparse.Namespace, test_set: TestSet) -> list[dict[str, Any]]:
    from silenttalk import persona as persona_module
    from silenttalk.conversation import ConversationTurn
    from silenttalk.copilot import llm as llm_module

    if not hasattr(llm_module.LocalReplyModel, "character_turn"):
        raise SystemExit(
            "--policy new needs LocalReplyModel.character_turn(turns=..., summary=..., "
            "addressed=..., engagement=...) in silenttalk/copilot/llm.py; it does not exist yet."
        )
    config = copilot_config()
    lora = (
        PROJECT_DIR / ".runtime" / "models" / "llm" / args.lora if args.lora else None
    )
    if lora is not None and not lora.is_file():
        raise SystemExit(f"LoRA adapter not found: {lora}")
    model = make_model(llm_module, args.model_path, config, lora)
    stand_in = LeaseStandIn(llm_module, args.model_path, lora, config)
    await model.start()
    records: list[dict[str, Any]] = []
    # --chain: a persona's conversations are consecutive days; its life
    # (with memory on) carries over from one to the next.
    lives: dict[str, Any] = {}
    chain_pos: dict[str, int] = defaultdict(int)
    try:
        for conv in test_set.conversations:
            persona = resolve_persona(persona_module, test_set, conv.persona_id)
            model.set_persona(persona)
            chain_pos[conv.persona_id] += 1
            recent = recent_lines(model)
            if recent is not None:
                recent.clear()
            if hasattr(model, "set_state"):
                from silenttalk.copilot.character_state import CharacterState

                model.set_state(
                    lives.get(conv.persona_id, CharacterState())
                    if args.chain and turn_eval_model.MEMORY not in (None, "off")
                    else CharacterState()
                )
            agenda: tuple[str, ...] = ()
            if args.agenda:
                agenda = await model.make_agenda()
            ids = speaker_ids(conv)
            if agent_persona() and hasattr(model, "set_owner"):
                # Only the owner's lines (by ID) can become the Agent's work.
                model.set_owner(ids.get(turn_eval_set.OWNER_NAME, -1), turn_eval_set.OWNER_NAME)
            turns: list[Any] = []
            now = time.time()
            for index, line in enumerate(conv.lines):
                now += args.seconds_per_line
                if line.get("self"):
                    turns.append(
                        ConversationTurn(
                            OWNER_ID,
                            persona.name,
                            line["text"],
                            is_self=True,
                            created_at=now,
                        )
                    )
                    _remember_said(model, line["text"])
                    continue
                turns.append(
                    ConversationTurn(
                        ids[line["speaker"]],
                        line["speaker"],
                        line["text"],
                        via=line.get("via", "voice"),
                        created_at=now,
                    )
                )
                started = time.perf_counter()
                task_fields: dict[str, Any] = {}
                task = ""
                if agent_persona() and line["speaker"] == turn_eval_set.OWNER_NAME:
                    # What the app asks first for the owner's lines: is it work?
                    found = await model.task_from_owner(
                        turns=list(turns), engagement=conv.engagement
                    )
                    # Older revisions (--old-rev) return the text alone.
                    task = getattr(found, "text", found) or ""
                    task_fields = {
                        "task_expected": bool(line.get("task")),
                        "task_said": bool(task),
                        "task_text": task,
                        "task_scope": getattr(found, "scope", None),
                    }
                if task:
                    reply = await model.character_turn(
                        turns=list(turns),
                        engagement=conv.engagement,
                        task_hint=("ack", task),
                    )
                else:
                    reply = await new_policy_turn(
                        model, list(turns), bool(line.get("mention")), conv.engagement
                    )
                latency = (time.perf_counter() - started) * 1000
                _forget_generated(model, reply)
                records.append(
                    base_record(conv, index, line)
                    | {
                        "gate": "model",
                        "addressed": bool(line.get("mention")),
                        "spoke": bool(reply),
                        "reply": reply,
                        "latency_ms": round(latency, 1),
                        "chain_pos": chain_pos[conv.persona_id],
                        **task_fields,
                    }
                )
            if args.lull:
                # The channel goes quiet after the last line: does the
                # character open a topic of its own?
                started = time.perf_counter()
                reply = await model.character_turn(
                    turns=list(turns),
                    addressed=False,
                    engagement=conv.engagement,
                    lull=True,
                )
                records.append(
                    {
                        "conv": conv.id,
                        "index": len(conv.lines),
                        "persona": conv.persona_id,
                        "engagement": conv.engagement,
                        "speaker": "",
                        "text": "",
                        "via": "voice",
                        "mention": False,
                        "expect": "lull",
                        "tags": ["lull"],
                        "gate": "lull",
                        "lull": True,
                        "addressed": False,
                        "spoke": bool(reply),
                        "reply": reply,
                        "chain_pos": chain_pos[conv.persona_id],
                        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                )
            if agenda:
                AGENDAS[conv.id] = list(agenda)
            if args.chain and turn_eval_model.MEMORY not in (None, "off"):
                # The chat is over: its life moves on, as when the app closes.
                model.set_state(await model.update_state(turns))
                if len(model.state.active_concerns()) < 2:
                    model.set_state(await model.fill_concerns(model.state))
                lives[conv.persona_id] = model.state
                STATES[conv.id] = model.state.prompt_block(full=turn_eval_model.MEMORY == "full")
            print(f"  {conv.id}: done", flush=True)
    finally:
        await model.stop()
        stand_in.close()
    return records


def base_record(conv: Conversation, index: int, line: dict[str, Any]) -> dict[str, Any]:
    return {
        "conv": conv.id, "index": index, "persona": conv.persona_id,
        "engagement": conv.engagement, "speaker": line["speaker"], "text": line["text"],
        "via": line.get("via", "voice"), "mention": bool(line.get("mention")),
        "expect": line["expect"], "tags": line["tags"],
        "spoke": False, "reply": "", "latency_ms": 0.0,
    }
