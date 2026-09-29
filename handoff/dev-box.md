# 開發機工作檔（Linux、RTX 3090）

更新：2026-09-29 深夜｜分支：`copilot-story-mode`
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
| **真人語音辨識** | ✅ 修好、真人驗過：DAVE 963 幀解開 961、解碼錯誤 0；照字念完的六句錯字率 0/0/0/7.7/0/10%（§4 A）。本機麥克風那條路沒收到聲音（原因未明，不影響） |
| **預設 E4B＋第三版 LoRA（判斷＋台詞）** | ✅ 出貨（`models/character-e4b-lora-v3.q8_0.gguf`；§5.2）。3050 Ti 上套 LoRA 判斷 211 ms、生成 26.0 token/s（沒 LoRA 205 ms、26.4）：延遲沒問題 |
| E2B＋v1 LoRA（只用在「是不是在叫你」） | 設定頁選 E2B 時自動換成它（adapter 跟著模型，`config.MODEL_ADAPTERS`） |
| 選項＝取樣四句、看的時候不會被換掉 | ✅ 出貨（§5.1） |
| 角色記憶（跨次演進的心事、看法、對人的感覺） | 🧊 架構做好（`character_state.py`、`copilot.character_memory`），E2B 上量輸，**預設 off**（§5.3） |
| E4B＋第一版資料練的判斷 LoRA | ❌ 不出貨：資料沒過硬關卡（檢查員只同意 82.7% 的判斷標籤 < 85%，§5.8） |
| 老師比較收尾 | ✅ 第四版照用 **Qwen3.6-27B**：同一輪盲評 2.38，35B-A3B 2.54、Gemma 31B 2.77、TAIDE 4.23（排除）；推理模式都更差（§5.5） |
| 筆電 | ⬜ `handoff/laptop.md`：**角色模式語音測試**（E4B＋v3 第一次真的被聽到）。不再請使用者念句子（他說好幾天沒說話、念不順） |

**測試：** `204 passed`（`tests/test_dave_receive.py` 需要開發用的 `cryptography`，沒有就跳過）。

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

**A. 等筆電回報**（`handoff/laptop.md`，回報在 `laptop-report` 分支的 `handoff/reports/laptop.md`）
- 前兩輪：E4B＋v3 延遲過關（套 LoRA 判斷 211 ms、生成 26.0 token/s）；真人語音辨識先是「部分對，但意思跑掉」，改了收音後 `--stt-check`：DAVE 963/961、解碼錯誤 0、像雜訊的片段 0/9，照字念完的六句 0/0/0/7.7/0/10%（程式平均 18.9% 是一句沒念、一句結巴）。**這一輪看角色本身**：使用者的三個感想＋log 數字（開口時機、聽到 → 角色開口的時間、選項延遲）。
- **收音怎麼改的**：Discord 語音多一層端對端加密（DAVE，MLS）。舊的 voice_recv fork 在 jitter buffer 之後、而且只在 session「ready」時才解，其餘幀把密文當 Opus 解碼、遺失補償也用沒解的下一幀。現在是上游＋PR #62（傳輸層解密後立刻解 DAVE，解不開就丟），加上 `silenttalk/voice_recv_patch.py`：先去掉 RTP padding（DAVE 的尾碼在最後，沒去掉就解不開；discord.js 也這樣做）、靜音幀（F8 FF FE，不加密）直接放行、SSRC 還沒對應到人的幀另外計數、同一人連續 36 幀解不開且沒有進行中的 transition 就回報最後一次 transition 無效並重建 session（discord.js 的做法；discord.py 只加密，不會發現）、解碼失敗的一幀當遺失幀。
- **離線驗證**：`scripts/dev/dave_loopback.py` 扮演語音伺服器（自己的 P-256 金鑰當 MLS external sender，簽 RFC 9420 的 Add 提案），讓兩個 davey session 組成真的群組，照 Discord 客戶端的格式送語音（Opus → DAVE → 帶擴充標頭的 RTP、部分加 padding → aead_xchacha20_poly1305_rtpsize → 結尾靜音）進 voice_recv 自己的 `AudioReader.callback`。結果：每一幀和送出的 Opus 完全相同，STT 錯字率 1.4%＝直接餵的；沒去 padding 前每 7 包丟 1 包。模擬舊的錯：30% 的幀是密文 → 錯字率 29%（部分對）、60% → 78%、100% → 辨識器什麼都不出。只丟幀 50% → 27%。
- `--stt-check` 現在由念的人控制節奏（Enter 下一句、r 重念、s 跳過不算），印麥克風名稱和音量；「收音」一列改報 RTP 序號算的封包遺失率（舊的「每秒幀數」把沒講話的時間平均進去，10.8 看起來像大量遺失，其實不是）。
- **判讀**（`log_summary.py` 的「收音」「STT 片段音量／頻譜平坦度」「真人辨識測試」三列）：
  - 經過 Discord ≤ 15% → 看角色模式語音測試的感想。
  - 經過 Discord 高、本機麥克風低 → 傳輸：看 DAVE 解不開丟掉、SSRC 未對應丟掉、每秒幀數（50＝全收到）、復原次數。
  - 兩條路一樣高 → 傳輸沒問題，是辨識器：比較更好的中文 ASR（例如更大的 SenseVoice／Paraformer、Whisper 系列、台灣口音的 Breeze-ASR），要在 3050 Ti 上量速度；開放測試集要用真人聲音（`--stt-check` 的句子），不能只用合成語音。
- **不要請使用者判斷辨識結果或角色的句子**（AGENTS.md 規則 2）：用 `--stt-check` 的錯字率。

**B. 第四版要改的**
- 劇本被丟掉 27%（試跑 13%），最多的是 JSON 解析失敗（39 個，多半是寫到 `max_tokens=3000` 被截斷）和「說話的人不在名單上」（33）：放寬 `max_tokens` 或要求短一點的劇本。
- 精修每句依序取 4 個樣本＋挑一句，受每路每秒 10 token 限制（精修 2636 句花 3 小時）。
- 檢查員每筆判斷題約 1.8 秒（31B dense、IQ3）；老師比較的 TAIDE（Gemma 4 26B MoE）如果夠好，可以當更快的檢查員，要先和 31B 比一致率。
- 訓練最大的浪費是每筆判斷題要把約 1400 token 的整段對話跑一次、只練 1 個字：同一段對話的判斷點共用前綴，用自訂 attention mask 一次練完，理論上快約 10 倍（Gemma 4 的滑動視窗要對得上，先用小資料確認 loss 和逐筆一樣）。

**C. 第三版怎麼跑的**：`scripts/dev/character_pipeline.sh`（資料和 log 在 `.runtime/dev/chardata-v3/`）。老師 `Qwen3.6-27B-UD-IQ3_XXS`（和 Q4 配對盲評平均名次 1.54 vs 1.46，在 0.1 的門檻內）、檢查員 `gemma-4-31B-it-UD-IQ3_XXS`（和 Q4 一致 99%）、學生 E4B QLoRA 1 輪（5024 筆，約 2 小時）。順序：`calibrate` → `pilot_*`（30 個人設走完到硬關卡）→ 人設數依試跑良率（199）→ 劇本 → 精修 → `render` → `student` → `check` → `filter` → 訓練 → `eval`／`eval_gate` → `eval_pair`。

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
| E2B＋LoRA vs E4B＋第一版判斷 LoRA（只套 called） | 35% vs 60% | 15 vs 27 | 20 vs 21 | 14 vs 28 | |
| 第一版判斷 LoRA 只套 called vs 也套台詞 | **59%** vs 37% | **31** vs 11 | **29** vs 13 | **31** vs 11 | |
| E4B（沒有 LoRA）vs **E4B＋v3 LoRA（判斷＋台詞，出貨）** | 40% vs **59%** | 15 vs **27** | 15 vs **27** | 17 vs **25** | |
| v3 只套判斷 vs **v3 判斷＋台詞** | 38% vs **61%** | 13 vs **29** | 11 vs **31** | 16 vs **26** | |
| E4B（沒有 LoRA）vs v3 只套判斷 | **52%** vs 43% | 22 vs 20 | 24 vs 18 | 14 vs 27 | |

開口時機（被叫才回的誤回／主動插嘴／該回有回）：無 LoRA 9.6% / 47% / 90%；E2B＋LoRA 只用在 called 1.0% / 37% / 89%；E4B 無 LoRA 9.1% / 53% / 94%；E4B＋第一版判斷 LoRA 只用在 called 0.0% / 39.8% / 95.6%；**E4B＋v3 LoRA（called、active、line）0.5% / 7.5% / 93.9%**；v3 只套 called、active 0.0% / 7.5% / 93.0%。
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

收尾組（`report-dense.json`，同一輪 6 個版本）：Qwen3.6-27B 挑選 **2.38**（不及格 22）、35B-A3B 挑選 2.54（23）、Gemma 4 31B 挑選 2.77（**12**）、Gemma 31B 先想再寫 3.31（只生成了一部分：Q4 放不進 GPU，Vulkan 版 server 逾時三次）、TAIDE（Gemma 4 26B 台灣版）挑選 4.23（139）、TAIDE 先想再寫 5.76（191）。→ TAIDE 排除；第四版照用 27B（IQ3，§4 C）。
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
| 第三版全量（199 個人設、288 個劇本） | **90.5%** ✅ | 93.2% / 88.5% | 64.3% | 78.1% | 1673 |

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
| `app.py --stt-check`（主人念 8 句，經過 Discord 和本機麥克風各算錯字率）、`scripts/dev/dave_loopback.py [--no-dave]`（離線的 Discord 收音＋真的 DAVE） | 真人語音辨識 |
| `scripts/dev/bench_hw.py [--model] [--lora --lora-uses]`、`tts_latency.py`、`stt_eval.py [--stress]`、`log_summary.py` | 延遲、語音辨識、log 數字 |
| `scripts/dev/ui_preview.py` | UI 截圖與流程檢查 |

## 7. 踩過的雷

- **llama-server 的 LoRA 比例**：沒寫比例的請求會套上已載入的 LoRA；比例一變就丟掉那個 slot 的快取。
- **TRL 的截斷從尾巴截**：太長的資料會連答案一起截掉。`train_lora.py` 現在會直接丟掉超過 `--max-length` 的資料並印出筆數。
- **QLoRA 不要用 `prepare_model_for_kbit_training`**：它把 Gemma 4 的每層嵌入表轉成 float32，多 8.75 GiB，OOM。改用 `enable_input_require_grads()`。
- **模型放不進空的 VRAM 時**：`--fit` 會把一部分丟到 CPU，GPU 大半時間在等；換一個整個放得下的量化版。換模型時也會發生（上一個還沒放掉記憶體），所以流程改成 `-ngl 99 --fit off` 並等空間。
- **等待迴圈別用 `pgrep -f <字串>`**：字串也在迴圈自己的指令裡，永遠比對得到自己，迴圈不會結束；「log 出現某行」也要只看啟動之後新增的行，不然舊內容會直接觸發。
- **下載會卡**：Xet 下載卡住時 `xget.py` 會重來，但 27B 那次重試 3 次花了 2.7 小時；GPU 工作不要排在下載後面空等。
- **render 會打亂資料順序**：學生和檢查員要照劇本、照順序送（`_by_script`），伺服器的快取才只需要讀新增的幾句。
- **合成語音的測試會繞過真實的輸入路徑**：`--copilot-smoke` 把合成語音直接餵給辨識器，錯字率 1.7%；真人經過 Discord 收音（DAVE 解密、jitter buffer）卻是 0/67。量下游（模型）之前，先用真實輸入把上游量過（`--stt-check`）。
- **DAVE 收音**：voice_recv 上游不解 DAVE；只解「ready」時的幀、或在 jitter buffer 之後才解，都會讓一部分密文變成聲音。RTP padding 要在解 DAVE 前去掉；靜音幀不加密。改收音時先跑 `dave_loopback.py`（每一幀要完全相同）。
- **HF 下載**：`.runtime/dev/m3/xget.py`（Xet＋卡住自動重來）；沒 token 時有時限速到 5 MB/s。
- **`claude -p` 偶爾卡超過 15 分鐘**：評審要每批存檔、可續跑、失敗重試。
- **E2B 的狀態更新**：編號會亂、同一件事換句話又出現、把自己的暱稱當別人——要讓小模型維護長期狀態前先量。
- **bash**：`wc -l < 不存在的檔 2>/dev/null` 還是會噴錯（重導向由左到右）；`2>/dev/null` 要寫在 `<` 前面。`git revert` 沒有 `-q`。
