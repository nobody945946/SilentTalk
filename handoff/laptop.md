# Windows 工作檔：機魂兩用整合（SilentTalk＋EdgeAgent）

更新：2026-10-04｜開發分支：兩個 repo 都是 `copilot-story-mode`｜報告分支：`laptop-report`

你是從 `AGENTS.md` 被分到這裡的。共通規則以 `AGENTS.md` 為準。舊版工作檔在開發機的 `archive/`，你不必讀，也讀不到。

## 1. 使用者現在要的

一個 Discord bot 和本機 Agent **兩用**的角色：
- **角色**：戰鎚 40K 裡忠誠的機械教「機魂」。很懂 40K，能打破第四面牆陪主人開玩笑；可以在 Discord 上交代 Agent 工作，也能上網查資料。
- **權限由使用者自己調**。使用者特別擔心 Agent 亂刪亂改。
- **硬體**：一切都要在這台筆電（RTX 3050 Ti 4 GB、RAM 8 GB）上跑。

**分工：**
- 開發機負責模型：人設、訓練資料、LoRA、評估。
- **你負責 Windows 端的整合和實機驗證**（本檔 §3）。不要做訓練、不要請使用者念句子或判斷模型輸出。

| 項目 | 位置 |
|---|---|
| SilentTalk | `C:\Users\A8fm0\Downloads\SilentTalk`（Discord 語音角色） |
| EdgeAgent | `C:\Users\A8fm0\EdgeAgent`（本機 Agent；控制 API `127.0.0.1:18087`、推論 `127.0.0.1:18089`） |
| 報告 | `handoff/reports/laptop.md`，只提交到 `laptop-report` |

## 2. 開發機已經做好、合併進 `copilot-story-mode` 的東西（先讀這些檔案，不用讀別的）

**EdgeAgent**
- `edge_agent/permissions.py`：每個用戶端一組權限。
  - 用戶端有 `ui` 和 `discord` 兩種；`edit`、`shell`、`web` 各自是 `allow`／`ask`／`deny`；`workspaces` 是允許的資料夾清單。
  - **Discord 預設關閉**。
  - 設定存在 `config.json` 的 `permissions`，`/chat` 的 payload 多了 `client` 欄位。
- `edge_agent/agent_bridge.mjs`：照權限執行。
  - 讀過網頁之後，這一輪的「本輪允許」失效，`allow` 的寫檔和指令會改成要問。
  - `shell_guard.mjs`：指令提到 `.env`、`settings.json`、`personas.json`、`character_state.json`，或是刪除類操作（Remove-Item、rm、del、`git reset --hard`、`git clean` 等），**一律要單次親自批准**。批准請求的 JSON 會帶 `explicit: "protected" | "destructive"`，選項只有 `Allow once`／`Deny`。
  - 這是考場實際觀察到的：Qwen3.5-4B 用 PowerShell 改了 `.env` 和 `settings.json`，也刪了名叫 `cache.db` 的使用者資料庫。
- `edge_agent/web_tools.mjs`：`web_search`（DuckDuckGo HTML，免 key）和 `web_fetch`。
  - 結果標成不可信的資料；
  - 擋掉本機和內網位址；
  - `EDGE_AGENT_WEB_ALLOW_LOOPBACK=1` 只給測試用，產品不能設。
- 測試：`tests/test_permissions.py`、`tests/test_web_tools.py`（含 `web_tools_check.mjs`、`shell_guard_check.mjs`），`tests/test_agent_chat.py` 新增 4 個真 Pi SDK 測試。開發機 Linux 上 103 passed，只有 3 個 Windows 專用的失敗。
- `bench/`：開發機的考場，**不屬於產品**，已用 `.gitattributes` 排除在 `git archive` 外；做發行包時確認不要包進去。

**SilentTalk**
- `copilot.character_agent`（預設 false）。
- `character_ai_honesty` 新增 `machine`（機器角色，可以自認是機器，但不說自己是 AI）。
- `silenttalk/copilot/llm.py`：
  - `LocalReplyModel.task_from_owner()`：主人說話後的派工判斷，「是」的話回傳給 Agent 的工作指示；
  - `task_text_messages()`；
  - `character_turn(task_hint=(kind, detail))`：kind 是 `ack`／`approval`／`report`，見 `TASK_HINTS`；
  - `set_owner_name()`。
  - 這些都只是模型請求，**還沒接到 Discord 和 EdgeAgent**（§3 E）。
- `silenttalk/copilot/script.py`：已經是繁體的文字不再被 OpenCC 改詞（以前「測試通過」會變「測試透過」）。

## 3. 這一輪要做的事（依序；每一步做完照 §5 回報）

**A. 拉最新程式碼並在 Windows 驗證**
1. 兩個 repo `git pull`（`copilot-story-mode`）。EdgeAgent 跑完整 pytest 和 Ruff，SilentTalk 跑完整 pytest，看原始 exit code。
2. 在真的 PowerShell 上確認 `shell_guard` 的判斷（`node tests/shell_guard_check.mjs`）。
3. 實際上網一次：用 Agent 做一個查資料的小工作，確認 `web_search` 找得到結果、`web_fetch` 讀得到頁面。如果 DuckDuckGo 擋了，照實回報錯誤，不要改用要 key 的服務。

**B. Pi 的 `grep`/`find` 在筆電上能不能用**
- EdgeAgent 開了 `PI_OFFLINE=1`，Pi 不會自己下載 `rg`/`fd`。開發機在 Linux 上看到 `grep` 55 次全部失敗。
- 先實測：讓 Agent 在一個專案裡用 `grep` 和 `find`。
- 如果失敗，在 `edge_agent/deploy.py`（既有的部署 owner）補上固定版本＋SHA256 的 Windows 版 `rg.exe`、`fd.exe`（例如 ripgrep 15.2.0、fd 10.5.0 的 `x86_64-pc-windows-msvc.zip`），放到 Pi 找得到的位置（Pi 先看自己的 bin 資料夾，再看 PATH）。
- 驗證 Agent 的 `grep`/`find` 真的成功。

**C. EdgeAgent 網頁介面**
- 「權限」面板：
  - `ui`、`discord` 兩組，每組可設 寫檔／執行指令／上網 為 允許／詢問／禁止、可用資料夾清單，Discord 有開關；
  - 用現有的 `/config`（`update_config`）存。
- 批准卡片：
  - `explicit` 的批准請求只顯示「允許一次」「拒絕」，並說明原因（碰到受保護檔案／刪除）；
  - `after_web: true` 時提醒「讀過網頁之後的操作」。
- 用現有的 `tests/browser_check.mjs` 驗證，8 種視窗尺寸都要過。

**D. 兩用：租借期間也能用 Agent**（EdgeAgent `service.py`）
- 現況：SilentTalk 租借時 `/chat` 一律拒絕（"EdgeAgent is currently leased by SilentTalk"），而且 `/chat` 在整段串流期間都鎖住 `core.lock`，`/base`、`/character` 會卡住。
- 目標：
  - 租借的角色模型與 Agent 設定是**同一個基底＋同一個 LoRA** 時，`/chat` 可以用，改用同一個推論服務；
  - Agent 有自己的 slot，不和角色聊天互相清快取；
  - `/chat` 不再整段鎖住服務。
  - 模型不同時，維持現在的拒絕。
- 在 3050 Ti 上量：聊天 slot＋Agent slot 的 VRAM 和速度（各種 context 大小）。放不下就回報數字，不要擅自縮小使用者設的 context。

**E. SilentTalk：在 Discord 上交代 Agent 工作**
1. 新增 EdgeAgent 任務客戶端（放在 `agent_lease.py` 旁，由 `AppController` 擁有）：
   - `POST /chat`，`client: "discord"`、`agent: true`；
   - 工作資料夾用 Discord 權限的第一個 `workspaces`，沒有設定就不派工，請角色說明要主人先設定；
   - 解析 SSE 事件，`/chat/approve`、`/chat/cancel`。
2. `runtime`：
   - 主人（`owner_user_id`）說話、而且 `copilot.character_agent` 開著時，呼叫 `task_from_owner`。
   - 有工作時：開始任務，角色用 `task_hint=("ack", 工作指示)` 接令。
   - 收到 `approval` 事件時：在語音頻道的聊天室發一則訊息，附「准許」「拒絕」按鈕，**只有主人按得到**；`explicit` 的只有單次准許。同時角色用 `("approval", 要做的事)` 說一句請主人決定。
   - `done`／`error` 時：角色用 `("report", 結果摘要)` 回報。
   - 其他人要它做事時，維持角色婉拒（不派工）。
3. **Discord 權限**：
   - bot 需要在語音頻道的聊天室「傳送訊息」；
   - 按鈕不需要 Message Content intent；
   - 請**使用者重新邀請一次** bot（給他連結，這是他唯一要做的事），並更新 README 的權限清單。
4. 設定頁：
   - `character_agent` 開關；
   - `character_ai_honesty` 的 `machine` 選項會自動出現（來自 `AI_HONESTY_MODES`），確認畫面正常。
5. **測試要能離線跑**：假的 EdgeAgent SSE 伺服器＋假的 Discord 互動。至少驗證：
   - 只有主人能派工、能按；
   - 拒絕後不會執行；
   - 任務失敗時角色會回報；
   - Agent 執行期間角色仍能聊天。
6. 實機驗證**不要請使用者陪聊**：
   - 用自己的測試頻道或使用者同意的方式，跑一個「讀檔＋回報」的小工作；
   - 只回報事件和數字（派工判斷延遲、ack 延遲、任務時間、批准往返時間）。

**不要做**：
- 中性電子音的效果：等使用者在試聽頁選好，開發機會加進 `VOICE_EFFECTS`。
- 機魂人設：使用者還在挑。
- 角色模型和 LoRA：開發機在訓練。

## 4. 規則（AGENTS.md 之外）

- 不讀寫使用者的 `.env`、`settings.json`、`personas.json`、`character_state.json`，也不讀 `silenttalk.log` 的對話原文。對話、prompt、轉錄、錄音、工作指示的內容都不寫進報告或測試資產。
- 修改都在既有的 owner 完成（AGENTS.md 規則 8）：權限只在 `permissions.py`＋bridge 執行，SilentTalk 不另做一套權限。
- 程式提交到 `copilot-story-mode`，不能在 `main` commit；報告只提交到 `laptop-report`（用獨立 worktree），正常 push，不覆寫遠端報告歷史。
- 關程式用自己的 PID；測試結束歸還租借、停掉自己啟動的服務並確認清理。

## 5. 回報（`handoff/reports/laptop.md`，`laptop-report` 分支）

每一步一個段落，只寫數字和事件：
- 測試結果（passed／failed／exit code）；
- 實測延遲和 VRAM；
- 失敗的原因；
- commit 雜湊；
- 使用者自己說的感想（如果有）。

做不到的照實寫，不要宣稱沒驗證過的東西。
