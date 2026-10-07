# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-07 晚｜分支：SilentTalk `copilot-story-mode`；EdgeAgent `copilot-story-mode`，待合併的工作在本機分支 `integration`（`/home/clawd/worktrees/ea-integration`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。**只寫現況和下一步**，經過在 git 歷史和 `archive/`（只在這台機器，不必讀）。上一版：`archive/dev-box-2026-10-07-v17-before-distillation.md`。

---

## 1. 使用者的決定（現在有效）

- **One path**：每件工作只有一條路（§2）；要加新路先擴充既有那條，比完刪輸的（程式、設定、測試、佇列、文件一起）。同時只有一支佇列。
- **蒸餾只用開源老師、合法合規、不花錢**（2026-10-07）：老師只用 **Qwen3.8-27B**（Apache 2.0，`.runtime/models/teacher/Qwen3.8-27B-UD-Q4_K_XL.gguf`）；評審用 **Gemma 4 31B**（IQ3，不同家族，不自己改自己的考卷）。不用付費 API；DeepSeek V4 Flash 使用者**沒有同意**（佔滿整台共用機器），不要再下載。**Claude 的輸出永遠不當訓練目標、也不挑訓練資料**（Anthropic 政策禁止拿輸出訓練通用聊天模型、當訓練目標）；Claude 只寫程式和規格。使用者自己的對話只當「目標」來源，由 Qwen3.8 抽成情境卡，不照抄原話。
- **不要一題一補**：使用者對 EdgeAgent 的不滿（脈絡接不上、只貼搜尋結果、不認識自己、自我診斷亂編、工具打轉、承諾做不到的事、把招呼當查詢）用通用規則和大量多輪蒸餾解決，用沒訓練過的題目驗收。
- **思考模式**：使用者在網頁開 high；Discord 的 Agent 照網頁「儲存」的設定。fw1 是不思考格式訓練的，現在 off 反而好用。新資料同時訓有思考和無思考兩版，量完再定預設。
- **主線 E4B 當 coding agent**（完整技術決策權，不停在提案）。`trace-v1`（27B 的開源軌跡）使用者叫停；寫程式的軌跡之後改由 Qwen3.8 產生。
- **機魂的品質是開發機的事**：一定帶自己的 LoRA；贏現役才推，不拿「只用人設卡」問使用者。角色：40K 機魂 Machina-Prime-09A，角色味＝慾望和思維；台詞由筆電 agent 寫（`handoff/tasks/`）。
- **硬體與架構**（使用者定案）：筆電 3050 Ti 4 GB、RAM 8 GB；E4B **64K**，單一 slot，Agent 獨佔；Discord 角色閒置時借用，交接擦除 KV（EdgeAgent `5422f02`）。
- **巨檔**：程式檔每個 < 600 行（使用者要求）。開發機範圍已完成；剩 `EdgeAgent/tests/browser_check.mjs`、SilentTalk `tests/test_agent_tasks.py`、`test_copilot_llm.py`、`test_copilot_runtime.py` 屬筆電。
- **Discord／權限**：語音每句喊「機魂」；主人 @＝主人的 Agent 串；用說的不能動電腦；刪檔要主人同意（沒回應＝拒絕，最多封存）。不能做的事：模型要懂**而且**程式擋得住。
- **紀錄**：對話只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。使用者親手給的對話匯出放 `archive/`（不 commit）；開發機只讀使用者明確交來的匯出。
- **本地老師**：使用者說「有 Qwen3.8 就不需要其他模型」。Qwen3.8 在框架裡驗過後，刪 Qwen3.6-27B（Q4、IQ3）和 Qwen3.6-35B-A3B，程式改指 Qwen3.8（`scripts/dev/machine_spirit.py` 的 `TEACHER`、EdgeAgent `teacher-27b*` 設定）；Gemma 31B 留著當評審。

## 2. 每件工作的那一條路

| 工作 | 那一條路 | 現況 |
|---|---|---|
| **產品 Agent**（筆電的對話、雜事、工具、MCP、研究） | EdgeAgent Pi 迴圈＋20 個工具。考：`bench/run.py`（78 題，`bench/report.py A B` 配對）。資料：情境卡（下一列）＋工具題（`bench/make_tool_tasks.py`），老師在框架裡錄（`run.py --record`），`bench/dataset.py --thinking both` 轉列，SilentTalk `scripts/dev/train_lora.py` 訓（列標 `thinking` 就用思考格式） | 出貨 `agent-fw1`。基準 `laptop-fw1`／`laptop-fw1-high`（64K）跑中；通用修正在 `integration` 待量 |
| **情境卡**（多輪蒸餾，使用者核准的設計） | `bench/scenarios/families.json`（8 類能力：脈絡、查資料並整理、交付完整、認識自己、自我稽核、工具紀律、該不該查、電腦雜事）→ `scenario_cards.py generate/tasks`（老師出卡；驗收卡主題和訓練卡分開）→ `run.py` 跑卡（`agent_runner.py` 模擬使用者只看回答）→ `scenario_checks.py`（程式檢查）→ `scenario_judge.py validate`（壞對話至少擋 90% 才信）／`judge`（Gemma 評兩次）→ `dataset.py`（每輪一列，只收評審通過的） | 程式在 `integration`，佇列試產 40 張訓練卡、24 張驗收卡 |
| **寫程式的 Agent**（主線） | mini-swe-agent 框架（`bench/mini_runner.py`），SWE-bench Verified 60 題（`bench/swebench_run.py`） | 基準 E4B 4/60。trace-v1 停；等 Qwen3.8 產生軌跡 |
| **機魂資料／台詞** | 筆電寫 → `character_data.py external-check` → `scripts/dev/character_pipeline.sh` → `line_ab.py` 盲評＋`chat_task_eval.py`、`task_scope_eval.py` | 出貨 `machine-spirit-char-v1`（台詞 76/80） |
| **筆電上的 adapter** | 一個 llama-server 兩個 adapter（`--lora-init-without-apply`，請求點名）；EdgeAgent `runtime.AGENT_ADAPTER`／`CHARACTER_ADAPTER` | 不變 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`；`chain.sh` 等舊佇列結束後換上 `queue.next.sh` | 順序：基準 off/high →（換手）`integrate`（主目錄快轉到 `integration`）→ `bench-general`／`-high` → `cards-pilot` → `scen-pilot` → `judge-validate` → `judge-pilot` → `teacher-bench` |

## 3. 接下來

1. **通用修正的判定**：`bench/report.py laptop-fw1 laptop-fw1-general`、`laptop-fw1-high laptop-fw1-general-high`。贏（或持平且 repo 題不再撞「重複 3 次」）就把 EdgeAgent 推上 `copilot-story-mode`（含拆檔與情境卡）；某項變差就只 revert 那一項再量。推之前先 `git fetch`，筆電有新 commit 就 rebase。
2. **試產結果**：評審驗證要 ≥90%；看各類通過率、老師每段對話花多久；VRAM 估值（`teacher-38` 18500＋1500/slot、`judge-gemma` 13000＋2500）照實際改。合理就放大（每類 40～60 張），加上工具題，`dataset.py --thinking both`，訓 `agent-fw2`。
3. **學生的驗收**：驗收卡要讓 E4B 上場、Qwen3.8 扮使用者 → 新設定（學生設定加 `"simulator": "<另一個設定>"`；模擬者用 Qwen3.8 IQ3 才放得下）。fw2 要在驗收卡和 78 題（off 和 high）都贏 fw1 才換 `AGENT_ADAPTER`。
4. **從使用者對話抽卡**：在 `scenario_cards.py` 加入口，Qwen3.8 讀使用者交來的匯出，寫抽象目標的卡（不照抄）。
5. **機魂下一批**：`handoff/tasks/machine-spirit-3`（不套贏的 4 組：被問設定直接答、要選就選、回報照實；加 `scope` 判斷題）。
6. **筆電下一回合**（推 EdgeAgent 之後寫 `handoff/laptop.md`，封存重寫）：Windows 驗拆完的 service／chat、通用修正的實際對話、拆 `browser_check.mjs` 和三個 app 測試、machine-spirit-3。第 6 回合照規則 12 評分（劇本不計分母）。
7. 拆檔子 agent 回報的既有問題（未修）：載入失敗時 `mode` 先變了；租借的 `port` 沒用到；非 Windows 上別人擁有的程序被當成死了。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼前先量，改完再量，變差就退回。修 bug 不用 A/B。
2. **Agent 只在沙盒裡跑**；改了 `sandbox()` 先跑 `--containment`。
3. 題目先過 `--selftest`；比較一律同批題目配對。
4. **Claude 的輸出不當訓練目標、不挑訓練資料**（可以當評審）。訓練資料只來自程式驗收、開源老師（Qwen3.8）、筆電 agent 寫的台詞。考題的 repo 不進訓練。
5. 只有過硬關卡的資料才能訓練；資料檔帶版本戳記，不混版本。
6. GPU、RAM 和別的專案共用（ComfyUI、whisper-api、ace-step），不動它們、不在旁邊擠；吃滿整台機器的東西要使用者同意。
7. 關程序只用確認過擁有者的 PID；不用字串比對。
8. `run.py` 開跑時會把產品程式複製一份固定，但 `agent_runner.py`、`relay.py` 是即時掛載：考場跑的時候不改它們和題目；改產品程式就在 worktree 做。
9. CPU 不要超載。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. 長佇列用 `setsid nohup ... &`；執行中的佇列腳本不改，換新版用 `chain.sh`。同一步連續失敗 3 次佇列會停下並寫原因：那是 bug，修好再重啟。
11. One path：加東西前先問哪一條既有的路負責。
12. 評筆電回合（不給筆電看），每項 0–2：範圍、修法、測試、誠實、使用者互動、隱私、清理、自主、產出。第 5 回合 15/18。
13. 工作檔只寫現況，狀況變了就封存重寫。
14. 開發機不改介面（`edge_agent/web.py`、SilentTalk 設定頁）。

**每次改完要跑：**

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider   # 353 passed, 13 skipped
.venv/bin/ruff check --target-version py312 --select F,E9,I,B silenttalk/copilot scripts tests
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider    # integration：306 passed；5 個平台相關失敗（Windows 指令、連接埠查詢、終端機）
/home/clawd/SilentTalk/.venv/bin/ruff check --target-version py312 --select F,E9,I,B bench/*.py edge_agent/toolbox edge_agent/*.py
```

## 5. 考場細節

- 產品考場：主機只跑模型；容器沒網路、root 唯讀、非 root。設定 `self_model`：老師錄資料時以產品模型的身分介紹自己（bridge 的 `<runtime>` 段，`edge_agent/prompt_sections.mjs`）。
- 情境題：`task.json` 的 `kind` 為 `scenario`，`check` 是 `true`（只驗工作資料夾沒被亂動）；過不過由評審決定（`<run>/verdicts.jsonl`）。模擬使用者預設用 Agent 的同一台伺服器；設定有 `simulator` 時另開一台，掛在 `/simsock`。
- Gemma 4 範本只在最後一則使用者訊息之後顯示思考；Pi 會把前面步驟的思考放進 `reasoning_content` 送回。所以每輪切一列，最後一步的思考從軌跡補回。
- SWE-bench：每題官方映像檔，官方評分。mini 框架的輸出格式和開源軌跡逐字相同。

## 6. 量過的數字

- **產品框架**（E4B、78 題×2）：base 22.4% → v3 36.5% → `agent-fw1` 48.7%（98K 舊設定、思考 off）。64K 的 off／high 基準跑中；off 前 76 題過 28，repo 題的失敗都是撞 64 次工具上限或「重複 3 次」中止。
- **E4B 寫程式**：SWE-bench Verified 60 題 4/60。
- **訓練 32K 列**（`train_lora.py`）：每層嵌入表放 RAM＋`--offload-activations`＋滑動窗注意力分塊 → 31K token 一步 40 秒（原本 105 秒），峰值 14.8 GiB。trace 列平均 2.5 萬 token，16K 內只有 3%。
- **小模型比較**（10/5）：改程式 E4B 12.2%、Qwen3.5-4B 37.8%、9B 31.7%；MCP 工具 E4B 77%、4B 38%、9B 54%；誤導率 E4B 20%、4B 24%、9B 11%。
- **機魂**：char-v1 台詞盲評 76/80、`chat_task` 39/40。
- **筆電**：64K、GPU41 層、雙 adapter 可用；128K 放不下（顯卡加 RAM 不夠）。

## 7. 踩過的雷

- 會必然重現的失敗（例如 OOM）重試沒有用：整晚白轉 7 輪。佇列已改成連續 3 次就停。
- `hf download repo 檔名 --include ...`：有寫檔名時 `--include` 會被忽略。
- `cd a && x &` 整串會在背景子殼跑，後面的指令不在 `a`。
- `--load-mode mlock` 等於不用 mmap；產品用 `mmap`＋`--lazy-mode on`。
- llama-server 開 `--lora-init-without-apply` 時，請求要點名 adapter。
- FlexAttention 在 3090 上 head_dim 256 編不過（共享記憶體不夠）。
- OpenCC `s2twp` 會改已是繁體的詞：只轉含簡體字的文字。`--fit` 會偷偷把模型放到 CPU（考場固定 `--fit off`）。
