# SilentTalk 交接（2026-09-27 下午，角色模式重蓋版）

> 給接手的模型或工程師。**一次做一個里程碑**，每個都有驗證方式和過關標準；沒過關不要進下一個。
> 文件沒寫到的判斷，停下來問使用者，不要猜。但**不要叫使用者做標註或評判樣本**，那是你的工作（見規則 9）。
> 這份是唯一要照著做的文件。前兩版封存在 `archive/HANDOFF-2026-09-25.md`、`archive/HANDOFF-2026-09-27-am.md`（只在開發機、不進 git）。

---

## 0. 五分鐘讀懂現況

**產品：** Windows 桌面程式。Discord Bot 在語音頻道裡有兩種用法：

1. **Copilot 模式**：聽別人講話 → STT → LLM 產生四個候選 → 使用者按 WASD 選 → TTS 替他說。**說話的是使用者本人。**
2. **角色模式**：Bot 自己就是使用者寫的人設，自己聽、自己決定要不要接話、自己講。**說話的是一個角色。**

**使用者的目標是 2，而且要做到「頂級電子人，講話無違和」。** 1 維持現狀，這一輪不動。
**人設是使用者自己寫的，而且大多是「關係」**：想要老婆就老婆、想要小孩就小孩、想要兄弟就兄弟（使用者原話）。所以角色要認得頻道裡的使用者本人（人設「人際關係」欄填 Discord 名稱），而且 LoRA 是**一個通用 adapter 服務所有人設**，不是訓練某一個角色。

**硬體標準：RTX 3050 Ti Laptop（4 GB VRAM）。** 使用者最差的機器就是這個等級，開發以它為準；純 CPU 只是退路（能用就好）。**不用任何付費 API**（這是玩具專案）。使用者的 3050 Ti 筆電是 Windows 11、Intel 11 代 8 執行緒，**實測數字見 5.1**。

**這一輪在做什麼：** 使用者同意把角色模式整個重蓋，舊的蒸餾資料和 LoRA 已停用、封存在 `archive/distill-v1/`（原因見那裡的 README，第 3 節也有摘要）。

**測試：** `152 passed`，三個檢查指令都乾淨（見 1.3）。**用 `pytest` 自己的 exit code 判斷**，不要 `pytest | tail` 後面接 `&&`（tail 會吃掉失敗，這一輪發生過）。

**目前狀態（2026-09-27 16:00）：**

| 項目 | 狀態 |
|---|---|
| M1 測試集＋評估 | ✅ `scripts/dev/turn_eval*.py`、`turn_eval_data.jsonl`（15 場、393 判斷點，另有 6 場關係型人設正在加） |
| M2 新架構（模型判斷＋只往後接） | ✅ 預設「被叫才回」過關；「主動」模式仍太吵（見 5.2） |
| M5 TTS 串流 | ✅ 開發機第一聲 600–700 ms → 270–290 ms；**沒在真 Discord 聽過** |
| M5 等對方講完 | ⬜ 需要真人語音資料才能調，先不動 |
| M3 挑老師 | 🔄 網路太慢，只能用本機的 Qwen3-30B-A3B（見 M3） |
| M4 LoRA | 🔄 資料產生器、訓練、轉檔、評估流程都寫好並試跑過（`scripts/dev/character_pipeline.sh`） |
| 實機 Discord 驗收 | ⬜ 需要使用者，步驟在第 4 節最後 |

---

## 1. 開工前

### 1.1 環境

需要 Python **3.12**。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt     # Windows: .venv\Scripts\python.exe
.venv/bin/python -m pytest -q
```

### 1.2 開發機上已經備好的東西（Linux，`.runtime/` 已 gitignore）

```bash
source .runtime/tools/env.sh     # llama-server b11179 (Vulkan) 進 PATH
```

- `.runtime/models/llm/` — Gemma 4 E2B（預設）、Qwen3.5-4B、Qwen3-1.7B、Qwen3-4B 等
- `.runtime/models/teacher/` — Qwen3-30B-A3B-Instruct-2507（17.7 GB）
- `.runtime/hf/gemma-4-E2B-it-qat/` — 學生模型的 HF 權重（訓練用）
- `.runtime/train-venv/` — torch cu124 + transformers + peft + trl
- `.runtime/tools/llama.cpp-b11179/` — `convert_lora_to_gguf.py` 等

開發機的 GPU 和別的專案共用（ComfyUI、whisper-api 常駐約 9 GB），**不要動它們的程序**。

**3090 的數字不能換算成 3050 Ti。** 用規格比例（×5）推估錯很多：實測 3050 Ti 生成速度是 3090 的 57%，不是 20%。要 3050 Ti 的數字就請使用者在筆電上跑 `scripts/dev/bench_hw.py`（見第 6 節），或給他一段 prompt 讓筆電上的 agent 跑。

### 1.3 每個任務結束都要跑

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk app.py tests scripts
.venv/bin/python -m compileall -q app.py silenttalk scripts/setup_copilot.py
```

改過 UI 再加 `xvfb-run -a .venv/bin/python scripts/dev/ui_preview.py --font "Noto Sans CJK TC"`，要真的打開 `.runtime/dev/ui_preview/` 的截圖看版面。

---

## 2. 規則（違反任一條都要先問使用者）

1. **對話內容不能寫進硬碟。** 轉錄文字、PCM、打字內容、prompt 都只在 RAM。不要提高 llama-server 的 verbosity，不要加 `--log-file`。`_LOG` 只能記數字、長度、ID、錯誤類型。（合成的訓練／測試資料不是真實對話，可以存。）
2. **回覆方向只有一個來源：** `silenttalk/copilot/types.py` 的 `REPLY_LANES`。
3. **劇情模式的 WASD 只在視窗有焦點時生效。** 不要註冊成全域熱鍵。
4. **不要 `ruff format` 整個 repo**，只格式化自己新增的檔案。
5. **殺程序不要用 `pkill -f <字串>`**。用 `pgrep -x` 或 `ps` 取 PID 再 `kill`。
6. **改 prompt、STT、模型、架構之前先量基準**，改完再量一次，變差就回退。
7. **不要在 `main` 直接 commit。** 目前分支是 `copilot-story-mode`。commit 前跑 1.3。
8. **Claude 的輸出不能用來訓練模型，也不能用來挑選訓練資料**（Anthropic 條款）。老師和資料篩選只能用開源權重模型；Claude 只能當**評估**用的評審。
9. **不要叫使用者標註資料、評判樣本。** 標籤要在出題時就決定（by construction），或用兩個以上互相獨立的評審交叉確認，意見不一致的題目丟掉或標成「兩種都算對」。使用者只負責做決定和實機驗收。
10. **每個設計都用 3050 Ti 實測數字判斷**，3090 數字只能看相對快慢。VRAM 預算：模型＋KV 要留空間給遊戲（使用者可能邊玩邊用）。
11. **不用付費 API。** 老師模型只能在開發機本機跑。
12. **不要用 `archive/distill-v1/` 的任何資料訓練。**

---

## 3. 為什麼重蓋、新架構長什麼樣

### 3.1 舊做法的問題（已查證，不要重蹈）

| 問題 | 證據 |
|---|---|
| 沒有「不該回話」的範例 | 情境 prompt 寫「最後一句要值得回應」→ 1452 筆角色資料只有 1 筆 SKIP |
| 一半資料教錯 | 758 筆（52%）因為句中有「你」就被標「必須回應」，包括「小魚你有看到嗎」這種對別人說的話 |
| 角色沒當過參與者 | 每筆都是冷插進一段陌生對話講一句 |
| 老師不比學生強 | 自然度：Qwen3-30B-A3B 3.10、Gemma 4 E2B 3.01 |
| 資料綁死 prompt | prompt 一改資料就過時 |
| 用關鍵字判斷語意 | `character.py` 的 `address_of()`／`is_question()`／`asks_if_ai()` 分不開「我剛才跟阿凱講話」和「阿凱你在嗎」 |
| 每句都重算整段對話 | 「最近 N 句」的視窗每次都在滑動，快取在視窗開頭就斷掉 |

### 3.2 新架構

**A. 每句都由模型決定講不講（已實作，`LocalReplyModel.character_turn`）。** 原本想讓「講什麼或 SKIP」一次做完，但**零訓練的 Gemma 4 E2B 18 句全都回話、一次都不 SKIP**，所以改成兩步、同一段快取：先在最後一句後面暫時附上「是不是在對你說話？只回答 是／否」，grammar 限制只解碼 1 個 token；答「是」才生成。煙霧測試 15/15，3090 上不講話約 80 ms、講話（判斷＋生成）160–350 ms。
- 結構化訊號（Discord @mention、回覆 Bot 的訊息）跳過判斷，直接回。
- 「多主動」是 `character_engagement`（called／active），只改 system prompt 和判斷問題的措辭。
- 關鍵字規則（`address_of` 等）已從執行路徑拿掉，只留在 `character.py` 當 M1 的舊基準；跟進時間窗、冷卻、插話間隔三個設定已刪除。
- 模型失敗 → 不講話＋log（判斷和生成是同一個模型，沒有「模型慢但規則快」的情況可以退）。
- M4 訓練好之後，可以再試「一次做完」省掉判斷那一次請求。

**B. 對話改成「只往後接」的多輪格式。** 別人說的話是 user 訊息（`名字：內容`），角色自己說的是 assistant 訊息，system 放人設。新的一句只要接在最後，前面的 KV 快取整段沿用。
- 對話太長要濃縮時才重建一次快取（`summarize` 已有）。
- 實測見 5.1：3050 Ti 上每次判斷 93 ms（舊格式 118 ms），在 GPU 上差距不大；純 CPU 時差距很大（0.15 s vs 0.65–1.65 s）。主要好處是 CPU 退路和長對話時不用重算。

**C. 從講完到出聲的整條路提速：**
- TTS 串流：`edge_tts.Communicate.stream()` 邊收邊送 Discord，不寫完整檔再播（現在是先存 MP3 再播）。
- STT 提早起跑：短停頓就先用暫定結果開始生成，最終結果一樣就沿用，不一樣就重來。
- 被打斷就停：別人開始講話時 Bot 收聲。
- 每一段都要有 log 數字（毫秒），才知道時間花在哪。

**D. Copilot 模式不動。** 之後若載入角色 LoRA，Copilot 的請求要把 LoRA 強度設 0（llama-server 有 `--lora-init-without-apply` 和 `POST /lora-adapters`，也支援單一請求指定 `lora`，上線前要實測確認）。

### 3.3 「無違和」的量法（所有決定都看這張表）

| 面向 | 指標 | 目標 |
|---|---|---|
| 反應 | 對方講完 → Bot 開始出聲 | 3050 Ti ≤ 1.5 s（純 CPU 退路 ≤ 3 s） |
| 時機 | 真的在叫它時有回（recall） | ≥ 95% |
| 時機 | 不是對它說卻插嘴（false speak） | ≤ 10%（「健談」設定另外量） |
| 內容 | 盲測：評審猜哪個參與者是 Bot | 猜中率越接近 50% 越好；先求比現況低 |
| 內容 | voice／stance／natural（沿用 persona_eval 評分表） | 不低於現況 |
| 不出戲 | 被質問身分時自爆 | 0 |

評審本身有誤差（同一份輸出重評：attribution ±0.07、voice ±0.1、stance ±0.25）。**差距小於誤差就不算贏。**

---

## 4. 里程碑（依序）

### M0｜量現況基準 ✅

- [x] 停掉舊蒸餾流程、刪 cron 看門狗、資料封存到 `archive/distill-v1/`
- [x] 3050 Ti 實機分段延遲（5.1，`bench_hw.py`）
- [x] 舊架構在 M1 上的分數（5.2）
- [ ] 還沒量的兩段：STT 從最後一個字到判定講完的實際等待、Discord 從拿到音訊到對方聽到。要真 Discord，App 的 log 有 `since_heard_ms`（聽到那句 → 角色的話備好）可以用

### M1｜測試集與指標 ✅

- `scripts/dev/turn_eval_data.jsonl`：整場多人對話，標籤出題時決定，**Claude 寫的，只能評估不能訓練**（檔頭有寫，也列出訓練資料不能重用的名字）。Qwen3-30B-A3B 交叉核對原始一致率 75.8%，模糊的改成 either。
- `scripts/dev/turn_eval.py --policy old|new [--only ids] [--judge] [--tag]`：逐句重播（角色的劇本台詞一定進歷史），old 路徑固定在 commit 5924fd0。**注意：** 評估時角色自己說出口的話不會進歷史，所以「主動」模式的角色看起來一直很久沒說話，插嘴率會比 App 裡高。
- 正在加 6 場關係型人設（老婆、國小兒子、死黨、阿嬤、女朋友、國中妹妹）的對話，加完後一樣要跑 `--policy new`。

### M2｜新架構 A＋B，先不訓練 ✅（「主動」模式除外）

- 結果見 5.2：recall 73.7% → 94.7%、名字聽錯 8% → 83%、自然度 2.81 → 3.39、契合 2.86 → 3.67；「被叫才回」插嘴 9.5%（目標 ≤ 10%）。
- 「主動」模式：先問「在對你說話嗎」，安靜滿 4 句才問「現在插一句自然嗎」（`_JOIN_AFTER_QUIET_LINES`），插嘴 75.8% → 53.0%，剩下的要靠 M4 訓練。
- 另外修掉的：判斷請求沒帶 engagement（主動模式判斷用錯 prompt、快取也接不上）、人際關係沒進 prompt（老婆人設不知道誰是老公）、幾乎照抄對方的回話（「有啊我們週末去看電影」→「有啊，週末去看電影」）。

### M5｜整條路提速（架構 C，不用 GPU，可以和 M3、M4 並行）

- **3050 Ti 實測顯示 LLM 不是瓶頸**（判斷＋一句話約 0.3 s），大頭是「等對方講完」（0.8 s 靜音規則＋STT 出字粒度）和 TTS。
- [x] **TTS 串流**（`silenttalk/tts/stream.py`，`scripts/dev/tts_latency.py` 量測）：開發機第一個 Opus 封包 16 字 594–638 ms → 268–290 ms，33 字 698–709 ms → 267–288 ms。關鍵：FFmpeg 宣告 `-f mp3` 並關掉探測（不然 602 ms）、aiohttp happy-eyeballs 改 50 ms。**還沒在真的 Discord 上聽過。**
- EdgeTTS 無法預先連線或重用連線；除非重寫它的協定，不要再試。
- [ ] 等對方講完：縮短會在句中停頓時搶話，要真人語音資料才能調，先不動。

### M3｜挑老師（只能用本機免費模型）🔄

- `scripts/dev/teacher_bakeoff.py generate|judge|report`：每個候選在 M1 的「該講」點用 App 的正式請求說一句，老師另有「+pick」（4 個版本自己挑一個），Claude 盲評排名（只評估）。結果在 `.runtime/dev/m3/`。
- 學生候選：Gemma 4 E2B（現役）、Qwen3.5-4B、Gemma 4 E4B（使用者說 3050 Ti 跑得動就可以換）。**但換學生要下載它的 HF 原始權重來訓練**（4B 級約 8 GB），網路不行就只能用 E2B。
- 老師候選（都是 Apache-2.0）：Qwen3.6-35B-A3B、Qwen3.6-27B、Gemma 4 31B、Gemma-4-26B-A4B-TAIDE-zhTW。**2026-09-27 下載不下來**：沒有 HF token，Xet 會卡住、HTTP 只有 ~0.5 MB/s，而且這台機器的頻寬被別的程式用掉大半。`.runtime/dev/m3/download.sh`（`xget.py` 看門狗）在背景慢慢抓。**有 HF token 的話請使用者給，速度會正常。**
- 所以這一輪先用本機的 Qwen3-30B-A3B。過關標準不變：「+pick」要比學生自然、差距超過評審誤差，否則不蒸餾。

### M4｜新資料、訓練、評估 🔄

- `scripts/dev/character_data.py personas|scripts|refine|render`：
  - 人設 80% 帶「和使用者的關係」（`ROLES`：老婆、兒子、死黨、阿嬤……），關係照人設編輯器的格式存（從角色的角度：「阿明：我老公」），使用者本人一定在對話裡。
  - 老師寫整場對話，每句標「對誰說」，講不講由劇本決定；和標籤矛盾的點丟掉。
  - 角色的每句台詞：用 App 的正式請求再寫 4 個版本，老師挑最自然的（避開「欸」開頭）。
  - 輸出兩種列：判斷題（是／否，否最多是是的 2 倍）和台詞；別人的語音台詞加 STT 雜訊；「欸」開頭最多 12%。
  - 親密關係只給成年人；未成年角色不碰戀愛。
- `scripts/dev/character_pipeline.sh [--status]`：personas → scripts → refine → render → train_check → train → convert → eval → eval_judge，無人值守、可續跑（規則同 6.1）。adapter 輸出到 `.runtime/models/llm/character-e2b-lora.gguf`，`[copilot] character_lora` 填這個檔名就會載入；**只有角色模式的請求套用，Copilot 請求的 LoRA 強度是 0**。
- 試跑過（小模型當替身老師）：四個資料步驟、訓練遮罩（只對答案算 loss）都正確。**單一請求切換 LoRA 強度還沒用真的 adapter 驗證過**，第一個 adapter 出來要先驗。
- **過關：** M1 上時機（尤其「主動」模式插嘴）和內容分數贏過 M2，差距超出評審誤差；3050 Ti 速度不退步。過關才上線。

### 需要使用者本人的驗收（等他有空，不要催）

**Discord 實機測試**是目前最缺的一塊。使用者在 3050 Ti 筆電上用 SSH 連開發機，筆電上有自己的 agent，給他下面這段 prompt 就好（使用者不想做雜事，**只請他講話和聽**）：

```text
在 C:\Users\A8fm0\Downloads\SilentTalk（Windows 11、RTX 3050 Ti）：
1. git fetch origin，git checkout copilot-story-mode，git pull。
2. .venv\Scripts\python.exe -m pip install -r requirements.txt，
   .venv\Scripts\python.exe scripts\setup_copilot.py（已下載的會跳過）。
3. 確認 .env 有 DISCORD_BOT_TOKEN、OWNER_USER_ID（沒有就停下來問使用者，不要自己填）。
4. .venv\Scripts\python.exe app.py --copilot-smoke，把輸出貼回來。
5. 用「啟動 SilentTalk.cmd」開 App，跟使用者說可以進語音頻道了。
6. 使用者測完後，從 silenttalk.log 抓這幾種行的數字（log 裡沒有對話內容）：
   copilot_turn_final、copilot_character_line（latency_ms、since_heard_ms、spoke）、
   job_done（synthesis_ms、streamed）、character_line_dropped、任何 error／failed。
   整理成表貼回來，並附上使用者說哪裡怪。
不要 commit、不要改 repo 的檔案、不要動 .env 和 settings.json。
```

使用者要做的（約 10 分鐘）：人設頁選或建一個人設，「人際關係」加一行「自己的 Discord 名字：我老公（或我兒子、我兄弟…）」→ 開角色模式 → 在語音頻道：
1. 叫它名字問一句 → 要回，感覺延遲
2. 跟朋友聊別的、不叫它 → 不能插嘴
3. 「我剛剛跟○○講過」（講到它但不是對它說）→ 不能回
4. 它回完話後直接接它的話（不叫名字）→ 要回
5. 故意叫錯一個同音字 → 最好要回
6. 「你是不是 AI」→ 不承認、自然帶過
7. 叫它寫程式或查天氣 → 用角色的方式推掉
8. 聽聲音：音色合不合、有沒有斷音或爆音（TTS 串流是新的）
9. 有沒有把你當成人際關係裡寫的那個人

其他：

| 項目 | 做法 |
|---|---|
| Discord 文字聊天 | Developer Portal → Bot → 打開 **Message Content Intent**；設定頁 → Discord → 打開「讀寫文字聊天」；在語音頻道聊天室 @Bot。預期 log 有 `text_message_received ... addressed=True` |
| 邊打遊戲的 VRAM | 筆電開著遊戲跑 `.venv\Scripts\python.exe scripts\dev\bench_hw.py`，貼回最後那張表 |
| voice-recv fork 修補 | 需要使用者的 GitHub，先問。要改 fork 的 `discord/ext/voice_recv/opus.py` 三處：`dave_session` 為 None 時不呼叫 `set_passthrough_mode`；`decrypt` 改用 `self._cached_id`；DAVE 還沒 ready 就丟掉封包。`discord_voice.py` 現有的防護不要刪 |
| 不切視窗選選項（可選） | 只能用「修飾鍵＋數字」這類組合，**絕不能註冊單獨的 W/A/S/D 全域熱鍵**。先問使用者要哪組按鍵 |

---

## 5. 量過的數字

### 5.1 3050 Ti 實機（2026-09-27，使用者筆電，`scripts/dev/bench_hw.py`，Gemma 4 E2B，App 的 low-VRAM 參數）

| 項目 | 3050 Ti（GPU） | 同一台純 CPU（`--gpu-layers 0`） | 3090 參考 |
|---|---|---|---|
| 模型佔用 VRAM | 1370 MiB（4 GB 裡還剩一半以上） | 122 MiB | — |
| 判斷一句：舊格式 | 118 ms | 615 ms | 77 ms |
| 判斷一句：新格式 | 93 ms | 644 ms | 49 ms |
| 生成速度 | 78.6 token/s | 8.8 token/s | 138 token/s |
| 回一句話（7 token） | 101 ms | 778 ms | — |
| TTS 第一段聲音 | 421–529 ms | | 257 ms |
| TTS 整句合成完 | 569–664 ms | | 395 ms |
| STT 解碼 | 0.14–0.18 × 即時 | | 0.09 × 即時 |
| STT 句尾收尾 | 44–70 ms，另外固定等 0.8 s 靜音 | | 44 ms |

- llama.cpp 在筆電上看到兩張卡：Vulkan0 是 Intel Iris Xe 內顯、Vulkan1 是 3050 Ti。依 nvidia-smi 的 VRAM 用量，模型是在 3050 Ti 上。**如果之後遇到速度異常，先檢查是不是跑到內顯**（可用 `--device Vulkan1` 或 `GGML_VK_VISIBLE_DEVICES=1` 固定）。
- 筆電的 llama-server 是 winget 的 b11193（開發機 b11179），winget 沒建 Links 捷徑，檔案在 `%LOCALAPPDATA%\Microsoft\WinGet\Packages\ggml.llamacpp_*\`。**App 的 `find_llama_server()` 目前只找 PATH**，在這台筆電上會找不到，要修。
- 純 CPU 的判斷時間新舊格式差不多，推測是 `-ngl 0` 時較長的 prompt 仍會被丟到 GPU 算，不是新格式沒用。開發機純 CPU（i9-12900，4 執行緒）：新格式 150–190 ms、舊格式 650–1650 ms、生成約 20 token/s。
- 同一個獨立 gate prompt 在 CPU 上約 1 s／句、15 題對 14 題，所以**不要另外加一次 gate 呼叫**，要併進生成。
- 結論：**3050 Ti 上 LLM 很快，VRAM 也還有空間**；使用者感受到的延遲主要來自 STT 斷句和 TTS。

### 5.2 角色模式時機與內容（M1，Gemma 4 E2B，3090，2026-09-27）

recall 算在「該講」、插嘴算在「不該講」，either 兩邊都不算。結果檔在 `.runtime/dev/turn_eval/`（舊版用 `-r2` 那份，另一份的延遲被 port 衝突汙染）。

| | 舊（關鍵字規則） | 新（模型判斷） |
|---|---|---|
| recall 全部（n=76） | 73.7% | **94.7%** |
| 　被叫才回（n=56） | 80.4% | 92.9% |
| 　名字被聽錯（n=12） | 8.3% | 83.3% |
| 　回應角色剛說的話（n=23） | 60.9% | 95.7% |
| 插嘴：被叫才回（n=158） | 6.3% | 9.5% |
| 插嘴：主動（n=66） | 83.3% | 75.8% → 兩段式判斷後 53.0% |
| 評審 natural / voice / fit | 2.81 / 3.58 / 2.86 | **3.39** / 3.60 / **3.67** |
| 每次呼叫中位數 | 182 ms | 不講 79 ms、講 255 ms |

出戲的全是「答應做做不到的事」（翻譯、查天氣、寫報告），沒有自承是 AI。原模型的毛病：凱哥 14 句裡 6 句「穩啦」、小晴像客服（「有什麼需要我幫忙的嗎」）、編造經歷。

### 5.3 模型比較（舊 persona_eval，四選項，3 人設 × 14 情境，Claude Sonnet 評審）

| 模型 | voice | stance | natural | lanes_ok | 捏造／踩底線 | VRAM | 3090 延遲 |
|---|---|---|---|---|---|---|---|
| Sonnet（天花板，只供對照） | 4.21 | 4.31 | 4.29 | 0.90 | 0 / 0 | — | — |
| **Gemma 4 E2B（預設）** | 3.54 | 3.25 | 3.01 | 0.76 | 0.04 / 0.05 | 1.4 GB＋2 GB RAM | 0.58 s |
| Qwen3.5-4B Q4_K_M | 3.60 | 3.29 | 3.06 | 0.80 | 0.05 / 0.07 | 2.9 GB | 0.81 s |
| Qwen3-4B-Instruct-2507 | 3.68 | 3.07 | 2.68 | 0.81 | 0.06 / 0.15 | 2.8 GB | 0.65 s |
| Qwen3-30B-A3B（舊老師） | 3.81 | 3.52 | 3.10 | 0.83 | 0.02 / 0.10 | 12 GB | 4 s |
| Qwen3-1.7B Q4_K_M | 3.10 | 2.52 | 2.21 | 0.54 | 0.10 / 0.10 | 1.4 GB | 0.34 s |

角色模式（舊 prompt，Gemma 4 E2B）：voice 3.68、stance 3.42、natural 3.26、fit 3.36、捏造 2%、踩底線 5%、盲測辨識 99%。

### 5.4 其他實測（仍然有效）

- **口頭禪重複**：連續說話時小模型 86% 的句子塞口頭禪；記住最近 4 句並在 prompt 點名「剛用過的不要再用」→ 40%。
- **不出戲**：預設「照角色演」政策下 3 人設 × 6 句身分質問 = 0/18 自爆。
- **名字出現頻率**：3887 句合成聊天裡人設名字只出現 1 次。語音裡叫名字很少，**不能只靠名字判斷**。
- **STT**：Paraformer 7.2% CER（預設）、SenseVoice 6.9%（可選）。STT 會把「凱哥」聽成「開哥」；目前靠人設的「暱稱」欄補。
- **音效音量補償**：RMS 差 ≤ 0.6 dB，峰值 ≤ −7 dBFS（只有儀器量過，沒人耳聽過）。

### 5.5 已驗證的下載資訊

| 檔名 | 來源 | 位元組 | sha256 |
|---|---|---|---|
| `gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf`（預設） | `unsloth/gemma-4-E2B-it-qat-GGUF` | 2,620,370,976 | `e531007218dfab990486a5de7676a6932d6ea8dea233d1f698d7c21cf8a16889` |
| `Qwen3.5-4B-Q4_K_M.gguf` | `unsloth/Qwen3.5-4B-GGUF` | 2,740,937,888 | `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` |
| `Qwen3-1.7B-Q4_K_M.gguf` | `unsloth/Qwen3-1.7B-GGUF` | 1,107,409,472 | `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897` |
| `Qwen3-30B-A3B-Instruct-2507-UD-Q4_K_XL.gguf` | `unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF` | 17,690,497,440 | `535f831bf3034a7fcfdcc8f0277a57cbad3a36c650c6068bf1d0894f25fb4383` |

---

## 6. 工具速查

| 指令 | 用途 | 狀態 |
|---|---|---|
| `python app.py --copilot-smoke` | 本機 STT＋LLM 一鍵驗收，exit 0＝通過 | 可用 |
| `scripts/dev/persona_eval.py` | 單句人格評分（盲測＋評分表），`--mode character`、`--probes assistant`、`--judge none`、`--rejudge` | 可用，但只量單句；M1 會加整場對話的評估 |
| `scripts/dev/bench_hw.py [--gpu-layers 0] [--llama-server PATH] [--skip-tts]` | 這台機器每一段各花多久；不 import silenttalk，舊安裝也能跑；需要 llama-server、模型、網路（TTS） | 可用 |
| `scripts/dev/llm_eval.py` | 四選項格式／方向／速度 | 可用 |
| `scripts/dev/stt_eval.py [--engine sensevoice]` | STT 準確度 | 可用 |
| `scripts/dev/ui_preview.py` | UI 截圖＋按鍵流程 | 可用 |
| `scripts/dev/turn_eval.py` | 角色模式時機＋內容評估（M1） | 可用 |
| `scripts/dev/teacher_bakeoff.py` | 比老師（M3） | 可用 |
| `scripts/dev/character_data.py`、`character_pipeline.sh` | 新 LoRA 資料與全流程（M4） | 可用 |
| `scripts/dev/tts_latency.py` | TTS 檔案 vs 串流的第一個封包時間 | 可用 |
| `scripts/dev/train_lora.py` | LoRA 訓練（通用，`--data`、`--max-length`） | 可用 |
| `scripts/dev/distill_data.py`、`distill_pipeline.sh` | 舊蒸餾流程 | **舊格式，不要跑** |

### 6.1 無人值守流程的經驗（重寫 M4 時沿用）

老師當掉 8.8 秒內重啟、卡死 44 秒內重啟；斷網時生成／訓練／轉檔照跑，只有評審等網路；VRAM 不足時等下一輪；同一階段連續失敗 3 次就標 `.blocked`、不再自動重試。cron 看門狗用完**一定要刪**。

---

## 7. 出問題時先看這裡

| 症狀 | 最可能原因 | 檢查 |
|---|---|---|
| `找不到 llama-server` | PATH 沒設 | `source .runtime/tools/env.sh` |
| `llama-server 啟動失敗，exit code=…` | 錯誤在 `｜` 後面 | port 被占用、VRAM 不足（`llm_gpu_layers` 調低或設 0） |
| 劇情模式按 WASD 沒反應 | 中文輸入法攔截 | 程式會自動關 IME；仍不行就切英數或用方向鍵 |
| 選項一直「思考中」 | LLM 請求逾時 | log 找 `copilot_suggestion_failed` |
| Copilot 沒反應但 TTS 正常 | Copilot 啟動失敗後自動降級 | log 找 `copilot_startup_failed` |
| 角色模式都不講話 | 預設是「被叫到才回」 | 叫它的名字，或設定頁改成「會主動加入」 |
| 設定改了沒效果 | 該項需要重開 | 設定頁上有「需重開」標示 |
| 測試在 import 就錯 | 用了 Python 3.10 | `python --version` 必須 3.12 |
| 背景任務莫名不動 | 鎖被孤兒程序持有 | `ls -l /proc/<pid>/fd \| grep .lock` |
