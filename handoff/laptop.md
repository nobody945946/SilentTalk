# Windows 工作檔：第 15 回合（裝喚醒器：筆電收到訊息就自己開工）

更新：2026-10-14｜SilentTalk `copilot-story-mode`｜回報 `laptop-report`｜上一版：開發機 `archive/laptop-2026-10-14-round14.md`（不必讀）

## 為什麼有這一回合

1. **第 14 回合 10/17**：第 1–5、7–11 步過；第 6 步（pythonw 開機啟動）被工具政策擋下，保持原樣不繞過；Discord V1–D4 依使用者 2026-10-14 的話延後（「只做 Agent 的事，不要再請他測聊天機器人」）。這回合不碰 Discord，也不請使用者測任何東西。
2. **Codex 一輪結束後，沒有東西能叫醒它**，交接在信箱裡放了 16 小時。使用者 2026-10-14 選了「裝事件喚醒器」：登入時用 pythonw 啟動一支常駐小程式（`scripts/dev/laptop_waker.py`），透過 SSH 在開發機的信箱上等、也等 Windows 的網路變化；有新訊息就開一次全新的 `codex exec`（固定提示「開工」，不帶訊息內容），做完就結束。它不定時詢問；只有連線失敗時才等一下再連（1 分鐘起、加倍、最多 30 分鐘，網路一變就立刻重連）。第 14 回合做的 Stop hook 已撤掉，只留這一套。
3. **信箱改了（開發機已部署）：** `wait` 不再刪訊息，印出的每行 JSON 多一個 `id`；做完要 `done <id>` 才刪。這樣 SSH 斷掉時，留在開發機的舊等待者不會把訊息吃掉。另有 `wait laptop --after <id>`（喚醒器用）。
4. **通道金鑰**：你 19:12 送來的 `silenttalk-channel-laptop` 公鑰，開發機已加進 authorized_keys，強制只能跑 `channel.py gate`：只能等、標記筆電的信，和寄信給開發機，其他指令一律拒絕。它沒有密碼，所以沒人在時喚醒器也能用。

## 通道（這回合起）

`<DEV>` 是你原本連開發機的 SSH 主機（完整權限，跟著 VS Code session）；`st-channel` 是第 3 步新增的主機名（通道金鑰，只能用信箱）。信箱操作一律用 `st-channel`。只傳 metadata，不傳對話內容、憑證、使用者檔案；訊息文字不要有 `'` 或 `"`。

- **收：** `ssh st-channel python3 /home/clawd/SilentTalk/scripts/dev/channel.py wait laptop`：有信就立刻印出（每行一則，含 `id`）後結束；沒信就等到有信。
- **標記：** 讀完、回了 `received` 之後：`ssh st-channel python3 /home/clawd/SilentTalk/scripts/dev/channel.py done laptop <id> [<id> ...]`。
- **送：** `ssh st-channel python3 /home/clawd/SilentTalk/scripts/dev/channel.py send devbox <received|report|note> "<一句話>"`。
- **被喚醒器叫起來的那一輪**（提示是「開工。這一輪是筆電的喚醒器……」）：照 AGENTS.md 拉新版、讀這份，再「收」一次。如果 `laptop-report` 上最新回報已經是這份工作檔那一回合的「完成」，就只處理信：每則 `note` 回一則 `note`（內容寫「waker run ok <id>」和你做了什麼），`done` 全部，然後結束，不重做這回合。需要使用者在場的步驟記成「待真人」，不要等。
- **使用者自己開 Codex 時：** 先看 `<ST>\.runtime\laptop-agent.json`；檔案在、而且裡面的 `pid` 還活著（`Get-Process -Id <pid>`），就是喚醒器開的那一輪正在做，告訴使用者，不要同時開工。

## 步驟

每一步失敗時，照該步寫的處理；沒寫的就停下，把錯誤最後 20 行寫進回報，跳到第 8 步。`<ST>` 是 `C:\Users\A8fm0\Downloads\SilentTalk`。「查一次」就是只跑一次指令；不寫等待迴圈。

1. **拉新版：**
   ```powershell
   git -C <ST> pull --ff-only
   git -C <ST> merge-base --is-ancestor c72f947 HEAD; $LASTEXITCODE
   ```
   預期：pull 成功，印 `0`。EdgeAgent 這回合不動。
2. **收件：** 用 `<DEV>`（通道金鑰第 3 步才設好）：`ssh <DEV> python3 /home/clawd/SilentTalk/scripts/dev/channel.py send devbox received "round 15 <ST HEAD 前 7 碼>"`。
3. **通道主機名：** 在 `%USERPROFILE%\.ssh\config` 加一段（`HostName`、`Port`、`User` 抄你 `<DEV>` 現在用的值）：
   ```
   Host st-channel
       HostName <同 DEV>
       Port <同 DEV>
       User <同 DEV>
       IdentityFile ~/.ssh/silenttalk_channel
       IdentitiesOnly yes
       BatchMode yes
   ```
   驗收（各查一次）：
   - `ssh st-channel python3 /home/clawd/SilentTalk/scripts/dev/channel.py send devbox note "channel key works"`：印出一行 JSON，exit 0。
   - `ssh st-channel id`：被拒（印 `refused: ...`），exit 不是 0。
   - `ssh st-channel python3 /home/clawd/SilentTalk/scripts/dev/channel.py wait laptop`：立刻印出開發機的 round 訊息（含 `id`）。接著 `done laptop <那些 id>`，預期印出刪掉的數量。
   金鑰檔權限只給你和 SYSTEM（上回合已設好，查一次就好）。
4. **找 codex 和無人時的權限：**
   - codex 用 VS Code 擴充套件裡的那支，路徑用萬用字元（擴充套件更新後資料夾會改名，喚醒器每次開工時自己挑最新的）：`$env:USERPROFILE\.vscode\extensions\openai.chatgpt-*-win32-x64\bin\windows-x86_64\codex.exe`。`Get-ChildItem` 那個樣式，預期至少一個。
   - `& <那支 codex> exec --help`，找出沙箱和核准相關選項。無人時的 run 要能跑 git（fetch、push 到 `laptop-report`）和 `ssh st-channel`，而且沒人能按核准。**選最少的權限**：先試使用者現有設定（不加選項）；不夠才加「工作區可寫＋允許網路」那類選項。**不要**用 `--dangerously-bypass-approvals-and-sandbox` 或同等的全開選項，不改使用者的 Codex 設定檔；最少權限也做不到就停下，在回報寫清楚缺什麼。
   - 試跑一次（前景，等它結束）：叫它只做三件事然後結束：`git -C <ST> fetch origin`、`git -C <ST> push --dry-run origin HEAD:laptop-report`、`ssh st-channel python3 /home/clawd/SilentTalk/scripts/dev/channel.py send devbox note "exec probe ok"`。預期：exit 0，開發機收到 `exec probe ok`。記下最後用的選項。
5. **裝喚醒器：**
   ```powershell
   <ST>\.venv\Scripts\python.exe <ST>\scripts\dev\laptop_waker.py install --dev st-channel --codex "<第 4 步的萬用字元路徑>" --codex-arg=<選項1> --codex-arg=<選項2>
   ```
   （第 4 步沒加選項就不要 `--codex-arg`。）預期印出 Startup 資料夾裡 `SilentTalk laptop waker.cmd` 的路徑。`Get-Content` 看一次：一行 `start "" ...pythonw.exe ...laptop_waker.py run --dev st-channel --codex ...`。
   然後現在就啟動一次：`cmd /c "<印出的 .cmd 路徑>"`。被工具政策擋下（像第 14 回合第 6 步）就不要繞過：記下來（它下次登入會自己啟動），跳到第 7 步。
6. **它在跑：** 各查一次：
   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object CommandLine -like '*laptop_waker.py*' | Select-Object ProcessId, CommandLine
   Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" | Where-Object CommandLine -like '*st-channel*' | Select-Object ProcessId, CommandLine
   ```
   預期：各一個（ssh 那個是 `... wait laptop`）。再跑一次 `cmd /c "<.cmd 路徑>"`，再查一次：pythonw 仍只有一個（第二個發現已有喚醒器就自己結束）。
7. **送回報並交給喚醒器：** 整份換掉 `handoff/reports/laptop.md`，推 `laptop-report`，然後 `send devbox report "laptop-report <sha> round 15 <完成或卡在第 N 步>"`。
   - 開頭寫「第 15 回合：完成」或「第 15 回合：卡在第 N 步」。
   - 版面沿用固定十節：機魂劇本（本回合無）／時間與額度／目標完成度（分母 7：第 1–7 步各 1）／測試執行結果（只有數字與指令結果）／修改檔案與 commit／記憶體與速度（喚醒器和 ssh 各用多少記憶體）／Discord 數字表（本回合無）／紀錄目錄（本回合沒碰）／使用者回饋／給接手模型的交接指示（寫第 4 步選的選項）。
   - **送完就結束這一輪，不要再開「收」**：之後的信由喚醒器接。開發機會送一則測試訊息，由喚醒器開的那一輪回覆，那就是端到端驗收（開發機記錄結果）。
8. **卡住時：** 照第 7 步的版面寫回報、推、`send devbox report`。喚醒器沒裝好的話，最後開一次「收」等開發機回覆。

## 不變的規則

- 同一台機器一次只開一個 agent。不讀另一台的工作檔，也不讀使用者的對話紀錄、`personas.json`、`character_state.json`。
- 不動 `.env`、`settings.json`；設定只從設定頁改。紀錄只用 `C:\Users\A8fm0\AgentRecords`，只查數量、大小、時間。
- 對話內容和角色狀態不進回報。使用者只負責講話、聽和做決定，不做雜事，也不要請他測東西。
- 關程式只用核對過的 PID。常駐程式只有使用者核准的喚醒器；不新增其他迴圈、排程、log 檔。
- 推 commit 之後等那次 push 的 GitHub 檢查跑完；失敗就修好再結束，修不了寫進回報並 `note` 開發機。
