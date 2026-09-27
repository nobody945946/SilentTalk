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

**硬體底線（2026-09-27 改）：一般文書機，只有 CPU、沒有獨顯，也要能跑。** 3050 Ti 筆電、3090 開發機只是比較快的等級。**不用任何付費 API**（這是玩具專案）。

**這一輪在做什麼：** 使用者同意把角色模式整個重蓋，舊的蒸餾資料和 LoRA 已停用、封存在 `archive/distill-v1/`（原因見那裡的 README，第 3 節也有摘要）。

**測試：** `125 passed`，三個檢查指令都乾淨（見 1.3）。

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

**模擬文書機：** `CUDA_VISIBLE_DEVICES= GGML_VK_VISIBLE_DEVICES= llama-server ... -ngl 0 -t 4`。開發機是 i9-12900，真的文書機大約再慢 1.5–2 倍，數字要打這個折扣。

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
10. **每個設計都先用文書機（CPU、4 執行緒）的數字判斷**，GPU 數字只當參考。
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

**A. 一次呼叫同時決定「講不講」和「講什麼」。** 每聽到一句就呼叫模型一次，第一個輸出決定：「沉默」→ 停（只花 1 個 token）；否則就是要講的話，串流出去。不另做 gate、不另發請求。
- 結構化訊號（Discord @mention、回覆 Bot 的訊息）直接當成「一定要回」，不用問模型。
- 模型逾時（預算見第 4 節 M2）→ 退回簡單規則，寧可少準一點也不讓人等（使用者明確說即時比精準重要）。
- 「多主動」是 prompt 裡的一個參數（被叫才回／偶爾插話／健談），由訓練資料教模型遵守。

**B. 對話改成「只往後接」的多輪格式。** 別人說的話是 user 訊息（`名字：內容`），角色自己說的是 assistant 訊息，system 放人設。新的一句只要接在最後，前面的 KV 快取整段沿用。
- 對話太長要濃縮時才重建一次快取（`summarize` 已有）。
- 實測見 5.1：文書機模擬下每次判斷 **0.15–0.19 s**，舊格式 0.65–1.65 s。

**C. 從講完到出聲的整條路提速：**
- TTS 串流：`edge_tts.Communicate.stream()` 邊收邊送 Discord，不寫完整檔再播（現在是先存 MP3 再播）。
- STT 提早起跑：短停頓就先用暫定結果開始生成，最終結果一樣就沿用，不一樣就重來。
- 被打斷就停：別人開始講話時 Bot 收聲。
- 每一段都要有 log 數字（毫秒），才知道時間花在哪。

**D. Copilot 模式不動。** 之後若載入角色 LoRA，Copilot 的請求要把 LoRA 強度設 0（llama-server 有 `--lora-init-without-apply` 和 `POST /lora-adapters`，也支援單一請求指定 `lora`，上線前要實測確認）。

### 3.3 「無違和」的量法（所有決定都看這張表）

| 面向 | 指標 | 目標 |
|---|---|---|
| 反應 | 對方講完 → Bot 開始出聲 | 文書機 ≤ 2.0 s，3050 Ti ≤ 1.5 s |
| 時機 | 真的在叫它時有回（recall） | ≥ 95% |
| 時機 | 不是對它說卻插嘴（false speak） | ≤ 10%（「健談」設定另外量） |
| 內容 | 盲測：評審猜哪個參與者是 Bot | 猜中率越接近 50% 越好；先求比現況低 |
| 內容 | voice／stance／natural（沿用 persona_eval 評分表） | 不低於現況 |
| 不出戲 | 被質問身分時自爆 | 0 |

評審本身有誤差（同一份輸出重評：attribution ±0.07、voice ±0.1、stance ±0.25）。**差距小於誤差就不算贏。**

---

## 4. 里程碑（依序）

### M0｜量現況基準 ✅ 部分完成

- [x] 停掉舊蒸餾流程、刪 cron 看門狗、資料封存到 `archive/distill-v1/`
- [x] 文書機模擬的格式延遲（5.1）
- [ ] 端到端延遲分段：STT 斷句 → 最終文字、LLM 判斷、LLM 生成、TTS 首個音訊、Discord 開始播放。用 `app.py --copilot-smoke` 或寫 dev 腳本量，CPU 和 GPU 各一份
- [ ] 現況（舊架構、Gemma 4 E2B、無 LoRA）在 M1 測試集上的時機指標和內容分數

### M1｜測試集與指標

- 產生**完整多人對話**（20–40 句、2–5 個人類加上角色），每一句別人的話都標好「角色此時該講／不該講」，**標籤在出題時就決定**。
- 難題要有固定比例：第三人稱提到角色、「你」其實在對別人、STT 聽錯名字（凱哥→開哥）、被問是不是 AI、被當助理使喚、別人在講私事、角色剛講完話後別人的回應（沒叫名字但是在回它）。
- 用兩個互相獨立的評審交叉確認標籤（例：本機 Qwen3-30B-A3B 和 Claude Sonnet；**Claude 只在測試集用**）。不一致的丟掉或標「兩種都算對」。
- 人設和情境種子要和之後的訓練資料完全分開（用內建 `PRESET_PERSONAS` 加另外手寫的幾個）。
- 寫一個評估腳本：餵整場對話、逐句記錄模型講不講、講什麼、花多久，輸出 3.3 的所有數字。
- **過關：** 測試集 ≥ 300 個判斷點；評估腳本能在 CPU 模式跑完；兩個評審的一致率要寫進第 5 節。

### M2｜新架構 A＋B，先不訓練

- 在 `llm.py`／`runtime.py` 實作只往後接的多輪格式和「第一個輸出決定講不講」。
- `address_of()`／`is_question()`／`asks_if_ai()` 從預設路徑拿掉，只留當逾時的後備規則。
- 用 Gemma 4 E2B 原模型直接跑 M1。
- **過關：** 時機指標比 M0 好、內容分數不退步、文書機模擬下每句判斷 < 300 ms；`pytest -q` 全過，而且有「模型逾時 → 退回規則」的測試。
- 不過關就把數字寫進第 5 節，停下來跟使用者報告。

### M5｜整條路提速（架構 C，不用 GPU，可以和 M3、M4 並行）

- 依 M0 量到的分段，從最大的那一段開始改。
- **過關：** 端到端延遲達到 3.3 的目標，或者清楚寫出還差多少、卡在哪。

### M3｜挑老師（只能用本機免費模型）

- 候選：本機的 Qwen3-30B-A3B，以及開發機（3090 24 GB + 125 GB RAM）用 CPU offload 跑得動、**授權允許拿輸出訓練**的更大開源模型。下載前先確認授權和檔案大小，超過 100 GB 先問使用者。
- 同一批 M1 題目上，讓每個候選當角色跑整場對話，用 Claude 評審（只評估）。
- 也要試「老師本身的提升手段」：同一句生成多個版本，再由開源模型挑最好的一個。
- **過關：** 找到一個老師，自然度比 M2 的學生高出評審誤差以上。**找不到就不蒸餾**，停下來報告。

### M4｜新資料、訓練、評估

- 老師寫整場對話，角色是參與者，講不講由對話本身決定（自然產生沉默樣本）；多主動的參數也放進資料。
- 別人的台詞加上 STT 雜訊（拿掉標點、同音錯字、聽錯名字），角色的台詞保持乾淨。
- 用開源模型和規則篩資料（**不能用 Claude**）。
- 訓練：多輪對話，每一個 assistant 位置（講或沉默）都算 loss。舊的 `scripts/dev/distill_data.py`、`distill_pipeline.sh`、`train_lora.py` 是舊格式，**要重寫，不要直接跑**；無人值守、斷點續跑、看門狗的做法可以沿用（見 6.1）。
- **過關：** M1 上所有指標贏過 M2，而且差距超出評審誤差；文書機速度不退步。過關才上線（adapter 量化成 q8_0 放進 repo、`setup_copilot.py` 加下載項）。

### 需要使用者本人的驗收（等他有空，不要催）

| 項目 | 做法 |
|---|---|
| Discord 文字聊天 | Developer Portal → Bot → 打開 **Message Content Intent**；設定頁 → Discord → 打開「讀寫文字聊天」；在語音頻道聊天室 @Bot。預期 log 有 `text_message_received ... addressed=True`。PrivilegedIntentsRequired＝沒開 intent；`text_send_failed reason=forbidden`＝沒發言權限 |
| 人設聲音 | 人設頁最下面「聲音」→「▶ 試聽」，主觀判斷合不合角色 |
| 實機速度 | 筆電／文書機上 `.venv\Scripts\python.exe app.py --copilot-smoke`，看 GPU 列表和延遲中位數 |
| voice-recv fork 修補 | 需要使用者的 GitHub，先問。要改 fork 的 `discord/ext/voice_recv/opus.py` 三處：`dave_session` 為 None 時不呼叫 `set_passthrough_mode`；`decrypt` 改用 `self._cached_id`；DAVE 還沒 ready 就丟掉封包。`discord_voice.py` 現有的防護不要刪 |
| 不切視窗選選項（可選） | 只能用「修飾鍵＋數字」這類組合，**絕不能註冊單獨的 W/A/S/D 全域熱鍵**。先問使用者要哪組按鍵 |

---

## 5. 量過的數字

### 5.1 文書機模擬：prompt 格式 vs 延遲（2026-09-27，i9-12900 CPU 4 執行緒，Gemma 4 E2B，凱哥人設）

| 格式 | 每句判斷（1 token） | 每句要重算的 token |
|---|---|---|
| 舊：每次重組「最近 N 句」 | **650–1650 ms** | 74–183 |
| 新：只往後接的多輪對話 | **150–190 ms** | 12–16 |

生成速度約 20 token/s，一句短回覆（10–15 token）約 0.5–0.8 s。真的文書機再慢 1.5–2 倍。
同一個獨立 gate prompt 在 CPU（8 執行緒）上約 1 s／句、15 題對 14 題，所以**不能另外加一次 gate 呼叫**，要併進生成。

### 5.2 模型比較（舊 persona_eval，四選項，3 人設 × 14 情境，Claude Sonnet 評審）

| 模型 | voice | stance | natural | lanes_ok | 捏造／踩底線 | VRAM | 3090 延遲 |
|---|---|---|---|---|---|---|---|
| Sonnet（天花板，只供對照） | 4.21 | 4.31 | 4.29 | 0.90 | 0 / 0 | — | — |
| **Gemma 4 E2B（預設）** | 3.54 | 3.25 | 3.01 | 0.76 | 0.04 / 0.05 | 1.4 GB＋2 GB RAM | 0.58 s |
| Qwen3.5-4B Q4_K_M | 3.60 | 3.29 | 3.06 | 0.80 | 0.05 / 0.07 | 2.9 GB | 0.81 s |
| Qwen3-4B-Instruct-2507 | 3.68 | 3.07 | 2.68 | 0.81 | 0.06 / 0.15 | 2.8 GB | 0.65 s |
| Qwen3-30B-A3B（舊老師） | 3.81 | 3.52 | 3.10 | 0.83 | 0.02 / 0.10 | 12 GB | 4 s |
| Qwen3-1.7B Q4_K_M | 3.10 | 2.52 | 2.21 | 0.54 | 0.10 / 0.10 | 1.4 GB | 0.34 s |

角色模式（舊 prompt，Gemma 4 E2B）：voice 3.68、stance 3.42、natural 3.26、fit 3.36、捏造 2%、踩底線 5%、盲測辨識 99%。

### 5.3 其他實測（仍然有效）

- **口頭禪重複**：連續說話時小模型 86% 的句子塞口頭禪；記住最近 4 句並在 prompt 點名「剛用過的不要再用」→ 40%。
- **不出戲**：預設「照角色演」政策下 3 人設 × 6 句身分質問 = 0/18 自爆。
- **名字出現頻率**：3887 句合成聊天裡人設名字只出現 1 次。語音裡叫名字很少，**不能只靠名字判斷**。
- **STT**：Paraformer 7.2% CER（預設）、SenseVoice 6.9%（可選）。STT 會把「凱哥」聽成「開哥」；目前靠人設的「暱稱」欄補。
- **音效音量補償**：RMS 差 ≤ 0.6 dB，峰值 ≤ −7 dBFS（只有儀器量過，沒人耳聽過）。

### 5.4 已驗證的下載資訊

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
| `scripts/dev/llm_eval.py` | 四選項格式／方向／速度 | 可用 |
| `scripts/dev/stt_eval.py [--engine sensevoice]` | STT 準確度 | 可用 |
| `scripts/dev/ui_preview.py` | UI 截圖＋按鍵流程 | 可用 |
| `scripts/dev/distill_data.py`、`distill_pipeline.sh`、`train_lora.py` | 舊蒸餾流程 | **舊格式，M4 重寫前不要跑** |

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
