# Windows 工作檔：第 2 回合，Windows 驗證，失敗的當場修（不需要使用者）

更新：2026-10-05｜兩個 repo 的開發分支：`copilot-story-mode`｜報告分支：`laptop-report`

你是從 `AGENTS.md` 被分到這裡的。這份是給**這台筆電**的，不管你是 Codex 還是 Antigravity 都照同一份做。

這一回合分兩段：
- **先驗證**（步驟 1–9）：跑指令、抄結果。這些檢查需要的程式，開發機都寫好了。
- **再修**（步驟 10）：只修驗證中在 Windows 上失敗的地方。開發機是 Linux，測不到 Windows，所以這部分交給你。

## 0. 先讀完這一段再開始

### 0.1 禁止事項（整個回合都適用）

1. **只修步驟 10 列出的失敗**：不做其他功能，不重構，也不「順便」改看不順眼的地方。
2. **不改測試**：不刪測試、不加 skip、不改預期值、不放寬判斷條件。只改產品程式。你認為該改的是測試本身的話，就不修，寫進報告。
3. **不讀無關的文件**：不讀 README、ARCHITECTURE、`archive/`、`handoff/dev-box.md`。報告檔只讀最後一段（步驟 0.4）。程式碼只讀錯誤訊息指到的檔案和相關部分。
4. **不安裝這裡沒列的東西**：包括 PowerShell 7、LibreOffice、Docker、任何 MCP 伺服器。
5. **不碰使用者的私人檔案**：不讀不改 `.env`、`settings.json`、`personas.json`、`character_state.json`、`silenttalk.log`；不開使用者的任何文件或 Excel 檔。
6. **危險的 git 指令一律不用**：`git stash`、`git reset`、`git clean`、`git push --force`。唯一的例外是步驟 10 裡的 `git restore`，而且只能用在你自己這一回合改過的檔案。
7. **不用名稱關程式**：不用 `Stop-Process -Name`、`taskkill /IM`、`pkill`。只用這份檔案給的指令。
8. **不啟動 SilentTalk、不連 Discord、不在 EdgeAgent 設定裡啟用 MCP。**
9. **驗證用的指令一字不改地照抄**，不要多跑別的測試或腳本。
10. **報告只寫事實**：指令輸出的原文片段、數字、exit code、commit 雜湊。不寫推測、建議或心得。

### 0.2 怎麼執行指令

- 所有指令都是 **PowerShell**。每個程式碼區塊**整塊當成一個指令**執行；如果你的工具一次只能跑一行，就照順序一行一行跑，而且**同一行裡用 `;` 串起來的部分不要拆開**（拆開的話，環境變數會不見）。
- 每個指令後面的 `"exit=$LASTEXITCODE"` 會印出 `exit=數字`。**報告的 exit code 一律抄這個數字**，不要自己判斷。
- 部署和測試可能要跑 15 分鐘。只要畫面還在出新的輸出就等。**超過 20 分鐘完全沒有新輸出**才按 Ctrl+C 停掉，報告寫「逾時」，然後做下一步。
- 每一步做完，**馬上**把結果寫進報告草稿（格式見步驟 12）。不要等到最後才憑記憶寫。

### 0.3 遇到計畫外的狀況

- 輸出跟「預期」不一樣：照那一步的「失敗時」做。沒寫「停下」的，就記下來，繼續下一步。
- 寫著「**停下**」的：後面的步驟都不做，直接跳到步驟 12 寫報告，最後一行寫「停在步驟 N」。
- **額度快用完時**也一樣：手上的修改如果已經通過步驟 10 的檢查，就先提交；沒通過的，用 `git restore` 還原。然後直接跳到步驟 12，寫「停在步驟 N（額度）」並推上去。下一個 agent 會從那裡接手。
- 不知道怎麼辦：**不要猜**。停下，用一句話問使用者，等他回答。

### 0.4 先看是不是接手別人做到一半的

先照步驟 12.1 找到報告資料夾，再執行：

```powershell
git -C <報告資料夾> pull --ff-only; Get-Content -Encoding UTF8 -Tail 20 <報告資料夾>\handoff\reports\laptop.md
```

- 最後一段的標題是「第 2 回合」，而且最後一行是「停在步驟 N」：你是接手的。先做步驟 1（確認起點），再從步驟 N 接著做。報告新開一段，標題寫「第 2 回合（續，從步驟 N）」。
- 其他情況：從步驟 1 開始。

## 1. 確認起點

目的：確認兩個 repo 在對的分支、沒有沒存的修改，並看 EdgeAgent 現在是什麼狀態。

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

失敗時：任何一個沒有達到預期，就**停下**，把錯誤訊息的最後 10 行抄進報告。部署不在這回合的修理範圍。

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

失敗時：記下來，繼續步驟 5。等到步驟 10 再修。

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

失敗時（沒有 JSON，或 exit 不是 0）：抄錯誤訊息的最後 10 行，繼續。值跟預期不同的話，**不修**，只抄進報告；翻譯器的說明要不要改，由開發機決定。

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

## 10. 修 Windows 上的失敗

步驟 4、5、8、9 都通過的話，報告寫「沒有要修的」，跳到步驟 11。

**不修的**（只抄進報告）：
- 失敗訊息說的是連不上外部網站或服務，例如 HTTP 503、timeout、DNS；
- 要裝這份檔案沒列的東西才會好的；
- 你判斷該改的是測試本身的（見 0.1 第 2 條）。

其他的失敗，**一個一個**照下面做。每個失敗最多試 **2 次**。

1. **抄下失敗**：測試名稱和錯誤訊息的原文。
2. **找負責的程式**：只讀錯誤訊息指到的檔案。修改要放在負責那件事的地方（`AGENTS.md` 規則 8），不要在別處加特例去補。
3. **改**：只改產品程式，越少越好。
4. **先跑失敗的那個測試**（把 `<測試>` 換成像 `tests/test_lingua_powershell.py::test_windows_aliases` 的名稱）：
   ```powershell
   Set-Location <那個 repo 的資料夾>; .\.venv\Scripts\python.exe -m pytest -q --tb=line -p no:cacheprovider <測試>; "exit=$LASTEXITCODE"
   ```
   如果它是在步驟 5 失敗的，前面要加上跟步驟 5 一樣的 `$env:EDGE_AGENT_PWSH = ...;`，同一行不要拆開。瀏覽器的失敗，就重跑步驟 8 的檢查。
5. **再跑那個 repo 的完整測試**（步驟 4 的指令）。條件：`FAILED`／`ERROR` 的行，只能比步驟 4 少，不能多出新的。
6. **通過**：提交並推上去。commit 訊息用英文寫一句，開頭寫 `Windows: `：
   ```powershell
   Set-Location <那個 repo 的資料夾>; git add <你改的檔案>; git commit -m "Windows: <一句話說修了什麼>"; git push origin copilot-story-mode; "exit=$LASTEXITCODE"; git rev-parse --short HEAD
   ```
   `git add` 只加你改的檔案，不要用 `git add .` 或 `-A`。
7. **試了 2 次還沒通過**：還原你改的檔案，報告寫「沒修好」和最後一次的錯誤訊息：
   ```powershell
   Set-Location <那個 repo 的資料夾>; git restore -- <你改的檔案>; git status --short
   ```
   `git status --short` 應該什麼都不印。

每個失敗在報告寫一行：測試名稱、修好或沒修好、改了哪些檔案、commit 雜湊。

## 11. 收尾

目的：把這一回合留下的東西清掉，把 EdgeAgent 恢復成原本的狀態。

```powershell
Set-Location C:\Users\A8fm0\EdgeAgent; if (Test-Path .test-tmp) { Remove-Item -LiteralPath .test-tmp -Recurse -Force }; Test-Path .test-tmp
```
```powershell
Get-NetTCPConnection -State Listen -LocalPort 18087,18090,9223 -ErrorAction SilentlyContinue | Select-Object LocalPort, OwningProcess
```
```powershell
git -C C:\Users\A8fm0\EdgeAgent status --short; git -C C:\Users\A8fm0\Downloads\SilentTalk status --short
```

預期：第一個印出 `False`，第二個和第三個什麼都不印（你的修改都已提交）。

只有在步驟 1 寫的是「原本在跑」時，才把 EdgeAgent 開回去：

```powershell
C:\Users\A8fm0\EdgeAgent\.venv\Scripts\python.exe -m edge_agent.cli start
```

預期：印出 `EdgeAgent running: ...`。

失敗時：照抄，繼續步驟 12。不要自己去關任何程式。

## 12. 寫報告並推上去

報告寫在 `laptop-report` 分支的 `handoff/reports/laptop.md`。這個分支已經有一個獨立資料夾（worktree），**不要**在 `C:\Users\A8fm0\Downloads\SilentTalk` 裡切換分支。

**12.1 找到報告資料夾**

```powershell
git -C C:\Users\A8fm0\Downloads\SilentTalk worktree list
```

找結尾是 `[laptop-report]` 的那一行，那一行開頭的路徑就是報告資料夾。下面用 `<報告資料夾>` 代表它。

如果沒有這一行，就建立一個：

```powershell
git -C C:\Users\A8fm0\Downloads\SilentTalk worktree add C:\Users\A8fm0\Downloads\SilentTalk-laptop-report laptop-report
```

這時 `<報告資料夾>` 就是 `C:\Users\A8fm0\Downloads\SilentTalk-laptop-report`。

**12.2 拉新報告分支**

```powershell
git -C <報告資料夾> pull --ff-only; "exit=$LASTEXITCODE"
```

**12.3 寫報告**

用你的檔案編輯工具打開 `<報告資料夾>\handoff\reports\laptop.md`。原本的內容不要改；只在**檔案最後面**加上下面這一段，存成 UTF-8。不要用 PowerShell 的 `Add-Content` 或 `Out-File` 寫，它們在 Windows PowerShell 5.1 會把中文寫壞。`<...>` 換成你抄下的原文；沒做的步驟寫「沒做」和原因（例如「步驟 1 停下」）。

```markdown
## 第 2 回合 <今天日期 YYYY-MM-DD>（<Codex 或 Antigravity，和模型名稱>）

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
- 10_修正：<沒有要修的；或每個失敗一行：測試名稱｜修好／沒修好／不修（原因）｜改的檔案｜commit 雜湊>
- 10_修正後完整測試：EdgeAgent <passed 那一行>，exit <n>；SilentTalk <passed 那一行>，exit <n>（沒修就寫「沒跑」）
- 11_收尾：.test-tmp 還在 <False/True>；監聽埠 <空 或 抄那幾行>；git status <空 或 抄那幾行>；EdgeAgent <維持停止／已開回去：抄印出的那行>
- 停在：<全部做完 或 步驟 N，原因>
```

**12.4 提交並推上去**（commit 訊息照抄）

```powershell
git -C <報告資料夾> add handoff/reports/laptop.md; git -C <報告資料夾> commit -m "laptop report: round 2 checks"; git -C <報告資料夾> push origin laptop-report; "exit=$LASTEXITCODE"
```

預期：`exit=0`。

失敗時：push 被拒絕的話，執行一次 `git -C <報告資料夾> pull --ff-only`，再 push 一次。還是失敗就停下，把錯誤告訴使用者。

## 13. 最後跟使用者說什麼

只說一句話，格式照抄：

「第 2 回合做完：<做完的步驟數>/11 步完成，修好 <n> 個、沒修好 <n> 個，報告已推到 laptop-report。」

不要解釋失敗原因，也不要提議下一步。開發機會讀報告和你的 commit，然後處理。
