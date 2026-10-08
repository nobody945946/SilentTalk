# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-09 凌晨｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`（EdgeAgent 的還沒推，出貨時才推）；規格 v2 已凍結併入（`92a1961`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。**只寫現況和下一步**，經過在 git 歷史和 `archive/`（只在這台機器，不必讀）。上一版：`archive/dev-box-2026-10-09-before-record-v2.md`。

---

## 1. 使用者的決定（現在有效）

- **One path**：每件工作只有一條路（§2）；要加新路先擴充既有那條，比完刪輸的（程式、設定、測試、佇列、文件一起）。同時只有一支佇列。
- **蒸餾**：老師只用 **Qwen3.8-27B**（Q4 出卡＝`teacher-38`，IQ3 錄對話＝`teacher-38-iq3`）；評審 **Gemma 4 31B**（`judge-gemma`）。不用付費 API、不下載別的老師。**Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨關卡的評審**；Claude 只寫程式和規格。使用者的對話只由 Qwen3.8 抽成情境卡。
- **一個模型版本一份凍結規格**（提示＋工具），挑最萬用、最成熟的；原生工具優先。規格 v2 是「不要補，重來」整份重設計：原生工具＋`web_research`／`web_fetch`（網頁、JSON、PDF）＋`search_history`＋`translate_machine`；權限預設 `reversible`（寫入先備份、可還原就自動，`undo.py`）；API 登錄（`apis.py`，金鑰不給模型看）。
- **品質是開發機的事**：使用者不當測試員；沒過關不是終點，診斷、修、下一版，直到筆電上有過關的 Agent 和機魂。改進迴圈由這個 session 驅動：問題由 session 自己發現（§4 第 11 條），不預寫備案腳本。
- **不降規**（2026-10-08）：Agent 的 **64K 是底線**；筆電 64K 已把 4 GB 獨顯用滿。語音不能等 Agent：角色必須在 Agent 工作時照常即時回話。用「降規格、降表現」交差，使用者會叫重來。
- **思考**：Agent 品質優先、可以慢；角色速度優先。思考長度用量的定（§6），不拿差的設定訓練。
- **Discord／權限**：語音每句喊「機魂」；主人 @＝主人的 Agent 串；用說的不能動電腦；刪檔要主人同意（沒回應＝拒絕，最多封存）。不能做的事：模型要懂**而且**程式擋得住。
- **紀錄**：對話只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。使用者親手給的對話匯出放 `archive/`（不 commit）。

## 2. 每件工作的那一條路

| 工作 | 那一條路 | 現況 |
|---|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈，規格 v2。考：`bench/run.py`（63 題×2，`ship_gate.py`）、情境卡驗收、Python 題（`py_tasks.py`）。資料：情境卡＋工具題＋Python 題，老師在框架裡錄，`dataset.py --thinking both`，SilentTalk `train_lora.py` 訓 | 規格 v2 凍結；產品預設思考 high、不設上限；老師預算定 1024（§6）；重錄中（§3） |
| **推論（角色和 Agent 共用一顆模型）** | `edge_agent/inference.py`：租用時兩個槽共用同一個池（`--kv-unified --no-cache-idle-slots --batch-size 512`），角色 0 號、Agent 1 號；用位元組上限記帳，接近滿池才請伺服器數 token；Agent 永遠拿得到整個池（需要時清角色的快取）；角色開口時 Agent 的新請求先等，還在讀提示的請求被切斷（等 1.2 秒讓 llama-server 看到）後重送 | 已併入；開發機和筆電都量過（§6）：兩邊共用一個 adapter 才成立 |
| **adapter** | 現在兩個（`agent-fw1`、`machine-spirit-char-v1`）。不同 adapter 不能同批算，角色得等 Agent 整個請求 → 重錄後同一份資料訓兩個：`agent-fw3`（只有 Agent）和 `machine-spirit-fw3`（Agent＋角色合一） | 合一版要在 Agent 關卡（對 `agent-fw3`）和角色關卡（台詞盲評對 `char-v1`、`chat_task`）都不輸才出貨 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py`（`recheck` 用當天的規則淘汰：API 卡要和文件一致、規定不能要求角色語氣或「不准簡體」）→ `run.py` → `scenario_checks.py` → `scenario_judge.py`（Gemma 48K；條件沒發生的「若…」規定算通過；先單獨判「每輪最後的回答有沒有回應那則訊息、話有沒有講完」，過了才逐條判卡片規定兩次；工具呼叫和結果各給到 8,000 字；驗證只算它放行的原對話，壞對話＝最後一則斷在句中／換成別卡的／全部換掉，至少放行 10 段、擋 ≥90%）→ `dataset.py`（被思考預算截斷的思考不當目標） | `cards` 步已淘汰訓練 20、驗收 5 張，正在補卡（訓練 G、J 到 30；驗收 D、G 到 10、J 到 11，含使用者的 J-o003）。驗收輪一律用錄製時驗證過的評審（同一把尺） |
| **角色台詞關卡** | SilentTalk `line_ab.py lines --against char-v1` → EdgeAgent `bench/pair_judge.py`（Gemma 31B，A/B 對調判兩次，先用壞台詞驗證）→ `line_ab.py score`；`chat_task_eval.py` | 新寫，第一次用在合一版 |
| **寫程式的 Agent** | mini-swe-agent（`bench/mini_runner.py`），SWE-bench Verified 60 題 | 老師 36/60、E4B 4/60 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`（一步一個 `.done`；失敗就停下、印一行讓 session 醒來診斷，修好再 `relaunch.sh`；只有顯存被搶回 3 會自己等）。插空檔量測：停佇列本身，等鎖放開跑完再 `relaunch.sh` | 重錄 v2（§3 第 1 項），2026-10-09 02:41 從 `cards` 開始 |

## 3. 接下來

1. **重錄 v2**（佇列正在跑）：`cards`（淘汰→補卡→檔案→任務資料夾）→ `py-train-top`、`py-eval-top`（Python 題補寫到 240、60 題；現在 159、38 題過自檢）→ 老師 `teacher-38-iq3`（預算 1024、每輪 30 分鐘）錄情境卡、工具題、Python 題 → 評審 → 轉列 → 訓 `agent-fw3` 和 `machine-spirit-fw3`（同一份資料）→ 兩者各自考（off／high／卡／Python）→ 角色關卡 → `gate-fw3`、`gate-ms3`（對筆電現在跑的，使用者的規則）、`gate-*-vs-v2f`（對凍結規格上的基底：adapter 不能輸給只換規格）、`gate-ms3-vs-fw3`。每次醒來看那一步的數字：補了幾張卡、幾題過自檢、評審有沒有過驗證、轉出幾列、為什麼丟。
2. **出貨**：`ms3` 過全部關卡就出合一 adapter（角色才能在 Agent 工作時開口）；只有 `fw3` 過時，先診斷 `ms3` 輸在哪、修了再訓，不拿兩個 adapter 出貨。出貨時才推 EdgeAgent 的 `copilot-story-mode`，把筆電工作檔改成出貨回合：v2 部署（會裝 PowerShell 7.6.6，`deploy.install_powershell`，要確認 Agent 的指令真的由 `pwsh.exe` 執行）、介面（`reversible` 選項、還原按鈕、API 登錄頁）、Discord 實測。筆電現在待命。
3. 之後：coding agent（Qwen3.8 軌跡）。

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
10. 工作檔只寫現況，狀況變了就封存重寫。筆電會自己 fetch：SilentTalk `copilot-story-mode` 的 `laptop.md` 一改就 pull 來做，而它的額度少（使用者 2026-10-09）。交辦一回合＝整份重寫一次 `laptop.md`（不要一改再改），開發機那邊真的準備好（驗過、CI 綠）才推；commit 可以先留在本機，有真實進展的階段才 push。
11. **push 完要等 GitHub CI 的結果**（`gh run watch <id> --exit-status`；EdgeAgent 是 Windows 上的 ruff＋pytest），紅的就修到綠才算完成。本機的檢查要和 CI 同一個指令。問題要由 session 自己發現，不能等使用者看到（使用者 2026-10-09）：喚醒腳本盯佇列的每個步驟事件和錯誤、每一步的產出比例（每一步都要印出留下和丟掉的數量）、兩個 repo 的 CI、筆電的新回報，兩小時沒動靜也叫醒；醒來先看資料、找出錯在檢查、資料、程式還是模型，修好、重排受影響的步驟，再掛回去。不要盲目重試，也不要預先寫好的備案（2026-10-08：EdgeAgent 的 CI 紅了 41 次是使用者先看到的；10-09：Python 題被丟 56% 是醒來後才查到的）。

**每次改完要跑：**

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider
cd /home/clawd/EdgeAgent && .venv/bin/python -m ruff check edge_agent tests   # 和 CI 同一個指令（ruff 釘在 0.16.10）
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider   # 405 passed；4 個只在 Windows 過（行程、終端機、搜尋工具）
# 其他 worktree 一樣兩行，加 PYTHONPATH=.（用 EdgeAgent 的 .venv，SilentTalk 的 ruff 是別的版本）。
# 新的 worktree 先把 .runtime/node、pi、pwsh 連到主工作區的，不然 PowerShell 的測試全失敗
# Windows 編碼（CI 在 Windows 上預設 cp1252）：在 ASCII 語系下跑，失敗的測試清單要和上一個 CI 綠的 commit 一樣；
# 多出來的就是 Windows 會壞的（讀寫檔案、子程序輸出沒寫 UTF-8）。原本就有的（中文檔名之類）Windows 不受影響。
env PYTHONPATH=. LC_ALL=C LANG=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0 PYTHONIOENCODING= \
  /home/clawd/EdgeAgent/.venv/bin/python -m pytest -q -p no:cacheprovider -rf | rg '^FAILED' | sed 's/ - .*//' | sort
```

## 5. 考場細節

- 產品考場：主機只跑模型；容器沒網路、root 唯讀、非 root。`self_model`：老師錄資料時以產品模型的身分介紹自己；硬體寫筆電的，沙盒裡的 Windows 指令（`Get-CimInstance`、`nvidia-smi`、`systeminfo`…）回每張卡那台筆電的數值（`bench/laptop.py`），`BENCH_SPEC` 讀完就移出 Agent 的環境。
- 情境題：`kind` 為 `scenario`，過不過由評審決定（`<run>/verdicts.jsonl`）。
- Gemma 4 範本只在最後一則使用者訊息之後顯示思考；每輪切一列，最後一步的思考從軌跡補回。
- llama-server（b11193）：每步從 0 號槽開始填批次；不同 LoRA 的槽不能同批（排前面的先做完）；串流請求立刻送標頭和空的第一塊；客戶端斷線要等「所有槽都 1 秒沒結果」才發現，取消在下一步生效；共用池子預設在任何槽開工時清空閒置的槽（要 `--no-cache-idle-slots`）；Gemma 的滑動窗快取回退要靠檢查點，找不到就整段重算。

## 6. 量過的數字

- **規格**（基底 E4B、63 題×2）：舊規格（筆電現在）off 66、high 86；v2c off 64、high 89。思考上限 512：83；1024：85；不設上限 89，平均時間反而最短（21.2 秒）。
- **雙管路**（開發機 3090、64K、兩槽一池）：第二個槽只多 10.6 MiB（滑動窗快取），全域快取 544 MiB 共用。Agent 生成時角色開口：同一個 adapter 0.8 秒，兩個 adapter 12.7 秒（等 Agent 生完）；Agent 讀 36K 提示時：改前 19.6 秒。每步 512 token 不影響讀提示速度（18.84 對 18.78 秒）。CPU 驗證（切斷＋保留閒置槽）：角色沿用快取只新算 16 token，Agent 重送沿用已讀的 1,025 token；沒有 `--no-cache-idle-slots` 時角色每次 Agent 動過就整段重算（1,180 對 35）。
- **雙管路（筆電 3050 Ti，2026-10-09，64K、41 層在顯卡）**：雙槽比單槽多約 62 MiB，共用記憶體固定 176 MiB，可用 RAM 只剩 200–290 MiB。Agent 生成時角色開口：兩個不同 adapter（角色 LoRA 對 Agent 不掛）30 秒逾時（502），共用角色 adapter 0.62 秒；Agent 讀長提示時角色 3–4 秒；Agent 用滿 65,024 token 的視窗兩組都成功，之後角色 2.4 秒。
- **筆電**：64K、GPU41 層時剩 398 MiB 顯存、可用 RAM 約 478 MiB；角色短句 12.7 token/s、Agent 22.5 token/s。
- **老師**：SWE-bench Verified 60 題 36/60（IQ3、預算 1024）；E4B 4/60。
- **老師預算**（規格 v2、每輪 15 分鐘，同一個評審重評，兩輪都過驗證：擋 34/36、30/33）：35 張卡（排除淘汰的 5 張）評審通過 1024 12、4096 9；兩邊都正常結束的 26 張 11 對 8；正常結束 30 對 27；總時間 5.8 對 8.1 小時；思考卡在預算 22% 對 9%、最長一成 3876 對 12682 字。Python 40 題 34 對 35，中位 131 對 227 秒、逾時 1 對 4。→ 錄製用 1024。逾時的大多是長工作不是打轉（使用者的 H 卡一次寫 8–15K 字），所以錄製每輪 30 分鐘。
- **機魂**：char-v1 台詞贏基底 76/80、`chat_task` 39/40。
- **訓練 32K 列**：31K token 一步 40 秒，峰值 14.8 GiB。

## 7. 踩過的雷

- 會必然重現的失敗重試沒用：佇列失敗就停，由 session 診斷。老師常把檔案包在 Markdown 程式碼框裡（`py_tasks.unfenced`）。
- 試錄抓到的：執行環境段的作業系統原本用 node 自己的平台（沙盒是 Linux），D 類回答因此被擋；「同一呼叫重複」把改完重跑測試也算錯；`Get-Process -Id`（查自己開的程式）被當成讀機器；評審驗證只改最後一則，多輪對話的規定多半在檢查過程，改壞的仍可能全部符合；llama.cpp 思考預算用完是硬切（現在用 `--reasoning-budget-message` 標記）。
- 評審看不到的東西會當成沒發生：工具結果原本只給 700 字、呼叫參數 300 字（寫進檔案的內容）。卡片的規定由正規式擋時，`must` 和 `must_not` 都要擋；卡片轉繁體會把「不要寫成簡體 X」的例子轉成同一個字。
- 先前「合一 adapter 讓 Agent 變差」（44.2% 對 48.7%）混了資料版本（fw2 對 fw1），不是乾淨比較；這次同資料比。
- `--fit` 會偷偷把模型放到 CPU（考場固定 `--fit off`）。OpenCC `s2twp` 會改已是繁體的詞：只轉含簡體字的文字。
- `cd a && x &` 整串會在背景子殼跑。開發機試跑要走筆電的實際路徑（已部署安裝、`deployment.json`），第 8 回合就是試跑沒走到的路徑壞掉。`hf download repo 檔名 --include` 會忽略 include。
