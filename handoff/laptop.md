# Windows 工作檔：Discord 實測與人設匯入

更新：2026-10-04 早上｜開發分支：兩個 repo 都是 `copilot-story-mode`｜報告分支：`laptop-report`

你是從 `AGENTS.md` 被分到這裡的。共通規則以 `AGENTS.md` 為準。上一輪（Windows 整合）已完成並回報，舊版工作檔在開發機的 `archive/`，你不必讀。

## 1. 現況

**使用者要的**：Discord bot 和本機 Agent 兩用的角色，戰鎚 40K 的機魂「馬基納」（Machina-Prime-09A）：
- 懂 40K，能打破第四面牆開玩笑；
- 主人能在 Discord 上交代 Agent 工作，危險操作要主人按按鈕批准；
- 權限由使用者自己調。

開發機在做角色和寫程式的訓練資料，還沒有訓練好的 LoRA。這一輪用現有模型驗證流程。

**上一輪你已經做好**（`laptop-report` 的「Windows integration 2026-10-04」）：rg/fd 部署、上網工具實測、權限 UI、同模型共用 slot、Discord 派工與批准按鈕（離線 13 項）。**還沒做的是 Discord 實測**，因為上次沒有測試頻道。

**使用者已經準備好測試伺服器**：
- guild ID `729722190857240717`，使用者說「這個是測試用的，安全」；
- bot 的「檢視頻道／傳送訊息」權限已經調好。

| 項目 | 位置 |
|---|---|
| SilentTalk | `C:\Users\A8fm0\Downloads\SilentTalk` |
| EdgeAgent | `C:\Users\A8fm0\EdgeAgent`（控制 `127.0.0.1:18087`、推論 `127.0.0.1:18089`） |
| 報告 | `handoff/reports/laptop.md`，只提交到 `laptop-report` |

**開發機這段期間在 `copilot-story-mode` 新增、你會碰到的東西**：
- `VOICE_EFFECTS["machine_spirit"]`（「機魂電子音」）：使用者試聽後選的中性電子音，配 `zh-TW-YunJheNeural`、音高 +22。
- `character_ai_honesty = "machine"`。
- `scripts/dev/turn_eval.py --persona-file`：開發機的評估工具，你不用跑。

## 2. 這一輪要做的事（依序；每一步做完照 §4 回報）

**A. 在測試伺服器做 Discord 實測**（只在 guild `729722190857240717`）

1. 你先準備好，不需要使用者：
   - 兩個 repo `git pull` 並跑完整測試；
   - 確認 bot 在這個 guild 裡；
   - 建一個測試工作資料夾（例如 `C:\Users\A8fm0\EdgeAgentTest`），放幾個假檔案，包含 2 個 `.tmp`；
   - 照產品流程啟動 SilentTalk。App 會自己讀憑證，你**不讀** `.env` 或憑證。
2. 一次一步引導使用者，每則訊息只給一個動作：
   1. 在 EdgeAgent 的「權限」面板打開 Discord，工作區只設上面那個測試資料夾；
   2. 在 SilentTalk 設定打開「交代 Agent 工作」（`character_agent`），角色模式開啟，人設先用任何一個；
   3. 進測試伺服器的語音頻道，對角色說一句「（角色名），幫我看一下測試資料夾裡有哪些檔案」；
   4. 再說「把裡面的 .tmp 檔刪掉」。批准按鈕出現後，**先按一次「拒絕」**，確認檔案還在；再說一次，**按「准許一次」**，確認只有 `.tmp` 被刪。
3. 你要量，只記數字和事件：
   - 派工判斷延遲、接令那句的延遲、Agent 任務時間；
   - 批准按鈕出現的時間、從按下到執行的時間；
   - 回報那句的延遲；
   - 非主人按按鈕會不會被擋。如果有第二個帳號可以順便測，沒有就照實寫「沒測」。
4. 不要把語音轉錄、工作指示、模型輸出的內容寫進報告。

**B. 人設匯入／匯出**（SilentTalk 人設編輯器，`persona_ui.py`、`PersonaStore` 是既有的 owner）
- **匯入**：使用者貼上一段人設 JSON。格式就是 `Persona` 的欄位，含 `voice`、`voice_pitch`、`voice_effect`。驗證方式和編輯器存檔相同（`validate_persona`）。通過後由 app 加進人設清單，名字重複就提示。
- **匯出**：把選定的人設複製成同樣格式的 JSON。
- 離線測試：
  - 有效 JSON 能匯入；
  - 欄位超過字數會照 `validate_persona` 的訊息擋下；
  - 未知欄位會被忽略（和 `persona_from_dict` 一致）；
  - `voice_effect: "machine_spirit"` 能匯入，試聽用同一個效果。
- **不要自己建機魂人設**：使用者還在調它的個性，開發機會給使用者一段 JSON 讓他自己貼。

**不要做**：角色模型和 LoRA（開發機在訓練）；請使用者念句子或判斷模型輸出好不好。

## 3. 規則（AGENTS.md 之外）

- 不讀寫使用者的 `.env`、`settings.json`、`personas.json`、`character_state.json`，也不讀 `silenttalk.log` 的對話原文。設定一律由使用者在 UI 上改。
- 實測只用測試 guild `729722190857240717` 和測試工作資料夾；Agent 的批准一律由使用者自己按。
- 修改都在既有的 owner 完成（AGENTS.md 規則 8）。程式提交到 `copilot-story-mode`，報告只提交到 `laptop-report`（用獨立 worktree），正常 push。
- 關程式用自己的 PID；結束後歸還租借、停掉自己啟動的服務、刪掉自己建的測試資料夾以外的暫存，並確認清理。測試資料夾留著，讓使用者自己決定要不要刪。

## 4. 回報（`handoff/reports/laptop.md`，`laptop-report` 分支）

每一步一個段落，只寫數字和事件：
- 延遲（ms）；
- 成功／失敗；
- 被擋的次數；
- 測試結果（passed／failed／exit code）；
- commit 雜湊；
- 使用者自己說的感想（如果有）。

做不到的照實寫。
