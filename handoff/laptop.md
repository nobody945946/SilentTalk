# Windows 工作檔：第 2 回合，照表操作的驗證（不需要使用者）

更新：2026-10-05｜兩個 repo 的開發分支：`copilot-story-mode`｜報告分支：`laptop-report`

你是從 `AGENTS.md` 被分到這裡的。這一回合**只跑指令、抄結果、寫報告**。所有程式都已經在開發機寫好、測過，你不需要寫或改任何程式。

## 0. 先讀完這一段再開始

### 0.1 禁止事項（每一條都適用整個回合）

1. **不改任何檔案**：程式、測試、設定、文件都不改；不 commit 到 `copilot-story-mode`。這一回合你唯一會寫的檔案是報告（步驟 11）。
2. **測試失敗不要修**：不要找原因、不要讀程式碼、不要重寫測試。照抄失敗的那幾行，然後做下一步。
3. **不讀其他文件**：不讀 README、ARCHITECTURE、程式碼、`archive/`、`handoff/dev-box.md`、舊的報告內容。你需要的都在這份檔案裡。
4. **不安裝這裡沒列的東西**：包括 PowerShell 7、LibreOffice、Docker、任何 MCP 伺服器。
5. **不碰使用者的私人檔案**：不讀不改 `.env`、`settings.json`、`personas.json`、`character_state.json`、`silenttalk.log`；不開使用者的任何文件或 Excel 檔。
6. **危險的 git 指令一律不用**：`git stash`、`git reset`、`git clean`、`git checkout -- <檔案>`、`git push --force`。
7. **不用名稱關程式**：不用 `Stop-Process -Name`、`taskkill /IM`、`pkill`。只用這份檔案給的指令。
8. **不啟動 SilentTalk、不連 Discord、不在 EdgeAgent 設定裡啟用 MCP。**
9. **不加步驟、不改指令**：指令一字不改地照抄執行，不要「順便」優化或多跑別的測試。
10. **報告只寫事實**：指令輸出的原文片段、數字、exit code。不寫推測、原因分析、建議或心得。

### 0.2 怎麼執行指令

- 所有指令都是 **PowerShell**。每個程式碼區塊**整塊當成一個指令**執行；如果你的工具一次只能跑一行，就照順序一行一行跑，而且**同一行裡用 `;` 串起來的部分不要拆開**（拆開的話，環境變數會不見）。
- 每個指令後面的 `"exit=$LASTEXITCODE"` 會印出 `exit=數字`。**報告的 exit code 一律抄這個數字**，不要自己判斷。
- 部署和測試可能要跑 15 分鐘。只要畫面還在出新的輸出就等。**超過 20 分鐘完全沒有新輸出**才按 Ctrl+C 停掉，報告寫「逾時」，然後做下一步。
- 每一步做完，**馬上**把結果寫進你手邊的報告草稿（步驟 11 的格式），不要等到最後憑記憶寫。

### 0.3 遇到計畫外的狀況

- 指令的輸出跟「預期」不一樣：照「失敗時」那一行做。沒寫「停下」的，就記下來，繼續下一步。
- 寫著「**停下**」的：不要再做後面的步驟，直接跳到步驟 11 寫報告，報告最後寫「停在步驟 N」。
- 不知道怎麼辦：**不要猜**。停下，用一句話問使用者，等他回答。

## 1. 確認起點

目的：確認兩個 repo 在對的分支、沒有別人沒存的修改，並看 EdgeAgent 現在是什麼狀態。

```powershell
Set-Location C:\Users\A8fm0\Downloads\SilentTalk; git branch --show-current; git status --short
```
```powershell
Set-Location C:\Users\A8fm0\EdgeAgent; git branch --show-current; git status --short
```
```powershell
C:\Users\A8fm0\EdgeAgent\.venv\Scripts\python.exe -m edge_agent.cli status
```

預期：
- 前兩個指令各印出 `copilot-story-mode`，`git status --short` 什麼都不印。
- 第三個指令印出下面三行之一。

失敗時：
- 分支不是 `copilot-story-mode`，或 `git status --short` 有以 `M`、`A`、`D`、`R`、`U` 開頭的行（有人改了檔案）：**停下**。不要切分支，也不要動那些檔案。把那幾行抄進報告。
- 只有以 `??` 開頭的行（沒追蹤的檔案）：抄進報告，繼續。

看第三個指令印什麼：
- `EdgeAgent stopped ...`：報告寫「原本停止」，繼續步驟 2。
- `EdgeAgent running: ...`：報告寫「原本在跑」，然後執行下面這行把它停掉。它應該印出 `EdgeAgent stopped ...`：
  ```powershell
  C:\Users\A8fm0\EdgeAgent\.venv\Scripts\python.exe -m edge_agent.cli stop
  ```
- `EdgeAgent is leased to SilentTalk ...`：表示使用者正在用 SilentTalk。**停下**，問使用者一句：「SilentTalk 正在使用中，我可以等你關掉之後再繼續嗎？」等他說可以，再從步驟 1 重新開始。
- 其他輸出或錯誤：抄進報告，**停下**。

## 2. 拉新版

目的：拿到開發機做好的程式。

```powershell
Set-Location C:\Users\A8fm0\Downloads\SilentTalk; git rev-parse --short HEAD; git pull --ff-only; "exit=$LASTEXITCODE"; git rev-parse --short HEAD
```
```powershell
Set-Location C:\Users\A8fm0\EdgeAgent; git rev-parse --short HEAD; git pull --ff-only; "exit=$LASTEXITCODE"; git rev-parse --short HEAD
```

預期：兩個都是 `exit=0`。EdgeAgent 最後一行的 commit 是 `a7cf64f` 或更新。

失敗時：`exit` 不是 0，就**停下**，把錯誤訊息的最後 10 行抄進報告。不要用其他 git 指令硬拉。

如果 SilentTalk 拉下來有新東西：**重新讀一次 `AGENTS.md` 和這份檔案**，再繼續。

## 3. 部署 EdgeAgent

目的：裝上新的相依套件（`sqlglot`、`pymavlink`、`capstone`，以及測試用的 `unicorn`）。

```powershell
Set-Location C:\Users\A8fm0\EdgeAgent; powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1 -SetupOnly; "exit=$LASTEXITCODE"
```
```powershell
Set-Location C:\Users\A8fm0\EdgeAgent; .\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -e ".[dev]"; "exit=$LASTEXITCODE"
```
```powershell
C:\Users\A8fm0\EdgeAgent\.venv\Scripts\python.exe -c "import pypdf, sqlglot, pymavlink, capstone, unicorn, pytest, edge_agent; print('imports ok')"
```

預期：前兩個指令都是 `exit=0`；第三個印出 `imports ok`。

失敗時：任何一個沒有達到預期，就**停下**，把錯誤訊息的最後 10 行抄進報告。

## 4. 兩個 repo 的完整測試

目的：確認新版在 Windows 上沒有壞掉。

```powershell
Set-Location C:\Users\A8fm0\EdgeAgent; .\.venv\Scripts\python.exe -m pytest -q --tb=line -p no:cacheprovider; "exit=$LASTEXITCODE"
```
```powershell
Set-Location C:\Users\A8fm0\Downloads\SilentTalk; .\.venv\Scripts\python.exe -m pytest -q --tb=line -p no:cacheprovider; "exit=$LASTEXITCODE"
```

預期：結尾有一行像 `180 passed, 5 skipped in 90.00s`，然後是 `exit=0`。有 `skipped` 是正常的（這台沒有 Docker 和 LibreOffice）。

要抄進報告的：
- 那一行 `... passed ...` 的原文；
- `exit=` 的數字；
- 每一行以 `FAILED` 或 `ERROR` 開頭的行，原文照抄。

失敗時：記下來，**繼續步驟 5**。不要修，也不要重跑。

## 5. 翻譯器在兩種 PowerShell 上

目的：PowerShell 翻譯器和正規表示式的 .NET 部分，要在 Windows PowerShell 5.1 和 PowerShell 7 上各驗證一次。

**5.1（每台 Windows 都有）**——這一行不要拆開：

```powershell
Set-Location C:\Users\A8fm0\EdgeAgent; $env:EDGE_AGENT_PWSH = (Get-Command powershell.exe).Source; .\.venv\Scripts\python.exe -m pytest -q --tb=line -p no:cacheprovider tests/test_lingua_powershell.py tests/test_lingua_regex.py tests/test_lingua_cli.py; "exit=$LASTEXITCODE"; Remove-Item Env:EDGE_AGENT_PWSH
```

**7**——先看有沒有裝：

```powershell
Get-Command pwsh.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
```

- 什麼都沒印：報告寫「沒有 PowerShell 7」，跳過，不要安裝。
- 印出一個路徑：執行下面這行（同樣不要拆開）：

```powershell
Set-Location C:\Users\A8fm0\EdgeAgent; $env:EDGE_AGENT_PWSH = (Get-Command pwsh.exe).Source; .\.venv\Scripts\python.exe -m pytest -q --tb=line -p no:cacheprovider tests/test_lingua_powershell.py tests/test_lingua_regex.py tests/test_lingua_cli.py; "exit=$LASTEXITCODE"; Remove-Item Env:EDGE_AGENT_PWSH
```

預期：`exit=0`。要抄的東西跟步驟 4 一樣（`passed` 那行、exit、`FAILED`／`ERROR` 行）。

失敗時：記下來，繼續。

## 6. 預設文字編碼

目的：翻譯器說「Windows 上 Python 開檔的預設編碼不是 UTF-8」，要知道這台實際是什麼。

```powershell
C:\Users\A8fm0\EdgeAgent\.venv\Scripts\python.exe -c "import locale; print(locale.getpreferredencoding(False))"
```

預期：印出一個編碼名稱，例如 `cp950`。照抄進報告。

## 7. Excel

目的：Excel 公式翻譯器有兩條說明，只有真的 Excel 才能驗證。腳本只開一個**新的空白活頁簿**，不存檔，結束時只關掉它自己開的 Excel。使用者自己開著的 Excel 不受影響。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\A8fm0\EdgeAgent\scripts\excel_check.ps1; "exit=$LASTEXITCODE"
```

預期：印出一行 JSON，然後是 `exit=0`。
- 有 Excel：`"excel":true`，`vlookup_past_table` 應該是 `#REF!`，`xlookup_default` 應該是 `#N/A`。舊版 Excel 沒有 XLOOKUP，會是 `#NAME?`，這也照抄。
- 沒有 Excel：`"excel":false`，另外兩個是 `null`。

要抄的：那一行 JSON 原文，和 exit。

失敗時（沒有 JSON，或 exit 不是 0）：抄錯誤訊息的最後 10 行，繼續。

## 8. 瀏覽器檢查

目的：用真的 Edge 檢查 EdgeAgent 網頁。三種模式（工作／求知儀式／推演儀式）、送出時帶的模式，以及批准卡片上「這個指令在做什麼」的說明。腳本會自己開一個**隱藏的、獨立的** Edge，結束時自己關掉。使用者平常用的 Edge 不受影響。

先確認要用的三個埠是空的：

```powershell
Get-NetTCPConnection -State Listen -LocalPort 18087,18090,9223 -ErrorAction SilentlyContinue | Select-Object LocalPort, OwningProcess
```

預期：什麼都不印。

失敗時：有印出東西，就把那幾行抄進報告，**跳過步驟 8**，做步驟 9。不要關掉那些程式。

再執行檢查（大約 1 到 4 分鐘，會載入模型）：

```powershell
Set-Location C:\Users\A8fm0\EdgeAgent; .\.venv\Scripts\python.exe -m tests.windows_check --browser --inference-port 18090; "exit=$LASTEXITCODE"
```

預期：最後幾行裡有 `{"event": "integration_cleanup", "listeners": []}`，然後是 `exit=0`。

要抄的：
- exit；
- `integration_cleanup` 那一行的原文；
- 失敗時，錯誤訊息的最後 15 行。裡面通常有一句英文，說是哪一項檢查沒過，例如 `approval explains the command`。

失敗時：記下來，繼續。

## 9. 上網研究工具

目的：確認 Agent 的 `web_research` 工具在這台電腦上真的能搜尋、讀網頁、挑出段落。腳本只印數字，不印網頁內容。

```powershell
Set-Location C:\Users\A8fm0\EdgeAgent; & .\.runtime\node\node-v22.23.3-win-x64\node.exe scripts\research_check.mjs; "exit=$LASTEXITCODE"
```

預期：一行 JSON，像 `{"pages_read":3,"passages":6,"mentions_2023":true}`，然後是 `exit=0`。數字不必一模一樣。

要抄的：那一行 JSON 原文，和 exit。

失敗時：抄錯誤訊息的最後 10 行，繼續。

## 10. 收尾

目的：把這一回合留下的東西清掉，把 EdgeAgent 恢復成原本的狀態。

```powershell
Set-Location C:\Users\A8fm0\EdgeAgent; if (Test-Path .test-tmp) { Remove-Item -LiteralPath .test-tmp -Recurse -Force }; Test-Path .test-tmp
```
```powershell
Get-NetTCPConnection -State Listen -LocalPort 18087,18090,9223 -ErrorAction SilentlyContinue | Select-Object LocalPort, OwningProcess
```

預期：第一個印出 `False`，第二個什麼都不印。

只有在步驟 1 寫的是「原本在跑」時，才把 EdgeAgent 開回去：

```powershell
C:\Users\A8fm0\EdgeAgent\.venv\Scripts\python.exe -m edge_agent.cli start
```

預期：印出 `EdgeAgent running: ...`。

失敗時：照抄，繼續步驟 11。不要自己去關任何程式。

## 11. 寫報告並推上去

報告寫在 `laptop-report` 分支的 `handoff/reports/laptop.md`。這個分支已經有一個獨立資料夾（worktree），**不要**在 `C:\Users\A8fm0\Downloads\SilentTalk` 裡切換分支。

**11.1 找到報告資料夾**

```powershell
git -C C:\Users\A8fm0\Downloads\SilentTalk worktree list
```

找結尾是 `[laptop-report]` 的那一行，那一行開頭的路徑就是報告資料夾。下面用 `<報告資料夾>` 代表它。

如果沒有這一行，就建立一個：

```powershell
git -C C:\Users\A8fm0\Downloads\SilentTalk worktree add C:\Users\A8fm0\Downloads\SilentTalk-laptop-report laptop-report
```

這時 `<報告資料夾>` 就是 `C:\Users\A8fm0\Downloads\SilentTalk-laptop-report`。

**11.2 拉新報告分支**

```powershell
git -C <報告資料夾> pull --ff-only; "exit=$LASTEXITCODE"
```

**11.3 寫報告**

用你的檔案編輯工具打開 `<報告資料夾>\handoff\reports\laptop.md`。原本的內容不要改，也不用讀；只在**檔案最後面**加上下面這一段，存成 UTF-8。不要用 PowerShell 的 `Add-Content` 或 `Out-File` 寫，它們在 Windows PowerShell 5.1 會把中文寫壞。`<...>` 換成你抄下的原文；沒做的步驟寫「沒做」和原因（例如「步驟 1 停下」）。

```markdown
## 第 2 回合 <今天日期 YYYY-MM-DD>（Antigravity）

- 1_起點：SilentTalk 分支 <...>，git status <空 或 抄那幾行>；EdgeAgent 分支 <...>，git status <...>；EdgeAgent 原本 <停止／在跑>
- 2_拉新版：SilentTalk <舊 commit> -> <新 commit>，exit <n>；EdgeAgent <舊> -> <新>，exit <n>
- 3_部署：bootstrap exit <n>；pip exit <n>；import <imports ok 或錯誤最後一行>
- 4_EdgeAgent 測試：<passed 那一行>；exit <n>；FAILED/ERROR：<無 或 每行原文>
- 4_SilentTalk 測試：<passed 那一行>；exit <n>；FAILED/ERROR：<無 或 每行原文>
- 5_PowerShell 5.1：<passed 那一行>；exit <n>；FAILED/ERROR：<無 或 每行原文>
- 5_PowerShell 7：<passed 那一行；或「沒有 PowerShell 7」>；exit <n>；FAILED/ERROR：<...>
- 6_編碼：<印出的名稱>
- 7_Excel：<JSON 原文>；exit <n>
- 8_瀏覽器：埠檢查 <空 或 抄那幾行>；exit <n>；<integration_cleanup 那一行>；失敗訊息：<無 或 最後 15 行>
- 9_上網研究：<JSON 原文>；exit <n>
- 10_收尾：.test-tmp 還在 <False/True>；監聽埠 <空 或 抄那幾行>；EdgeAgent <維持停止／已開回去：抄印出的那行>
- 停在：<全部做完 或 步驟 N，原因>
```

**11.4 提交並推上去**（commit 訊息照抄）

```powershell
git -C <報告資料夾> add handoff/reports/laptop.md; git -C <報告資料夾> commit -m "laptop report: round 2 checks"; git -C <報告資料夾> push origin laptop-report; "exit=$LASTEXITCODE"
```

預期：`exit=0`。

失敗時：push 被拒絕的話，執行一次 `git -C <報告資料夾> pull --ff-only`，再 push 一次。還是失敗就停下，把錯誤告訴使用者。

## 12. 最後跟使用者說什麼

只說一句話，格式照抄：

「第 2 回合做完：<做完的步驟數>/10 步完成，<有失敗的步驟編號，或「沒有失敗」>，報告已推到 laptop-report。」

不要解釋失敗原因，也不要提議怎麼修。開發機會讀報告，然後處理。
