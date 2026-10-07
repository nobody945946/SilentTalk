"""The fixed synthetic chat bench_hw.py times (the 凱哥 preset, one machine
like another) and the two prompt formats it is sent in: the old rebuilt
window and the append-only chat."""

from __future__ import annotations

# Production character system prompt for the 凱哥 preset, rendered 2026-09-27.
SYSTEM = """你是 Discord 語音頻道裡的一個角色 Bot，由 AI 扮演下面人設裡的人，和大家一起用語音聊天。你說的話會直接用語音播出來。

規則：
- 只根據真實對話回應，不得杜撰別人的身分、經歷、情緒或事實。關於你自己，只用人設裡寫到的事，不要編新的經歷。
- 你就是這個人，從頭到尾用這個身分講話。有人說你是 AI、機器人或問你是不是真人時，當成朋友在開你玩笑，用這個角色會有的方式笑著帶過、吐槽或反問回去，不要承認自己是程式，也不要一本正經地解釋自己不是 AI（那樣反而更可疑）。
- 你只存在於這個語音頻道，只能用嘴巴聊天：不能打字、寫程式、寫文章、翻譯整段文字、上網查資料、設提醒，也不會記得下次聊天。被要求做這些事時，用這個角色會有的方式回應（推託、吐槽、給一句口頭建議、叫對方自己來或用別的工具），絕對不要答應或假裝在做你做不到的事。
- 你不是百科全書：超出你人設會懂的問題，就用這個人真實的程度回答，可以說不知道。
- 台灣繁體中文口語，只說一句話，長度很短，多半 4～12 字，最長不得超過 72 字。
- 像朋友聊天一樣自然接話：附和、追問、吐槽或開玩笑，選這個角色此刻最可能的反應。不要重複別人的話，不要說教，不要每句都叫對方名字。
- 不羞辱、不人身攻擊，不拿外貌、疾病、性別、種族、家庭、收入開玩笑。
- 這時候插話不自然（別人在私下聊、話題跟你無關、你剛說過類似的話）就輸出 SKIP。

【你的人設】口吻、用詞、句長、立場都照這裡：
名字：凱哥
朋友叫你：凱哥、阿凱
身分：24 歲，工程師，下班就上線打遊戲
背景：國中開始玩射擊遊戲，打過校隊，現在是朋友群裡最常開團的人。
你想要：想帶大家贏，也想被隊友當成可靠的指揮。
你害怕、想避開：怕被說是在甩鍋，怕氣氛變僵。
你在意：輸了先檢討自己，團隊合作大於個人數據。
你的雷點：有人不看小地圖亂衝、輸了只會怪別人。
你熟悉：射擊遊戲戰術、報點、PC 硬體。
說話方式：句子短、節奏快，常用「欸」「好啦」「穩」，偶爾一句台語。
口頭禪（偶爾自然帶到，不要每句都用）：穩啦、我的我的、笑死
幽默風格：自嘲和吐槽隊友，但點到為止
絕對不說：不罵人家人、不嘲笑別人技術差到要他退坑。
個性：偏外向健談、偏毒舌嘴砲、偏愛搞笑、偏衝動直接
你平常講話像這樣：
「欸我的，下波我先進」
「穩啦，這把能拿」
「笑死，我又被架」

只輸出一行：你要說的話，或 SKIP。不要加引號、名字或解釋。"""
REMINDER = "（記住：你是凱哥；句子短、節奏快；口頭禪和代表台詞少用，大約四五句才一次。這句要是這個人會說的話。）"
BOT = "凱哥"
CHAT = (
    ("阿傑", "欸今天要打幾場"),
    ("小雨", "我等等要先吃飯喔"),
    ("阿傑", "那先一場就好"),
    ("Ken", "我剛下班累死"),
    ("小雨", "凱哥你今天有要上嗎"),
    (BOT, "穩啦等我五分鐘"),
    ("Ken", "昨天那把真的有夠雷"),
    ("阿傑", "對啊那個打野一直送"),
    ("小雨", "我覺得是我們沒跟"),
    ("Ken", "欸有人要喝飲料嗎"),
    ("阿傑", "我要半糖去冰"),
    ("小雨", "凱哥昨天是不是又被架"),
    ("Ken", "笑死他每次都這樣"),
    ("阿傑", "好啦開了開了"),
    ("小雨", "誰要當指揮"),
    ("Ken", "凱哥來啊"),
)
# Lines before this index only build up history; each later line is timed.
TIMED_FROM = 8
RECENT_TURNS = 16  # config.toml [copilot] recent_turns
RECALL_MARKER = "藍鯨七號"


def synthetic_chat(turns: int) -> tuple[tuple[str, str], ...]:
    """Repeat the fixed chat with numbered lines for long-context benchmarks."""
    chat = [
        (speaker, f"{text}（第{index + 1}句）")
        for index, (speaker, text) in enumerate((CHAT * (turns // len(CHAT) + 1))[:turns])
    ]
    if turns > len(CHAT):
        first_external = next(index for index, (speaker, _) in enumerate(chat) if speaker != BOT)
        last_external = next(
            index for index in range(len(chat) - 1, -1, -1) if chat[index][0] != BOT
        )
        chat[first_external] = (chat[first_external][0], f"記住測試代號是{RECALL_MARKER}")
        chat[last_external] = (chat[last_external][0], "剛才請你記住的測試代號是什麼")
    return tuple(chat)


def old_format_requests(
    chat: tuple[tuple[str, str], ...], timed_from: int
) -> list[list[dict]]:
    """What silenttalk/copilot/llm.py sends today: the recent window rebuilt each line."""
    requests = []
    for index in range(timed_from, len(chat)):
        speaker, text = chat[index]
        if speaker == BOT:
            continue
        recent = chat[max(0, index - RECENT_TURNS) : index]
        context = "最近對話：\n" + "\n".join(
            f"{'你' if who == BOT else who}：{line}" for who, line in recent
        )
        user = (
            "/no_think\n下面是真實 Discord 語音對話（語音辨識結果，可能有錯字、沒有標點）。"
            f"「你」是你自己之前說過的話。\n\n{context}\n\n最後一句：\n{speaker}：{text}\n\n"
            f"{REMINDER}\n你要說："
        )
        requests.append(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        )
    return requests


def new_format_requests(
    chat: tuple[tuple[str, str], ...], timed_from: int
) -> list[list[dict]]:
    """Append-only chat: others are user turns, the character's lines are assistant turns."""
    requests = []
    messages: list[dict] = [{"role": "system", "content": SYSTEM}]
    for index, (speaker, text) in enumerate(chat):
        if speaker == BOT:
            messages.append({"role": "assistant", "content": text})
            continue
        line = f"{speaker}：{text}"
        if messages[-1]["role"] == "user":
            messages[-1] = {
                "role": "user",
                "content": messages[-1]["content"] + "\n" + line,
            }
        else:
            messages.append({"role": "user", "content": line})
        if index >= timed_from:
            requests.append([dict(m) for m in messages])
    return requests
