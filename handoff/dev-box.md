# 開發機工作檔（Linux、RTX 3090）

更新：2026-09-27 19:00｜分支：`copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。舊版在 `archive/`（只在這台機器、不進 git），不必讀。

---

## 1. 現況

**產品：** Windows 桌面程式，Discord Bot 兩種用法。
- **Copilot 模式**：聽別人講話 → 本機 LLM 想四個回覆 → 使用者按 WASD 選 → TTS 替他說。**這一輪不動。**
- **角色模式**：Bot 自己就是使用者寫的人設，自己判斷要不要開口、自己講。**這一輪的重點。**

**使用者要的：**
- 「頂級電子人，講話無違和」。
- 人設是使用者自己寫、隨時切換，大多是和他的**關係**：想要老婆就老婆、想要小孩就小孩、想要兄弟就兄弟。使用者本人就在語音頻道裡，人設的「人際關係」欄用他的 Discord 名稱。所以 LoRA 是**一個通用 adapter 服務所有人設**。
- 即時比精準重要。
- **硬體標準是 RTX 3050 Ti 4 GB**，只用免費、本機的東西，不用付費 API。
- 學生模型可以換，只要 3050 Ti 跟得上。

| 項目 | 狀態 |
|---|---|
| 模型判斷何時開口（取代關鍵字規則） | ✅ 完成，數字見 §5.2 |
| 對話只往後接、快取沿用 | ✅ |
| 關係型人設（關係進 prompt、稱呼說明） | ✅ |
| TTS 串流進 Discord | ✅（開發機量過，沒在真 Discord 聽過） |
| 角色 LoRA（Copilot 請求強度 0） | 🔄 資料產生中，§4 |
| 真 Discord 實測 | ⬜ 筆電第一次回報（2026-09-27 20:48，`laptop-report`）：bench 一樣（判斷 89 ms、68 token/s）、`--copilot-smoke` 通過（STT CER 1.7%、四選項中位數 1.34 s）；**語音測試沒做**（使用者沒空）；log 有 5 次 discord.py「Attempting a reconnect」ERROR，原因未知，`log_summary.py` 現在會列出例外類別，下次回報就知道 |
| 縮短「等對方講完」 | ⬜ 需要真人語音資料 |

**測試：** `157 passed`。

## 2. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、架構之前先量，改完再量，變差就退回。
2. **Claude 的輸出不能用來訓練，也不能用來挑選訓練資料**（Anthropic 條款）。Claude 只能當評審。老師模型只能用授權允許的開源權重模型。
3. 測試集 `scripts/dev/turn_eval_data.jsonl` 是 Claude 寫的，**只能評估**；它的檔頭列出訓練資料不能用的名字，`character_data.py` 會自動排除。
4. GPU 和別的專案共用（ComfyUI 約 9.4 GB、whisper-api），**不要動它們的程序**。
5. 不要 `ruff format` 整個 repo，只格式化自己新增的檔案。
6. 回覆方向只有一個來源：`silenttalk/copilot/types.py` 的 `REPLY_LANES`。劇情模式的 WASD 絕不註冊成全域熱鍵。
7. 正在跑的 bash 腳本不要原地改（bash 邊跑邊讀檔）：寫成新檔再 `os.replace`，然後重啟那個流程。
8. 這台機器沒有 git 身分：commit 用 `git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。

**每次改完要跑：**

```bash
.venv/bin/python -m pytest -q        # 看 exit code
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk app.py tests scripts
.venv/bin/python -m compileall -q app.py silenttalk scripts/setup_copilot.py
xvfb-run -a .venv/bin/python scripts/dev/ui_preview.py --font "Noto Sans CJK TC"   # 改過 UI 才需要，要打開截圖看
```

`source .runtime/tools/env.sh` 會把 llama-server（b11179，Vulkan）放進 PATH。

## 3. 角色模式怎麼運作

主程式在 `silenttalk/copilot/llm.py` 的 `LocalReplyModel.character_turn`，由 `runtime.py` 對每一句聽到的話呼叫：

1. **對話格式：只往後接。** 別人的話是 user 訊息（`名字：內容`），角色自己的話是 assistant 訊息。人設和人際關係放在 system prompt。新的一句只接在最後，前面整段快取沿用。
   - 舊的輪次會整批丟掉（`_TURN_WINDOW`），壓縮摘要（`summarize`）時才整段重建。
   - 這次請求專用的提示只附在最後一則訊息，下一次請求就拿掉。
2. **判斷要不要開口：在同一段快取上問 是／否，用 grammar 限制只輸出 1 個 token。**
   - 先問「是不是在對你說話」。
   - 「主動」模式下，角色已經安靜滿 4 句（`_JOIN_AFTER_QUIET_LINES`）才再問「現在插一句自然嗎」。
   - Discord 的 @mention 或「回覆 Bot 的訊息」直接算作在叫它，跳過判斷。
   - **不要**改回「一次呼叫、講或 SKIP」：零訓練的模型 18 句全回，一次都不 SKIP。
3. **生成：** 如果是被叫到，附上「在叫你，要回應」；如果是主動插話，附上「沒有人叫你，你決定插一句」。
   - 輸出會擋掉幾乎照抄對方的回話（`_echoes`）。
4. **LoRA：** `[copilot] character_lora` 填 `.runtime/models/llm/` 裡 adapter 的檔名。
   - 角色模式的請求強度 1。
   - Copilot 和摘要的請求強度 0，已實測過：強度 0 的輸出和沒掛 LoRA 一字不差。
5. **TTS：** EdgeTTS 的 MP3 一邊收到一邊餵給 FFmpeg（`silenttalk/tts/stream.py`），不寫進硬碟。
   - FFmpeg 必須宣告 `-f mp3` 並關掉格式探測。
   - aiohttp 的 happy-eyeballs 設 50 ms。

## 4. 正在跑的：角色 LoRA（M4）

`scripts/dev/character_pipeline.sh`，用 `--status` 看進度。依序跑：
personas → scripts → refine → render → train_check → train → convert → eval → eval_judge。
- 無人值守、可以接著續跑。
- 老師模型當掉或卡死會自動重啟。
- 同一階段連續失敗 3 次會標成 `.blocked`。
- **cron 看門狗已經加了**：`*/5 * * * * .../character_pipeline.sh`。**看到 `.runtime/dev/chardata/state/done` 就從 `crontab -e` 刪掉。**

**進度（2026-09-27 21:10）：** 人設 300、劇本 515（丟掉 85 份不合格的），精修台詞 13 句／分，預計 01:30 完成，之後才是訓練（約 4 小時）和評估。

**設定：**
- 老師：Qwen3-30B-A3B（§5.3 挑出來的），8 個 slot。
- 學生：Gemma 4 E2B。
- 300 個人設 × 2 場對話。
- 資料超過 8000 筆只訓練 1 輪。

**資料（`scripts/dev/character_data.py`）怎麼做：**
- 人設 75% 和使用者有關係，關係照人設編輯器的格式寫（「阿明：我老公」），而且使用者本人一定在對話裡。
- 老師寫整場對話，每句標「對誰說」。和這個標記矛盾的判斷點丟掉。
- 角色的每一句都用 App 的正式請求再寫 4 個版本，然後在同一段對話的最後問老師「哪一句最像你會說的」。挑選沿著每份劇本依序做，這樣快取可以沿用：原本亂序做每分鐘只有 5.5 句，改了之後 13.3 句。盲評抽 40 題，挑出來的句子 29 次拿第一、劇本原句只有 11 次，所以精修值得做。沒精修到的句子退回用劇本原句。
- 產生的訓練資料有三種：第一題判斷（答案看「是不是對角色說」）、第二題判斷（只在主動模式、安靜滿 4 句時出現，答案看角色有沒有開口）、台詞本身。
- 別人的台詞加上 STT 雜訊；「欸」開頭的台詞最多 12%。
- 標記規則的測試在 `tests/test_character_data.py`。

**跑完之後：**
1. 先用**現在的程式、不掛 LoRA** 在全部 21 場對話重跑一次基準：`turn_eval.py --policy new --judge --tag new-base-now`。舊的 `new-gemma-4-E2B-*.json` 是舊程式跑的，不能直接拿來比。再和 `new-lora-e2b.json` 比較。
2. **過關標準**：開口時機（尤其「主動」模式的插嘴率）和內容分數都要贏，而且差距要大於評審本身的誤差（±0.1–0.25）；3050 Ti 上不能變慢。
3. **過關的話**：
   - adapter 轉成 q8_0（約 25 MB）放進 repo。
   - `setup_copilot.py` 加上下載或複製這個檔案的步驟。
   - config 預設值填上檔名。
   - 在 `handoff/laptop.md` 加一個「掛 LoRA 再測一次」的步驟（照 skill 的做法，封存舊版再重寫）。
4. **沒過關的話**：把數字寫進 §5，停下來問使用者。
5. 有空的話可以開下一輪老師比較。已經下載好的候選有 Qwen3.6-35B-A3B、Qwen3.6-27B、Gemma 4 31B，都是 Apache-2.0，都在 `.runtime/models/teacher/`。用 `scripts/dev/teacher_bakeoff.py` 比。

## 5. 量過的數字

### 5.1 3050 Ti 實機（使用者筆電，`bench_hw.py`，Gemma 4 E2B）

| | GPU | 純 CPU |
|---|---|---|
| 模型 VRAM | 1370 MiB | — |
| 判斷一句（只往後接） | 93 ms | 644 ms |
| 生成速度 | 78.6 token/s | 8.8 token/s |
| TTS 第一段聲音（當時還沒串流） | 421–529 ms | |
| STT 收尾 | 44–70 ms（另外還要等 0.65–0.8 s 才判定講完） | |

**3090 的數字不能照比例換算成 3050 Ti**：實測 3050 Ti 的生成速度是 3090 的 57%，不是 20%。筆電有兩張 Vulkan 裝置（Intel 內顯和 3050 Ti），模型實際跑在 3050 Ti 上。

### 5.2 角色模式時機與內容（M1，Gemma 4 E2B，3090）

| | 舊（關鍵字規則） | 新（模型判斷） |
|---|---|---|
| 該回的有回（n=76） | 73.7% | **94.7%** |
| 名字被聽錯 | 8.3% | 83.3% |
| 回應角色剛說的話 | 60.9% | 95.7% |
| 插嘴：被叫才回 | 6.3% | 9.5% |
| 插嘴：主動 | 83.3% | 75.8% → 兩段式判斷後 53.0% |
| 評審 natural / voice / fit | 2.81 / 3.58 / 2.86 | 3.39 / 3.60 / 3.67 |

家庭對話（c16–c21，加了稱呼說明之後）：
- 該回的有回 86.8%，插嘴率 20.8%（「被叫才回」模式 12.0%）。
- 關係分數 3.64，對使用者本人 4.06。
- 同一段稱呼說明如果也加進判斷題，插嘴率會升到 32.5%，所以沒有加。

評估時角色實際說出口的話不會進歷史，所以「主動」模式量到的插嘴率比 App 裡實際的高。

### 5.3 老師比較（114 個「該講」的點 × 2 輪 Claude 盲評）

| 候選 | 平均名次 | 贏學生 | 不及格 |
|---|---|---|---|
| Qwen3-30B-A3B＋挑選 | 1.90 | 76% | 24 |
| Qwen3-30B-A3B | 2.21 | 71% | 29 |
| 學生 Qwen3.5-4B | 2.89 | 52% | 70 |
| 學生 Gemma 4 E2B | 3.00 | — | 69 |

### 5.4 TTS（開發機，`tts_latency.py`，文字備好到第一個 Opus 封包）

| | 原本（先存成檔案） | 串流 |
|---|---|---|
| 16 字 | 594–638 ms | 268–290 ms |
| 33 字 | 698–709 ms | 267–288 ms |

## 6. 工具

| 指令 | 用途 |
|---|---|
| `scripts/dev/turn_eval.py --policy old/new [--lora F] [--only ids] [--judge] [--judge-only TAG]` | 角色模式的時機和內容評估 |
| `scripts/dev/teacher_bakeoff.py generate/judge/report` | 老師比較 |
| `scripts/dev/character_data.py`、`character_pipeline.sh` | LoRA 資料和全流程 |
| `scripts/dev/train_lora.py --data F --max-length N [--check]` | LoRA 訓練（`--check` 是 CPU 上的遮罩檢查） |
| `scripts/dev/bench_hw.py`、`tts_latency.py`、`log_summary.py` | 速度量測、log 數字整理 |
| `scripts/dev/persona_eval.py`、`llm_eval.py`、`stt_eval.py`、`ui_preview.py` | 四選項、STT、UI 的舊工具，仍然可用 |
| `scripts/dev/distill_data.py`、`distill_pipeline.sh` | 舊格式，不要跑 |

## 7. 踩過的雷

- **HF 下載**：沒有 token 時，`hf` 的 Xet 會停在 0 B/s，HTTP 也只有約 0.5 MB/s。`.runtime/dev/m3/xget.py` 是有耐心的看門狗：Xet 會亂序抓區塊，所以不能只看檔案大小判斷有沒有卡住。
- **兩個 agent 同時跑同一個任務**：會互相覆寫檔案、撞 port。派工前確認前一個真的結束了。
- **`pgrep -f` / `pkill -f`**：比對到的字串也在自己的 shell 命令列裡，結果把自己殺掉（exit 144）。
