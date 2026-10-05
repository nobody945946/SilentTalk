# Windows 工作檔：第 3 回合（目標式，做法由你決定）

更新：2026-10-05｜兩個 repo 的開發分支：`copilot-story-mode`｜報告分支：`laptop-report`

你是從 `AGENTS.md` 被分到這裡的。這份給**這台筆電**，Codex 和 Antigravity 都照同一份做。筆電負責的範圍見 `AGENTS.md` 的「分工」。

**這一回合沒有逐步指令。** 下面只寫目標、背景和驗收標準：要讀哪些程式和文件、用什麼指令、怎麼安排順序、怎麼查原因，都由你判斷。`AGENTS.md` §2 的規則照舊適用：
- 隱私和對話紀錄；
- 不碰使用者的檔案；
- 不在 `main` 上 commit；
- 用 PID 關程式；
- 看 pytest 自己的 exit code；
- 從責任所在重寫，不疊補丁。

只有「講話、聽、做決定」需要使用者，其他都是你的事。

如果你是接手別人做到一半的：先看報告分支 `handoff/reports/laptop.md` 的最後一段，從它停下的地方繼續。

## 背景（第 2 回合之後）

- **第 2 回合的結果**（`laptop-report`「第 2 回合」）：
  - 瀏覽器、Excel、上網研究的檢查都通過。
  - 你在 8c9c86a 修好了 PowerShell 5.1 的兩個翻譯器測試。開發機看過：`Get-ChildItem -r` 被當成 `-Recurse` 是一個關於 PowerShell 行為的說法，所以補了一個真的執行它的檢查（`tests/test_lingua_powershell.py` 的 BEHAVIOUR）。
  - 但有 **227 個測試沒跑到**：EdgeAgent 97、SilentTalk 130。原因是 `PermissionError`，`C:\Users\A8fm0\AppData\Local\Temp\pytest-of-A8fm0` 存取被拒，這是工作檔的指令少了 `--basetemp`。上上回合用 repo 裡的暫存資料夾就正常（兩個 repo 的 `.gitignore` 都有 `.test-tmp/`）。
- **之後開發機做了這些**（兩個 repo 都在 `copilot-story-mode`）：
  - EdgeAgent 升到 2.1.0，要重新部署。
  - 兩個 repo 加了授權（PolyForm Strict 1.0.0）。
  - Discord 有了這些新功能（SilentTalk）：
    - 主人在文字頻道 @ bot 會開討論串，串裡各自是一段對話。
    - 主人下令的訊息會加 ⚙️，完成換 ✅、失敗換 ❌。
    - 邀請連結：`discord_voice.BOT_PERMISSIONS`、`invite_url()`、`AppController.invite_link`。
  - Excel 翻譯器現在會說 XLOOKUP 要 Excel 2021 以後才有。這台的 Excel 顯示 `#NAME?`。

## 目標（依序）

### 1. 新版在 Windows 上完整驗證

- 部署 EdgeAgent 2.1.0。兩個 repo 的完整測試要**真的全部跑到**：沒有 setup `ERROR`，`passed`／`skipped` 的數字合理（EdgeAgent 約 180 個、SilentTalk 約 290 個）。
- 在 Windows 上失敗的，找出原因並修好，修在負責的地方。不能用刪測試、加 skip、改預期值或放寬條件來讓它過。
  - 如果你確定是測試本身錯了，在報告裡說明證據，再修測試。
- `Get-ChildItem -r` 的實際行為如果和翻譯器說的不一樣，要讓翻譯器說實話。

### 2. 功能：Discord 實測的數字表（`scripts/dev/log_summary.py`）

- 實測要量延遲和送達，但不能讀對話原文。給這個腳本加上 Agent、批准、私訊、討論串和表情的數字，事件都已經寫進 log：
  - `agent_task_decision`、`agent_task_finished`、`agent_task_dispatch_failed`；
  - `agent_approval_decided`、`agent_approval_failed`、`agent_approval_timeout_failed`；
  - `agent_result_private`、`agent_private_failed`、`private_send_failed`；
  - `thread_opened`、`thread_open_failed`；
  - `task_marked`、`task_mark_failed`。
- 底線：除了事件名稱、數字、True／False 和幾個列舉值，輸出不能有任何文字。要有測試證明，假 log 裡的一句對話不會出現在輸出。

### 3. 功能：設定頁的邀請連結（SilentTalk 設定）

- 在新伺服器，使用者要請管理員加 bot。在設定的 Discord 頁顯示 `AppController.invite_link`，附一個複製按鈕。還沒登入時顯示提示，說明連上 Discord 後才會出現。
- 權限清單和網址只能來自 `discord_voice.py`，不要另寫一份。README 有這條連結，也有測試檢查它和權限清單一致；介面完成後，README 補一句可以從哪裡複製。
- 要有測試。

### 4. Discord 實測（需要使用者，先問他現在方不方便）

- **範圍**：
  - 只用測試伺服器 `729722190857240717`（語音頻道 `729722190857240721`），文字頻道請使用者挑。
  - Agent 的工作區只放測試資料夾 `C:\Users\A8fm0\EdgeAgentTest`；資料夾要有 2 個 `.tmp` 和幾個其他檔案。
  - 設定和批准由使用者自己按，一次只請他做一件事。
- **要確認的事**：
  - bot 的權限用設定頁的邀請連結補齊。
  - 語音頻道聊天室裡打字下令：⚙️ 會變成 ✅，角色用說的接令和回報，結果在私訊。
  - 文字頻道 @ bot：
    - 會開出討論串，⚙️ 會變成 ✅；
    - 串裡沒有接令或完成的訊息；
    - 串裡不 @ 也會回；
    - 原頻道不會被洗版。
  - 在討論串要刪 `.tmp`：
    - 批准只在私訊，附「這個指令在做什麼」；
    - 拒絕後檔案都在，准許後只少 `.tmp`。
  - 用說的下令不會派工。
  - 第二個帳號下令被擋、閒聊照常。沒有第二個帳號就寫沒測，不要用 webhook 或 bot 代替。
  - 最後用你在目標 2 做的數字表量延遲和送達。
- **結束後**：
  - 測試資料夾留著；
  - 設定要不要改回、程式要不要關，問使用者；
  - 你自己留下的暫存和程序清乾淨。

## 回報

寫在 `handoff/reports/laptop.md` 的最後面，推到 `laptop-report`（用既有的 worktree，不要在主資料夾切分支）。格式你決定，但要有：
- 每個目標做到哪裡，沒做到的原因；
- 每次測試的 `passed`／`failed`／`skipped`／`error` 和 exit code；
- 每個修正的原因、改了哪些檔案和 commit 雜湊；
- 實測每一項的結果，用有／沒有、成功／失敗表示，加上數字表原文；
- 使用者自己說的感想（原話）；
- 你用的是哪個 agent 和模型。

報告不寫對話內容、檔名清單以外的私人資料。最後跟使用者用一兩句話說結果。

開發機會讀報告，也會看你的每個 commit。

## 之後（這回合不要做）

- 第 4 回合：加密外接硬碟和對話紀錄的設定（需要使用者），加上 EdgeAgent 的紀錄設定介面。
- 第 5 回合：MCP 設定介面和啟用。
- 人設匯入／匯出和馬基納人設：等馬基納做好再做。
- 「推演儀式」改成正式名稱：要等使用者命名。
