# Windows 工作檔：第 16 回合（選項模式已移除：拉新版、用使用者的設定載入一次）

更新：2026-10-15｜SilentTalk `copilot-story-mode`｜回報 `laptop-report`｜上一版：開發機 `archive/laptop-2026-10-15-round15.md`（不必讀）

## 為什麼有這一回合

1. **使用者 2026-10-15 結案語音試用**（第 15 回合回報 `ed6573d`）：選項模式移除以省效能；不再做真人測試，也不擴張語音辨識改良。
2. **開發機已移除選項模式**（`9f29c2a`）：對話頁只剩「角色」和「打字」；角色沒開時，聽到的話只轉錄、顯示、記錄，不再向模型要四個候選回覆（之前打字頁也會一直生）。設定頁少了「想好就自動跳出視窗」。舊的 `settings.json` 若在 `character_lora_uses` 寫了 `options`，新版會略過它照常啟動。開發機已跑完整套測試、用虛擬螢幕跑過 `scripts/dev/ui_preview.py` 的流程（打字 Enter 說出、心情選單、角色頁），GitHub 的 Windows 測試也會跑。
3. **筆電只做開發機做不到的兩件事：** 把新版拉到使用者的 SilentTalk，並用**使用者真正的設定**載入一次（開發機沒有他的 `settings.json`）。不開 GUI、不連 Discord、不跑模型，也不請使用者做任何事。

## 通道

信箱一律用 `st-channel`（只傳 metadata，不傳對話內容、憑證、使用者檔案；訊息文字不要有 `'` 或 `"`）：

- **收：** `ssh st-channel python3 /home/clawd/SilentTalk/scripts/dev/channel.py wait laptop`（有信立刻印出，每行一則含 `id`；沒信就等）。
- **標記：** `ssh st-channel python3 /home/clawd/SilentTalk/scripts/dev/channel.py done laptop <id> [<id> ...]`。
- **送：** `ssh st-channel python3 /home/clawd/SilentTalk/scripts/dev/channel.py send devbox <received|report|note> "<一句話>"`。
- **被喚醒器叫起來的那一輪**（提示是「開工。這一輪是筆電的喚醒器……」）：照 AGENTS.md 拉新版、讀這份，再「收」一次。如果 `laptop-report` 上最新回報已經是「第 16 回合：完成」，就只處理信：每則 `note` 回一則 `note`（寫「waker run ok <id>」和你做了什麼），`done` 全部，然後結束，不重做這回合。
- **使用者自己開 Codex 時：** 先看 `<ST>\.runtime\laptop-agent.json`；檔案在、而且裡面的 `pid` 還活著（`Get-Process -Id <pid>`），就是喚醒器開的那一輪正在做，告訴使用者，不要同時開工。

## 步驟

`<ST>` 是 `C:\Users\A8fm0\Downloads\SilentTalk`。每一步失敗時照該步寫的處理；沒寫的就停下，把錯誤最後 20 行寫進回報，跳到第 5 步。每個指令只跑一次，不寫等待迴圈。

1. **拉新版：**
   ```powershell
   git -C <ST> pull --ff-only
   git -C <ST> merge-base --is-ancestor 9f29c2a HEAD; $LASTEXITCODE
   ```
   預期：pull 成功，印 `0`。EdgeAgent 這回合不動。
2. **收件：** `ssh st-channel python3 /home/clawd/SilentTalk/scripts/dev/channel.py send devbox received "round 16 <ST HEAD 前 7 碼>"`，然後「收」一次並 `done` 收到的 round 訊息。
3. **用使用者的設定載入一次：**
   ```powershell
   Set-Location <ST>
   .\.venv\Scripts\python.exe -c "from pathlib import Path; from silenttalk.config import load_settings; s = load_settings(Path('.')); print('settings ok', s.copilot.enabled, list(s.copilot.character_lora_uses))"
   ```
   預期：印出一行 `settings ok ...`，exit 0。只把這一行抄進回報（它不含金鑰或對話）。印出設定錯誤就**不要改 `settings.json`**：把錯誤那一行抄進回報，`send devbox note "round 16 settings load failed"`，繼續第 4 步。
4. **SilentTalk 是否正在跑（只看，不關）：**
   ```powershell
   Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object CommandLine -like '*app.py*' | Select-Object ProcessId, Name
   ```
   記下有幾個。正在跑的話不要關它（使用者可能正在用）；新版在他下次開 SilentTalk 時生效，回報寫這句。
5. **送回報並結束：** 整份換掉 `handoff/reports/laptop.md`，推 `laptop-report`，然後 `send devbox report "laptop-report <sha> round 16 <完成或卡在第 N 步>"`。
   - 開頭寫「第 16 回合：完成」或「第 16 回合：卡在第 N 步」。
   - 版面沿用固定十節：機魂劇本（本回合無）／時間與額度／目標完成度（分母 4：第 1–4 步各 1）／測試執行結果（只有數字與指令結果）／修改檔案與 commit／記憶體與速度（本回合無）／Discord 數字表（本回合無）／紀錄目錄（本回合沒碰）／使用者回饋（本回合沒有新的就寫「無」）／給接手模型的交接指示。
   - 送完就結束這一輪，不要再開「收」；之後的信由喚醒器接。

## 不變的規則

- 同一台機器一次只開一個 agent。不讀另一台的工作檔，也不讀使用者的對話紀錄、`personas.json`、`character_state.json`。
- 不動 `.env`、`settings.json`；設定只從設定頁改。紀錄只用 `C:\Users\A8fm0\AgentRecords`，這回合不碰。
- 對話內容和角色狀態不進回報。使用者只負責講話、聽和做決定，不做雜事，也不要請他測東西。
- 關程式只用核對過的 PID。常駐程式只有使用者核准的喚醒器；不新增其他迴圈、排程、log 檔。
- 推 commit 之後等那次 push 的 GitHub 檢查跑完；失敗就修好再結束，修不了寫進回報並 `note` 開發機。
