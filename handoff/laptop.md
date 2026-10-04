# Windows 工作檔：第 2 回合，跟上與 Windows 驗證（不需要使用者）

更新：2026-10-05 清晨｜開發分支：兩個 repo 都是 `copilot-story-mode`｜報告分支：`laptop-report`

你是從 `AGENTS.md` 被分到這裡的。共通規則以 `AGENTS.md` 為準。舊版工作檔在開發機的 `archive/`，你不必讀。

## 0. 這一輪的大小

小回合、**不需要使用者**。Discord 實測（使用者打字下令、私訊批准、第二個帳號）是下一回合，這次不要做。額度快用完就停在做完的那一步，照 §4 回報做到哪裡。

## 1. 現況（開發機做好、你要跟上的）

| 東西 | 位置 |
|---|---|
| SilentTalk | `C:\Users\A8fm0\Downloads\SilentTalk` |
| EdgeAgent | `C:\Users\A8fm0\EdgeAgent`（控制 `127.0.0.1:18087`、推論 `127.0.0.1:18089`） |
| 報告 | `handoff/reports/laptop.md`，只提交到 `laptop-report` |

第 1 回合之後開發機做的（都在 EdgeAgent，除非另外寫）：

- **機器語言精準翻譯**（`edge_agent/lingua/`）：正規表示式（Python／.NET／JS）、PowerShell、Excel 公式、SQL、Python、MAVLink、機器碼。翻譯由解析器產生，每條說明都在真引擎上驗證過。
  - Agent 新工具 `translate_machine`（執行 `python -m edge_agent.lingua`）；正規表示式可附範例字串，用真引擎跑。
  - Agent 要執行 PowerShell 指令而請求批准時，批准卡片（和 SilentTalk 的 Discord 私訊）會先附上這個指令的白話和影響。
- **上網研究工具** `web_research`：程式搜尋、讀網頁、挑出最相關的 6 段附編號和網址。
- **MCP**：可接本機 HTTP 伺服器（`url`，只准 127.0.0.1／localhost）；`read_only_tools` 讓擁有者替沒標記的工具擔保唯讀（台股伺服器 173 個工具都沒標記）。
- **新相依套件**：`sqlglot==30.21.0`、`pymavlink==2.4.50`、`capstone==5.0.9`（`pyproject.toml` 變了，`bootstrap.ps1` 會重裝）。

## 2. 這一回合要做的事（依序；每一步做完照 §4 回報）

**A. 跟上**
1. 兩個 repo `git pull`；照既有部署流程部署 EdgeAgent（`bootstrap.ps1 -SetupOnly`），確認 `import pypdf, sqlglot, pymavlink, capstone, edge_agent` 都成功。
2. 兩個 repo 跑完整測試，回報 passed／failed／skipped 和 exit code。EdgeAgent 的已知 Windows 以外失敗在 Windows 上應該都通過。

**B. 在 Windows 上驗證翻譯器**（測試檔已寫好，只要跑和回報）
1. PowerShell 翻譯器和正規表示式的 .NET 部分要在**兩種 PowerShell** 各跑一次：
   - Windows PowerShell 5.1：`$env:EDGE_AGENT_PWSH = (Get-Command powershell.exe).Source`
   - PowerShell 7（如果有裝 `pwsh.exe`）：`$env:EDGE_AGENT_PWSH = (Get-Command pwsh.exe).Source`
   - 每次跑 `tests/test_lingua_powershell.py tests/test_lingua_regex.py tests/test_lingua_cli.py`；失敗的列出測試名稱和斷言訊息。只在 Windows 才有的指令（Stop-Service、Restart-Computer、Stop-Computer、Clear-RecycleBin）會在這裡被驗證。
2. `tests/test_lingua_python.py`：回報 `test_windows_default_encoding_is_not_utf8` 的結果，和 `python -c "import locale; print(locale.getpreferredencoding(False))"` 印出的編碼名稱。
3. **Excel**：先查有沒有裝 Excel（COM `Excel.Application`）。
   - 有：開一個新活頁簿（不存檔），用 COM 填公式、讀回顯示值，回報這兩格：`=VLOOKUP(1,{1,"a";3,"b"},3,FALSE)`（預期 `#REF!`）和 `=XLOOKUP(4,{1;3;5},{"a";"b";"c"})`（預期 `#N/A`）。結束時關掉活頁簿不存檔、`Quit()`、釋放 COM 物件，並用 PID 確認 Excel 程序已結束。
   - 沒有：回報「沒有 Excel」，跳過。
   - 另外回報有沒有裝 LibreOffice（`soffice.exe`），只回報有沒有。
4. `tests/test_lingua_mavlink.py`、`tests/test_lingua_asm.py`、`tests/test_lingua_sql.py`、`tests/test_lingua_excel.py` 在 Windows 上的結果（沒有 Docker 或 Calc 的部分會 skip，照實回報 skip 數）。

**C. 產品端實測**（不需要使用者）
1. `translate_machine` 的命令列：在 EdgeAgent 的 venv 跑
   `"ls -r *.log | rm -WhatIf" | .venv\Scripts\python.exe -m edge_agent.lingua powershell`
   回報輸出裡的「解讀環境：」那一行，以及有沒有寫出「ls 是 Get-ChildItem 的別名」「rm 是 Remove-Item 的別名」「只是模擬」。
2. **批准卡片**：用既有的真 Edge 瀏覽器檢查（`tests/browser_check.mjs` 那一套），加一個情境：權限 shell 設成「問」，請 Agent 執行 `Get-Date`；等批准卡片出現後確認卡片裡有「這個指令在做什麼」的展開區塊，然後按「拒絕」。在既有的檢查 owner 裡加，不另寫新腳本。回報檢查結果和視窗大小。
3. **上網研究**：用 Node 直接呼叫 `edge_agent/web_tools.mjs` 的 `webResearch('Python 3.12 是哪一天發布的？', ['Python 3.12 release date'])`，只回報：讀了幾個網頁、回了幾段、段落裡有沒有出現「2023」。不要把網頁內容寫進報告。
4. `tests/test_mcp.py` 在 Windows 的結果（包含新的 `url`、`read_only_tools` 驗證）。這回合**不要**在 EdgeAgent 設定裡啟用任何 MCP 伺服器。

## 3. 規則（AGENTS.md 之外）

- 不讀寫使用者的 `.env`、`settings.json`、`personas.json`、`character_state.json`，也不讀 `silenttalk.log` 的對話原文。
- 不改使用者的預設模型和權限設定；測試用的設定測完換回原狀。
- Excel 只開新的空活頁簿，絕不開使用者的檔案，也不存檔。
- 修改都在既有的 owner 完成（AGENTS.md 規則 8）。程式提交到 `copilot-story-mode`；報告只提交到 `laptop-report`，用獨立 worktree，正常 push。
- 結束後停掉自己啟動的服務和程式（用自己的 PID），刪掉自己的暫存，並確認清理。

## 4. 回報（`handoff/reports/laptop.md`，`laptop-report` 分支）

每一步一個段落，只寫：
- 數字和事件；
- 測試結果（passed／failed／skipped、exit code）；
- 版本和 commit 雜湊；
- 做不到的原因；
- 額度用到哪裡停（如果有停）。
