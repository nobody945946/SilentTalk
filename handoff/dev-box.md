# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-08 深夜｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`；規格 v2 在 EdgeAgent 分支 `spec-v2`（worktree `/home/clawd/worktrees/ea-spec2`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。**只寫現況和下一步**，經過在 git 歷史和 `archive/`（只在這台機器，不必讀）。上一版：`archive/dev-box-2026-10-08-v21-before-teacher-pilot.md`。

---

## 1. 使用者的決定（現在有效）

- **One path**：每件工作只有一條路（§2）；要加新路先擴充既有那條，比完刪輸的（程式、設定、測試、佇列、文件一起）。同時只有一支佇列。
- **蒸餾**：老師只用 **Qwen3.8-27B**（Q4 出卡＝`teacher-38`，IQ3 錄對話＝`teacher-38-iq3`）；評審 **Gemma 4 31B**（`judge-gemma`）。不用付費 API、不下載別的老師。**Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨關卡的評審**；Claude 只寫程式和規格。使用者的對話只由 Qwen3.8 抽成情境卡。
- **一個模型版本一份凍結規格**（提示＋工具），挑最萬用、最成熟的；原生工具優先。規格 v2 是「不要補，重來」整份重設計：原生工具＋`web_research`／`web_fetch`（網頁、JSON、PDF）＋`search_history`＋`translate_machine`；權限預設 `reversible`（寫入先備份、可還原就自動，`undo.py`）；API 登錄（`apis.py`，金鑰不給模型看）。
- **品質是開發機的事**：使用者不當測試員；沒過關不是終點，診斷、修、下一版，直到筆電上有過關的 Agent 和機魂。改進迴圈由這個 session 驅動：佇列事件和兩小時沒動靜叫醒 session 判斷，不預寫備案腳本。
- **不降規**（2026-10-08）：Agent 的 **64K 是底線**；筆電 64K 已把 4 GB 獨顯用滿。語音不能等 Agent：角色必須在 Agent 工作時照常即時回話。用「降規格、降表現」交差，使用者會叫重來。
- **思考**：Agent 品質優先、可以慢；角色速度優先。思考長度用量的定（§6），不拿差的設定訓練。
- **Discord／權限**：語音每句喊「機魂」；主人 @＝主人的 Agent 串；用說的不能動電腦；刪檔要主人同意（沒回應＝拒絕，最多封存）。不能做的事：模型要懂**而且**程式擋得住。
- **紀錄**：對話只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。使用者親手給的對話匯出放 `archive/`（不 commit）。

## 2. 每件工作的那一條路

| 工作 | 那一條路 | 現況 |
|---|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈，規格 v2。考：`bench/run.py`（63 題×2，`ship_gate.py`）、情境卡驗收、Python 題（`py_tasks.py`）。資料：情境卡＋工具題＋Python 題，老師在框架裡錄，`dataset.py --thinking both`，SilentTalk `train_lora.py` 訓 | v2c 提示＋執行環境段寫筆電的作業系統（`e76787c`）；產品預設思考 high、不設上限；老師預算比較中（§3），比完凍結、併入、重錄 |
| **推論（角色和 Agent 共用一顆模型）** | `edge_agent/inference.py`：租用時兩個槽共用同一個池（`--kv-unified --no-cache-idle-slots --batch-size 512`），角色 0 號、Agent 1 號；用位元組上限記帳，接近滿池才請伺服器數 token；Agent 永遠拿得到整個池（需要時清角色的快取）；角色開口時 Agent 的新請求先等，還在讀提示的請求被切斷（等 1.2 秒讓 llama-server 看到）後重送 | `spec-v2`（已推）；開發機 CPU／GPU 驗過（§6）；**筆電第 8 回合實測**（`tests/lanes_check.py`，釘在 `9b173ff`） |
| **adapter** | 現在兩個（`agent-fw1`、`machine-spirit-char-v1`）。不同 adapter 不能同批算，角色得等 Agent 整個請求 → 重錄後同一份資料訓兩個：`agent-fw3`（只有 Agent）和 `machine-spirit-fw3`（Agent＋角色合一） | 合一版要在 Agent 關卡（對 `agent-fw3`）和角色關卡（台詞盲評對 `char-v1`、`chat_task`）都不輸才出貨 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py` → `run.py` → `scenario_checks.py` → `scenario_judge.py`（Gemma；每張卡多一條「每則回答都完整回應當時那則訊息」；驗證只算它放行的原對話，壞對話＝最後一則斷句／換成別卡的／全部換掉，至少放行 10 段、擋 ≥90%）→ `dataset.py`（被思考預算截斷的思考不當目標） | 訓練 317 張、驗收 91 張（含使用者對話 21 張）。驗收輪一律用錄製時驗證過的評審（同一把尺） |
| **角色台詞關卡** | SilentTalk `line_ab.py lines --against char-v1` → EdgeAgent `bench/pair_judge.py`（Gemma 31B，A/B 對調判兩次，先用壞台詞驗證）→ `line_ab.py score`；`chat_task_eval.py` | 新寫，第一次用在合一版 |
| **寫程式的 Agent** | mini-swe-agent（`bench/mini_runner.py`），SWE-bench Verified 60 題 | 老師 36/60、E4B 4/60 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`（一步一個 `.done`；連錯 3 次停；顯存被搶回 3 不算失敗）。插空檔量測：停佇列本身，等鎖放開跑完再 `relaunch.sh` | 老師 4096 錄卡中 → 空檔腳本（session scratchpad `between5.sh`：新評審重評 1024、`lanes_check` 試跑）→ `relaunch` → 評 4096 → `py-eval`／`py-train` → 老師 1024／4096 Python 題 |

## 3. 接下來

1. **老師預算**：同 40 張卡、40 題 Python，`teacher-38-iq3` 1024 對 4096。兩輪都用新評審評完再比：評審通過率、思考被截斷的比例、時間；也要想到學生會學老師的思考長度（筆電每秒約 22 token）。寫程式考慮多錄幾次留過的。
2. **錄製的每輪時間**：老師設定的 `time_scale` 0.5（每輪 15 分鐘）會切掉大任務：1024 輪 7/40 逾時，使用者自己的卡 4 張逾時 3 張（例：俄羅斯方塊一步寫 1.4 萬字，光生成 352 秒）。錄製前調大（比較期間兩邊同為 0.5，不動）。
3. **凍結規格 v2**：`spec-v2` 併入 `copilot-story-mode`。之後只修模型看不到的 bug。
4. **重錄**（草稿 `EdgeAgent/.runtime/fw/record-v2.draft.sh`）：情境卡、工具題、Python 題 → 評審 → 轉列 → 訓 `agent-fw3` 和 `machine-spirit-fw3` → 兩者各自考（off／high／卡／Python）→ 角色關卡 → `gate-fw3`、`gate-ms3`、`gate-ms3-vs-fw3`。
5. **筆電**：雙管路實測（`tests/lanes_check.py`）的結果決定推論設計是否成立；出貨回合再做 v2 部署、介面（`reversible` 選項、還原按鈕、API 登錄頁）。
6. 之後：沙盒的 Windows 外觀（Linux 版 PowerShell 沒有的 `Get-CimInstance`、`Get-PhysicalDisk`、`nvidia-smi` 等回筆電的數值，CPU、溫度、磁碟每張卡隨機），只重錄電腦雜事卡（例 F-019 查 C 槽是不是 NVMe）。現在讀機器的對話一律不當資料（8/40，多數本來就是老師做錯）。
7. 之後：coding agent（Qwen3.8 軌跡）。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼前先量，改完再量，變差就退回。修 bug 不用 A/B。
2. **Agent 只在沙盒裡跑**；改了 `sandbox()` 先跑 `--containment`。
3. 題目先過 `--selftest`；比較一律同批題目配對。
4. 只有過硬關卡的資料才能訓練；資料檔帶版本戳記，不混版本。
5. GPU、RAM 和別的專案共用（ComfyUI、whisper-api），不動它們；吃滿整台機器、大下載要使用者同意。
6. 關程序只用確認過的 PID；不用字串比對。
7. `run.py` 開跑時複製產品程式；`agent_runner.py`、`relay.py` 是即時掛載，考試中不改。改產品程式在 worktree 做。
8. 執行中的佇列腳本不改：先用 PID 停佇列本身（正在跑的那步會跑完並抓著鎖），再用 `relaunch.sh` 接手。
9. 開發機不改介面（`edge_agent/web.py`、SilentTalk 設定頁）。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. 工作檔只寫現況，狀況變了就封存重寫。

**每次改完要跑：**

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider
cd /home/clawd/worktrees/ea-spec2 && /home/clawd/EdgeAgent/.venv/bin/python -m pytest -q -p no:cacheprovider   # 385 passed；4 個只在 Windows 過（行程、終端機、搜尋工具）
/home/clawd/SilentTalk/.venv/bin/ruff check --target-version py312 --select F,E9,I,B edge_agent/*.py bench/*.py
```

## 5. 考場細節

- 產品考場：主機只跑模型；容器沒網路、root 唯讀、非 root。`self_model`：老師錄資料時以產品模型的身分介紹自己；硬體寫筆電的（`run.LAPTOP_HARDWARE`）。
- 情境題：`kind` 為 `scenario`，過不過由評審決定（`<run>/verdicts.jsonl`）。
- Gemma 4 範本只在最後一則使用者訊息之後顯示思考；每輪切一列，最後一步的思考從軌跡補回。
- llama-server（b11193）：每步從 0 號槽開始填批次；不同 LoRA 的槽不能同批（排前面的先做完）；串流請求立刻送標頭和空的第一塊；客戶端斷線要等「所有槽都 1 秒沒結果」才發現，取消在下一步生效；共用池子預設在任何槽開工時清空閒置的槽（要 `--no-cache-idle-slots`）；Gemma 的滑動窗快取回退要靠檢查點，找不到就整段重算。

## 6. 量過的數字

- **規格**（基底 E4B、63 題×2）：舊規格（筆電現在）off 66、high 86；v2c off 64、high 89。思考上限 512：83；1024：85；不設上限 89，平均時間反而最短（21.2 秒）。
- **雙管路**（開發機 3090、64K、兩槽一池）：第二個槽只多 10.6 MiB（滑動窗快取），全域快取 544 MiB 共用。Agent 生成時角色開口：同一個 adapter 0.8 秒，兩個 adapter 12.7 秒（等 Agent 生完）；Agent 讀 36K 提示時：改前 19.6 秒。每步 512 token 不影響讀提示速度（18.84 對 18.78 秒）。CPU 驗證（切斷＋保留閒置槽）：角色沿用快取只新算 16 token，Agent 重送沿用已讀的 1,025 token；沒有 `--no-cache-idle-slots` 時角色每次 Agent 動過就整段重算（1,180 對 35）。
- **筆電**：64K、GPU41 層時剩 398 MiB 顯存、可用 RAM 約 478 MiB；角色短句 12.7 token/s、Agent 22.5 token/s。
- **老師**：SWE-bench Verified 60 題 36/60（IQ3、預算 1024）；E4B 4/60。
- **老師試錄 40 張卡**（規格 v2、預算 1024、每輪 15 分鐘，2 小時 8 分）：修正檢查後 23/40 過程式檢查（讀機器 8、逾時 7、同一網址重抓 3、沒附來源 1）；舊評審驗證沒過（壞對話只擋 75%）。思考 21% 卡在預算、斷在半句。預算 4096：同卡慢 2–2.3 倍，每步思考 2–3 倍長。
- **機魂**：char-v1 台詞贏基底 76/80、`chat_task` 39/40。
- **訓練 32K 列**：31K token 一步 40 秒，峰值 14.8 GiB。

## 7. 踩過的雷

- 會必然重現的失敗重試沒用；佇列連續 3 次就停。
- 試錄抓到的：執行環境段的作業系統原本用 node 自己的平台（沙盒是 Linux），D 類回答因此被擋；「同一呼叫重複」把改完重跑測試也算錯；`Get-Process -Id`（查自己開的程式）被當成讀機器；評審驗證只改最後一則，多輪對話的規定多半在檢查過程，改壞的仍可能全部符合；llama.cpp 思考預算用完是硬切（現在用 `--reasoning-budget-message` 標記）。
- 先前「合一 adapter 讓 Agent 變差」（44.2% 對 48.7%）混了資料版本（fw2 對 fw1），不是乾淨比較；這次同資料比。
- `--fit` 會偷偷把模型放到 CPU（考場固定 `--fit off`）。OpenCC `s2twp` 會改已是繁體的詞：只轉含簡體字的文字。
- `cd a && x &` 整串會在背景子殼跑。`hf download repo 檔名 --include` 會忽略 include。
