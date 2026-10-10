# 開發機工作檔（Linux、RTX 3090）

更新：2026-10-09 下午｜SilentTalk、EdgeAgent 都在 `copilot-story-mode`（EdgeAgent 的還沒推，出貨時才推）；規格 v2 已凍結併入（`92a1961`）
你是從 `AGENTS.md` 被分到這裡的。通用規則在 `AGENTS.md`，這份只寫開發機的事。**只寫現況和下一步**；經過在 git 歷史和 `archive/`（只在這台機器，不必讀）。上一版：`archive/dev-box-2026-10-09-before-relay.md`。

---

## 1. 使用者的決定（現在有效）

- **One path：** 每件工作只有一條路（§2）。要加新路，先擴充既有那條；比完就刪掉輸的那條，程式、設定、測試、佇列、文件一起刪。同時只有一支佇列。
- **蒸餾：**
  - 老師只用 **Qwen3.8-27B**：Q4 出卡用 `teacher-38`，IQ3 錄對話用 `teacher-38-iq3`。
  - 評審用 **Gemma 4 31B**（`judge-gemma`）。
  - 不用付費 API，不下載別的老師。
  - Claude 的輸出永遠不當訓練目標、不挑資料、不當出貨評審。
  - 使用者的對話只由 Qwen3.8 抽成情境卡。
- **一個模型版本一份凍結規格（提示＋工具）：** 規格 v2 包含：
  - 原生工具，加上 `web_research`／`web_fetch`（網頁、JSON、PDF）、`search_history`、`translate_machine`；
  - 權限預設 `reversible`；
  - API 登錄（金鑰不給模型看）。
  
  工具的「定義」凍結；實作可以改得更穩，例如錯誤訊息、備援。
- **品質是開發機的事：** 使用者不當測試員。沒過關不是終點，要診斷、修好、再出下一版。被資料關卡擋掉的失敗（例如老師錄製逾時）還是產品的問題：要在真實路徑上量，修在產品（使用者 2026-10-09：「別上線後連上網都失敗」）。
- **從自己的錯學（2026-10-10）：** 部署的模型不夠力（使用者覺得不夠，或關卡顯示弱點），就用這個方法練：學生先做，沒過的由老師在同一個情境示範做對，再加上「學生錯的、老師對的」成對訓練。使用者願意等多出來的錄製時間。
- **要贏過原版（2026-10-10）：** 訓練好的 Agent 要贏過原本的基底，基底用它自己表現較好的溫度比，才不冤枉任何一方；Python 題也要看。工具題和 MCP 題各自都不能輸（之後的外掛靠它們），`ship_gate.py` 第 4 條。
- **不降規：** Agent 的 64K 是底線。角色必須在 Agent 工作時照常即時回話。
- **思考：** Agent 品質優先、可以慢；角色速度優先。
- **Discord／權限：** 語音每句喊「機魂」；用說的不能動電腦；刪檔要主人同意。不能做的事要兩層都擋：模型懂，程式也擋得住。
- **紀錄：** 對話只寫進使用者指定的紀錄資料夾（AGENTS.md 規則 1）。
- **接力只在必要節點觸發（2026-10-09）：** 兩台機器都不准有常駐迴圈、心跳、定時輪詢、log 垃圾，沒事不印東西（§4 第 11 條）。筆電額度少：一回合＝整份重寫一次 `laptop.md`，開發機準備好才推；commit 先留本機，有真實進展才 push。

## 2. 每件工作的那一條路

| 工作 | 那一條路 | 現況 |
|---|---|---|
| **產品 Agent** | EdgeAgent Pi 迴圈＋規格 v2。考試：`bench/run.py`（63 題×2，`ship_gate.py`）、情境卡驗收、Python 題（`py_tasks.py`）。資料：老師在框架裡錄 → `dataset.py --thinking both` → SilentTalk `train_lora.py` | 重錄中（§3） |
| **網頁工具** | `edge_agent/web_tools.mjs`：<br>• 錯誤講原因（查不到網域、拒絕、逾時、憑證；Cloudflare 驗證、404、429）<br>• 少於 500 字又有 script 的頁面，交給本機瀏覽器（Windows 用 Edge）無頭重讀，經本地代理擋私有位址，無痕、用完即刪的設定檔、一次一頁<br>• 跟隨 meta refresh、處理 Big5<br>• bridge 的重複保護涵蓋網頁工具<br>量測：`bench/web_live.mjs`（30 站＋6 搜尋） | `c06b78b`、`6b952da`（本機）；開發機 27/30 讀到、2 個 Cloudflare、1 個要登入、6/6 搜尋。Windows 實測在出貨回合 |
| **推論（角色和 Agent 共用一顆模型）** | `edge_agent/inference.py`：兩槽一池；角色 0 號、Agent 1 號；角色開口時 Agent 讓路 | 兩邊都量過（§6）：共用一個 adapter 才成立 |
| **adapter** | 同一份資料訓兩個：`agent-fw3`（只有 Agent）和 `machine-spirit-fw3`（Agent＋角色） | 合一版在 Agent 關卡（對 `agent-fw3`）和角色關卡（對 `char-v1`）都不輸才出貨 |
| **情境卡** | `families.json`（A–J）→ `scenario_cards.py`（`recheck` 淘汰不合今天規則的卡）→ `run.py` → `scenario_checks.py` → `scenario_judge.py`（先驗證自己，至少放行 10 段、擋 ≥90%；條件沒發生的規定算通過）→ `dataset.py` | 訓練 314 張、驗收 91 張（已補齊） |
| **Python 題** | `py_tasks.py generate/validate`（老師出題，沙盒自檢過才留） | 訓練 210、驗收 57。淘汰的是老師的標準答案過不了自己的測試、或沒改就全過，不是檢查錯 |
| **角色台詞關卡** | SilentTalk `line_ab.py` → EdgeAgent `bench/pair_judge.py`（Gemma，A/B 對調判兩次）→ `line_ab.py score`；`chat_task_eval.py` | 第一次用在合一版 |
| **寫程式的 Agent** | mini-swe-agent，SWE-bench Verified 60 題 | 老師 36/60、E4B 4/60 |
| **佇列** | `EdgeAgent/.runtime/fw/queue.sh`：一步一個 `.done`；失敗就停下、印一行，session 醒來修好再 `relaunch.sh`；只有顯存被搶（回 3）會自己等 | §3 第 1 項 |

## 3. 接下來

1. **重錄 v2（佇列正在跑）：**
   - 錄完、評完：`fw3-scen` 314 段收 101；`fw3-tools` 152 題過 127；`fw3-py` 210 題過 171。轉成 881 列。
     - 情境卡程式檢查擋 109（查本機 58、老師逾時 23），評審擋 104（C 組 55 張只收 6）。
   - 訓練完：`agent-fw3` 驗證誤差 0.62；`machine-spirit-fw3` 第 1 輪 0.904、第 2 輪 0.918（`-e1` 留著）。
   - **取樣：** 橋接器的 Agent 溫度 0.2 從沒量過。0.2 下 fw3 失敗指令原樣重跑到重複上限 32 次（轉檔沒問題）。`ea-sample`（分支 `model-sampling` 04c3885）改成照模型檔取樣（1.0、top-k 64、top-p 0.95）。off 126 次：基底 0.2 64，fw3 0.2 73，fw3 1.0 79（重複上限 9 次）；工具 4→7→13，MCP 24→21→18。
   - **MCP 輸：** `mcp-s-compare` 參數名照舊工具亂填（`name` 而不是 schema 的 `stock_no`、日期和代號對調）；881 列只有 8 列 MCP。`mcp-d-takeoff` 是評分錯（起飛前解鎖被判多餘，`next-world` 已修）。下一輪：很多種假 MCP 伺服器，練讀 schema。
   - 佇列（新版）：`fw3-eval` 照舊跑完當對照，之後 Agent 全用 `ea-sample` 產品，tag 後綴 `-t1`。順序：fw3、ms3、基底的 off／high，情境卡（加上筆電現行產品），Python，角色，最後關卡（`gate-fw3`、`gate-ms3` 對筆電現行，`gate-*-vs-base`、`gate-*-vs-v2f` 對 1.0 和 0.2 的基底，`gate-ms3-vs-fw3`）。基底兩種溫度都考（`base-v2f*` 是 0.2）。
2. **筆電：** 第 10 回合已審；下一回合是出貨回合（第 3 點）。
3. **出貨：** `ms3` 過全部關卡，就出合一 adapter；只有 `fw3` 過，就先診斷 `ms3` 輸在哪、修了再訓。出貨時：
   - 先把 EdgeAgent 分支 `model-sampling`（取樣贏了才合）和 `next-world`（見下面第 4 點）合併進 `copilot-story-mode`，跑完整測試，再推 EdgeAgent；
   - 整份重寫 `laptop.md` 成出貨回合，內容包括：
     - v2 部署：PowerShell 7.6.6，確認 Agent 指令真的由 `pwsh.exe` 執行；
     - 介面：`reversible`、還原按鈕、API 登錄頁；
     - Discord 實測；
     - **網頁實測**：用 `node bench/web_live.mjs` 和開發機的數字比；Edge 無頭讀頁要成功；記下每頁秒數，以及讀頁時角色回話的延遲和可用 RAM（兩條管路都在跑時）；
     - **唯讀任務查本機**：問「記憶體多大」「C 碟還剩多少」，要答出實際數字（`Get-CimInstance`、`Get-Volume` 不再被擋）；`Get-CimInstance Win32_Process` 仍要被擋；
     - **唯讀任務算資料**：問「app.log 最常見的錯誤是什麼、幾次」，要用 `Where-Object`／`Group-Object` 算出來，不是一直重讀檔案；`Get-Process | Format-List *`、`Get-Process | Select-Object Name, CommandLine`、`Write-Output C:\Users | Get-ChildItem` 要被擋；
     - Windows 上要過：`test_real_sdk_stops_fetching_the_same_dead_address`、`tests/test_lingua_powershell.py`（新加的 Windows 指令和參數）。
4. **EdgeAgent 分支 `next-world`（worktree `ea-web`，都有測試）：** 這一輪關卡結束後才合併，讓這一輪的考試全程用同一套評分和產品程式。
   - **產品（隨 v2 出貨）：**
     - 唯讀任務可以讀本機（記憶體、磁碟、服務），只認 Windows 內建模組（`CimCmdlets`、`Storage`、核心模組），`Get-CimInstance` 只准固定的類別清單（不含程序、開機程式、帳號、環境變數）。工具題 `sysinfo` 8 題原本都因為唯讀擋掉 `Get-CimInstance` 而只能照提示詞答。
     - 唯讀任務可以在讀到的東西上計算：變數、運算、`{ }` 區塊、`if`／`foreach`、純計算的方法（`[math]::Round`、`.Trim()`）、`2>$null`。只能讀這段指令自己設的變數（`$env:` 和 session 裡之前的變數都不行）。工具題 log 3 題原本都因為不能統計而重讀檔案到逾時；這一輪錄製被擋的 190 條指令有 95 條改判可以跑，其餘是讀工作區外、跑程式或 .NET 讀檔。
     - 補兩個漏洞：字串經管線傳給 `Get-ChildItem` 會被當成路徑，能列出任何資料夾；`Get-Process` 的 `CommandLine` 屬性看得到其他程式的命令列。現在管線傳來的路徑只接受證明看過的（`Get-Item` 指名的檔案、`Get-Content` 的來源檔，`Get-ChildItem` 後面只能算雜湊）；命令列和一次顯示全部屬性的寫法（`*`、`PSObject`）都擋。
     - `Select-Object Name, Length` 這種逗號列表算固定值；`git -C 工作區`、`git --no-pager`、`-ErrorAction` 可以用。
   - **測試環境（下一輪錄製和考試用）：**
     - 假 API 照真的 API 回應：分頁、格式參數不影響資料；沒有資料的值回 404 並說它有哪一天的資料；缺參數回 400；不存在的端點回 JSON 404。J 組（主人的 API）26 張只過 15 張，多半是 Agent 把日期換成今天、拿到空的 404 就一直換寫法重試。
     - 工作區比原本多出 100 MB 以上，判 `bloat` 失敗，評分程式不複製、不崩潰。`train-I-028` 留下約 2.4 GB 測試檔，塞爆評分用的 2 GB /tmp。
     - 假無人機有狀態：沒解鎖不能起飛，在地上不能返航；起飛前解鎖不算多餘的飛行。返航題從空中開始。
     - 記憶體題對照模擬筆電的 8 GB（原本拿開發機的 125.6 GB 對答案，考試題 `tool-sysinfo` 每個模型都必錯）。
     - 工具題出題：照片改名題明寫「每一張（IMG_、DSC_、PXL_ 都有）」，原本老師改寫成「IMG 開頭」而評分要全部（2/10 題）；整理題的 PDF、試算表可以和文件放同一個資料夾（兩題失敗都是這樣分的）。
     - C 組（交付完整）：52 張訓練卡有 22 張禁止補漏時重貼整張表（補一欄就得重貼），評審因此退掉老師完整的修正表，`train-C-028` 卻規定要貼。題型定義改成「原本對的一字不改，使用者明說才只給缺的部分」，出卡規則淘汰這種卡（訓練 22、考試 2 張，下一輪錄製前 `recheck` 再 `generate` 補回）。
     - 沙盒的 Windows 指令來自 Windows 同名的模組，唯讀判斷和筆電一致。`Get-Process`、`Get-PSDrive`、`Get-ComputerInfo` 是 `Microsoft.PowerShell.Management` 自己的 cmdlet（蓋過映像的清單，加上 `run.py` 編的 LaptopCore.dll），回筆電的程序和磁碟；Agent 自己的 PowerShell 和它啟動的程序是真的。fw3 查本機被擋的 58 段，26 段只用了這兩個。
   - **還沒做（下一輪錄製前）：** 假網路讓每個網域都解析得到；卡片網頁用原本的 https 網址（本地 CA＋443）；卡片沒有的頁面回 404。這樣訓練資料不會再出現 `:8081` 和「網路可能斷了」（`EAI_AGAIN`）。另外，`$PSVersionTable`（常數）和 `[Environment]`（.NET）還是容器的答案，換不了：查本機檢查改看工具輸出有沒有 Linux 字樣，不看指令。
5. **之後：** 第一輪「從自己的錯學」（§1）：學生是這一輪出貨的 adapter；coding agent（Qwen3.8 軌跡）；清掉不用的 worktree（`ea-laptop`、`ea-spec2`、`ea-freeze`；`ea-web` 等 `next-world` 合併後）。

## 4. 開發機規則（通用規則在 AGENTS.md）

1. 改 prompt、模型、設定、外殼前先量，改完再量，變差就退回。修 bug 不用 A/B。
2. **Agent 只在沙盒裡跑。** 改了 `sandbox()` 先跑 `--containment`。
3. 題目先過 `--selftest`；比較一律用同一批題目配對。
4. 只有過硬關卡的資料才能訓練。資料檔帶版本戳記，不混版本。
5. **共用機器：** GPU、RAM 和 ComfyUI、whisper-api 共用，不動它們。要吃滿整台機器、大下載，先問使用者。
6. 關程序只用確認過的 PID，不用字串比對。
7. **考試中別動：** `run.py` 開跑時會複製產品程式；`agent_runner.py`、`relay.py`、`bench/web_fixture.py` 是即時掛載，考試中不改。改產品程式在 worktree 做。
8. **執行中的佇列腳本不改：** 先用 PID 停佇列本身，再用 `relaunch.sh` 接手。
9. **開發機不改介面**（`edge_agent/web.py`、SilentTalk 設定頁）。git 身分：`git -c user.name="nobody945946" -c user.email="104478886+nobody945946@users.noreply.github.com" commit ...`。
10. **工作檔：** 只寫現況，狀況變了就封存重寫。
11. **喚醒只在必要節點：** `scripts/dev/wake.sh` 在背景跑，醒來處理完就重新掛上。它只等真的在等的東西，用它能發出訊號的方式等：
    - **佇列 log：** 等核心的檔案通知，不輪詢。步驟事件、產出數字、錯誤都會叫醒；一小時沒有任何一行是卡住（SILENCE）。長步驟只印進度行，兩小時到時 log 還在長就是 ALIVE，看一眼數字再掛回。
    - **CI：** push 完執行 `wake.sh ci <repo> <完整 sha>`，跑完就不再問。
    - **筆電：** 交辦後執行 `wake.sh handoff <小時>`，只在回合可能做完時和兩小時到時各問一次 GitHub。沒有回條＝筆電沒開；收件後超時沒回報，只叫醒一次。
    - **什麼都沒在等：** 腳本直接結束，不掛回去。狀態只放在 `.runtime/wake/` 的兩個小檔，不寫 log。
    
    醒來先看資料，判斷錯在檢查、資料、程式還是模型，修好、重排受影響的步驟。不要盲目重試，也不要預寫備案。push 完要等 CI 綠才算完成。

**每次改完要跑：**

```bash
cd /home/clawd/SilentTalk && .venv/bin/python -m pytest -q -p no:cacheprovider
cd /home/clawd/EdgeAgent && .venv/bin/python -m ruff check edge_agent tests   # 和 CI 同一個指令（ruff 0.16.10）
cd /home/clawd/EdgeAgent && .venv/bin/python -m pytest -q -p no:cacheprovider   # 407 passed；4 個只在 Windows 過
# worktree：加 PYTHONPATH=.，用 EdgeAgent 的 .venv；先把 .runtime/node、pi、pwsh 連到主工作區。
# Windows 編碼：在 ASCII 語系下跑（LC_ALL=C LANG=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0 PYTHONIOENCODING=），
# 失敗清單要和上一個 CI 綠的 commit 一樣，多出來的就是 Windows 會壞的。
```

## 5. 考場細節

- **沙盒：** 主機只跑模型；容器沒網路、root 唯讀、非 root；沒有瀏覽器，所以網頁備援只在筆電上用。
- **Windows 指令：** 回每張卡那台筆電的數值（`bench/laptop.py`）。
- **情境題：** 過不過由評審決定（`<run>/verdicts.jsonl`）。Gemma 4 範本只在最後一則使用者訊息後顯示思考，所以每輪切成一列。
- **llama-server（b11193）：** 不同 LoRA 的槽不能同批；共用池要加 `--no-cache-idle-slots`；考場固定 `--fit off`。

## 6. 量過的數字

- **規格（基底 E4B，63 題×2）：** 舊規格 off 66、high 86；v2 off 64、high 89。
- **雙管路，筆電 3050 Ti、64K：** Agent 生成時角色開口要等多久：
  - 兩個不同 adapter：逾時（30 秒）；
  - 共用一個 adapter：0.62 秒。
  - 可用 RAM 只剩 200–290 MiB。
- **老師：**
  - SWE-bench 60 題 36/60。
  - 預算 1024 對 4096：情境卡評審通過 12 對 9，Python 34 對 35，時間少 73%。→ 錄製用 1024，每輪 30 分鐘。
- **錄製 `fw3-scen` 前 79 段：** 9 段逾時或出錯，都是在打假網路沒有的網址。真實網路上同類網址都讀得到（§2 網頁工具）。
- **機魂：** char-v1 台詞贏基底 76/80，`chat_task` 39/40。
- **訓練 32K 列：** 一步 40 秒，峰值 14.8 GiB。
- **訓練前檢查：** 老師試錄的 74 列加角色 770 列，合併後沒有一列被丟。

## 7. 踩過的雷

- **重試沒用：** 會必然重現的失敗重試沒用。佇列失敗就停下，由 session 診斷。
- **老師出題：** 常把檔案包在 Markdown 程式碼框裡（`py_tasks.unfenced`）。
- **評審看不到就當沒發生：** 工具結果要給足字數。
- **舊的比較混了資料版本：** 「合一 adapter 讓 Agent 變差」那次混了 fw2 和 fw1 的資料；這次用同一份資料比。
- **Node 的錯誤：** 只說「fetch failed」，原因藏在 `cause` 裡。模型聽不懂，就會重抓同一個網址直到逾時。
- **Linux 上的 Chrome 無頭模式：** 不加 `--password-store=basic` 會等密碼鑰匙圈 25 秒。
- **這台的 `gh`：** 太舊，沒有 `run list --commit`，要用 API 的 `head_sha` 查。
- **試跑要走對方的實際路徑：** 第 8 回合就是試跑沒走到的路徑壞掉。
- **`cd a && x &`：** 整串會在背景子殼跑。
