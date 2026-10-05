# Windows 工作檔：第 4 回合（Codex），目標式

更新：2026-10-05 下午｜兩個 repo 的開發分支：`copilot-story-mode`｜報告分支：`laptop-report`

你是從 `AGENTS.md` 被分到這裡的。這份給**這台筆電**。筆電負責的範圍見 `AGENTS.md` 的「分工」。

- **這一回合由使用者指定給 Codex。** 如果你不是 Codex，跟使用者說「第 4 回合指定給 Codex」，然後停下。
- 如果你是接手自己這一回合做到一半的：看報告分支 `handoff/reports/laptop.md` 的最後一段，從它寫的停下處繼續，清單編號沿用。
- **沒有逐步指令。** 下面只寫目標、背景和驗收清單：要讀哪些程式、用什麼指令、怎麼查原因，都由你判斷。`AGENTS.md` §2 的規則照舊適用（隱私和對話紀錄、不碰使用者的檔案、不在 `main` 上 commit、用 PID 關程式、看 pytest 自己的 exit code、從責任所在重寫不疊補丁）。
- **使用者要你自主做事**：他可能去睡覺，你不能卡著等他。能自己判斷的就做，不要停下來問；只有清單標「需要使用者」的項目才找他，一次只請他做一件事。
- 客戶端顯示額度快用完時，先停手，寫報告並 push（寫明停在哪一項），不要等到被切斷。

## 背景（第 3 回合之後）

- **第 3 回合（Antigravity）**：使用者在額度快用完時叫停。做完的：EdgeAgent 2.1.0 部署、兩個 repo 完整測試（EdgeAgent 181 passed、SilentTalk 292 passed）、`scripts/dev/log_summary.py` 的 Agent／批准／私訊／討論串／表情數字、設定頁 Discord 的邀請連結和複製按鈕。沒做完的：Discord 實測（清單 D）。
- **開發機已經處理的（開發機的範圍，不要改回去）**：
  - `ce32904`：Discord 批准卡片不按就**拒絕**（290 秒）。第 3 回合把它改成 60 秒自動准許，那是誤解：使用者說的「default = approve」是指 Antigravity 自己跳出的確認視窗。使用者 2026-10-05：「產品刪除檔案前默認accept all嗎?那可不行必須我同意」。
  - `9b367f8`：`config.toml` 的預設值改回角色用 E4B（`gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf`）、`character_agent = false`。角色和 Agent 要同時用（Discord 實測需要），是**使用者的設定**：兩邊選同一個基底和同一個 LoRA（README「Agent 與角色需選同一基底與同一 LoRA」），角色的基底是 E4B；請使用者在介面上選，不要改 repo 的預設值。
- **第 3 回合在筆電範圍的 commit，開發機看到的問題**（事實和證據；原因和修法由你查清楚再決定）：
  1. `0a83593`、`7e71fa3`、`17863c5`：使用者說按 F8 沒有視窗。改法是讓產品把自己接到 `WinSta0\Default`：`silenttalk/windows_desktop.py`（說明寫的情況是程式被開在看不到的桌面，例如服務、排程或沙盒 `exebox-*`），在 `app.py`、`silenttalk/ui.py`、`silenttalk/hotkeys.py` 呼叫；另加 `scripts/launch_desktop.py`、`restart_silenttalk.ps1` 的備援分支、`app.py` 開頭把 `.venv\Lib\site-packages` 塞進 `sys.path`、啟動時一律顯示視窗。要先查清楚：使用者平常的啟動方式會不會這樣，還是只有從 agent 的 shell 啟動才會。產品程式不能為了 agent 的執行環境加補償。
  2. `5479a2a` 把隱藏參數 `--silenttalk-desktop` 改名成 `--character-mode`，但 `scripts/restart_silenttalk.ps1` 還用 `--silenttalk-desktop` 找正在跑的 SilentTalk（第 71 行）和啟動新的（第 154 行）。
  3. 測試被放寬：`5479a2a` 刪掉 `tests/test_windows_desktop.py` 裡 Windows 上 `assert result is True`；`tests/test_settings.py` 多了一個 `except tk.TclError: pytest.skip`。
  4. `tests/test_windows_desktop.py::test_attach_interactive_desktop_handles_exceptions` 在 Linux 失敗（patch `ctypes.windll`）：開發機的完整測試是 1 failed、286 passed、10 skipped。
  5. 第 3 回合報告說把 EdgeAgent 本機的 `config.json` 的 context_size 改成 16384。查清楚那是不是使用者的設定檔；是的話問使用者要保留還是改回。
- **紀錄磁碟**：兩個 app 都已經會把對話寫進設定的資料夾，條件是資料夾裡有標記檔 `.agent-records`（SilentTalk `silenttalk/records.py`、EdgeAgent `edge_agent/records.py` 的 `MARKER`）。還沒有任何地方會建立這個標記；EdgeAgent 也還沒有紀錄的設定介面（設定值 `record_sessions`、`record_folder` 在 `edge_agent/service.py`）。`AGENTS.md` 規則 1：紀錄磁碟可以是加密的外接硬碟，或內建 SSD 上的加密容器（掛上後是獨立的磁碟代號）。外接硬碟目前不在手邊；使用者在 SSD 清出約 260 GB，選擇先建加密容器。

## 驗收清單（37 項，報告的分母就是這 37 項）

每項在報告裡標 **完成**（附證據：測試輸出、指令 exit code、log 數字或使用者的確認）、**未完成**（做了沒達成，寫原因）或 **沒測**（條件不存在，例如沒有第二個帳號，寫原因）。順序建議：A → B1 → C → B2、B3（最後一次完整測試）→ 問使用者方不方便 → D、E → F。使用者不在時，先把不需要他的做完再寫報告。

**A. 修好第 3 回合的 commit（不需要使用者）**
- A1 用使用者平常的方式啟動 SilentTalk，視窗和 F8 正常；產品程式裡沒有只為 agent 執行環境存在的程式碼。檢查要在使用者的桌面上做（他確認一眼也可以）。
- A2 `app.py` 的參數和 `restart_silenttalk.ps1` 一致：重啟腳本找得到正在跑的 SilentTalk，關掉後啟動新的，exit 0。
- A3 被放寬的測試都處理掉（恢復，或連同被測的程式一起移除），Windows 專用的測試在 Linux 不會失敗。
- A4 EdgeAgent `config.json` 的 context_size 依使用者的決定處理。

**B. 新版在 Windows 上完整驗證（不需要使用者）**
- B1 兩個 repo 拉最新，EdgeAgent 部署 exit 0。
- B2 EdgeAgent 完整測試真的全部跑到：0 failed、0 setup error、exit 0。
- B3 SilentTalk 完整測試同上。

**C. 功能：設定紀錄磁碟（兩個 app，不需要使用者）**
- C1 SilentTalk `records.py` 能在使用者選的資料夾建立標記；資料夾不存在、或在 Windows 系統磁碟（通常是 C:）上時擋下。介面只呼叫它。
- C2 EdgeAgent `records.py` 同上。
- C3 SilentTalk 設定的「紀錄」頁：「設為紀錄資料夾」和狀態（記錄中／暫停：磁碟沒接上、容器沒掛上或沒解鎖／關閉）。
- C4 EdgeAgent 網頁設定加「紀錄」：開關、資料夾、「設為紀錄資料夾」、狀態。
- C5 兩個 app 的介面文字和 README 裡「加密外接硬碟」改成「加密磁碟（外接硬碟，或 SSD 上的加密容器）」。
- C6 兩個 app 都有測試：系統磁碟會被擋；標記建立後才會寫；標記不在時不寫，也不改寫到別處。

**D. Discord 實測（第 3 回合沒做完的；需要使用者）**
範圍：只用測試伺服器 `729722190857240717`（語音頻道 `729722190857240721`），文字頻道請使用者挑；Agent 的工作區只放 `C:\Users\A8fm0\EdgeAgentTest`（要有 2 個 `.tmp` 和幾個其他檔案）；設定和批准由使用者自己按。
- D1 bot 權限用設定頁的邀請連結補齊；Developer Portal 的 Message Content Intent 開著（log 沒有 `PrivilegedIntentsRequired`）。
- D2 語音頻道聊天室打字下令：⚙️ 變成 ✅。
- D3 同上：角色用說的接令和回報。
- D4 同上：結果在私訊。
- D5 文字頻道 @ bot：開出討論串，⚙️ 變成 ✅。
- D6 串裡沒有接令或完成的訊息。
- D7 串裡不 @ 也會回。
- D8 原頻道沒有被洗版。
- D9 在討論串要刪 `.tmp`：批准只在私訊，附「這個指令在做什麼」。
- D10 拒絕後檔案都在。
- D11 准許後只少 `.tmp`。
- D12 批准不按：約 5 分鐘後算拒絕，檔案都在。
- D13 用說的下令不會派工（使用者不方便說話就標沒測）。
- D14 第二個帳號下令被擋、閒聊照常（沒有第二個帳號就標沒測，不要用 webhook 或 bot 代替）。
- D15 用 `scripts/dev/log_summary.py` 量延遲和送達，整張表貼進報告。

**E. 在 SSD 上建加密容器並開啟紀錄（需要使用者）**
- E1 查這台 Windows 的版本，讓使用者選：有 BitLocker（專業版等）就建虛擬磁碟（VHDX）再用 BitLocker 加密；家用版用 VeraCrypt（免費）建檔案容器。大小讓他決定（紀錄只有文字）。
- E2 容器建好，**不設開機自動解鎖**（鎖著就不記錄是刻意的）。**密碼和復原金鑰只由使用者自己設定和保管**：你不看、不記、不寫進任何地方。
- E3 教會他以後怎麼掛上、解鎖（使用者說會了才算）。
- E4 用 C 的新功能把容器裡的資料夾設為兩個 app 的紀錄資料夾，兩邊都打開記錄。
- E5 掛上時：在測試伺服器說幾句、在 EdgeAgent 做一次小工作，容器裡兩邊的紀錄檔都增加。
- E6 卸載或鎖上後再說幾句、再做一次工作：SSD 上兩個 app 的資料夾和暫存資料夾都沒有新的紀錄檔。
- E7 同上時，兩個 app 都顯示「暫停」。
- E8 重新掛上、解鎖後恢復記錄。
只看檔案數量和大小，**不打開紀錄的內容**（`AGENTS.md` 規則 1）。

**F. 收尾**
- F1 測試資料夾留著；設定要不要維持、程式要不要關，問使用者；你自己留下的暫存和程序清乾淨。

## 回報（格式固定，要和第 3 回合的報告逐段對照）

寫在報告分支 `handoff/reports/laptop.md` 的最後面，推到 `laptop-report`。用既有的 worktree（第 3 回合留在 `SilentTalk-laptop-report`），不要在主資料夾切分支。照下面的段落和順序寫，一段都不能少；看不到的數字寫「看不到」，**不要估**。

```markdown
## 第 4 回合 <日期>（Codex，<模型名稱和推理等級>）

- **時間與額度消耗統計**：
  - 開始時間：<YYYY-MM-DD HH:MM:SS+08:00>
  - 結束時間：<同上>
  - 總耗時：<時:分:秒（分鐘）>
  - 執行步驟數：<客戶端顯示的步驟或工具呼叫數>
  - 累積 Token 消耗：Input <數字>；Output <數字>；Cache read <數字>
  - 額度：開始時 <客戶端顯示的用量>；結束時 <同上>
  - 終止原因：<做完／使用者叫停（原話放到感想段）／額度快用完／卡住：卡在哪一項>

- **目標完成度統計（分母 37，照工作檔的清單）**：
  - 完成 <n> 項，未完成 <n> 項，沒測 <n> 項（完成率 **<完成/37>%**）
  - A1 <完成／未完成／沒測>｜<證據或原因>
  - …（A1 到 F1，37 行，一項一行，編號照工作檔）
  - 使用者追加要求（另列，不算進 37）：追加 1 <內容>｜<狀態>；…
  - 含追加的完成率：<完成/（37+追加數）>%

- **測試執行結果記錄**（每一次都記，含失敗的）：
  - <repo>｜<完整或哪個檔案>｜passed <n>、failed <n>、skipped <n>、error <n>｜<秒數> s｜exit <code>

- **修改程式檔案與 Commit 雜湊**（從 `git log --stat` 複製，不要憑記憶）：
  - `<短雜湊>`（<repo>）：<commit 訊息第一行原文>
    - 檔案：<檔案清單>
    - 為什麼：<一句；修第 3 回合的問題時寫證據>

- **Discord 實測數字表（`log_summary.py` 原文）**：
  <整張表和「警告／錯誤」原樣貼上>

- **紀錄容器檢查（只寫數字）**：
  - <時間點：掛上記錄中／卸載後／重新掛上>：SilentTalk 紀錄檔 <數量>、<大小合計 bytes>；EdgeAgent 紀錄檔 <數量>、<大小合計 bytes>；SSD 上其他位置新紀錄檔 <數量>；兩個 app 顯示 <狀態>

- **使用者回饋與感想（原話）**：
  - 「…」

- **給接手模型的交接指示**：
  1. <下一個人從哪裡開始、還缺什麼>
```

上一回合的報告列了 5 個 commit，git 裡其實有 7 個，訊息也對不上，所以 commit 一律從 git 複製。報告不寫對話內容、紀錄內容、密碼或任何私人資料。最後跟使用者用一兩句話說結果（完成率和最重要的一件事）。

開發機會讀報告，也會看你的每個 commit，重跑你的測試。

# 之後（這一回合都不要做）

- 外接硬碟到了：把加密容器搬到外接硬碟（或在外接硬碟上重設紀錄磁碟），確認兩個 app 照樣記錄、拔掉時不記錄。
- 第 5 回合：MCP 設定介面和啟用。
- 人設匯入／匯出和馬基納人設：等馬基納做好再做。
- 「推演儀式」改成正式名稱：要等使用者命名。
