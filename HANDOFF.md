# SilentTalk 交接（2026-09-27）

> 給接手的模型或工程師。**一次做一個任務**，每個任務都有驗證指令和完成標準；沒達標不要進下一步。
> 文件沒寫到的判斷，停下來問使用者，不要猜。
> 這份是唯一要照著做的文件，內容自足。上一版封存在 `archive/HANDOFF-2026-09-25.md`，**只存在開發機上、不進 git**，裡面只剩當時的施工過程，必要的結論都已經搬到這裡。

---

## 0. 五分鐘讀懂現況

**產品是什麼：** Windows 桌面程式。Discord Bot 在語音頻道裡有兩種用法：

1. **Copilot 模式**：聽頻道裡其他人講話 → 本機 STT → 本機 LLM 產生四個候選回覆 → 使用者按 WASD 選一個 → Bot 用 TTS 替他說出來。**說話的是使用者本人。**
2. **角色模式**：Bot 自己就是使用者寫的人設，會自己聽、自己決定要不要接話、用自己的聲音講出來或打字。**說話的是一個角色。**

使用者的最終目標是 2，1 是它的基礎，兩者並存。硬體目標是 **RTX 3050 Ti Laptop 4 GB VRAM**（使用者的筆電，開發機是 3090）。

**目前可以動的東西（都已 commit 到 `copilot-story-mode`）：**

| 功能 | 狀態 |
|---|---|
| Copilot 四選項、WASD 劇情頁、逐行串流顯示 | 可用 |
| 人設系統（背景、慾望、底線、口頭禪、個性滑桿、心情） | 可用 |
| 每個人設自己的聲音（14 種中文聲線＋音效） | 可用，**沒在真的喇叭上聽過** |
| 角色模式（自己接話、被叫到才回、不出戲） | 可用 |
| Discord 文字聊天（讀寫語音頻道內建聊天室） | 程式完成，**沒連過真的 Discord** |
| 設定頁（38 項設定分 6 類） | 可用 |
| 自動壓縮舊對話 | 可用 |
| 本機 STT（Paraformer 預設／SenseVoice 可選） | 可用 |

**測試：** `125 passed`。三個檢查指令都乾淨（見 1.3）。

---

## 1. 開工前

### 1.1 環境

需要 Python **3.12**（用到 `tomllib`、`StrEnum`）。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt     # Windows: .venv\Scripts\python.exe
.venv/bin/python -m pytest -q                               # 應該 125 passed
```

### 1.2 開發機上已經備好的東西（Linux，`.runtime/` 已 gitignore）

```bash
source .runtime/tools/env.sh     # llama-server b11179 (Vulkan) 進 PATH
```

- `.runtime/models/llm/` — Gemma 4 E2B（預設）、Qwen3.5-4B、Qwen3-1.7B、Qwen3-4B 等
- `.runtime/models/teacher/` — Qwen3-30B-A3B-Instruct-2507（蒸餾老師，17.7 GB）
- `.runtime/hf/gemma-4-E2B-it-qat/` — 學生模型的 HF 權重（訓練用，9.5 GB）
- `.runtime/train-venv/` — torch cu124 + transformers + peft + trl
- `.runtime/tools/llama.cpp-b11179/` — `convert_lora_to_gguf.py` 等

**在別台機器上要重建：** 跑 `.venv/bin/python scripts/setup_copilot.py`（會下載約 2.9 GB 的 STT 與 LLM 模型）。老師模型和訓練環境只有開發機需要。

### 1.3 每個任務結束都要跑

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk app.py tests scripts
.venv/bin/python -m compileall -q app.py silenttalk scripts/setup_copilot.py
```

改過 UI 的話再加：

```bash
xvfb-run -a .venv/bin/python scripts/dev/ui_preview.py --font "Noto Sans CJK TC"
```

它會截圖到 `.runtime/dev/ui_preview/` 並檢查按鍵流程，最後印 `UI flow OK`。**要真的打開圖看版面**，Linux 上中文顯示成方框是正常的（缺字型），只看排版。

---

## 2. 規則（違反任一條都要先問使用者）

1. **對話內容不能寫進硬碟。** 轉錄文字、PCM、打字內容、prompt 都只在 RAM。不要提高 llama-server 的 verbosity，不要加 `--log-file`。`_LOG` 只能記數字、長度、ID、錯誤類型。
2. **回覆方向只有一個來源：** `silenttalk/copilot/types.py` 的 `REPLY_LANES`。
3. **劇情模式的 WASD 只在視窗有焦點時生效。** 不要註冊成全域熱鍵（使用者在打遊戲）。
4. **不要 `ruff format` 整個 repo**，只格式化自己新增的檔案。
5. **殺程序不要用 `pkill -f <字串>`**（會殺到自己的 shell，exit 144）。用 `pgrep -x` 取 PID 再 `kill`。
6. **改 prompt、STT、模型之前先量基準**，改完再量一次，變差就回退。
7. **不要在 `main` 直接 commit。** 目前分支是 `copilot-story-mode`。commit 前跑 1.3。
8. **Claude 的輸出不能用來訓練模型**（Anthropic 條款）。蒸餾老師必須是開源權重模型；Claude 只能當評審。

---

## 3. 目前已知的基礎問題（使用者 9/27 同意可以回頭重蓋）

這一節是這份交接最重要的部分。**這些不是 bug，是設計層級的問題**，使用者說時間充裕、可以打掉重做。

### P1｜用關鍵字判斷語意（最該重蓋的一個）

**現況：** `silenttalk/copilot/character.py` 用字串／regex 判斷三件事：

| 函式 | 判斷什麼 | 現在用在哪 |
|---|---|---|
| `address_of()` | 這句是不是在叫我 | 角色模式**預設路徑**，決定要不要生成 |
| `is_question()` | 這句是不是問句 | 只有 `engagement = "active"` 用到 |
| `asks_if_ai()` | 有沒有人在問你是不是 AI | 只有 `character_ai_honesty = "admit"` 用到 |

**問題：** 字面相同意思相反的句子分不開。「我剛才跟阿凱講話」和「阿凱你在嗎」都含名字，但一個是在講他、一個是在叫他。加再多條件都會有漏網的。

**已經做過的補救（不是解法）：** `address_of()` 改成看位置——名字開頭＝明確被叫（強制回答），名字在句中＝只是被提到（生成但不強制）。Discord 那邊用 `message.mentions` 是結構化訊號，精確，不算 regex。

**正解已經驗證過了，就差實作。** 用主模型本身當判斷器，只解碼 1 個 token：

```
system: 你在一個 Discord 語音聊天室裡，名字叫「凱哥」，朋友也叫你「阿凱」。
        判斷最後一句是不是在對你說話（叫你、問你、回應你、要你做什麼）。
        只是在提到你、或在跟別人講話，都算不是。只回答 是 或 否。
user:   <最近幾句>\n\n最後一句是在對你說話嗎？
grammar: root ::= "是" | "否"        max_tokens: 1        temperature: 0
```

**實測（Gemma 4 E2B，開發機 3090）：**

| 指標 | 數字 |
|---|---|
| 準確率 | **14/15**（唯一一個「錯」其實是我標籤標錯，前一句就是在對他講話） |
| 每次耗時 | 約 75–110 ms（含 HTTP；純運算約 25 ms） |
| system prompt 快取 | 命中（只 prefill 新增的 ~30 token） |
| **對生成呼叫的影響** | **沒有**。`--parallel 1` 下交錯呼叫，生成仍保有 841 token 快取 |

最後一項是我原本最擔心的風險，實測不存在，所以**不需要多開 slot、不用切 context**。

**要做的事：** 寫一個 `AddressGate`，取代 `address_of()` 在預設路徑的角色。保留 Discord `message.mentions` 當快速路徑（結構化訊號不需要問模型）。gate 失敗或逾時就退回現在的位置規則。實驗腳本在 `/tmp/.../scratchpad/gate.py` 和 `slots.py`（session 結束會消失，照上面的參數重寫即可）。

### P2｜訓練資料沒有「不該回話」的範例

**現況：** `.runtime/dev/distill/replies.jsonl` 有 4789 筆，其中 1452 筆是角色模式，**每一筆都有回答，沒有任何一筆是 SKIP**。

**後果：** 模型從來沒看過「這句不用理」的範例，所以它不會 SKIP。實測：給它三句「只是提到你」的話，三句都回了。

**正解：** 下一輪產生資料時加入負面範例——挑一些「明顯不是在跟角色說話」的情境，讓老師輸出 SKIP，佔角色資料的 20–30%。這樣 LoRA 才學得會閉嘴。改 `scripts/dev/distill_data.py` 的 `_reply_jobs()` 和 `_reply_round()`。

### P3｜正在訓練的 LoRA 有兩個已知落差

1. **角色模式 prompt 變了**：那 1452 筆資料的 system prompt 帶的是舊規則「被問是不是 AI 要承認」，現在正式版預設是「照角色演，不承認」。**但回覆裡 0 句自承是 AI**（已查證），所以 adapter 不會學到自爆，落差只有 prompt 的一行。
2. **沒有負面範例**（見 P2）。

**要做的事：** 訓練跑完先評估（見 T1），有退步才重做資料。

### P4｜聲音和 Discord 文字聊天沒有實機驗證

- **人設聲音**：14 種聲線、音效、音量補償都只有用 FFmpeg 量測（RMS 差 ≤0.6 dB、峰值 ≤ −7 dBFS），**沒有人真的聽過**。音色合不合角色要人耳判斷。
- **Discord 文字聊天**：開發機連不到真的 Discord，`on_message` / `send_text` 只有單元測試。

**要做的事：** 見 T2、T3，都需要使用者本人操作。

### P5｜語音叫名字會被 STT 聽錯

「凱哥」可能被聽成「開哥」。2 個字的名字用編輯距離補會誤判成「大哥」「二哥」，所以沒做。目前的解法是請使用者把常被聽錯的寫法加進人設的「暱稱」欄（人設頁已有提示文字）。P1 的 gate 做完後可以重新評估——模型對同音字的容忍度比字串比對高。

---

## 4. 任務清單（依序做）

### T1｜LoRA 訓練跑完後的評估與決定（最優先，隨時可能完成）

**現在的狀態：** `scripts/dev/distill_pipeline.sh` 正在跑。訓練約 445/582 步（13:08），預計 **14:15 前後**完成，之後會自動轉 GGUF 並跑評估。
用 `scripts/dev/distill_pipeline.sh --status` 看進度。

**跑完後要做的事：**

1. **先重跑無 LoRA 的角色模式基準**（重要：角色 prompt 改過，`character_norepeat` 那份不能直接比）：
   ```bash
   source .runtime/tools/env.sh
   .venv/bin/python scripts/dev/persona_eval.py --mode character --runs 2 --tag gemma4-E2B_character_v3
   ```
2. **比較這四份**（在 `.runtime/dev/persona_eval/`）：

   | 比較 | 無 LoRA | 有 LoRA |
   |---|---|---|
   | 四選項 | `gemma4-E2B_prod_r2.json` | `gemma4-E2B_lora_r2.json` |
   | 角色模式 | `gemma4-E2B_character_v3.json`（步驟 1 產生） | `gemma4-E2B_lora_character.json` |

3. **判準：** 評審本身有誤差（同一份輸出重評：attribution ±0.07、voice ±0.1、stance ±0.25）。**差距小於這些就不算贏。**
4. **另外跑一次不出戲的檢查**（LoRA 資料是用舊規則產生的，見 P3）：
   ```bash
   .venv/bin/python scripts/dev/persona_eval.py --probes assistant --mode character \
       --server-args="--lora $PWD/.runtime/dev/lora/gemma4-e2b-persona-lora.gguf" --judge none --tag lora_assistant
   ```
   看它被問「你是不是 AI」時有沒有自爆。
5. **決定：**
   - **明顯變好** → 上線：adapter 量化後放進 repo（f16 是 48 MB，q8_0 約 25 MB），`llm.py` 啟動參數加 `--lora`，`setup_copilot.py` 加下載項。
   - **差不多或變差** → 不上線，把結論寫進這份文件，資源轉去 P1/P2。
6. **流程全部跑完後**，把 cron 看門狗那行從 `crontab -e` 刪掉（`*/5 * * * * .../distill_pipeline.sh`）。

### T2｜Discord 文字聊天實機驗收（需要使用者）

程式已完成但沒連過真的 Discord。請使用者：

1. Discord Developer Portal → 你的 Bot → Bot → Privileged Gateway Intents → 打開 **Message Content Intent**。
2. 確認 Bot 在該語音頻道有「讀取訊息」「發送訊息」權限。
3. 設定頁 → Discord → 打開「讀寫文字聊天」（或 `config.toml` 的 `[discord] text_chat = true`），重開 SilentTalk。
4. 進語音頻道，在該頻道的聊天室 **@Bot** 說一句話。

**預期：** Bot 用打字回覆。`silenttalk.log` 會有 `text_message_received ... addressed=True`。

| 症狀 | 原因 | 怎麼辦 |
|---|---|---|
| Bot 連不上、log 有 PrivilegedIntentsRequired | Intent 沒開 | 回到步驟 1 |
| 看得到訊息但不回 | 沒 @ 到，或不在「被叫到才回」的條件內 | 確認有 @ Bot |
| log 有 `text_send_failed reason=forbidden` | 沒有發言權限 | 檢查頻道權限 |

### T3｜人設聲音試聽（需要使用者）

設定好人設 → 人設頁最下面「聲音」區塊 → 按「▶ 試聽」（只在本機播放，不會進 Discord）。
請使用者確認音色合不合角色，不合就換聲線或調音高／音效。**這是主觀判斷，只有人耳能決定。**

### T4｜做 P1 的 gate（可以開始）

見第 3 節 P1，參數和實測數字都在那裡。完成標準：

- 在一組人工標註的句子上準確率 ≥ 90%（現在有 15 句的測試集，建議擴充到 40 句以上）
- 生成呼叫的 `cache_n` 沒有下降
- 角色模式端到端延遲增加 < 150 ms
- `pytest -q` 全過，且 gate 失敗時會退回舊規則（要有測試）

### T5｜做 P2 的負面訓練資料（等 T1 決定後再做）

見第 3 節 P2。如果 T1 決定 LoRA 不上線，這項就跟著取消或改成「先解決 P1 再說」。

### T6｜3050 Ti 實機驗收（需要使用者，從舊文件接過來）

所有速度數字都是 3090 上量的，3050 Ti 是推估。請使用者在筆電上：

```powershell
.venv\Scripts\python.exe app.py --copilot-smoke
```

看 `llama.cpp 看到的 GPU：` 有沒有列出 3050 Ti，以及 `延遲中位數`。目標 < 3 s。
實際使用時看 `silenttalk.log` 的 `copilot_suggestion_ready latency_ms=`（目標中位數 < 1500）。

### T7｜修補 discord-ext-voice-recv fork（需要使用者的 GitHub，先問）

`requirements.txt` 釘的是 `rdphillips7/discord-ext-voice-recv@ddd2860`（上游 PR #54，支援 DAVE 解密）。它有兩個 bug，目前在 `discord_voice.py` 繞過了；從源頭修比較乾淨。

要改 fork 的 `discord/ext/voice_recv/opus.py` 三處：

1. 約第 63 行 `self.vc._connection.dave_session.set_passthrough_mode(True, 10)` 前面加 `if self.vc._connection.dave_session is not None:`。
2. 約第 151 行 `dave_session.decrypt(member.id, ...)` 改用 `self._cached_id`（`member` 可能是 None）。
3. `dave_protocol_version > 0` 但 `dave_session.ready` 為 False 時，直接丟掉這個封包（回傳 `source=None`），不要把密文送去 opus 解碼。

步驟：請使用者 fork → 你寫 patch → 使用者 push → `requirements.txt` 換成新 commit 的 zip → `pip install -r requirements.txt` → `pytest -q` → 請使用者在 Discord 實測。

**完成標準：** log 有 `voice_receive_started dave_version=1`、有 `copilot_turn_final`、沒有 `voice_transport_recovery` 反覆出現。
**`discord_voice.py` 現有的防護不要刪**，留著當第二層保險。

### T8｜（可選，先問使用者）不切視窗也能選選項

劇情模式現在要先按 F8 讓視窗取得焦點才能按 WASD。若使用者想在遊戲中直接選：`silenttalk/hotkeys.py` 目前只支援 F1–F12，可以加「修飾鍵＋數字」（例如 Ctrl+Alt+1～4）對應四個方向。**絕不能註冊單獨的 W/A/S/D 全域熱鍵**（規則 3：使用者在打遊戲，會直接壞掉移動鍵）。動手前先問使用者要哪組按鍵。

---

## 5. 量過的數字（別重複做這些實驗）

### 模型選擇（`scripts/dev/persona_eval.py`，3 人設 × 14 情境，Claude Sonnet 當評審）

| 模型 | voice | stance | natural | lanes_ok | 捏造／踩底線 | VRAM | 3090 延遲 |
|---|---|---|---|---|---|---|---|
| Sonnet（天花板，只供對照） | 4.21 | 4.31 | 4.29 | 0.90 | 0 / 0 | — | — |
| **Gemma 4 E2B（目前預設）** | 3.54 | 3.25 | 3.01 | 0.76 | 0.04 / **0.05** | **1.4 GB**＋2 GB RAM | 0.58 s |
| Qwen3.5-4B Q4_K_M | 3.60 | 3.29 | 3.06 | 0.80 | 0.05 / 0.07 | 2.9 GB | 0.81 s |
| Qwen3-4B-Instruct-2507 | 3.68 | 3.07 | 2.68 | 0.81 | 0.06 / 0.15 | 2.8 GB | 0.65 s |
| Qwen3-30B-A3B（蒸餾老師） | 3.81 | 3.52 | 3.10 | 0.83 | 0.02 / 0.10 | 12 GB | 4 s |
| Qwen3-1.7B Q4_K_M（舊預設） | 3.10 | 2.52 | 2.21 | 0.54 | 0.10 / 0.10 | 1.4 GB | 0.34 s |
| Qwen3.5-2B / MiniCPM5-2B | 2.76 / 3.14 | 2.45 / 2.64 | 2.14 / 2.02 | 0.49 / 0.37 | — | — | — |

**為什麼選 Gemma 4 E2B：** 品質和 4B 級打平，但 VRAM 只要 1.4 GB（它的 per-layer embedding 留在 RAM），速度快 30%。純 CPU 每次 5–6 秒（第一個選項約 2 秒），可以當備援。

### 角色模式（`--mode character --runs 2`，Gemma 4 E2B）

voice 3.68、stance 3.42、natural 3.26、fit（時機）3.36、捏造 2%、踩底線 5%、盲測辨識 99%、3090 上 0.34 s／句。

### 其他實測

- **口頭禪重複**：一句接一句說時，小模型 86% 的句子都塞口頭禪。讓模型記住最近 4 句、prompt 裡點名「剛用過的不要再用」→ 降到 40%，其他分數沒退。
- **不出戲**：預設政策下，3 人設 × 6 句身分質問 = **0/18 自爆**，有沒有關鍵字提示都一樣（所以提示已移出預設路徑）。
- **老師的判斷力**：1452 筆角色資料裡，57 筆對話提到 AI／機器人，但**只有 3 筆是真的在質問身分**，其餘是在虧隊友或講遊戲。老師 30B 全部正確地留在角色裡——它讀得懂玩笑和認真的差別，小模型讀不懂。
- **名字出現頻率**：3887 句真實風格聊天裡，人設名字只出現 1 次（0.03%），而且那一次是第三人稱誤判。
- **STT**：Paraformer 7.2% CER（預設）、SenseVoice 6.9%（可選，有標點、CPU 較省，多下載 240 MB）。差距在誤差範圍內。
- **音效音量補償**：每種音效與原聲的 RMS 差 ≤ 0.6 dB，峰值 ≤ −7 dBFS。

### 已驗證的下載資訊

| 檔名 | 來源 | 位元組 | sha256 |
|---|---|---|---|
| `gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf`（預設） | `unsloth/gemma-4-E2B-it-qat-GGUF` | 2,620,370,976 | `e531007218dfab990486a5de7676a6932d6ea8dea233d1f698d7c21cf8a16889` |
| `Qwen3.5-4B-Q4_K_M.gguf` | `unsloth/Qwen3.5-4B-GGUF` | 2,740,937,888 | `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` |
| `Qwen3-1.7B-Q4_K_M.gguf` | `unsloth/Qwen3-1.7B-GGUF` | 1,107,409,472 | `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897` |
| `Qwen3-30B-A3B-Instruct-2507-UD-Q4_K_XL.gguf`（老師） | `unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF` | 17,690,497,440 | `535f831bf3034a7fcfdcc8f0277a57cbad3a36c650c6068bf1d0894f25fb4383` |

---

## 6. 工具速查

| 指令 | 用途 | 需要 |
|---|---|---|
| `python app.py --copilot-smoke` | 本機 STT＋LLM 一鍵驗收，exit 0＝通過 | `.env`、模型、llama-server、ffmpeg、網路（EdgeTTS） |
| `scripts/dev/persona_eval.py` | 人格穩定度評分（盲測辨識＋評分表） | llama-server、`claude` CLI 當評審 |
| ↳ `--mode character` | 角色模式（一句話）而不是四選項 | |
| ↳ `--probes assistant` | 被當成助理使喚時的表現 | |
| ↳ `--url http://...` | 評分一個已經在跑的 server（例如老師模型） | |
| ↳ `--judge none` | 只生成不評分（離線可用，之後 `--rejudge` 補評） | |
| `scripts/dev/llm_eval.py` | 四選項的格式／方向／速度 | llama-server |
| `scripts/dev/stt_eval.py [--engine sensevoice]` | STT 準確度（16 句） | ASR 模型、ffmpeg |
| `scripts/dev/ui_preview.py` | UI 截圖＋按鍵流程檢查 | pillow；Linux 要 `xvfb-run -a` 加 `--font` |
| `scripts/dev/distill_pipeline.sh [--status]` | 蒸餾全流程（可中斷續跑） | 開發機 |
| `scripts/dev/distill_data.py` | 產生人設／情境／回覆訓練資料 | 老師模型在跑 |
| `scripts/dev/train_lora.py [--check]` | LoRA 訓練；`--check` 是 15 秒的 CPU 預檢 | `.runtime/train-venv` |

**蒸餾流程的無人值守規則（已實測）：** 老師當掉 8.8 秒內重啟、卡死 44 秒內重啟；斷網時生成／訓練／轉檔照跑，只有評審等網路；VRAM 不足時等下一輪。同一階段連續真的失敗 3 次 → `state/<stage>.blocked`，不再自動重試，要看 `logs/<stage>.log` 修好後刪掉 `.blocked`。

---

## 7. 出問題時先看這裡

| 症狀 | 最可能原因 | 檢查 |
|---|---|---|
| `找不到 llama-server` | PATH 沒設 | `source .runtime/tools/env.sh` |
| `llama-server 啟動失敗，exit code=…` | 錯誤在 `｜` 後面 | 常見：port 被占用、VRAM 不足（把 `llm_gpu_layers` 調低或設 0） |
| 劇情模式按 WASD 沒反應 | 中文輸入法攔截 | 程式會自動關 IME；仍不行就切英數或用方向鍵 |
| 選項一直「思考中」 | LLM 請求逾時 | log 找 `copilot_suggestion_failed` |
| Copilot 沒反應但 TTS 正常 | Copilot 啟動失敗後自動降級 | log 找 `copilot_startup_failed` |
| 角色模式都不講話 | 預設是「被叫到才回」 | 叫它的名字，或設定頁改成「會主動加入」 |
| 角色模式太吵 | 設定在「會主動加入」 | 設定頁 → 聊天 → 開口時機 |
| 設定改了沒效果 | 該項需要重開 | 設定頁上有「需重開」標示 |
| 測試在 import 就錯 | 用了 Python 3.10 | `python --version` 必須 3.12 |
| 背景任務莫名不動 | 鎖被孤兒程序持有 | `ls -l /proc/<pid>/fd | grep .lock`，見 P1 註記的踩雷史 |
