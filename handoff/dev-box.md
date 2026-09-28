# 開發機工作檔（Linux、RTX 3090）

更新：2026-09-28 08:30｜分支：`copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。舊版在 `archive/`（只在這台機器、不進 git），不必讀。

---

## 1. 現況

**產品：** Windows 桌面程式，Discord Bot 兩種用法，同一個本機模型、同一段對話格式。
- **選項模式**：聽別人講話 → 本機模型想四句「這個角色自己會說的話」→ 使用者按 WASD 選 → TTS 替他說。
- **角色模式**：Bot 自己就是使用者寫的人設，自己判斷要不要開口、自己講。

**使用者要的：**
- 「頂級電子人，講話無違和」；免費；使用者不標資料、不評樣本。
- 人設是使用者自己寫、隨時切換，大多是和他的**關係**（老婆、小孩、兄弟），使用者本人就在語音頻道裡。所以 LoRA 是**一個通用 adapter 服務所有人設**。
- 即時比精準重要。**硬體標準是 RTX 3050 Ti 4 GB**，只用免費、本機的東西。學生模型可以換，只要 3050 Ti 跟得上。

| 項目 | 狀態 |
|---|---|
| 選項不被新的一組蓋掉（6 秒保留、R 換過去） | ✅ 開發機 ui_preview 驗過；**筆電還沒試** |
| 選項改成取樣「角色自己會說的話」 | ✅ 盲評贏舊版，§5.1；**筆電還沒試** |
| 角色 LoRA v1，只用在「是不是在叫你」 | ✅ 已隨 repo 出貨（`models/`），§5.2；**筆電還沒試** |
| 模型判斷何時開口、對話只往後接、關係型人設、TTS 串流、UI 重做 | ✅（前幾輪） |
| 真 Discord 實測 | ⬜ 等筆電這一輪（`handoff/laptop.md`）的回報 |
| Gemma 4 E4B 當學生 | 🔄 開發機：選項大贏、角色台詞輸；3050 Ti 速度等筆電量，§4 |
| 老師比較第二輪 | 🔄 等 GPU（別的專案佔 17 GB），§4 |

**測試：** `160 passed`。

## 2. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、架構之前先量，改完再量，變差就退回。量不出贏就不出貨。
2. **Claude 的輸出不能用來訓練，也不能用來挑選訓練資料**（Anthropic 條款）。Claude 只能當評審。老師模型只能用授權允許的開源權重模型。
3. 測試集 `scripts/dev/turn_eval_data.jsonl` 是 Claude 寫的，**只能評估**；檔頭列出訓練資料不能用的名字，`character_data.py` 會自動排除。
4. GPU 和別的專案共用（ComfyUI、whisper-api、musichub 的 `stage_music.py` 會佔到 17 GB），**不要動它們的程序**。要大量 VRAM 的工作先等空間（`nvidia-smi --query-gpu=memory.free`）。
5. 不要 `ruff format` 整個 repo，只格式化自己新增的檔案。
6. 選項的四個位置只有一個來源：`silenttalk/copilot/types.py` 的 `REPLY_LANES`。選項模式的 WASD 絕不註冊成全域熱鍵。
7. 正在跑的 bash 腳本不要原地改（bash 邊跑邊讀檔）：寫成新檔再 `os.replace`，然後重啟那個流程。
8. 這台機器沒有 git 身分：commit 用 `git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
9. 同時跑兩個評估時各給一個 port（`turn_eval.py --port`、`options_eval.py --port`），否則會連到對方的模型。

**每次改完要跑：**

```bash
.venv/bin/python -m pytest -q        # 看 exit code
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk app.py tests scripts
xvfb-run -a -s "-screen 0 2400x1600x24" .runtime/tools/ui-preview-env/bin/python \
    scripts/dev/ui_preview.py --font "Noto Sans CJK TC" [--scale 1.5]   # 改過 UI 才需要，要打開截圖看
```

UI 截圖一定要用 `.runtime/tools/ui-preview-env/bin/python`（conda-forge 的 Tk，有 Xft）；專案 venv 的 Tk 中文粗體會變方框。

## 3. 怎麼運作（主程式 `silenttalk/copilot/llm.py` 的 `LocalReplyModel`）

1. **對話格式：只往後接。** 別人的話是 user 訊息（`名字：內容`），角色／使用者自己的話是 assistant 訊息，人設和人際關係在 system prompt。新的一句只接在最後，前面整段快取沿用；這次請求專用的提示只附在最後一則訊息。
2. **角色模式 `character_turn`：** 在同一段快取上問 是／否（grammar 限制 1 個 token）。先問「是不是在對你說話」；「主動」模式下角色安靜滿 4 句才再問「現在插一句自然嗎」。是的話再寫一句。**不要**改回「一次呼叫、講或 SKIP」：零訓練的模型 18 句全回。
3. **選項模式 `suggest`：** 同一段對話尾端問「換你說話了：說一句你現在會說的話」，溫度 1.0 取樣最多 7 次，留最多四句彼此不像、也不重複對方的句子。每多一次只多生成那一句（快取沿用）。
4. **LoRA：** `copilot.character_lora`＋`copilot.character_lora_uses`（`called`／`active`／`line`／`options`）。預設只有 `called`。有 LoRA 時 llama-server 開兩個 slot：套 LoRA 的請求走 slot 0、不套的走 slot 1（`_lora_field`）。**llama-server 在 LoRA 比例改變時會丟掉該 slot 的快取**（實測整段 1336 token 重讀），共用一個 slot 的話每次開口都重讀整段對話。兩個 slot 的 VRAM：1395 → 1486 MiB。
5. **TTS：** EdgeTTS 的 MP3 一邊收一邊餵 FFmpeg（`silenttalk/tts/stream.py`），不寫硬碟。

## 4. 接下來

**等筆電回報（`laptop-report` 分支）：** 選項和角色模式的使用者感想、`--copilot-smoke` 秒數、E4B 在 3050 Ti 的 VRAM 和速度、Windows 截圖。

**E4B 要不要換：** 開發機上（§5.3）E4B 寫選項大贏 E2B，但角色台詞的自然度、口吻反而輸。現在跑的 `options_eval.py --tag sampled-e4b`（CPU）看「取樣選項」格式下 E4B 還贏不贏。如果贏、而且筆電量到 E4B 跑得動，可以考慮：選項模式用 E4B、角色模式用 E2B＋LoRA，切模式時重開 llama-server（4 GB 放不下兩個模型）。

**老師比較第二輪：** 2026-09-28 早上有一個背景程序在等 GPU 空出來（E4B 學生要 6 GB、老師要 21 GB）再跑。它不在了的話，自己在有空間時跑（可續跑）：
```bash
.venv/bin/python scripts/dev/teacher_bakeoff.py generate \
    --only student-gemma4-e4b,qwen3.6-35b-a3b,qwen3.6-27b,gemma4-31b,gemma4-26b-taide
```
每個老師都有「寫四句挑一句」（`+pick`）和「先想再寫」（`+think`）兩種。跑完用：
```bash
.venv/bin/python scripts/dev/teacher_bakeoff.py judge --tag pick --variants student-gemma4-e2b,qwen3-30b-a3b+pick,<各老師>+pick
.venv/bin/python scripts/dev/teacher_bakeoff.py judge --tag think --variants student-gemma4-e2b,qwen3-30b-a3b+pick,<各老師>+think
```
（一次最多排 6 個版本，評審才穩。）`timing.json` 有每個版本每點幾秒：老師要重產幾千句，太慢的不實際。

**LoRA v2 的方向（照 §5.2 的教訓）：** v1 的台詞會硬塞人設背景（「我已經存了三萬」這種答非所問），因為老師寫劇本時每句都在用人設。下一版資料要：台詞先接住對方那句、人設只在自然時出現；換掉老師要照上面的比較結果；判斷題的資料可以保留（v1 的判斷是贏的）。

## 5. 量過的數字

### 5.1 選項（`options_eval.py`，21 場對話每隔一句、269 點 × 正反順序各評一次，Claude 盲評，1–5 分）

| 比較 | 誰比較好 | 自己的想法 | 接得上 | 口吻 | 自然 | 可用句數（/4） |
|---|---|---|---|---|---|---|
| 舊四方向 vs **先寫心裡想再寫四句** | 55% vs 40% | 2.61 / 2.55 | 2.83 / 2.50 | 3.09 / 2.89 | 3.00 / 2.86 | 2.00 / 1.75 |
| 舊四方向 vs **取樣角色會說的話**（出貨） | 39% vs **56%** | 2.42 / 2.31 | 2.51 / **3.04** | 2.69 / **2.95** | 2.80 / **3.17** | 1.37 / **1.75** |
| 心裡想格式：E2B vs **E4B** | 26% vs **70%** | 2.38 / 2.87 | 2.45 / 3.11 | 2.70 / 3.22 | 2.78 / 3.19 | 1.30 / 2.00 |
| 心裡想格式：無 LoRA vs 套 LoRA | 67% vs 31% | — | — | — | — | LoRA 版一組平均空一格 |

- 把上一輪的「心裡想」帶進下一輪：小模型直接照抄，248 次裡 151 次幾乎一樣（一個角色連續九輪都在講跳傘），已退回。
- 同一次評分裡的分數才能比；不同次的絕對分數會漂。

### 5.2 角色模式（`turn_eval.py`，545 個判斷點，Claude 評台詞）

| | 無 LoRA | LoRA 全開 | **LoRA 只用在「是不是在叫你」（出貨）** | E4B 無 LoRA |
|---|---|---|---|---|
| 被叫才回：該回的有回 | 89.0% | 89.0% | **89.0%** | 93.9% |
| 被叫才回：不該回卻回 | 9.6% | 1.0% | **1.0%** | 9.6% |
| 主動：該回的有回 | 93.8% | 84.4% | 84.4% | 93.8% |
| 主動：插嘴 | 47.3% | 54.8% | **38.7%** | 48.4% |
| 自然／口吻／時機 | 3.54 / 3.70 / 3.82 | 3.60 / 3.85 / 3.76 | 3.44 / 3.68 / 3.81 | 3.08 / 3.23 / 3.64 |
| 對使用者本人：自然／時機 | 3.42 / 3.61 | 2.90 / 3.14 | 3.43 / 3.61 | 3.36 / 4.19 |

- 無 LoRA 基準是 `--cpu` 跑的（當時 GPU 在訓練），判斷和台詞可以比，延遲不能比。
- q8_0 的 LoRA 和 f16 在 545 點裡 543 點判斷相同。

### 5.3 3050 Ti 實機（使用者筆電，`bench_hw.py`，Gemma 4 E2B）

| | GPU | 純 CPU |
|---|---|---|
| 模型 VRAM | 1370 MiB | — |
| 判斷一句（只往後接） | 78–93 ms | 644 ms |
| 生成速度 | 68–79 token/s | 8.8 token/s |

**3090 的數字不能照比例換算成 3050 Ti**：實測 3050 Ti 的生成速度是 3090 的 57%，不是 20%。

### 5.4 老師比較第一輪（114 個「該講」的點 × 2 輪 Claude 盲評）

| 候選 | 平均名次 | 贏學生 | 不及格 |
|---|---|---|---|
| Qwen3-30B-A3B＋挑選（v1 的老師） | 1.90 | 76% | 24 |
| Qwen3-30B-A3B | 2.21 | 71% | 29 |
| 學生 Qwen3.5-4B | 2.89 | 52% | 70 |
| 學生 Gemma 4 E2B | 3.00 | — | 69 |

### 5.5 TTS（開發機，文字備好到第一個 Opus 封包）：串流 267–290 ms（原本先存檔 594–709 ms）。

## 6. 工具

| 指令 | 用途 |
|---|---|
| `scripts/dev/options_eval.py generate --rev R [--model/--old-model/--lora/--cpu/--port] --tag T`、`judge --tag T`、`report --tag T` | 選項 A/B：`--rev` 的程式 vs 工作目錄 |
| `scripts/dev/turn_eval.py --policy new [--lora F --lora-uses called] [--cpu] [--port] [--judge] [--judge-only TAG]` | 角色模式的時機和內容 |
| `scripts/dev/teacher_bakeoff.py generate/judge/report [--variants --tag]` | 老師比較 |
| `scripts/dev/character_data.py`、`character_pipeline.sh`、`train_lora.py` | LoRA 資料和全流程（v1 跑完了；cron 看門狗已刪） |
| `scripts/dev/bench_hw.py [--model]`、`tts_latency.py`、`log_summary.py` | 速度量測、log 數字整理 |
| `scripts/dev/stt_eval.py`、`ui_preview.py` | STT、UI |

## 7. 踩過的雷

- **llama-server 的 LoRA 比例**：沒寫比例的請求會套上已載入的 LoRA；比例一變就丟掉那個 slot 的快取。所有請求都要寫比例，套和不套各用一個 slot。
- **HF 下載**：沒有 token 時 Xet 會停在 0 B/s。分段 `curl -r` 平行下載（8 段）加 sha256 驗證最穩，E4B 4.2 GB 約 15 分鐘。
- **`claude -p` 偶爾卡超過 15 分鐘**：評審一定要每批存檔、可以續跑、失敗重試（`options_eval.py judge` 已經這樣做）。
- **`pgrep -f` / `pkill -f`**：比對到的字串也在自己的 shell 命令列裡，結果把自己殺掉。
- **`git revert` 沒有 `-q`**：加了只會印出用法、什麼都沒做。
