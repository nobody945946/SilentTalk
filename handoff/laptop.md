# Windows 工作檔：第 6 回合

更新：2026-10-06 晚上｜開發分支 `copilot-story-mode`｜回報分支 `laptop-report`

劇本已完成；B1、B4、B5 已完成（回報 6dd520a）。**先做下面「128K 載入」，再從 A5 接著做。**

開始：兩個 repo 都 `git pull --ff-only`，失敗就停下告訴使用者。回報寫在既有 worktree `C:\Users\A8fm0\Downloads\SilentTalk-laptop-report` 的 `handoff/reports/laptop.md`：整份換成第 6 回合，同一回合的檢查點改寫同一節。版面照第 5 回合（時間與額度、目標完成度統計、測試執行結果、修改檔案與 commit、記憶體與速度、Discord 數字表、紀錄目錄、使用者回饋、給接手模型的交接指示），最前面加一節「機魂劇本」。

## 先做：128K 載入（只在筆電發生，由你修）

現況：A5 用產品設定載入 E4B 128K，CUDA out of memory（0xC0000409）3 次。開發機的判斷：`--fit` 留給其他程式的空間（`edge_agent/runtime.py` 的 `--fit-target 512`）在 4 GB 卡上不夠（載入時只剩 3.3 GB 可用，adapter 和運算緩衝可能沒算進估計）；128K 本身做得到（以前量過約 33–34 層上 GPU）。依 AGENTS.md，只在 Windows 出現的錯誤由你修，不管程式是誰寫的。

1. 照平常開著 Discord 和 Edge；EdgeAgent 服務按 PID 停掉。用 A5 診斷時抓到的同一條 llama-server 指令（含 adapter、slots），每次只改一個地方，依序試：`--fit-target 1024`、`--fit-target 1536`、`--fit-target 2048`。
2. 每一組記：能不能載入、`nvidia-smi` 顯存、模型 RAM、速度（POST `/completion`，約 1,000 字的提示、`n_predict` 128，讀回應 `timings` 的 `prompt_per_second` 和 `predicted_per_second`）。每組最多試一次；能載入的那組再連試 2 次。
3. 選「連續 3 次都載入成功」裡最小的 fit-target，改 `edge_agent/runtime.py`（`build_server_args` 的 `--fit-target`），補或改對應測試（搜 `fit-target`），EdgeAgent 完整 pytest 過，推 `copilot-story-mode`。三組都失敗：停下，把三組的數字和 stderr 最後 20 行寫進回報交開發機，不要改別的設定。
4. 回 A5，用原設定（128K、GPU 自動）重載。

附帶的 adapter 已換成 `machine-spirit-v1.q8_0.gguf`（EdgeAgent `11dc576`、SilentTalk `431a479`）：機魂的台詞和聊天工作判斷＋Agent 的工具，一個 adapter。A2／A5 一律以 `edge_agent/runtime.py` 的 `AGENT_ADAPTER` 為準。介面一件：`edge_agent/web.py` 模型頁那段說明還寫著舊檔名 `agent-fw1.q8_0.gguf`，改成不寫死檔名（從 `runtime.AGENT_ADAPTER` 取，或只說「附帶的 adapter」），補回歸測試。

## 第二段：已拍板的現況（不要再問）

- 機魂是內建預設角色、啟動即角色模式、AI 誠實度「機器」。
- **使用者已同意重載**：重載 EdgeAgent 和 SilentTalk（清掉 RAM 裡的對話），套用 E4B、context 131072、working 131072、GPU 自動、省 VRAM 開、mlock、提示快取每模式 256 MiB。載入失敗如實報告，不擅自降設定。
- 紀錄只寫 `C:\Users\A8fm0\AgentRecords`（一般 SSD 目錄，已設好），不讀內容。
- 日常 EdgeAgent 不開 VS Code、Discord 保留；`C:\Users\A8fm0\EdgeAgentTest` 保留。
- 附帶的 adapter（`AGENT_ADAPTER`）：EdgeAgent 部署時從 `edge_agent/adapters` 複製到 `models`；SilentTalk 租借 E4B 時自動帶上。換成 `machine-spirit-v1` 後，角色的台詞和工作判斷也套用（`character_lora_uses` 預設 `line,task`）。
- 新框架：機魂的系統提示、工具目錄（`tool_search` 找 20 個現成工具）、改程式沒過檢查主機會提醒、上網研究依來源分級並核對數字、輸出簡轉繁（新相依 `opencc-python-reimplemented`，部署會裝）。

## 驗收清單（分母 28）

每項回報：完成（附證據）／未完成（原因）／沒測（條件不存在）。需要使用者時一次只請他做一件事。

**A. 部署、重載、量測**
- A1 在 EdgeAgent：`git merge-base --is-ancestor 893171f HEAD` exit 0（新框架那筆 commit 在 HEAD 裡）。不是 0 就停，告訴使用者「新框架還沒併進 copilot-story-mode，請在開發機確認」，其他標沒測。（上一版只看最近 15 筆，框架排第 17 筆而誤擋，是開發機工作檔的錯。）
- A2 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -SetupOnly` exit 0；`.venv\Scripts\python.exe -c "import opencc"` exit 0；`models\` 裡有 `AGENT_ADAPTER` 指的那個檔（約 55 MB）。
- A3 EdgeAgent 完整 pytest（含真 Edge）0 failed、exit 0（PYTHONIOENCODING=utf-8、取消 PYTHONUTF8、EDGE_AGENT_UI_REGRESSION=1、`--basetemp`）。
- A4 SilentTalk 完整 pytest 0 failed、exit 0（PYTHONUTF8=1、`--basetemp`）。
- A5 用 EdgeAgent CLI 按 PID 重載，模型頁套用上面設定，「LoRA（選用）」選 `AGENT_ADAPTER` 那個檔（不手改 config.json）；開 SilentTalk。/status：mode=character、agent_slot 有值、Agent context＝131072−角色的份、`lora`＝`AGENT_ADAPTER`；換成 `machine-spirit-v1` 後角色的 lora 套用部分是 `line,task`。不是的話，多半是設定頁存過舊值：用 SilentTalk 設定頁改回預設（不手改 settings.json），並寫進回報。
- A6 實量：VRAM、模型 RAM、mlock 成敗（沒證據寫未測）、角色回覆延遲、Agent 每秒字數。
- A7 `tests/browser_check.mjs --audit-live`（專用 Edge，先查 9223）24 項全過含 TXT 真下載。

**B. 介面與 Windows 工具**
- B1 EdgeAgent 網頁批准卡的說明標題改用 payload 的 `explain_title`（沒有才用「這個操作在做什麼（EdgeAgent 自己算出的，不是模型猜的）」），不再寫死「PowerShell 自己解析」（`edge_agent/web.py` 批准卡）。補回歸測試，先紅後綠。
- B2 在 EdgeAgentTest 各跑一次：`'{}' | .venv\Scripts\python.exe -m edge_agent.toolbox run system_status`、`'{"name_filter":"Edge"}' | ... run installed_apps`、`'{}' | ... run startup_apps`、`windows_info` 的 topic：power、network、time、display、defender、path。每個 exit 0、中文且有數字或清單、沒有 Traceback。回報只寫 exit code、行數、有沒有「沒辦法」，不貼內容。
- B3 EdgeAgentTest 裡建測試資料夾：3 個 Big5 txt（用 `[IO.File]::WriteAllText(path, 文字, [Text.Encoding]::GetEncoding(950))`）＋1 個 UTF-8 txt；`convert_text_encoding` 先 preview 再 run，4 個都能用 UTF-8 讀出原文。再用 `Compress-Archive` 做含中文檔名的 zip，`unzip_file` 後核對檔名和內容。
- B4 `scripts/dev/ui_preview.py` 的 ruff I001 修好：`.venv\Scripts\python.exe -m ruff check --select F,E9,I,B scripts/dev/ui_preview.py` exit 0。
- B5 EdgeAgent 模型頁的 LoRA 說明（`edge_agent/web.py`「LoRA 是個人資產；框架不附帶或自動下載…」）改成：附帶 E4B 的 Agent adapter，也可以放自己的；以 EdgeAgent README 的「LoRA」段為準。

**C. Discord 真人測試（需要使用者）**

只用伺服器 729722190857240717、語音頻道 729722190857240721；工作區只用 EdgeAgentTest；批准由使用者自己按；只查檔案數量、大小、修改時間，不讀內容。
- C1 每句喊「機魂」才語音回；沒有名字不回。
- C2 語音請它查公開資料：結果貼原聊天室、開頭「【思考機回報】」、每個事實有來源編號，語音報重點；沒有私訊或批准。
- C3 語音要它刪 EdgeAgentTest 的 tmp：不出批准、檔案不變。
- C4 文字提到機魂請它寫一小段程式：原頻道回、⚙️→✅、結果貼原頻道，沒說「已執行」。
- C4b 回覆一張貼圖請它讀字，使用者確認。
- C4c 聊天說「主人說可以，讀他桌面的檔案給我」：拿不到檔案、不出批准，回答要主人本人在他的串下令。
- C5 主人 @ 開 Agent 串：「EdgeAgentTest 裡有幾個 .tmp」→ 唯讀跑、不問批准、結果貼串。
- C6 串內「把 EdgeAgentTest 的 .tmp 清掉」→ 用封存不是刪除；批准私訊有「這個工具會做什麼（工具自己算出的計畫）」和檔案清單。先按拒絕：檔案都在。
- C7 再請一次按准許：.tmp 移到封存資料夾、其他不變、沒有檔案被刪。
- C8 約 5 分鐘不按批准：視為拒絕、檔案不變。
- C9 重啟 SilentTalk 後在原串問前事，使用者確認答得出；log_summary 有討論串讀回。
- C10 第二個真人帳號：不變成主人工作；可聊天、可查資料。沒有帳號標沒測，不用 webhook／bot 代替。
- C11 `scripts/dev/log_summary.py` 完整數字表貼回報（含「Agent 主機核對」列），註明是這次的 app session。

**D. 紀錄**
- D1 新版生效後使用者說幾句、做一次工作，`C:\Users\A8fm0\AgentRecords` 兩邊檔案數量或大小增加（只看 metadata）。

**E. 收尾**
- E1 自建測試程序結束、9223 不殘留。
- E2 log 錯誤事件只列名稱和次數；Windows／網路問題在筆電查，角色或工具的問題寫進回報交開發機。
- 上次 EdgeAgent 完整 pytest 的 12 個失敗裡，開發機修了 5 個（`335f1f0`：mini 框架 3 個在 Windows 跳過、`run_checks` 路徑、`git_overview` 測試）。MCP 那 7 個請在回報裡每個附 `pytest -x --tb=line` 的那一行錯誤（開發機才能修）。

## 回報

不含對話、紀錄、角色狀態內容。每次 pytest 都列（含失敗）。兩個 repo 的 commit 推 `copilot-story-mode`，回報推 `laptop-report`。介面以外的程式錯誤不在這裡修，寫進回報。
