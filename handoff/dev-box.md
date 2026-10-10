# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-10 下午｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`，commit 先留本機，出貨時才推；規格 v2 已凍結（`92a1961`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事，**只寫現況和下一步**。上一版：`archive/dev-box-2026-10-10-before-fixes-started.md`（只在這台機器，不必讀）。

---

## 1. 使用者的決定（現在有效）

- **One path：** 每件工作只有一條路（§2）。要加新路先擴充既有那條；比完刪掉輸的，程式、設定、測試、佇列、文件一起刪。同時只有一支佇列。**有原生的就用原生的**（SDK 本來就有的機制、工具），不另立名目。
- **蒸餾：** 老師只用 Qwen3.8-27B（Q4 出卡 `teacher-38`，IQ3 錄對話 `teacher-38-iq3`）；評審 Gemma 4 31B（`judge-gemma`）。不用付費 API、不下載別的老師。Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨評審。使用者的對話只由 Qwen3.8 抽成情境卡。
- **一個模型版本一份凍結規格（提示＋工具）：** v2 是原生工具加 `web_research`／`web_fetch`、`search_history`、`translate_machine`；權限預設 `reversible`；API 登錄（金鑰不給模型看）。工具定義凍結，實作可以改得更穩。規格變動集中到下一版（§3 第 5 點）。
- **品質是開發機的事：** 使用者不當測試員。沒過關要診斷、修好、出下一版。被資料關卡擋掉的失敗還是產品的問題，要在真實路徑上量、修在產品。
- **從自己的錯學：** 部署的模型不夠力，就讓學生先做，沒過的由老師在同一個情境示範做對，加上「學生錯的、老師對的」成對訓練。使用者願意等。
- **要贏過原版：** 訓練好的 Agent 要贏過原本的基底，每個模型都用它自己較好的溫度比，誰都不冤枉；Python 題也要看。工具題、MCP 題各自不能輸（之後的外掛靠它們；`ship_gate.py` 第 4 條）。
- **長期記憶用原生 `AGENTS.md`：** 全域那份在 EdgeAgent 的 `.runtime/pi-state/AGENTS.md`（Pi 的 agentDir），加上專案資料夾裡的。主人說「記住…」，Agent 用 `edit` 寫進全域那份。它和 `personas.json` 一樣屬於使用者：不受紀錄資料夾限制，回報不寫內容。
- **不降規：** Agent 的 64K 是底線；角色在 Agent 工作時照常即時回話。Agent 品質優先、可以慢；角色速度優先。
- **Discord／權限：** 語音每句喊「機魂」；用說的不能動電腦；刪檔要主人同意。不能做的事兩層都擋：模型懂，程式也擋。
- **紀錄：** 對話只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。
- **接力只在必要節點：** 不准有常駐迴圈、心跳、定時輪詢、log 垃圾（§4 第 10 條）。筆電額度少：一回合＝整份重寫一次 `laptop.md`；有真實進展才 push。

## 2. 每件工作的那一條路

| 工作 | 那一條路 |
|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈＋規格 v2。考試 `bench/run.py`（63 題×2，`ship_gate.py`）、情境卡驗收、Python 題。資料：老師在框架裡錄 → `dataset.py --thinking both` → SilentTalk `train_lora.py` |
| **取樣** | 橋接器（`agent_bridge.mjs`）是 owner。最佳溫度隨模型和模式不同（§3 第 1 點），所以出貨時要做成「每個 adapter 帶自己 off／high 的取樣」，基底 0.2／0.2。分支 `model-sampling`（worktree `ea-sample`）ce8810a 寫死的是 fw3 的規則（high 0.2、off 照模型檔），出貨前照實際出貨的 adapter 改寫；`ea-t1`（04c3885）是兩種都照模型檔的考試用產品 |
| **網頁工具** | `edge_agent/web_tools.mjs`（錯誤講原因；空殼頁交給本機無頭瀏覽器；meta refresh、Big5）。量測 `bench/web_live.mjs`：開發機 27/30、6/6 搜尋 |
| **推論** | `edge_agent/inference.py`：兩槽一池，角色 0 號、Agent 1 號，角色開口時 Agent 讓路；共用一個 adapter 才成立（§6） |
| **adapter** | 同一份資料訓兩個：`agent-fw3`（只有 Agent）、`machine-spirit-fw3`（Agent＋角色）；合一版在 Agent 和角色關卡都不輸才出 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py`（`recheck` 淘汰）→ `run.py` → `scenario_checks.py` → `scenario_judge.py`（先驗證自己）→ `dataset.py`。訓練 314、驗收 91 |
| **Python 題** | `py_tasks.py generate/validate`。訓練 210、驗收 57 |
| **角色台詞** | `line_ab.py` → `bench/pair_judge.py`（Gemma，對調判兩次）→ `line_ab.py score`；`chat_task_eval.py` |
| **寫程式的 Agent** | mini-swe-agent，SWE-bench Verified 60 題：老師 36、E4B 4 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`：一步一個 `.done`；失敗就停下印一行，修好再 `relaunch.sh`；顯存被搶（回 3）才自己等 |

## 3. 接下來

1. **這一輪的結果（不出貨）：**
   - 資料 881 列（情境 101/314、工具 127/152、Python 171/210）。`agent-fw3` 驗證誤差 0.62；`machine-spirit-fw3` 0.904 → 0.918。
   - **126 次的成績（溫度 0.2／1.0，同設定重考差 3–4 分）：**

     | | off | high |
     |---|---|---|
     | 基底 | **64、60**／57 | **89、86**／77 |
     | fw3 | 73／**79** | **82**／73 |
     | ms3 | **73**／73 | 70／**77** |

     粗體是各自較好的溫度。ms3 off 平手取 0.2（聊天題全過、MCP 22），但 0.2 被重複上限停 33 次、程式 0/14。
   - **最佳對最佳：** off 兩個都贏基底（79、73 對 60–64）；high 都輸（82、77 對 86–89），MCP high 都輸（20、19 對 24）。兩條硬規則已輸，關卡不跑。
   - **要優化的是合一版**（產品的形狀）和它的資料。輸在 high、MCP、雜事、查資料、陷阱；贏在 off、工具、權限。
2. **弱點和修法（進行中）：**
   - **high 弱＝老師的思考被篩短：** 錄製預算 1024 切斷了情境 25%、工具 9%、Python 15% 的思考（被切的中位 3,575 字，留下的 797 字）；被切的列不帶思考訓練，所以學生只學到短的，每步只想基底的一半（310 對 610–750 字）。
     - 今晚實驗（佇列尾端）：`machine-spirit-fw3n`，同樣 595 段對話完全不帶思考（`dataset.py --thinking none`，a1d9280），考 off／high × 兩種溫度。
     - v3 錄製：老師預算放寬到幾乎不切（切斷率 <2%），思考長度至少和基底一樣；先試錄 30 張卡挑預算（錄製約慢 3 倍，使用者接受）。之後「完整長思考」對「不帶思考」各練一版，留贏的。
   - **MCP：** 子代理在 worktree `ea-mcp`（分支 `mcp-variety`，從 `next-world`）做 6–8 個假 MCP 伺服器（不同領域、參數名、必填、錯誤訊息點名參數），訓練題和考試題；回來後審 diff、跑 selftest 和全部測試再合併。
   - **聊天會動工具：** Agent 的訓練資料沒有任何純聊天（考試的聊天題在訓練裡沒對應）；角色台詞資料不帶工具。v3 加 Agent 情境下的純聊天題（和考試題不同），老師錄。
   - **雜事：** 評分都對，是模型真的做錯；三題評分遇到格式錯的答案會崩潰，已改成說清楚（`next-world` 2b3eed1）。
   - **重複鬼打牆：** 每個 adapter 帶自己的取樣（§2）；剩下的交給「從自己的錯學」。
3. **佇列：** 情境卡、Python（基底 0.2、ms3 1.0）、ms3 角色台詞 → 訓練 `machine-spirit-fw3n` → 它的四場考試。預計清晨跑完。
4. **筆電：** 第 10 回合已審；這一輪不出貨，下一回合等有 adapter 過關再排。
5. **出貨（有 adapter 過全部關卡時）：** 優先合一版。取樣做成每個 adapter 帶自己的（§2）。合併 `model-sampling`、`next-world` 進 `copilot-story-mode`，跑完整測試，推 EdgeAgent，等 CI 綠。整份重寫 `laptop.md`：
   - PowerShell 7.6.6 部署，確認 Agent 指令由 `pwsh.exe` 執行；介面：`reversible`、還原、API 登錄頁；Discord 實測；
   - 網頁實測：`node bench/web_live.mjs` 和開發機比，Edge 無頭讀頁，記下秒數、角色回話延遲、可用 RAM；
   - 唯讀查本機：「記憶體多大」「C 碟還剩多少」要答出實數；`Get-CimInstance Win32_Process`、`Get-Process | Format-List *`、`... CommandLine`、`Write-Output C:\Users | Get-ChildItem` 要被擋；唯讀算資料要用 `Group-Object` 算出來；
   - Windows 上要過 `test_real_sdk_stops_fetching_the_same_dead_address`、`tests/test_lingua_powershell.py`。
6. **EdgeAgent `next-world`（worktree `ea-web`，都有測試）：** 這一輪考試跑完才合併。
   - **產品：** 唯讀任務可讀本機（只認 Windows 內建模組，`Get-CimInstance` 只准固定類別），可在讀到的東西上計算；補兩個漏洞（管線傳路徑給 `Get-ChildItem`、`Get-Process` 的 `CommandLine`）。
   - **測試環境：** 假 API 照真的回應；工作區多出 100 MB 判 `bloat`；假無人機有狀態、起飛前解鎖不算多餘；記憶體題對 8 GB；工具題出題錯修好；C 組淘汰「禁止重貼整張表」的卡；三題雜事評分不再崩潰；沙盒的 `Get-Process`、`Get-PSDrive`、`Get-ComputerInfo` 是 `Microsoft.PowerShell.Management` 自己的 cmdlet（`bench/pshome`），回筆電的程序和磁碟。
7. **下一版規格 v3（一起決定、一起錄、一起訓）：** 上面第 2 點的思考、MCP、純聊天，加上：
   - **記憶（§1）：** 提示詞（`edge_agent/prompt_sections.mjs`）拿掉「你沒有跨對話的記憶」，改成長期的交代在 `AGENTS.md`、主人說記住就寫進全域那份。v2 已經會讀 `AGENTS.md`（Pi 預設），但考場從沒有過：加有 `AGENTS.md` 的題目、「記住」的題目和檢查。
   - **取樣：** 每個新 adapter 考 off／high 各兩種溫度，取較好的寫進 adapter 的設定。
   - **第一輪「從自己的錯學」：** 學生是合一版，在它的最佳溫度、在訓練卡和訓練題上收集失敗（考試的卡和題不碰）。
   - **錄製前：** 假網路讓每個網域都解析得到、卡片網頁用原本的 https 網址、沒有的頁面回 404；`$PSVersionTable`、`[Environment]` 換不了，查本機檢查改看工具輸出有沒有 Linux 字樣；C 組 `recheck` 再 `generate`。
8. **之後：** coding agent（Qwen3.8 軌跡；E4B 在 SWE-bench 4/60 對老師 36/60，是蒸餾補不滿的天花板）；清掉不用的 worktree（`ea-laptop`、`ea-spec2`、`ea-freeze`；`ea-web`、`ea-sample`、`ea-t1`、`ea-mcp` 合併或用完後）。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼前先量，改完再量，變差就退回。修 bug 不用 A/B。取樣、上限這類設定每個模型、每個模式各自量。
2. **Agent 只在沙盒裡跑。** 改了 `sandbox()` 或 `code_mounts()` 先跑 `--containment`。
3. 題目先過 `--selftest`；比較一律用同一批題目配對。
4. 只有過硬關卡的資料才能訓練。資料檔帶版本戳記，不混版本。
5. **共用機器：** GPU、RAM 和 ComfyUI、whisper-api 共用，不動它們。吃滿整台機器、大下載先問使用者。考試進行中不要另外對考場的模型伺服器發請求（會拖慢考生、造成逾時）。
6. 關程序只用確認過的 PID，不用字串比對。
7. **考試中別動：** `agent_runner.py`、`relay.py`、`bench/web_fixture.py`、`bench/grade.py` 是即時掛載。改產品程式在 worktree 做。
8. **執行中的佇列腳本不改：** 新檔 `mv` 蓋過去，用 PID 停佇列本身（不停 `run.py`），再背景跑 `relaunch.sh >> queue.log`。
9. **開發機不改介面**（`edge_agent/web.py`、SilentTalk 設定頁）。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. **喚醒只在必要節點：** `scripts/dev/wake.sh` 在背景跑，醒來先重新掛上再處理。佇列 log 用核心的檔案通知；一小時 log 沒長是 SILENCE，兩小時到時還在長是 ALIVE。push 完 `wake.sh ci <repo> <sha>`；交辦筆電後 `wake.sh handoff <小時>`。什麼都沒在等就不掛。醒來先看資料，判斷錯在檢查、資料、程式還是模型；不盲目重試、不預寫備案。push 完要等 CI 綠才算完成。

**每次改完要跑**（看 pytest 自己的 exit code）：

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider
cd /home/clawd/EdgeAgent && .venv/bin/python -m ruff check edge_agent tests   # 和 CI 同一個指令
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider   # 4 個只在 Windows 過：test_processes 1、test_sdk_permissions 1、test_terminal 2
# worktree：加 PYTHONPATH=.，用 EdgeAgent 的 .venv；先把 .runtime/node、pi 連到主工作區。
# Windows 編碼：在 ASCII 語系下跑（LC_ALL=C LANG=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0 PYTHONIOENCODING=），失敗清單要和上一個 CI 綠的一樣。
```

## 5. 考場細節

- **沙盒：** 主機只跑模型；容器沒網路、root 唯讀、非 root；沒有瀏覽器。Windows 指令回每張卡那台筆電的數值（`bench/laptop.py`）。
- **情境題、Python 題：** 都是開思考考的。情境題過不過由評審決定（`<run>/verdicts.jsonl`）。Gemma 4 範本只在最後一則使用者訊息後顯示思考，所以每輪切成一列。
- **llama-server（b11193）：** 不同 LoRA 的槽不能同批；共用池加 `--no-cache-idle-slots`；考場固定 `--fit off`。請求沒給溫度時讀模型檔（Gemma 4：1.0／64／0.95，min-p 0.05）。

## 6. 量過的數字

- **規格（基底 E4B，63 題×2，0.2）：** 舊規格 off 66、high 86；v2 off 64、high 89。
- **雙管路（3050 Ti、64K）：** Agent 生成時角色開口要等：兩個不同 adapter 逾時（30 秒），共用一個 0.62 秒；可用 RAM 只剩 200–290 MiB。
- **老師：** SWE-bench 36/60。思考預算 1024 對 4096：情境卡 12 對 9、Python 34 對 35、時間少 73%，錄製用 1024。
- **機魂：** char-v1 台詞贏基底 76/80，`chat_task` 39/40。
- **訓練 32K 列：** 一步 40 秒，峰值 14.8 GiB。

## 7. 踩過的雷

- **沒量過的預設值：** Agent 溫度 0.2 從改寫起就在，對基底剛好，對訓練後的模型不一定；而且兩個 adapter 的最佳溫度方向相反。不能從一個模型推到另一個。
- **錄製省下的預算會被學走：** 老師思考上限 1024 讓學生學到想太短；省時間的錄製設定要量對學生的影響。
- **重試沒用：** 必然重現的失敗重試沒用；佇列失敗就停下，由 session 診斷。
- **老師出題：** 常把檔案包在 Markdown 程式碼框裡（`py_tasks.unfenced`）。
- **評審看不到就當沒發生：** 工具結果要給足字數。
- **Node 的錯誤：** 只說「fetch failed」，原因在 `cause`；模型聽不懂就重抓同一個網址到逾時。
- **被殺的 `run.py`：** 它的 relay 會變孤兒留著，停佇列後要清。
- **這台的 `gh`：** 太舊，沒有 `run list --commit`，用 API 的 `head_sha` 查。
- **試跑要走對方的實際路徑。** `cd a && x &` 整串會在背景子殼跑。
