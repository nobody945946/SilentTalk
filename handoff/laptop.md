# Windows 工作檔：第 1 回合，跟上與預備（不需要使用者）

更新：2026-10-04 晚上｜開發分支：兩個 repo 都是 `copilot-story-mode`｜報告分支：`laptop-report`

你是從 `AGENTS.md` 被分到這裡的。共通規則以 `AGENTS.md` 為準。舊版工作檔在開發機的 `archive/`，你不必讀。

## 0. 這一輪的大小

使用者要工作切成小回合：開發機每到一個里程碑，你就做一回合份量小、做得完的事，不要一次耗光 5 小時額度。

這一回合**只做不需要使用者的預備工作**。Discord 實測和人設匯入是之後的回合，這次不要做。

如果額度快用完了，就停在做完的那一步，照 §4 回報做到哪裡。

## 1. 現況（開發機做好、你要跟上的）

| 東西 | 位置 |
|---|---|
| SilentTalk | `C:\Users\A8fm0\Downloads\SilentTalk` |
| EdgeAgent | `C:\Users\A8fm0\EdgeAgent`（控制 `127.0.0.1:18087`、推論 `127.0.0.1:18089`） |
| 報告 | `handoff/reports/laptop.md`，只提交到 `laptop-report` |

開發機上一個里程碑完成的內容：

- **SilentTalk 的 Discord 防話術**：
  - 只有主人**打字**的話能派工，用說的只算聊天；
  - 批准按鈕和結果只私訊主人；
  - 機魂看得出哪句是打字的。
- **EdgeAgent 的「求知儀式」模式**：
  - 模式只剩「工作／求知儀式」，「規劃」拿掉了；
  - 使用的是繁體中文、逐類想過的 grill-me skill。
- **EdgeAgent 的 MCP 支援**（`edge_agent/mcp.py`、`agent_bridge.mjs`）：
  - 只接本機 stdio 伺服器，設定由 EdgeAgent 管；
  - 工具隨用隨載（`tool_search`）；
  - 每次呼叫都過權限：唯讀的可自動執行，其他的都問；不可逆的、實體裝置的每一步都問；
  - 每個伺服器可以只開放部分工具（`tools`），也可以設「一輪問一次」（`confirm: "turn"`）；
  - `scripts/mcp_probe.mjs` 可以在啟用前列出伺服器的工具和標記。

## 2. 這一回合要做的事（依序；每一步做完照 §4 回報）

**A. 跟上**
1. 兩個 repo `git pull`，照既有部署流程部署 EdgeAgent，兩邊跑完整測試。
   - Windows 上的真 Pi SDK 測試要包含 `tests/test_mcp.py` 和 `tests/test_agent_chat.py -k interview`。
2. 用既有的真 Edge 瀏覽器檢查：
   - 模式選單只有「工作」「求知儀式」；
   - 送出時 `/chat` 帶 `interview: true`；
   - 8 種視窗大小版面正常；
   - 既有瀏覽器檢查裡用到「規劃」的地方，照新選單改。

**B. 準備 MCP 的執行環境**
- 確認 Node 有 `npm`／`npx`。沒有就照 EdgeAgent 既有的部署 owner 補上（使用者說「請她載 npm」）。
- 裝 `uv`（官方安裝程式）。台股伺服器要 Python 3.13，由 uv 管理，不動系統的 Python。
- 這些都裝在 EdgeAgent 的部署範圍或使用者層級；不要改系統設定，也不要用系統管理員權限。

**C. 安裝並探測三個 MCP 伺服器**（固定版本；**這回合不要在 EdgeAgent 裡啟用**，設定介面是之後的回合）

1. **無人機（只用假無人機）**：`uv tool install mavlink-mcp==0.1.5`
   - 用 `node scripts/mcp_probe.mjs -- mavlink-mcp --backend fake` 探測一次，再加上 `--enable-actuation` 探測一次；
   - 再用 `--call get_status {}` 對假無人機呼叫一次。
   - 開發機已經驗過：沒開動作模式時有 5 個唯讀工具，開了以後多 14 個飛行工具，全部標成不可逆。你要確認 Windows 上一樣。
   - **絕對不要加 `--allow-real-vehicle`，也不要接任何實體飛控。**
2. **瀏覽器測試**：`@playwright/mcp@0.0.83`
   - 參數 `--browser msedge --headless --isolated`（用 Windows 內建的 Edge，不要另外下載 Chromium）；
   - 探測一次，再呼叫 `browser_navigate` 開 `about:blank`，接著呼叫 `browser_snapshot`。
   - 開發機看到的是 25 個工具，幾乎都標成不可逆。
3. **台股**：TWStockMCPServer v1.9.0（`https://github.com/twjackysu/TWStockMCPServer`，commit `8857b2e`）
   - `git clone` 到 EdgeAgent 的 `.runtime` 底下，`uv sync`；
   - 用 `MCP_STDIO=1` 跑 stdio。**不要用它預設的 HTTP 模式**，那會開在 `0.0.0.0` 讓區網都連得到；
   - 探測一次，再呼叫一次 `get_exchange_rates`。
   - 它約有 173 個工具，太多了。從探測結果挑**10 個左右**，涵蓋：個股日成交、三大法人、月營收、股利、財報（公開資訊觀測站）、大盤指數、央行匯率。工具名稱寫進報告（只寫名稱）。

**每個伺服器都要記錄**：
- 版本；
- 安裝耗時和佔用空間；
- 閒置時佔用的記憶體；
- 工具數；
- 唯讀、不可逆、會連外三種標記各有幾個；
- **有沒有標記看起來不對的工具**，例如會改東西卻標成唯讀。權限把關就是靠這些標記。

**D. 求知儀式實測**（不需要使用者）

在測試資料夾用真模型跑「求知儀式」：送一個假點子，例如「做一個記帳小工具」。只記數字：
- 第一輪題數、`➡️` 建議答案數；
- 有沒有呼叫寫檔或指令工具（應該 0）；
- 延遲。

E4B 和目前預設的 Qwen3.5-4B 各跑一次，量完換回原本的模型設定。不要記模型輸出的內容，也不要替使用者改預設模型。

## 3. 規則（AGENTS.md 之外）

- 不讀寫使用者的 `.env`、`settings.json`、`personas.json`、`character_state.json`，也不讀 `silenttalk.log` 的對話原文。
- MCP 伺服器只在探測時啟動，探測完就關（用自己的 PID）。不要讓它們常駐，不要開放到區網。
- 修改都在既有的 owner 完成（AGENTS.md 規則 8）。程式提交到 `copilot-story-mode`；報告只提交到 `laptop-report`，用獨立 worktree，正常 push。
- 結束後停掉自己啟動的服務、刪掉自己的暫存，並確認清理。裝好的工具（uv、MCP 伺服器）留著，下一回合要用。

## 4. 回報（`handoff/reports/laptop.md`，`laptop-report` 分支）

每一步一個段落，只寫：
- 數字和事件；
- 測試結果（passed／failed／exit code）；
- 版本和 commit 雜湊；
- 做不到的原因；
- 額度用到哪裡停（如果有停）。
