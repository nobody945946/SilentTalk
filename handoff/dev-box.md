# 開發機工作檔（Linux、RTX 3090）

更新：2026-09-28 下午｜分支：`copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。舊版在 `archive/`（只在這台機器、不進 git），不必讀。

---

## 1. 現況

**產品：** Windows 桌面程式，Discord Bot 兩種用法，同一個本機模型、同一段對話格式。
- **角色模式**：Bot 就是使用者寫的人設，自己判斷要不要開口、自己講；有「今天在想」的心事，冷場時會自己開話題。
- **選項模式**：聽別人講話 → 取樣四句「這個角色自己會說的話」→ 使用者按 WASD 選 → TTS 替他說。

**使用者要的：**「頂級電子人，講話無違和」；免費；不標資料、不評樣本。人設大多是和他的**關係**（老婆、小孩、兄弟），一個通用 LoRA 服務所有人設。即時比精準重要。**硬體標準是 RTX 3050 Ti 4 GB**；學生模型可以換，**速度別掉太多**。每一項都要在 3050 Ti 的小模型上量過才開；小模型扛不住的架構可以先留著給以後的大主機。慢的候選（例如 dense 老師）也要量完再決定，不能因為慢就跳過。

| 項目 | 狀態 |
|---|---|
| 人設只給「塑造這個人」的部分、今天的心事、冷場開話題 | ✅ 出貨（§5.2） |
| 角色 LoRA v1 只用在「是不是在叫你」（E2B） | ✅ 出貨 |
| 選項＝取樣四句、看的時候不會被換掉 | ✅ 出貨（§5.1） |
| 角色記憶（跨次演進的心事、看法、對人的感覺） | 🧊 架構做好（`character_state.py`、`copilot.character_memory`），E2B 上量輸，**預設 off**（§5.3） |
| **換學生 E4B＋自己的判斷 LoRA** | 🔄 背景流程在跑（§4 A） |
| 老師比較第二輪 | 🔄 挑選法已評完，Gemma 31B 先想再寫和 TAIDE 還沒跑（§4 B、§5.5） |
| 筆電（本輪，不需要使用者） | ⬜ `handoff/laptop.md`：更新、先下載 E4B、延遲拆解、UI 截圖、確認 App 能啟動。**語音測試等 E4B 出貨後才做**（同一輪測試不要讓使用者做兩次） |

**測試：** `178 passed`。

## 2. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、架構之前先量，改完再量，變差就退回。量不出贏就不出貨。
2. **評審的絕對分數（1–5）在不同次之間會漂移，漂移比我們要看的差異還大**（同一版本兩次差到 0.7）。要比兩個版本，一律用**配對盲評**（`turn_eval.py --judge-pair`、`options_eval.py judge`、`teacher_bakeoff.py judge`：同一個點兩版並排、正反順序各評一次）。
3. **Claude 的輸出不能用來訓練，也不能用來挑選訓練資料**（Anthropic 條款）。Claude 只能當評審。老師模型只能用授權允許的開源權重模型。
4. 測試集 `scripts/dev/turn_eval_data.jsonl` 是 Claude 寫的，**只能評估**；檔頭的名字清單，`character_data.py` 會自動排除。
5. GPU 和別的專案共用（ComfyUI、whisper-api、musichub 有時佔到 17 GB），**不要動它們的程序**。長時間的大工作（老師、訓練）不要擋在急的小評估前面；要大量 VRAM 先等空間。在別人佔著 GPU 時量到的速度不算數。
6. 關程序：**先列出 PID 再 kill**；`awk`/`grep` 比對的字串如果也出現在自己這行指令裡，會連自己的 shell 一起殺掉（exit 144，這台機器發生過兩次）。
7. 背景的「等 A 結束再做 B」監看，在 A 被手動停掉後會照樣做 B：停掉 A 時一併停掉監看，或換新的輸出檔名。
8. 不要 `ruff format` 整個 repo。正在跑的 bash 腳本不要原地改。
9. 這台機器沒有 git 身分：commit 用 `git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. 同時跑兩個評估時各給一個 port（`--port`）。

**每次改完要跑：**

```bash
.venv/bin/python -m pytest -q        # 看 exit code
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk app.py tests scripts
xvfb-run -a -s "-screen 0 2400x1600x24" .runtime/tools/ui-preview-env/bin/python \
    scripts/dev/ui_preview.py --font "Noto Sans CJK TC" [--scale 1.5]   # 改過 UI 才需要，要打開截圖看
```

## 3. 怎麼運作（`silenttalk/copilot/llm.py` 的 `LocalReplyModel`）

1. **對話格式：只往後接。** 別人的話是 user 訊息（`名字：內容`），角色／使用者自己的話是 assistant 訊息，人設、人際關係、今天的心事在 system prompt。請求專用的提示只附在最後一則訊息。
2. **人設（`Persona.render_prompt_block`）**：名字、身分、背景、想要、害怕、在意、最近、個性滑桿、說話感覺（去掉引號裡的詞）、幽默感、心情。口頭禪、代表台詞、雷點、熟悉、秘密、底線**不送**：小模型會逐字照抄（寫了「常說『真的啦』」的人設 80% 句子帶啦）。評審看完整人設（`render_system_block`）。
3. **今天的心事**：runtime 在設定人設時背景產生最多 4 件（`fill_concerns`，只照人設、只在記憶體），放在人設後面；角色畫面顯示，「換一批」換掉還沒說過的。
4. **角色模式 `character_turn`**：同一段快取上問 是／否（grammar 1 token）；先問「是不是在對你說話」，「主動」模式安靜滿 4 句再問「插一句自然嗎」；是的話寫一句。**冷場**：`character_lull_seconds`（預設 30）沒人說話 → `lull=True` 不問閘門，開個話題；照念心事就重寫；同一段冷場只一次。
5. **選項模式 `suggest`**：同一段對話尾端問「換你說話了」，溫度 1.0 取樣最多 7 次，留最多四句不像彼此、不重複對方的。
6. **LoRA**：`copilot.character_lora`＋`character_lora_uses`（預設只有 `called`）。有 LoRA 時開兩個 slot：套的走 slot 0、不套的走 slot 1（llama-server 在 LoRA 比例改變時會丟掉 slot 的快取）。
7. **角色記憶（`character_state.py`，預設 off）**：`light`＝心事和進度、近況、心情存在 `character_state.json`（使用者同意的例外：只存角色自己的狀態、用它自己的話），只在關閉或 90 秒冷場後更新；`full`＝再加看法和對人的感覺、每 16 句更新；兩者都帶時間（「星期五晚上 23:40」）。off 就是量過贏的版本，**不帶時間**。

## 4. 接下來

**A. E4B 判斷 LoRA（`scratchpad/e4b_gate.sh`，無人值守）**：下載 `google/gemma-4-E4B-it-qat-q4_0-unquantized`（rev 476025a…，sha256 驗證）到 `.runtime/hf/gemma-4-E4B-it-qat` → CPU 遮罩檢查 → 用 `.runtime/dev/chardata/train-gate-compact.jsonl`（8280 筆判斷題、精簡人設格式、最長 2126 token）訓練 1 輪（`--max-length 2304`，約 5 小時）→ 轉 q8_0 到 `.runtime/models/llm/character-e4b-gate-v1.q8_0.gguf` → `turn_eval --tag now-e4b-gate` → 和 `now-e2b` 配對盲評。流程不在了的話照這個順序手動跑。
- 判斷題的答案來自 v1 老師（Qwen3-30B-A3B）寫劇本時標的「對誰說」；v1 的判斷部分量過會贏，台詞部分沒用。v1 的完整人設版資料備份在 `train-v1-fullsheet.jsonl`。
- **過關標準**：開口時機（被叫才回的誤回 ≤ 2%、主動插嘴不高於 E2B 的 37%）＋配對盲評不輸 E2B。
- **過關就出貨**：adapter 放 `models/`、`setup_copilot.py` 的 `BUNDLED` 加上它、config 預設 `llm_model` 換 E4B（setup 會下載 4.2 GB）、`character_lora` 換成它；重寫筆電工作檔加一次 E4B 實測。
- 3050 Ti：E4B 載入 10 s、VRAM 2.7 GB、生成 26.5 token/s（E2B 76）、判斷 174 ms（E2B 約 90）；每說一句約多 0.4 秒。

**B. 老師比較收尾**：Gemma 4 31B（dense）的 +think 只做了 43/114，TAIDE（`gemma4-26b-taide`）還沒跑。在 GPU 乾淨時用 pinned worktree `/home/clawd/SilentTalk-bakeoff`（b6a6a3d，舊的完整人設格式，和其他老師一致）跑 `teacher_bakeoff.py generate --only gemma4-31b,gemma4-26b-taide`，同時重量 Gemma 31B 沒被搶資源時的速度，再和目前前兩名一起盲評。

**C. 第三版資料**：老師先定 **Qwen3.6-35B-A3B＋挑選**（和 27B 打平、最快；§5.5），除非 B 的 dense 候選明顯更好（那就用它，算好重產時間）。**不要開推理模式**（先想再寫兩個都輸）。台詞先接住對方那句、人設只在自然時出現；格式和 App 現在一致（精簡人設＋今天的心事＋冷場開話題的提示）；**產資料時先抽查**：隨機抽一批資料台詞，和學生自己寫的配對盲評，資料沒有明顯比較好就不訓練。學生看 A 的結果（E4B 過關就用 E4B）。

**D. 等筆電回報**：延遲拆解（模型 1.27 s、TTS 1.26 s 是哪一段慢）、App 能不能啟動。E4B 出貨時再寫一輪語音測試：角色模式的感受（今天在想、冷場開話題、認不認識這個人、語助詞）、真人聲音的語音辨識（log 的空白片段數、片段長度）。

## 5. 量過的數字

### 5.1 選項（`options_eval.py`，21 場對話每隔一句、269 點、正反順序各評一次）

| 比較 | 誰比較好 | 接得上 | 可用句數（/4） | 含「啦」 |
|---|---|---|---|---|
| 舊四方向 vs **取樣角色會說的話** | 39% vs **56%** | 2.51 / **3.04** | 1.37 / **1.75** | |
| 取樣：完整人設 vs **精簡人設＋心事**（出貨） | 45% vs 45% | 2.91 / 2.83 | 1.60 / 1.58 | 31% → **16%** |
| 取樣：E2B vs **E4B** | 32% vs **60%** | 2.84 / 3.17 | 1.53 / 1.94 | |

「先寫心裡想再寫四句」（輸 40% vs 55%）、把上一輪的想法帶到下一輪（小模型照抄）、選項套 LoRA（輸 31% vs 67%）、語氣詞規則（輸 37% vs 47%）都沒出貨。

### 5.2 角色模式（`turn_eval.py`，21 場、545 個判斷點；配對盲評＝逐句，以及整場「比較認識這個人／比較像真人」）

| 比較 | 逐句 | 認識這個人 | 像真人 | 含「啦」 |
|---|---|---|---|---|
| 出貨前 vs **精簡人設＋個性＋心事＋冷場（C2）** | 48% vs 45% | 13 vs **28** | 15 vs **26** | 39% → **14%** |
| C2 vs C2 去掉語氣詞規則（出貨） | 46% vs 43% | 17 vs 25 | 24 vs 18 | 14% → 18% |
| E2B＋LoRA vs **E4B（沒有 LoRA）** | 36% vs **60%** | 17 vs **25** | 16 vs **26** | 22% / 22% |

開口時機（被叫才回的誤回／主動插嘴／該回有回）：無 LoRA 9.6% / 47% / 90%；**E2B＋LoRA 只用在 called 1.0% / 37% / 89%**；E4B 無 LoRA 9.1% / 53% / 94%。
- 靈魂分數（`--judge-soul`，看完角色的話對他認識多少 1–5）：出貨前 2.6，8/21 場「看不出來」。
- 精簡人設但不加個性和幽默：逐句略輸、認識度平手 → 個性和幽默要留。

### 5.3 角色記憶（`--chain --memory`，5 個人設 × 2–3 場連續，第 2 場以後配對盲評）

| | off | light |
|---|---|---|
| 逐句 | **52%** | 39% |
| 認識這個人 | **12** | 6 |
| 生活會往前走 | **13** | 5 |

E2B 寫不好狀態：三天的心事一字不差、同一件事換句話又出現、把自己的暱稱當成別人、把「下午三點半」寫死在心事裡。帶時間和新格式的版本也輸（認識度 10 vs 19），所以 off 退回量過的版本。

### 5.4 3050 Ti 實機（`bench_hw.py`）

| | E2B | E4B |
|---|---|---|
| VRAM | 1370 MiB | 2694 MiB |
| 判斷一句 | 78–93 ms | 174 ms |
| 生成速度 | 68–79 token/s | 26.5 token/s |

上一輪真 Discord：角色開口時模型本身中位數 1.27 s、TTS 到第一段聲音 1.26 s（開發機 0.27 s），原因待本輪拆解。**3090 的數字不能照比例換算成 3050 Ti**。

### 5.5 老師（114 個「該講」的點 × 2 輪盲評排名，越小越好；每組最多 6 個版本）

挑選組（寫四句，同一個模型挑一句）：

| 候選 | 平均名次 | 贏學生 | 不及格 | 秒／點 |
|---|---|---|---|---|
| Qwen3.6-27B（dense） | **2.52** | 82% | 29 | 9.1 |
| Gemma 4 31B（dense） | 2.62 | 83% | **22** | 57.6（GPU 被別的專案佔，不準） |
| Qwen3.6-35B-A3B（MoE） | 2.65 | 79% | 35 | **6.2** |
| Qwen3-30B-A3B（MoE，v1 的老師） | 3.03 | 75% | 53 | — |
| 學生 Gemma 4 E2B | 4.19 | — | 116 | — |

先想再寫組：35B-A3B 挑選 2.77、27B 挑選 2.81、**35B-A3B 先想再寫 3.04**、v1 老師 3.14、**27B 先想再寫 3.24** → 推理模式反而變差，而且慢 4 倍。
學生組：v1 老師 1.85、**E4B 2.61**、Qwen3.5-4B 2.69、E2B 2.81。

### 5.6 語音辨識壓力測試（`stt_eval.py --stress`，合成語音）

SenseVoice 在快 60%、小聲 -18 dB、悶住、連著講都維持 CER 6.9–10.7%、沒有漏；Paraformer 小聲漏 10/16、悶住全漏。使用者說的失敗在合成語音上重現不了 → 等真人 log。

## 6. 工具

| 指令 | 用途 |
|---|---|
| `scripts/dev/turn_eval.py --policy new [--model] [--lora F --lora-uses called] [--agenda] [--lull] [--memory M --chain] [--cpu] [--port]` | 角色模式 |
| `turn_eval.py --judge-pair A B [--later-only]`、`--judge-soul TAG`、`--judge-only TAG` | 配對盲評、靈魂分數、單版評分 |
| `scripts/dev/options_eval.py generate --rev R [--model/--old-model/--lora/--agenda/--cpu/--port] --tag T`、`judge`、`report` | 選項 A/B |
| `scripts/dev/teacher_bakeoff.py generate/judge/report [--variants --tag]` | 老師比較 |
| `scripts/dev/character_data.py`、`character_pipeline.sh`、`train_lora.py` | LoRA 資料與訓練 |
| `scripts/dev/bench_hw.py [--model] [--lora]`、`tts_latency.py`、`stt_eval.py [--stress]`、`log_summary.py` | 延遲、語音辨識、log 數字 |
| `scripts/dev/ui_preview.py` | UI 截圖與流程檢查 |

## 7. 踩過的雷

- **llama-server 的 LoRA 比例**：沒寫比例的請求會套上已載入的 LoRA；比例一變就丟掉那個 slot 的快取。
- **TRL 的截斷從尾巴截**：太長的訓練資料會連答案一起截掉；先量 token 長度再設 `--max-length`。
- **HF 下載**：分段 `curl -r` 平行下載加 sha256 驗證最穩；Hugging Face 有時限速到 5 MB/s。
- **`claude -p` 偶爾卡超過 15 分鐘**：評審要每批存檔、可續跑、失敗重試。
- **E2B 的狀態更新**：編號會亂、同一件事換句話又出現、把自己的暱稱當別人——要讓小模型維護長期狀態前先量。
- **`git revert` 沒有 `-q`**。
