# 開發機工作檔（Linux、RTX 3090）

更新：2026-09-29 早上｜分支：`copilot-story-mode`
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。舊版在 `archive/`（只在這台機器、不進 git），不必讀。

---

## 1. 現況

**產品：** Windows 桌面程式，Discord Bot 兩種用法，同一個本機模型、同一段對話格式。
- **角色模式**：Bot 就是使用者寫的人設，自己判斷要不要開口、自己講；有「今天在想」的心事，冷場時會自己開話題。
- **選項模式**：聽別人講話 → 取樣四句「這個角色自己會說的話」→ 使用者按 WASD 選 → TTS 替他說。

**使用者要的：**「頂級電子人，講話無違和」；免費；不標資料、不評樣本。人設大多是和他的**關係**（老婆、小孩、兄弟），一個通用 LoRA 服務所有人設。即時比精準重要。**硬體標準是 RTX 3050 Ti 4 GB**；學生模型可以換，**速度別掉太多**。每一項都要在 3050 Ti 的小模型上量過才開；小模型扛不住的架構可以先留著給以後的大主機。慢的候選（例如 dense 老師）也要量完再決定。**只有通過硬關卡的資料才能拿去訓練**（§2 規則 11）。使用者嫌流程慢：長工作先確認 GPU 真的在做事、先小規模試跑（§2 規則 12）。

| 項目 | 狀態 |
|---|---|
| 人設只給「塑造這個人」的部分、今天的心事、冷場開話題 | ✅ 出貨（§5.2） |
| 角色 LoRA v1 只用在「是不是在叫你」（E2B） | ✅ 出貨（目前的預設） |
| 選項＝取樣四句、看的時候不會被換掉 | ✅ 出貨（§5.1） |
| 角色記憶（跨次演進的心事、看法、對人的感覺） | 🧊 架構做好（`character_state.py`、`copilot.character_memory`），E2B 上量輸，**預設 off**（§5.3） |
| 換學生 E4B＋第一版資料練的判斷 LoRA | ❌ **不出貨**：考試很好（被叫誤回 0%），但它的資料沒過硬關卡（檢查員只同意 82.7% 的判斷標籤 < 85%，§5.8） |
| **第三版資料＋硬關卡 → E4B LoRA** | 🔄 試跑過關（判斷一致 90.3%、老師贏學生 63.4%）；全量 199 個人設在跑，預計 9/29 晚上 7 點左右考完（§4 A） |
| 老師比較收尾（TAIDE、Gemma 31B 先想再寫） | ⬜ 排在佇列最後，只給第四版參考 |
| 筆電 | ⬜ 本輪（不需要使用者）已回報。**語音測試等 E4B 出貨後才做**（同一個問題不要讓使用者測兩次） |

**測試：** `189 passed`。

## 2. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、架構之前先量，改完再量，變差就退回。量不出贏就不出貨。
2. **評審的絕對分數（1–5）在不同次之間會漂移，漂移比我們要看的差異還大**（同一版本兩次差到 0.7）。要比兩個版本，一律用**配對盲評**（`turn_eval.py --judge-pair`、`options_eval.py judge`、`teacher_bakeoff.py judge`：同一個點兩版並排、正反順序各評一次）。
3. **Claude 的輸出不能用來訓練，也不能用來挑選訓練資料**（Anthropic 條款）。Claude 只能當評審。老師和檢查員只能用授權允許的開源權重模型。
4. 測試集 `scripts/dev/turn_eval_data.jsonl` 是 Claude 寫的，**只能評估**；檔頭的名字清單，`character_data.py` 會自動排除。
5. GPU 和別的專案共用（ComfyUI、whisper-api 常駐約 7.7 GB，musichub 有時佔到 17 GB），**不要動它們的程序**。要大量 VRAM 就排隊等空間（`wait_mem`），不搶。在別人佔著 GPU 時量到的速度不算數。
6. 關程序：**先列出 PID 再 kill**；`awk`/`grep` 比對的字串如果也出現在自己這行指令裡，會連自己的 shell 一起殺掉（exit 144，這台機器發生過兩次）。
7. 背景的「等 A 結束再做 B」監看，在 A 被手動停掉後會照樣做 B：停掉 A 時一併停掉監看，或換新的輸出檔名。
8. 不要 `ruff format` 整個 repo。**正在跑的 bash 腳本不要原地改**（bash 邊跑邊讀檔）。
9. 這台機器沒有 git 身分：commit 用 `git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. 同時跑兩個評估時各給一個 port（`--port`）。
11. **訓練資料一律過硬關卡**（`character_data.py` 的 `student` → `check` → `filter`，門檻在 `HARD_CHECK`）：檢查員是和出題老師**不同家族**的開源模型；判斷題要檢查員答得一樣才留；台詞要老師那句在正反順序都贏過學生自己寫的才留，還要過語氣詞（≤ 1 個）和不照抄對方的規則。整批有一項沒過（覆蓋 ≥ 98%、判斷一致 ≥ 85% 且是／否各 ≥ 75%、老師勝率 ≥ 50%〔亂猜是 25%〕、檢查員正反一致 ≥ 70%、留下台詞 ≥ 1500）就**整批拒絕、一筆都不訓練**（exit 3，stage 標 `.blocked`）。用沒檢查過的資料訓練出來的東西，要等補檢查過了才能出貨。
12. **長工作之前**：(a) 模型要整個放得進空著的 VRAM（約 16 GB），放不進去會掉到 CPU，整張卡只剩每秒 20–60 token；換模型時要等上一個程序真的結束、記憶體回來才啟動下一個（`character_pipeline.sh` 用 `-ngl 99 --fit off`，空間不夠就等，不會偷偷降速）；每次啟動後看一下速度（server 的 CPU 用量應該約 100%，不是 900%）；(b) 用實際要用的 build、模型、平行數先跑 `llama-bench`／`llama-batched-bench`；(c) 先用小規模把整條路（含品質關卡）走一遍；(d) 資料量看上一次的學習曲線決定，不要照習慣；(e) 會被後面步驟丟掉的東西不要算（例如 filter 只留 4000 筆判斷題，就不要檢查 9600 筆）。
13. **開發機的資料工作用 CUDA 版 llama-server**（`.runtime/tools/llama.cpp-b11179-src/build-cuda/bin/llama-server`，靜態連結、sm_86、CUDA 12.5）；`.runtime/tools/llama-b11179` 的 Vulkan 版留給評估（和筆電一致）。同一個 27B 老師 8 路平行：CUDA 每秒寫 112 token、Vulkan 25。重編：原始碼 `git clone --depth 1 --branch b11179 https://github.com/ggml-org/llama.cpp .runtime/tools/llama.cpp-b11179-src`；cmake＋ninja 在 `.runtime/tools/cmake-venv`（uv 裝的）；`cmake -B build-cuda -G Ninja -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DBUILD_SHARED_LIBS=OFF -DLLAMA_CURL=OFF -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.5/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.5`（不指定的話會用 `/usr/bin/nvcc`、連到舊的 CUDA 11.5 函式庫而連結失敗），再 `cmake --build build-cuda --target llama-server`。

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
7. **角色記憶（`character_state.py`，預設 off）**：`light`＝心事和進度、近況、心情存在 `character_state.json`（使用者同意的例外：只存角色自己的狀態、用它自己的話），只在關閉或 90 秒冷場後更新；`full`＝再加看法和對人的感覺、每 16 句更新；兩者都帶時間。off 就是量過贏的版本，**不帶時間**。

## 4. 接下來

**A. 第三版（`scripts/dev/character_pipeline.sh`，`--status` 看進度；資料在 `.runtime/dev/chardata-v3/`，log 在 `logs/`；外層佇列 `/tmp/claude-1012/-home-clawd-SilentTalk/fe1c7542-61d8-4f8b-a6a4-1202fdd9cc55/scratchpad/night_queue3.sh`，機器重開過就不在了：直接跑 `GENERATOR=.runtime/models/teacher/Qwen3.6-27B-UD-IQ3_XXS.gguf CHECKER=.runtime/models/teacher/gemma-4-31B-it-UD-IQ3_XXS.gguf scripts/dev/character_pipeline.sh`，每一階段都能續跑）**
- 老師 `Qwen3.6-27B-UD-IQ3_XXS`（和 Q4 配對盲評平均名次 1.54 vs 1.46，在 0.1 的門檻內；快 1.3 倍）；檢查員 `gemma-4-31B-it-UD-IQ3_XXS`（和 Q4 判同樣 100 題一致 99%）；學生 E4B。
- 順序：`calibrate` ✅ → `pilot_*`（30 個人設）✅ 過關 → 全量（人設數依試跑良率＝199）→ `refine` → `render` → `student` → `check`（判斷題只檢查 filter 用得到的量）→ `filter` → E4B QLoRA 1 輪 → `eval`（LoRA 套判斷＋台詞，`--tag v3-e4b`）、`eval_gate`（只套判斷，`v3-e4b-gate`）→ `eval_pair`：`now-e4b` vs `v3-e4b`、`now-e4b` vs `v3-e4b-gate`、`v3-e4b-gate` vs `v3-e4b`（`.runtime/dev/turn_eval/pair-*.json`）。
- 實測速度（CUDA、整個模型在 GPU）：劇本 12 路每秒約 124 token；精修約每分鐘 11–15 句（每句依序取 4 個樣本＋挑一句，受每路每秒 10 token 限制）；檢查員每筆判斷題約 1.8 秒（有快取）。
- 之後佇列會跑老師比較收尾（TAIDE、Gemma 31B 先想再寫），只給第四版參考。

**B. 出貨判斷（第三版考完）**：
- 開口時機：被叫誤回 ≤ 2%、主動插嘴誤開口 ≤ 37%（E2B＋LoRA 的水準）、該回有回 ≥ 90%（看 `eval.log`／`eval_gate.log` 的表）。
- 配對盲評：贏 `now-e4b`（E4B 沒有 LoRA）才用 LoRA；`v3-e4b` 和 `v3-e4b-gate` 哪個贏就用哪種 `character_lora_uses`（第一版的判斷 LoRA 套台詞時逐句 59% vs 37% 大輸，所以台詞可能要留給原本的 E4B）。
- 都沒贏：出 E4B 不帶 LoRA（被叫誤回 9.1%），或留 E2B＋v1 LoRA，把兩種的數字寫給使用者選。
- 出貨步驟：adapter 放 `models/`、`setup_copilot.py` 的 `BUNDLED` 加上它、config 預設 `llm_model` 換 E4B（setup 會下載 4.2 GB）、`character_lora`／`character_lora_uses` 換掉；重寫筆電工作檔，**這時才做語音測試**，並用 `bench_hw.py --lora` 量 3050 Ti 上套 LoRA 的判斷延遲（E2B 上是 265 ms vs 90 ms）。

**C. 之後**：訓練最大的浪費是每筆判斷題要把約 1400 token 的整段對話跑一次、只練 1 個字。同一段對話的所有判斷點共用前綴，用自訂 attention mask 一次練完，理論上快約 10 倍；風險是 Gemma 4 的滑動視窗和自訂 mask 要對得上，要先用小資料確認 loss 和逐筆訓練一樣。

## 5. 量過的數字

### 5.1 選項（`options_eval.py`，21 場對話每隔一句、269 點、正反順序各評一次）

| 比較 | 誰比較好 | 接得上 | 可用句數（/4） | 含「啦」 |
|---|---|---|---|---|
| 舊四方向 vs **取樣角色會說的話** | 39% vs **56%** | 2.51 / **3.04** | 1.37 / **1.75** | |
| 取樣：完整人設 vs **精簡人設＋心事**（出貨） | 45% vs 45% | 2.91 / 2.83 | 1.60 / 1.58 | 31% → **16%** |
| 取樣：E2B vs **E4B** | 32% vs **60%** | 2.84 / 3.17 | 1.53 / 1.94 | |

「先寫心裡想再寫四句」（輸 40% vs 55%）、把上一輪的想法帶到下一輪（小模型照抄）、選項套 LoRA（輸 31% vs 67%）、語氣詞規則（輸 37% vs 47%）都沒出貨。

### 5.2 角色模式（`turn_eval.py`，21 場、545 個判斷點；配對盲評＝逐句，以及整場「比較認識這個人／比較像真人／生活會往前走」）

| 比較 | 逐句 | 認識這個人 | 像真人 | 生活 | 含「啦」 |
|---|---|---|---|---|---|
| 出貨前 vs **精簡人設＋個性＋心事＋冷場（C2）** | 48% vs 45% | 13 vs **28** | 15 vs **26** | | 39% → **14%** |
| C2 vs C2 去掉語氣詞規則（出貨） | 46% vs 43% | 17 vs 25 | 24 vs 18 | | 14% → 18% |
| E2B＋LoRA vs **E4B（沒有 LoRA）** | 36% vs **60%** | 17 vs **25** | 16 vs **26** | 16 vs **26** | 22% / 22% |
| E2B＋LoRA vs **E4B＋判斷 LoRA（只套 called）** | 35% vs **60%** | 15 vs **27** | 20 vs 21 | 14 vs **28** | |
| **E4B＋判斷 LoRA 只套 called** vs 也套台詞 | **59%** vs 37% | **31** vs 11 | **29** vs 13 | **31** vs 11 | |

開口時機（被叫才回的誤回／主動插嘴／該回有回）：無 LoRA 9.6% / 47% / 90%；E2B＋LoRA 只用在 called 1.0% / 37% / 89%；E4B 無 LoRA 9.1% / 53% / 94%；**E4B＋判斷 LoRA 只用在 called 0.0% / 39.8% / 95.6%**（3090 上每次判斷中位數 284 ms）。
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
| 判斷一句 | 78–93 ms（套 LoRA 265 ms） | 174 ms |
| 生成速度 | 68–79 token/s（套 LoRA 50） | 26.5 token/s |

上一輪真 Discord：角色開口時模型本身中位數 1.27 s、TTS 到第一段聲音 1.26 s（開發機 0.27 s）。**3090 的數字不能照比例換算成 3050 Ti**。

### 5.5 老師（114 個「該講」的點 × 2 輪盲評排名，越小越好；每組最多 6 個版本）

挑選組（寫四句，同一個模型挑一句）：

| 候選 | 平均名次 | 贏學生 | 不及格 | 秒／點 |
|---|---|---|---|---|
| Qwen3.6-27B（dense） | **2.52** | 82% | 29 | 9.1 |
| Gemma 4 31B（dense） | 2.62 | 83% | **22** | 57.6（GPU 被別的專案佔，不準） |
| Qwen3.6-35B-A3B（MoE） | 2.65 | 79% | 35 | **6.2** |
| Qwen3-30B-A3B（MoE，v1 的老師） | 3.03 | 75% | 53 | — |
| 學生 Gemma 4 E2B | 4.19 | — | 116 | — |

先想再寫組：推理模式兩個都變差（27B 2.81 → 3.24、35B-A3B 2.77 → 3.04），而且慢 4 倍。
學生組：v1 老師 1.85、**E4B 2.61**、Qwen3.5-4B 2.69、E2B 2.81。

### 5.6 第一版老師與訓練的效率

- 第一版老師（17.7 GB 的 MoE，專家一部分在 CPU）：寫劇本時整張 3090 每秒生成 55–59 token；精修時生成 20、讀 prompt 115 token/s。劇本 3.2 小時、精修 4.5 小時。
- E4B QLoRA 判斷 LoRA：8032 筆 × 1 輪 = 502 步 × 20.5 s ≈ 3 小時（每筆約 1.3 s）。驗證 loss：0.104（10%）→ 0.063（20%）→ 0.065（50%）→ 0.052（70%）：大部分在前 1600 筆就學到了 → 第三版判斷題上限 4000 筆、1 輪。

### 5.7 開發機 GPU 效率（3090，其他專案常駐約 7.7 GB，剩約 16 GB）

| | 設定 | 結果 |
|---|---|---|
| 27B 老師 IQ3，8 路 | Vulkan / **CUDA** | 寫 25 / **112** token/s；讀 650 / 1200 |
| 27B 老師 IQ3，CUDA | 1 / 2 / 4 / 8 / 16 路 | 寫 43 / 68 / 92 / 112 / 151 token/s |
| Gemma 31B 檢查員 IQ3，CUDA | 1 / 2 / 4 / 8 路 | 讀 414 / 386 / 239 / 112 token/s（路越多越慢） |
| 校準 | 800 筆隨機 vs **60 個整段劇本** | 每筆 10 s vs **約 1.5 s**（同一段對話依序送，快取只讀新增的約 90 token） |
| 換模型時 `--fit` | 上一個還沒放掉記憶體 | 部分層掉到 CPU，每路每秒 2 token（正常 10） |

混合架構（Qwen3.5／3.6 的 qwen35）在多路平行下前綴快取正常（每句只重讀約 50 token）；llama-server 不支援一次請求取多個樣本（`n` 回 400）。

### 5.8 硬關卡

| | 判斷一致 | 是 / 否 | 老師贏學生 | 檢查員正反一致 | 留下台詞 |
|---|---|---|---|---|---|
| 第一版判斷資料（抽 60 個劇本 966 筆） | 82.7% ❌ | 90.4% / 78.1% | — | — | — |
| 第三版試跑（30 個人設、52 個劇本） | **90.3%** ✅ | 92.3% / 88.9% | 63.4% | 77.7% | 303 |

第一版被檢查員質疑的「否」約一半是標錯：別人在回應角色剛說的話（「欸 你別急著下結論」），老師把 to 標成別人；另一半是檢查員太想開口。第三版劇本 prompt 把 to 定義成「這句要誰接話」（和 App 的判斷提示一致），一致率升到 90.3%。

### 5.9 語音辨識壓力測試（`stt_eval.py --stress`，合成語音）

SenseVoice 在快 60%、小聲 -18 dB、悶住、連著講都維持 CER 6.9–10.7%、沒有漏；Paraformer 小聲漏 10/16、悶住全漏。使用者說的失敗在合成語音上重現不了 → 等真人 log。

## 6. 工具

| 指令 | 用途 |
|---|---|
| `scripts/dev/turn_eval.py --policy new [--model] [--lora F --lora-uses called] [--agenda] [--lull] [--memory M --chain] [--cpu] [--port]` | 角色模式 |
| `turn_eval.py --judge-pair A B [--later-only]`、`--judge-soul TAG`、`--judge-only TAG` | 配對盲評、靈魂分數、單版評分 |
| `scripts/dev/options_eval.py generate --rev R [--model/--old-model/--lora/--agenda/--cpu/--port] --tag T`、`judge`、`report` | 選項 A/B |
| `scripts/dev/teacher_bakeoff.py generate/judge/report [--variants --tag]` | 老師比較（生成要在 pinned worktree `/home/clawd/SilentTalk-bakeoff` 跑，prompt 格式才和其他老師一致；那裡多加了 `qwen3.6-27b-iq3` 候選，沒 commit） |
| `scripts/dev/character_data.py personas/scripts/refine/render/student/check/filter [--rows]`、`character_pipeline.sh [--status]`、`train_lora.py [--4bit] [--check]` | LoRA 資料、硬關卡與訓練（`CHARDATA_DIR` 決定資料夾） |
| `scripts/dev/bench_hw.py [--model] [--lora]`、`tts_latency.py`、`stt_eval.py [--stress]`、`log_summary.py` | 延遲、語音辨識、log 數字 |
| `scripts/dev/ui_preview.py` | UI 截圖與流程檢查 |

## 7. 踩過的雷

- **llama-server 的 LoRA 比例**：沒寫比例的請求會套上已載入的 LoRA；比例一變就丟掉那個 slot 的快取。
- **TRL 的截斷從尾巴截**：太長的資料會連答案一起截掉。`train_lora.py` 現在會直接丟掉超過 `--max-length` 的資料並印出筆數。
- **QLoRA 不要用 `prepare_model_for_kbit_training`**：它把 Gemma 4 的每層嵌入表轉成 float32，多 8.75 GiB，OOM。改用 `enable_input_require_grads()`。
- **模型放不進空的 VRAM 時**：`--fit` 會把一部分丟到 CPU，GPU 大半時間在等；換一個整個放得下的量化版。換模型時也會發生（上一個還沒放掉記憶體），所以流程改成 `-ngl 99 --fit off` 並等空間。
- **等待迴圈別用 `pgrep -f <字串>`**：字串也在迴圈自己的指令裡，永遠比對得到自己，迴圈不會結束；「log 出現某行」也要只看啟動之後新增的行，不然舊內容會直接觸發。
- **下載會卡**：Xet 下載卡住時 `xget.py` 會重來，但 27B 那次重試 3 次花了 2.7 小時；GPU 工作不要排在下載後面空等。
- **render 會打亂資料順序**：學生和檢查員要照劇本、照順序送（`_by_script`），伺服器的快取才只需要讀新增的幾句。
- **HF 下載**：`.runtime/dev/m3/xget.py`（Xet＋卡住自動重來）；沒 token 時有時限速到 5 MB/s。
- **`claude -p` 偶爾卡超過 15 分鐘**：評審要每批存檔、可續跑、失敗重試。
- **E2B 的狀態更新**：編號會亂、同一件事換句話又出現、把自己的暱稱當別人——要讓小模型維護長期狀態前先量。
- **bash**：`wc -l < 不存在的檔 2>/dev/null` 還是會噴錯（重導向由左到右）；`2>/dev/null` 要寫在 `<` 前面。`git revert` 沒有 `-q`。
